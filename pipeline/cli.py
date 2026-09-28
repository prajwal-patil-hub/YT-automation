"""Command line entry point.

    yta new "topic"            create a job
    yta run  <id>              run the pipeline (resumes where it stopped)
    yta redo <id> visuals      re-run one stage and everything after it
    yta show <id>              stage states, warnings, output paths
    yta list                   recent jobs
    yta doctor                 check the local toolchain
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from . import config as config_mod
from .db import Store
from .models import STAGES
from .providers import available
from .runner import run_job


def _store(cfg) -> Store:
    return Store(cfg.db_path)


def cmd_new(args, cfg) -> int:
    with _store(cfg) as store:
        job_id = store.create_job(args.topic)
        print(f"job {job_id}: {args.topic}")
        if args.run:
            run_job(cfg, store, job_id, options={"script_path": args.script})
            print(f"\nreview: {cfg.job_dir(job_id)}")
    return 0


def cmd_run(args, cfg) -> int:
    with _store(cfg) as store:
        ctx = run_job(
            cfg, store, args.job_id,
            stages=args.stages or None,
            force=args.force,
            options={"script_path": args.script},
        )
        print(f"\noutput: {ctx.job_dir}")
    return 0


def cmd_redo(args, cfg) -> int:
    """Re-run one stage and every stage after it.

    This is the granular-redo path: a 90%-good video should cost one stage,
    not the whole render.
    """
    if args.stage not in STAGES:
        print(f"Unknown stage '{args.stage}'. One of: {', '.join(STAGES)}", file=sys.stderr)
        return 2
    tail = STAGES[STAGES.index(args.stage):]
    with _store(cfg) as store:
        store.reset_stages(args.job_id, tail)
        ctx = run_job(cfg, store, args.job_id, stages=tail, force=True,
                      options={"script_path": args.script})
        print(f"\noutput: {ctx.job_dir}")
    return 0


def cmd_show(args, cfg) -> int:
    with _store(cfg) as store:
        job = store.get_job(args.job_id)
        if not job:
            print(f"No job {args.job_id}", file=sys.stderr)
            return 1
        print(f"job {job['id']}  {job['status']}")
        print(f"  topic: {job['topic']}")
        if job["title"]:
            print(f"  title: {job['title']}")

        states = store.stages_for(args.job_id)
        print("\n  stages")
        for name in STAGES:
            row = states.get(name)
            status = row["status"] if row else "pending"
            took = ""
            if row and row["started_at"] and row["finished_at"]:
                took = f"  {row['finished_at'] - row['started_at']:.1f}s"
            print(f"    {name:<10} {status}{took}")
            if row and row["error"]:
                print(f"      {row['error'].splitlines()[0]}")

        assets = store.assets_for(args.job_id)
        gen = sum(1 for a in assets if a["generated"])
        print(f"\n  assets: {len(assets)} ({gen} generated)")
        print(f"  disclosure flag: {'YES' if store.requires_disclosure(args.job_id) else 'no'}")

        warnings = [e for e in store.events_for(args.job_id, 200) if e["level"] == "warn"]
        if warnings:
            print(f"\n  warnings ({len(warnings)})")
            for e in reversed(warnings[:12]):
                print(f"    [{e['stage'] or '-'}] {e['message']}")

        meta_path = cfg.job_dir(args.job_id) / "metadata.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text())
            print(f"\n  master: {meta.get('master')}")
            print(f"  proxy:  {meta.get('proxy')}")
            print(f"  length: {meta.get('duration_seconds')}s")
    return 0


def cmd_list(args, cfg) -> int:
    with _store(cfg) as store:
        rows = store.list_jobs(args.limit)
        if not rows:
            print("no jobs yet — try: yta new \"your topic\" --run")
            return 0
        for r in rows:
            print(f"  {r['id']:>4}  {r['status']:<22} {(r['title'] or r['topic'])[:60]}")
    return 0


def cmd_doctor(args, cfg) -> int:
    """Check everything the pipeline needs before a first run."""
    ok = True

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal ok
        ok = ok and good
        print(f"  [{'ok' if good else 'XX'}] {label}{('  — ' + detail) if detail else ''}")

    print("binaries")
    for name in ("ffmpeg", "ffprobe"):
        override = cfg.get(f"paths.{name}")
        found = override or shutil.which(name)
        check(name, bool(found), found or "not on PATH — install FFmpeg")

    print("\npython packages")
    try:
        import PIL  # noqa: F401
        check("Pillow", True, f"version {PIL.__version__}")
    except ImportError:
        check("Pillow", False, "pip install Pillow")

    print("\nfonts")
    try:
        from .render.theme import Theme
        theme = Theme.from_config(cfg.section("theme"))
        for role in ("display", "body", "mono"):
            check(role, True, Path(theme.font_file(role)).name)
    except Exception as exc:  # noqa: BLE001
        check("fonts", False, str(exc))

    print("\nproviders registered")
    for kind, names in available().items():
        print(f"  {kind:<8} {', '.join(names)}")

    print("\nconfigured")
    print(f"  script   {cfg.get('script.provider')}")
    print(f"  voice    {cfg.get('voice.provider')}")
    print(f"  video    {cfg.get('video.width')}x{cfg.get('video.height')} @ {cfg.get('video.fps')}fps")
    print(f"  work dir {cfg.work_dir}")
    stock = cfg.stock_dir
    print(f"  stock    {stock}{'' if stock.exists() else '  (missing — stock intents will fall back)'}")

    print("\n" + ("all good" if ok else "some checks failed — see above"))
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="yta", description="Local prompt-to-video pipeline")
    p.add_argument("--config", help="path to config.toml")
    sub = p.add_subparsers(dest="cmd", required=True)

    n = sub.add_parser("new", help="create a job")
    n.add_argument("topic")
    n.add_argument("--run", action="store_true", help="run the pipeline immediately")
    n.add_argument("--script", help="script JSON (for the 'file' script provider)")
    n.set_defaults(func=cmd_new)

    r = sub.add_parser("run", help="run or resume a job")
    r.add_argument("job_id", type=int)
    r.add_argument("--stages", nargs="*", choices=STAGES, help="only these stages")
    r.add_argument("--force", action="store_true", help="re-run even if done")
    r.add_argument("--script", help="script JSON (for the 'file' script provider)")
    r.set_defaults(func=cmd_run)

    d = sub.add_parser("redo", help="re-run one stage and everything after it")
    d.add_argument("job_id", type=int)
    d.add_argument("stage", choices=STAGES)
    d.add_argument("--script")
    d.set_defaults(func=cmd_redo)

    s = sub.add_parser("show", help="job detail")
    s.add_argument("job_id", type=int)
    s.set_defaults(func=cmd_show)

    l = sub.add_parser("list", help="recent jobs")
    l.add_argument("--limit", type=int, default=20)
    l.set_defaults(func=cmd_list)

    doc = sub.add_parser("doctor", help="check the local toolchain")
    doc.set_defaults(func=cmd_doctor)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        cfg = config_mod.load(Path(args.config) if args.config else None)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    try:
        return args.func(args, cfg)
    except KeyboardInterrupt:
        print("\ninterrupted — re-run the same command to resume", file=sys.stderr)
        return 130
    except Exception as exc:  # noqa: BLE001
        print(f"\nerror: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
