"""Stage 03 — resolve each beat's visual intent into a concrete asset.

Providers are looked up by intent kind. A provider failure degrades to the
colour fallback rather than killing the render, and every resolution is
recorded in the asset manifest with its provenance.
"""
from __future__ import annotations

from ..providers import ProviderUnavailable, get_visual
from ..providers.visuals import kind_map


def run(ctx) -> None:
    mapping = kind_map()
    overrides = ctx.cfg.section("visuals").get("kind_map") or {}
    mapping.update(overrides)

    vis_dir = ctx.job_dir / "visuals"
    vis_dir.mkdir(parents=True, exist_ok=True)

    # Replace, never append — see Store.clear_stage_assets.
    ctx.store.clear_stage_assets(ctx.job_id, "visuals")

    cache: dict[str, object] = {}
    used_paths: set[str] = set()
    fallbacks = 0

    def provider_for(name: str):
        if name not in cache:
            cache[name] = get_visual(name, ctx.cfg)
        return cache[name]

    for beat in ctx.script.beats:
        kind = beat.visual.kind
        name = mapping.get(kind, "colour")
        out = vis_dir / f"beat-{beat.index:03d}.png"
        beat_ctx = {
            "beat_index": beat.index,
            "narration": beat.narration,
            "fallback_title": ctx.script.title,
            "used_paths": used_paths,
        }
        try:
            rendered = provider_for(name).render(beat.visual, out, beat_ctx)
        except (ProviderUnavailable, ValueError, OSError) as exc:
            ctx.log(f"beat {beat.index}: {name} failed ({exc}); using colour fallback", "warn")
            from ..models import VisualIntent
            rendered = provider_for("colour").render(
                VisualIntent("colour", {"label": f"beat {beat.index}"}), out, beat_ctx
            )
            fallbacks += 1

        beat.visual_path = str(rendered.path)
        used_paths.add(str(rendered.path))
        beat.visual_asset_id = ctx.store.add_asset(
            ctx.job_id, rendered.kind, rendered.path, rendered.provider,
            stage="visuals", beat_index=beat.index,
            source_url=rendered.source_url,
            license=rendered.license,
            generated=rendered.generated,
            photorealistic=rendered.photorealistic,
        )
        ctx.media_kinds[beat.index] = rendered.media

    ctx.script.save(ctx.script_path)
    note = f", {fallbacks} fallback(s)" if fallbacks else ""
    ctx.log(f"resolved {len(ctx.script.beats)} visuals{note}")

    reused = ctx.store.reused_assets(ctx.job_id)
    for row in reused:
        ctx.log(
            f"beat {row['beat_index']}: asset also used in job(s) {row['seen_in']} — "
            "vary it if this repeats",
            "warn",
        )
