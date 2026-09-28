"""Stage 01 — produce the script (title, beats, sources)."""
from __future__ import annotations

from ..models import Script
from ..providers import get_script


def run(ctx) -> None:
    provider_name = ctx.cfg.get("script.provider", "file")
    provider = get_script(provider_name, ctx.cfg)
    ctx.log(f"script provider: {provider_name}")

    script = provider.generate(ctx.topic, path=ctx.options.get("script_path"))

    if not script.beats:
        raise ValueError("Script provider returned no beats")
    script.save(ctx.script_path)
    ctx.script = script
    ctx.store.update_job(ctx.job_id, title=script.title)
    ctx.log(
        f"{len(script.beats)} beats, {script.word_count} words, "
        f"{len(script.sources)} sources"
    )
