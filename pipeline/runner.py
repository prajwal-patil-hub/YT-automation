"""Stage runner.

Every stage is resumable: its state lives in SQLite, so an interrupted run
picks up where it stopped instead of starting over. That is the single most
useful property for a pipeline whose stages can take minutes each.
"""
from __future__ import annotations

import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .config import Config
from .db import Store
from .models import STAGES, Script
from .stages import (
    assemble_stage, captions_stage, package_stage,
    script_stage, visuals_stage, voice_stage,
)

STAGE_FUNCS: dict[str, Callable[["StageContext"], None]] = {
    "script": script_stage.run,
    "voice": voice_stage.run,
    "visuals": visuals_stage.run,
    "captions": captions_stage.run,
    "assemble": assemble_stage.run,
    "package": package_stage.run,
}


@dataclass
class StageContext:
    cfg: Config
    store: Store
    job_id: int
    topic: str
    force: bool = False
    options: dict[str, Any] = field(default_factory=dict)
    script: Script | None = None
    stage: str | None = None
    quiet: bool = False
    # Populated by the visuals stage; read by the assembler.
    media_kinds: dict[int, str] = field(default_factory=dict)

    # --- paths ----------------------------------------------------------------
    @property
    def job_dir(self) -> Path:
        d = self.cfg.job_dir(self.job_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def script_path(self) -> Path: return self.job_dir / "script.json"
    @property
    def ass_path(self) -> Path: return self.job_dir / "captions.ass"
    @property
    def srt_path(self) -> Path: return self.job_dir / "captions.srt"
    @property
    def master_path(self) -> Path: return self.job_dir / "master.mp4"
    @property
    def proxy_path(self) -> Path: return self.job_dir / "review-proxy.mp4"
    @property
    def metadata_path(self) -> Path: return self.job_dir / "metadata.json"

    @property
    def ffmpeg(self) -> str | None: return self.cfg.get("paths.ffmpeg")
    @property
    def ffprobe(self) -> str | None: return self.cfg.get("paths.ffprobe")

    def log(self, message: str, level: str = "info") -> None:
        self.store.log(self.job_id, level, message, self.stage)
        if not self.quiet:
            mark = {"info": "  ", "warn": "! ", "error": "x "}.get(level, "  ")
            print(f"{mark}[{self.stage or '-'}] {message}")


def load_script_if_present(ctx: StageContext) -> None:
    if ctx.script is None and ctx.script_path.exists():
        ctx.script = Script.load(ctx.script_path)


def run_job(
    cfg: Config,
    store: Store,
    job_id: int,
    *,
    stages: list[str] | None = None,
    force: bool = False,
    options: dict[str, Any] | None = None,
    quiet: bool = False,
) -> StageContext:
    job = store.get_job(job_id)
    if job is None:
        raise ValueError(f"No job {job_id}")

    wanted = stages or STAGES
    ctx = StageContext(
        cfg=cfg, store=store, job_id=job_id, topic=job["topic"],
        force=force, options=options or {}, quiet=quiet,
    )
    load_script_if_present(ctx)

    if force:
        store.reset_stages(job_id, wanted)

    for name in STAGES:
        if name not in wanted:
            continue
        if store.stage_status(job_id, name) == "done" and not force:
            ctx.stage = name
            ctx.log("already done, skipping")
            continue

        ctx.stage = name
        store.stage_begin(job_id, name)
        store.update_job(job_id, status=f"running:{name}")
        try:
            load_script_if_present(ctx)
            if name != "script" and ctx.script is None:
                raise RuntimeError(
                    "No script for this job. Run the 'script' stage first."
                )
            STAGE_FUNCS[name](ctx)
            store.stage_done(job_id, name)
        except Exception as exc:  # noqa: BLE001 — recorded, then re-raised
            detail = f"{type(exc).__name__}: {exc}"
            store.stage_failed(job_id, name, f"{detail}\n{traceback.format_exc()}")
            store.update_job(job_id, status=f"failed:{name}")
            ctx.log(detail, "error")
            raise

    done = all(store.stage_status(job_id, s) == "done" for s in STAGES)
    store.update_job(job_id, status="ready-for-review" if done else "partial")
    ctx.stage = None
    return ctx
