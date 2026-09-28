"""Stage 02 — render narration, one audio file per beat.

Per-beat rendering is what gives the assembler exact durations and makes a bad
line a two-second fix rather than a full re-render.
"""
from __future__ import annotations

from ..providers import get_tts
from ..util import ffmpeg


def run(ctx) -> None:
    provider_name = ctx.cfg.get("voice.provider", "kokoro")
    tts = get_tts(provider_name, ctx.cfg)
    ctx.log(f"voice provider: {provider_name}")

    audio_dir = ctx.job_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    ctx.store.clear_stage_assets(ctx.job_id, "voice")
    gap = float(ctx.cfg.get("voice.beat_gap", 0.35))

    for beat in ctx.script.beats:
        out = audio_dir / f"beat-{beat.index:03d}.wav"
        if out.exists() and not ctx.force:
            beat.audio_path = str(out)
            beat.duration = ffmpeg.probe_duration(out, override=ctx.ffprobe) + gap
            continue
        tts.synth(beat.narration, out)
        beat.audio_path = str(out)
        # Duration is measured, never estimated — the timeline depends on it.
        beat.duration = ffmpeg.probe_duration(out, override=ctx.ffprobe) + gap
        ctx.store.add_asset(
            ctx.job_id, "audio", out, provider_name,
            stage="voice", beat_index=beat.index, license="generated-speech",
        )

    ctx.script.save(ctx.script_path)
    ctx.log(f"narration {ctx.script.total_duration:.1f}s across {len(ctx.script.beats)} beats")
