"""Stage 05 — assemble the timeline into a finished file.

Three passes, deliberately, rather than one enormous filtergraph:
  1. one short segment per beat, all encoded to identical parameters
  2. a stream-copy concat of those segments (fast, lossless)
  3. one final pass that mixes audio, ducks music and burns the captions

Splitting it this way means a failure names the beat that caused it, and a
re-run skips segments that already rendered.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from ..util import ffmpeg

VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}


def _escape_filter_path(path: Path) -> str:
    """FFmpeg filter arguments need ':' and '\\' escaped inside the value."""
    text = str(path)
    return text.replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


def _segment(ctx, beat, out: Path) -> Path:
    """Render one beat to a fixed-parameter video segment (no audio)."""
    w, h = int(ctx.cfg.get("video.width", 1920)), int(ctx.cfg.get("video.height", 1080))
    fps = int(ctx.cfg.get("video.fps", 30))
    duration = max(beat.duration or 0.0, 0.1)
    src = Path(beat.visual_path)
    is_video = ctx.media_kinds.get(beat.index) == "video" or src.suffix.lower() in VIDEO_EXT

    # Scale to fit, pad to exact frame — never distort the source aspect.
    vf = (
        f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"fps={fps},format=yuv420p"
    )
    if is_video:
        args = ["-y", "-stream_loop", "-1", "-i", str(src), "-t", f"{duration:.3f}"]
    else:
        args = ["-y", "-loop", "1", "-i", str(src), "-t", f"{duration:.3f}"]

    args += [
        "-vf", vf, "-an",
        "-c:v", "libx264", "-preset", ctx.cfg.get("video.preset", "veryfast"),
        "-crf", str(ctx.cfg.get("video.crf", 20)),
        "-pix_fmt", "yuv420p", "-r", str(fps),
        "-video_track_timescale", "90000",
        str(out),
    ]
    ffmpeg.run(args, override=ctx.ffmpeg)
    return out


def run(ctx) -> None:
    seg_dir = ctx.job_dir / "segments"
    seg_dir.mkdir(parents=True, exist_ok=True)

    # --- 1. per-beat segments -------------------------------------------------
    segments = []
    for beat in ctx.script.beats:
        if not beat.visual_path:
            raise RuntimeError(f"Beat {beat.index} has no visual; run the visuals stage first")
        seg = seg_dir / f"seg-{beat.index:03d}.mp4"
        if not seg.exists() or ctx.force:
            _segment(ctx, beat, seg)
        segments.append(seg)
    ctx.log(f"rendered {len(segments)} segments")

    # --- 2. concat video ------------------------------------------------------
    listing = ctx.job_dir / "segments.txt"
    listing.write_text(
        "".join(f"file '{p.resolve().as_posix()}'\n" for p in segments), encoding="utf-8"
    )
    silent_video = ctx.job_dir / "video-silent.mp4"
    ffmpeg.run(
        ["-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(silent_video)],
        override=ctx.ffmpeg,
    )

    # --- 3. narration track ---------------------------------------------------
    audio_parts = []
    gap = float(ctx.cfg.get("voice.beat_gap", 0.35))
    pad_dir = ctx.job_dir / "audio"
    for beat in ctx.script.beats:
        audio_parts.append(Path(beat.audio_path))
        if gap > 0:
            pad = pad_dir / f"gap-{beat.index:03d}.wav"
            if not pad.exists():
                ffmpeg.silence(gap, pad, override=ctx.ffmpeg)
            audio_parts.append(pad)
    narration = ffmpeg.concat_audio(audio_parts, ctx.job_dir / "narration.wav",
                                    override=ctx.ffmpeg)

    # --- 4. final mux: music duck + caption burn-in ---------------------------
    music_path = ctx.cfg.get("audio.music_file")
    music = Path(music_path) if music_path else None
    if music and not music.is_absolute():
        music = (ctx.cfg.root / music).resolve()

    inputs = ["-i", str(silent_video), "-i", str(narration)]
    if music and music.exists():
        inputs += ["-stream_loop", "-1", "-i", str(music)]

    sub_filter = f"subtitles='{_escape_filter_path(ctx.ass_path)}'"
    if ctx.cfg.get("captions.burn_in", True) and ctx.ass_path.exists():
        video_chain = f"[0:v]{sub_filter}[v]"
    else:
        video_chain = "[0:v]null[v]"

    if music and music.exists():
        duck_db = float(ctx.cfg.get("audio.music_gain_db", -22))
        # Sidechain the music against the narration so speech always wins.
        filter_complex = (
            f"{video_chain};"
            f"[2:a]volume={duck_db}dB[bed];"
            f"[bed][1:a]sidechaincompress=threshold=0.05:ratio=8:attack=20:release=400[ducked];"
            f"[1:a][ducked]amix=inputs=2:duration=first:dropout_transition=0[a]"
        )
        ctx.log(f"music bed: {music.name} at {duck_db} dB, ducked under narration")
    else:
        filter_complex = f"{video_chain};[1:a]anull[a]"
        if music_path:
            ctx.log(f"music file not found at {music}; continuing without a bed", "warn")

    ffmpeg.run(
        [
            "-y", *inputs,
            "-filter_complex", filter_complex,
            "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", ctx.cfg.get("video.preset", "veryfast"),
            "-crf", str(ctx.cfg.get("video.crf", 20)), "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-movflags", "+faststart",
            "-shortest",
            str(ctx.master_path),
        ],
        override=ctx.ffmpeg,
    )
    duration = ffmpeg.probe_duration(ctx.master_path, override=ctx.ffprobe)
    size_mb = ctx.master_path.stat().st_size / 1e6
    ctx.log(f"master: {ctx.master_path.name} · {duration:.1f}s · {size_mb:.1f} MB")

    # --- 5. review proxy ------------------------------------------------------
    # Telegram bots cap uploads at 50 MB, and a small file loads far faster on a
    # phone. Build the proxy every time, whatever the master's size.
    if ctx.cfg.get("review.make_proxy", True):
        height = int(ctx.cfg.get("review.proxy_height", 720))
        ffmpeg.run(
            ["-y", "-i", str(ctx.master_path),
             "-vf", f"scale=-2:{height}",
             "-c:v", "libx264", "-preset", "veryfast",
             "-crf", str(ctx.cfg.get("review.proxy_crf", 30)),
             "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart",
             str(ctx.proxy_path)],
            override=ctx.ffmpeg,
        )
        proxy_mb = ctx.proxy_path.stat().st_size / 1e6
        flag = "" if proxy_mb < 50 else "  (still over Telegram's 50 MB bot cap)"
        ctx.log(f"proxy: {ctx.proxy_path.name} · {proxy_mb:.1f} MB{flag}")
