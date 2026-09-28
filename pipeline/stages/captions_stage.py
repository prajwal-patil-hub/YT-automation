"""Stage 04 — karaoke .ass for burn-in, plus a clean .srt to upload."""
from __future__ import annotations

from ..render import subtitles


def run(ctx) -> None:
    timeline, cursor = [], 0.0
    for beat in ctx.script.beats:
        duration = beat.duration or 0.0
        timeline.append((beat.narration, cursor, duration))
        cursor += duration

    style = ctx.cfg.section("captions")
    subtitles.write_ass(
        ctx.ass_path, timeline,
        width=int(ctx.cfg.get("video.width", 1920)),
        height=int(ctx.cfg.get("video.height", 1080)),
        style=style,
    )
    subtitles.write_srt(ctx.srt_path, timeline)
    ctx.log(f"captions written for {cursor:.1f}s ({ctx.ass_path.name}, {ctx.srt_path.name})")
