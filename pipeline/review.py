"""The decision loop.

`yta watch` polls Telegram and resolves pending approvals. It is deliberately a
separate process from rendering: a render that blocks on a person dies when the
terminal closes, and an approval that arrives eight hours later is normal rather
than exceptional.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from . import channels as channels_mod
from .db import Store
from .models import STAGES
from .stages.review_stage import REDO_TARGETS, build_client
from .util.telegram import Callback, TelegramClient, decode_action


@dataclass
class Decision:
    job_id: int
    action: str
    user_id: int
    note: str = ""


def _ack_text(action: str) -> str:
    return {
        "approve": "Approved — ready to publish",
        "schedule": "Approved for scheduling",
        "reject": "Rejected",
    }.get(action, f"Re-running from {REDO_TARGETS.get(action, action)}")


def handle_callback(store: Store, client: TelegramClient, cb: Callback,
                    *, rerun: Callable[[int, str], None] | None = None) -> Decision | None:
    """Apply one button press. Returns the decision, or None if unusable."""
    parsed = decode_action(cb.data)
    if not parsed:
        return None
    job_id, action = parsed

    job = store.get_job(job_id)
    if job is None:
        client.answer_callback(cb.callback_id, f"No job {job_id}")
        return None

    if action in ("approve", "schedule"):
        store.set_approval(job_id, "video", "approved", decision=action,
                           notes=f"user {cb.user_id}")
        store.update_job(job_id, status="approved")
    elif action == "reject":
        store.set_approval(job_id, "video", "rejected", decision=action,
                           notes=f"user {cb.user_id}")
        store.update_job(job_id, status="rejected")
    elif action in REDO_TARGETS:
        store.set_approval(job_id, "video", "redo", decision=action,
                           notes=f"user {cb.user_id}")
        store.update_job(job_id, status=f"redo:{REDO_TARGETS[action]}")
        if rerun:
            rerun(job_id, REDO_TARGETS[action])
    else:
        client.answer_callback(cb.callback_id, f"Unknown action {action}")
        return None

    client.answer_callback(cb.callback_id, _ack_text(action))
    store.log(job_id, "info", f"review: {action} by user {cb.user_id}", "review")
    return Decision(job_id, action, cb.user_id)


def rerun_from(channel: str, job_id: int, stage: str, *, quiet: bool = False) -> None:
    """Re-run one stage and everything after it, in the job's own channel."""
    from .runner import run_job

    cfg = channels_mod.load(channel)
    tail = STAGES[STAGES.index(stage):]
    with Store(cfg.db_path) as store:
        store.reset_stages(job_id, tail)
        run_job(cfg, store, job_id, stages=tail, force=True, quiet=quiet)


def watch(cfg, *, once: bool = False, poll_timeout: int = 30,
          on_decision: Callable[[Decision], None] | None = None) -> int:
    """Poll for decisions until interrupted. Returns the number handled."""
    client = build_client(cfg)
    if not client.allowed:
        raise RuntimeError(
            "TELEGRAM_ALLOWED_USER_ID is not set. Refusing to listen: without an "
            "allow-list, anyone who finds the bot can publish to your channel."
        )

    handled = 0
    offset: int | None = None
    store = Store(cfg.db_path)
    try:
        while True:
            updates = client.get_updates(offset, timeout=poll_timeout)
            for update in updates:
                offset = int(update.get("update_id", 0)) + 1
            for cb in client.callbacks(updates):
                job = store.get_job(decode_action(cb.data)[0]) if decode_action(cb.data) else None
                channel = job["channel"] if job else cfg.channel_slug

                def _rerun(job_id: int, stage: str, _ch=channel) -> None:
                    rerun_from(_ch, job_id, stage)

                decision = handle_callback(store, client, cb, rerun=_rerun)
                if decision:
                    handled += 1
                    if on_decision:
                        on_decision(decision)
            if once:
                return handled
            if not updates:
                time.sleep(1)
    finally:
        store.close()
