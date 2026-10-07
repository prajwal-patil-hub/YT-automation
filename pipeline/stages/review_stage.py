"""Stage 08 — send the finished video for human approval.

This stage does not block. It sends the review request, records the approval
as pending, and returns; `yta watch` resolves the decision later. A render
that waits synchronously on a person is a render that dies when the terminal
closes.

What goes in the message matters more than it looks. The machine has already
checked everything objectively checkable in preflight, so the message leads
with what preflight found and then asks for the judgement only a human can
give. The buttons are granular on purpose: with only approve and reject, a
90%-good video costs a whole re-render.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from ..util.telegram import TelegramClient, encode_action

# Which stage each redo button rewinds to. The runner re-runs that stage and
# everything after it.
REDO_TARGETS = {
    "redo-script": "script",
    "redo-voice": "voice",
    "redo-visuals": "visuals",
    "redo-assemble": "assemble",
}


def build_client(cfg) -> TelegramClient:
    allowed = [u for u in (os.environ.get("TELEGRAM_ALLOWED_USER_ID", "")
                           .replace(" ", "").split(",")) if u]
    return TelegramClient(
        os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        api_base=os.environ.get("TELEGRAM_API_BASE") or "https://api.telegram.org",
        allowed_user_ids=allowed,
    )


def _summary(ctx) -> str:
    meta = json.loads(ctx.metadata_path.read_text(encoding="utf-8"))
    duration = meta.get("duration_seconds", 0)
    mins, secs = divmod(int(duration), 60)

    lines = [
        f"🎬 <b>{meta.get('title', 'Untitled')}</b>",
        f"<code>job {ctx.job_id} · {ctx.cfg.channel_slug} · "
        f"{mins}:{secs:02d} · {len(ctx.script.beats)} beats</code>",
        "",
    ]

    pre_path = ctx.job_dir / "preflight.json"
    if pre_path.exists():
        pre = json.loads(pre_path.read_text(encoding="utf-8"))
        counts = pre.get("counts", {})
        lines.append(
            f"✅ preflight {counts.get('pass', 0)} pass · "
            f"{counts.get('warn', 0)} warn · {counts.get('fail', 0)} fail"
        )
        for check in pre.get("checks", []):
            if check["status"] != "pass":
                lines.append(f"  • {check['name']}: {check['detail']}")
        lines.append("")

    titles = meta.get("title_variants") or []
    if titles:
        lines.append("<b>Title options</b>")
        lines.extend(f"  {i}. {t}" for i, t in enumerate(titles, 1))
        lines.append("")

    if meta.get("altered_or_synthetic_content"):
        lines.append("⚠️ <b>Synthetic-content disclosure will be set</b>")
        lines.append("")

    lines.append(f"Sources: {len(meta.get('sources', []))} · "
                 f"Chapters: {len(meta.get('chapters', []))}")
    return "\n".join(lines)


def _buttons(job_id: int):
    j = lambda a: encode_action(job_id, a)  # noqa: E731
    return [
        [("✅ Approve", j("approve")), ("📅 Schedule", j("schedule"))],
        [("🔁 Visuals", j("redo-visuals")), ("🔁 Voice", j("redo-voice"))],
        [("🔁 Script", j("redo-script")), ("🔁 Re-assemble", j("redo-assemble"))],
        [("❌ Reject", j("reject"))],
    ]


def run(ctx) -> None:
    chat_id = os.environ.get("TELEGRAM_CHAT_ID") or os.environ.get("TELEGRAM_ALLOWED_USER_ID", "")
    chat_id = chat_id.split(",")[0].strip()
    if not chat_id:
        raise RuntimeError(
            "TELEGRAM_CHAT_ID (or TELEGRAM_ALLOWED_USER_ID) is not set in .env — "
            "nowhere to send the review."
        )

    client = build_client(ctx.cfg)

    # Prefer the proxy: it is well under the upload cap and loads fast on a
    # phone, which is where this gets reviewed.
    video = ctx.proxy_path if ctx.proxy_path.exists() else ctx.master_path
    if video.stat().st_size > client.upload_limit():
        ctx.log(
            f"{video.name} exceeds this endpoint's upload limit; sending a link instead",
            "warn",
        )
        sent = client.send_message(
            chat_id, _summary(ctx) + f"\n\n<code>{ctx.master_path}</code>",
            buttons=_buttons(ctx.job_id),
        )
    else:
        sent = client.send_video(
            chat_id, video, caption=_summary(ctx), buttons=_buttons(ctx.job_id)
        )

    message_id = int(sent.get("message_id", 0))
    ctx.store.set_approval(ctx.job_id, "video", "pending", message_id=message_id)
    ctx.store.update_job(ctx.job_id, status="awaiting-review")
    ctx.log(
        f"sent for review to chat {chat_id} (message {message_id}); "
        "resolve it with: ./run.sh watch"
    )
