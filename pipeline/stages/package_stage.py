"""Stage 06 — metadata, chapters, thumbnail and the disclosure flag.

Nothing here talks to YouTube. It produces the upload payload and stops, so the
review gate always sits between packaging and publishing.
"""
from __future__ import annotations

import json

from ..render import cards
from ..render.theme import Theme


def _chapters(script) -> list[tuple[str, float]]:
    """Chapters are free: beat boundaries already exist from the TTS durations."""
    out, cursor = [], 0.0
    for beat in script.beats:
        spec = beat.visual.spec
        label = spec.get("heading") or spec.get("title") or spec.get("kicker")
        if label and (not out or out[-1][0] != label):
            out.append((str(label), cursor))
        cursor += beat.duration or 0.0
    return out


def _timestamp(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def run(ctx) -> None:
    script = ctx.script
    theme = Theme.from_config(ctx.cfg.section("theme"))
    size = (int(ctx.cfg.get("video.width", 1920)), int(ctx.cfg.get("video.height", 1080)))

    # --- thumbnails: three variants, because choosing is a real human call ----
    thumb_dir = ctx.job_dir / "thumbnails"
    thumb_dir.mkdir(parents=True, exist_ok=True)
    thumbs = []
    for i, kicker in enumerate(["", (ctx.cfg.get("channel.name") or "").upper(), "EXPLAINED"]):
        path = thumb_dir / f"thumb-{chr(ord('a') + i)}.png"
        cards.title_card(
            path, size, theme,
            title=script.title,
            kicker=kicker or None,
            subtitle=None if i else (script.description[:90] or None),
        )
        thumbs.append(str(path))

    # --- chapters + description ----------------------------------------------
    chapters = _chapters(script)
    lines = [script.description.strip(), ""]
    if chapters:
        # YouTube requires the first chapter to start at 0:00.
        lines.append("Chapters")
        lines.append(f"0:00 {chapters[0][0] if chapters else 'Intro'}")
        for label, at in chapters[1:]:
            lines.append(f"{_timestamp(at)} {label}")
        lines.append("")
    if script.sources:
        lines.append("Sources")
        lines.extend(f"- {s}" for s in script.sources)

    disclosure = ctx.store.requires_disclosure(ctx.job_id)
    reused = [dict(r) for r in ctx.store.reused_assets(ctx.job_id)]

    payload = {
        "job_id": ctx.job_id,
        "title": script.title,
        "title_variants": [
            script.title,
            f"{script.title} (In {max(1, round(script.total_duration / 60))} Minutes)",
            f"{script.title} — Explained Properly",
        ],
        "description": "\n".join(lines).strip(),
        "tags": ctx.cfg.get("channel.tags", []),
        "category_id": str(ctx.cfg.get("channel.category_id", "27")),
        "privacy_status": ctx.cfg.get("publish.privacy_status", "private"),
        "self_declared_made_for_kids": bool(ctx.cfg.get("channel.made_for_kids", False)),
        # Derived from the asset manifest, not from memory.
        "altered_or_synthetic_content": disclosure,
        "chapters": [{"label": l, "start": a} for l, a in chapters],
        "sources": script.sources,
        "thumbnails": thumbs,
        "master": str(ctx.master_path),
        "proxy": str(ctx.proxy_path) if ctx.proxy_path.exists() else None,
        "captions_srt": str(ctx.srt_path),
        "duration_seconds": round(script.total_duration, 2),
        "warnings": (
            [f"beat {r['beat_index']}: asset reused from job(s) {r['seen_in']}" for r in reused]
        ),
    }
    ctx.metadata_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    ctx.log(
        f"packaged: {len(thumbs)} thumbnails, {len(chapters)} chapters, "
        f"disclosure={'YES' if disclosure else 'no'}"
    )
    if disclosure:
        ctx.log(
            "this video contains photorealistic generated assets — the "
            "altered-or-synthetic flag is set",
            "warn",
        )
