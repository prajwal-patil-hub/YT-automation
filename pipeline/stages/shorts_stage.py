"""Stage 10 — derive vertical clips from the finished long-form video.

Long-form carries the revenue and Shorts carry the discovery, so the clip is a
by-product of the main render rather than a separate production.

The clips are **re-rendered from the original sources**, not cropped out of the
master. Cropping 16:9 to 9:16 throws away about 60% of the frame and cuts text
in half; because the pipeline still holds every beat's audio and visual intent,
it can compose a proper vertical frame instead. That is the practical payoff of
keeping sources around rather than only the finished file.

Captions are burned in here even when the long-form has them off: Shorts are
watched muted first.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .. import standards
from ..channels import deep_merge
from ..config import Config
from ..models import VisualIntent
from ..providers import ProviderUnavailable, get_visual
from ..providers.visuals import kind_map, resolve_kind
from ..render import subtitles
from ..util import ffmpeg, loudness


@dataclass
class Clip:
    index: int
    beats: list[int]
    title: str
    duration: float


def vertical_config(cfg: Config) -> Config:
    """A view of the channel config at Shorts dimensions.

    Providers read their frame size from config, so swapping the dimensions is
    all it takes to make every visual provider compose vertically.
    """
    override = {
        "video": {
            "width": standards.SHORTS_WIDTH,
            "height": standards.SHORTS_HEIGHT,
        },
        "captions": {
            "burn_in": True,
            "margin_v": int(standards.SHORTS_HEIGHT
                            * standards.SHORTS_CAPTION_BOTTOM_MARGIN),
        },
    }
    return Config(raw=deep_merge(cfg.raw, override), root=cfg.root)


def plan_clips(ctx) -> list[Clip]:
    """Explicit clips from the script, else contiguous runs inside the budget."""
    script_obj = json.loads(ctx.script_path.read_text(encoding="utf-8"))
    declared = script_obj.get("shorts") or []
    beats = ctx.script.beats
    durations = {b.index: (b.duration or 0.0) for b in beats}

    clips: list[Clip] = []
    if declared:
        for i, spec in enumerate(declared):
            lo = int(spec.get("from_beat", 0))
            hi = int(spec.get("to_beat", lo))
            chosen = [b.index for b in beats if lo <= b.index <= hi]
            if not chosen:
                continue
            clips.append(Clip(i, chosen, spec.get("title") or ctx.script.title,
                              sum(durations[i] for i in chosen)))
        return clips

    # Auto: walk the beats, closing a clip once it passes the target, and never
    # letting one exceed the hard ceiling.
    target = float(ctx.cfg.get("shorts.target_seconds", standards.SHORTS_TARGET_SECONDS))
    limit = float(ctx.cfg.get("shorts.max_seconds", standards.SHORTS_MAX_SECONDS))
    wanted = int(ctx.cfg.get("shorts.count", 1))

    current: list[int] = []
    total = 0.0
    for beat in beats:
        d = durations[beat.index]
        if current and (total + d > limit or total >= target):
            clips.append(Clip(len(clips), current, ctx.script.title, total))
            current, total = [], 0.0
            if len(clips) >= wanted:
                break
        current.append(beat.index)
        total += d
    if current and len(clips) < wanted:
        clips.append(Clip(len(clips), current, ctx.script.title, total))
    return clips[:wanted]


def _render_vertical_visuals(ctx, vcfg: Config, clip: Clip, out_dir: Path) -> dict[int, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    mapping = kind_map()
    default_kind = vcfg.get("visuals.default_kind", "card")
    cache: dict[str, Any] = {}
    paths: dict[int, Path] = {}

    def provider_for(name: str):
        if name not in cache:
            cache[name] = get_visual(name, vcfg)
        return cache[name]

    for beat in ctx.script.beats:
        if beat.index not in clip.beats:
            continue
        kind = resolve_kind(beat.visual, default_kind)
        name = mapping.get(kind, mapping.get(default_kind, "colour"))
        out = out_dir / f"beat-{beat.index:03d}.png"
        beat_ctx = {"beat_index": beat.index, "narration": beat.narration,
                    "fallback_title": clip.title, "used_paths": set()}
        try:
            rendered = provider_for(name).render(beat.visual, out, beat_ctx)
            paths[beat.index] = Path(rendered.path)
        except (ProviderUnavailable, ValueError, OSError) as exc:
            ctx.log(f"short beat {beat.index}: {name} failed ({exc}); colour fallback", "warn")
            rendered = provider_for("colour").render(
                VisualIntent("colour", {}), out, beat_ctx)
            paths[beat.index] = Path(rendered.path)
    return paths


def _segment(ctx, vcfg, beat, src: Path, out: Path) -> Path:
    w, h = standards.SHORTS_WIDTH, standards.SHORTS_HEIGHT
    fps = int(vcfg.get("video.fps", 30))
    duration = max(beat.duration or 0.0, 0.1)
    motion = vcfg.get("video.motion", "none")
    rate = float(vcfg.get("video.motion_rate", 0.16))

    fit = (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
           f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black")
    if motion in ("drift", "parallax"):
        over = standards.MOTION_OVERSCAN
        over_w, over_h = int(w * over), int(h * over)
        vf = (f"scale={over_w}:{over_h},crop={w}:{h}"
              f":x='(in_w-out_w)*(0.5+0.5*sin(t*{rate:.4f}))'"
              f":y='(in_h-out_h)*(0.5+0.35*sin(t*{rate * 0.61:.4f}))',"
              f"fps={fps},format=yuv420p")
    else:
        vf = f"{fit},fps={fps},format=yuv420p"

    ffmpeg.run(
        ["-y", "-loop", "1", "-i", str(src), "-t", f"{duration:.3f}",
         "-vf", vf, "-an", "-c:v", "libx264",
         "-preset", vcfg.get("video.preset", "veryfast"),
         "-crf", str(vcfg.get("video.crf", 20)), "-pix_fmt", "yuv420p",
         "-r", str(fps), "-video_track_timescale", "90000", str(out)],
        override=ctx.ffmpeg,
    )
    return out


def _escape(path: Path) -> str:
    return str(path).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


def run(ctx) -> None:
    if not ctx.cfg.get("shorts.enabled", True):
        ctx.log("shorts disabled for this channel")
        return

    vcfg = vertical_config(ctx.cfg)
    clips = plan_clips(ctx)
    if not clips:
        ctx.log("no clips to cut", "warn")
        return

    root = ctx.job_dir / "shorts"
    root.mkdir(parents=True, exist_ok=True)
    manifest = []

    for clip in clips:
        if clip.duration > standards.SHORTS_MAX_SECONDS:
            ctx.log(
                f"clip {clip.index} is {clip.duration:.0f}s, over the "
                f"{standards.SHORTS_MAX_SECONDS:.0f}s Shorts ceiling — skipped",
                "warn",
            )
            continue

        work = root / f"clip-{clip.index:02d}"
        work.mkdir(parents=True, exist_ok=True)
        visuals = _render_vertical_visuals(ctx, vcfg, clip, work / "visuals")

        # segments
        segments = []
        for beat in ctx.script.beats:
            if beat.index not in clip.beats:
                continue
            seg = work / f"seg-{beat.index:03d}.mp4"
            if not seg.exists() or ctx.force:
                _segment(ctx, vcfg, beat, visuals[beat.index], seg)
            segments.append(seg)

        listing = work / "segments.txt"
        listing.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p in segments),
                           encoding="utf-8")
        silent = work / "video-silent.mp4"
        ffmpeg.run(["-y", "-f", "concat", "-safe", "0", "-i", str(listing),
                    "-c", "copy", str(silent)], override=ctx.ffmpeg)

        # audio for just these beats
        parts = [Path(b.audio_path) for b in ctx.script.beats
                 if b.index in clip.beats and b.audio_path]
        narration = ffmpeg.concat_audio(parts, work / "narration.wav", override=ctx.ffmpeg)

        # captions, positioned above the Shorts furniture
        timeline, cursor = [], 0.0
        for beat in ctx.script.beats:
            if beat.index not in clip.beats:
                continue
            d = beat.duration or 0.0
            timeline.append((beat.narration, cursor, d))
            cursor += d
        ass = work / "captions.ass"
        subtitles.write_ass(ass, timeline,
                            width=standards.SHORTS_WIDTH,
                            height=standards.SHORTS_HEIGHT,
                            style=vcfg.section("captions"))

        out = root / f"short-{clip.index:02d}.mp4"
        ffmpeg.run(
            ["-y", "-i", str(silent), "-i", str(narration),
             "-filter_complex",
             f"[0:v]subtitles='{_escape(ass)}'[v];[1:a]anull[a]",
             "-map", "[v]", "-map", "[a]",
             "-c:v", "libx264", "-preset", vcfg.get("video.preset", "veryfast"),
             "-crf", str(vcfg.get("video.crf", 20)), "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
             "-movflags", "+faststart", "-shortest", str(out)],
            override=ctx.ffmpeg,
        )

        # Same delivery target as the long form.
        if ctx.cfg.get("audio.normalise", True):
            try:
                staged = work / "normalised.mp4"
                m = loudness._measure_for_loudnorm(out, override=ctx.ffmpeg)
                af = (f"loudnorm=I={standards.TARGET_LUFS}"
                      f":TP={standards.TARGET_TRUE_PEAK_DB}"
                      f":LRA={standards.TARGET_LRA}"
                      f":measured_I={m['input_i']}:measured_TP={m['input_tp']}"
                      f":measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}"
                      f":offset={m['target_offset']}:linear=true")
                ffmpeg.run(["-y", "-i", str(out), "-af", af, "-c:v", "copy",
                            "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                            "-movflags", "+faststart", str(staged)],
                           override=ctx.ffmpeg)
                staged.replace(out)
            except (RuntimeError, KeyError, OSError) as exc:
                ctx.log(f"clip {clip.index} loudness skipped: {exc}", "warn")

        measured = ffmpeg.probe_duration(out, override=ctx.ffprobe)
        manifest.append({
            "index": clip.index, "path": str(out), "title": clip.title,
            "beats": clip.beats, "duration_seconds": round(measured, 2),
            "resolution": f"{standards.SHORTS_WIDTH}x{standards.SHORTS_HEIGHT}",
        })
        ctx.log(f"short {clip.index}: {measured:.1f}s · beats {clip.beats[0]}–{clip.beats[-1]} "
                f"· {out.stat().st_size / 1e6:.1f} MB")

    (root / "shorts.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    ctx.store.merge_meta(ctx.job_id, shorts=len(manifest))
