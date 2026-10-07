"""Stage 09 — publish, only after an explicit human approval.

The approval is read from the database rather than trusted from a callback
payload, so nothing publishes because a button press was replayed or forged.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..util.youtube import YouTubeClient, build_video_body


def build_client() -> YouTubeClient:
    return YouTubeClient(
        os.environ.get("YOUTUBE_CLIENT_ID", ""),
        os.environ.get("YOUTUBE_CLIENT_SECRET", ""),
        os.environ.get("YOUTUBE_REFRESH_TOKEN", ""),
    )


def _publish_at(cfg) -> str | None:
    hours = cfg.get("publish.schedule_hours_ahead")
    if not hours:
        return None
    when = datetime.now(timezone.utc) + timedelta(hours=float(hours))
    return when.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run(ctx) -> None:
    approval = ctx.store.get_approval(ctx.job_id, "video")
    if not approval or approval["state"] != "approved":
        state = approval["state"] if approval else "never requested"
        raise RuntimeError(
            f"Job {ctx.job_id} is not approved (state: {state}). "
            "Publishing is gated on an explicit approval recorded in the database."
        )

    meta = json.loads(ctx.metadata_path.read_text(encoding="utf-8"))
    scheduled = approval["decision"] == "schedule"
    publish_at = _publish_at(ctx.cfg) if scheduled else None

    body = build_video_body(meta, publish_at=publish_at)
    if body["status"]["containsSyntheticMedia"]:
        ctx.log("declaring altered-or-synthetic content, derived from the asset manifest")

    client = build_client()

    def progress(sent: int, total: int) -> None:
        if total and (sent // (16 * 1024 * 1024)) != ((sent - 1) // (16 * 1024 * 1024)):
            ctx.log(f"upload {sent / total * 100:.0f}%")

    result = client.upload_video(ctx.master_path, body, progress=progress)
    ctx.log(f"uploaded {result.video_id} ({result.privacy_status}) — {result.url}")

    thumbs = [Path(p) for p in meta.get("thumbnails", [])]
    chosen = thumbs[0] if thumbs else None
    if chosen and chosen.exists():
        try:
            client.set_thumbnail(result.video_id, chosen)
            ctx.log(f"thumbnail set from {chosen.name}")
        except Exception as exc:  # noqa: BLE001 — never lose an upload over a thumbnail
            ctx.log(f"thumbnail failed: {exc}", "warn")

    if ctx.srt_path.exists() and ctx.cfg.get("publish.upload_captions", True):
        try:
            client.upload_caption(result.video_id, ctx.srt_path,
                                  language=ctx.cfg.get("publish.caption_language", "en"))
            ctx.log("caption track uploaded")
        except Exception as exc:  # noqa: BLE001
            ctx.log(f"caption upload failed: {exc}", "warn")

    ctx.store.merge_meta(ctx.job_id, youtube_video_id=result.video_id,
                         youtube_url=result.url,
                         published_at=publish_at or "immediate")
    ctx.store.update_job(ctx.job_id, status="published")
    (ctx.job_dir / "publish.json").write_text(
        json.dumps({"video_id": result.video_id, "url": result.url,
                    "privacy_status": result.privacy_status,
                    "publish_at": publish_at, "request": body}, indent=2),
        encoding="utf-8",
    )
