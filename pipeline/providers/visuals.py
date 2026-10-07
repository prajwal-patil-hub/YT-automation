"""Visual providers.

Each provider declares the intent `kinds` it can resolve. The visuals stage
looks up a provider by the beat's intent kind and falls back to `colour` so a
single missing asset can never hard-fail an otherwise good render.

This module is the seam where Option B (generated stills) and Option C
(generated clips) would plug in later: add a provider, declare its kinds, set
`generated=True` on what it returns. Nothing else in the pipeline changes.
"""
from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Any, Sequence

from . import ProviderUnavailable, RenderedVisual, register_visual
from ..render import cards, layered, scenes
from ..render.theme import Theme

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}
STOPWORDS = {
    "a", "an", "the", "of", "and", "or", "to", "in", "on", "for", "with",
    "at", "by", "from", "is", "are", "be", "this", "that", "it", "as",
}


def _tokens(text: str) -> set[str]:
    return {w for w in re.split(r"[^a-z0-9]+", text.lower()) if w and w not in STOPWORDS}


class _CardBase:
    kinds: tuple[str, ...] = ()

    def __init__(self, cfg):
        self.cfg = cfg
        self.theme = Theme.from_config(cfg.section("theme"))
        self.size = (
            int(cfg.get("video.width", 1920)),
            int(cfg.get("video.height", 1080)),
        )
        self.footer = cfg.get("theme.footer") or None


@register_visual("card")
class CardVisual(_CardBase):
    """Text cards: title, bullet list, pull quote.

    These are original artefacts — the thing the inauthentic-content policy
    actually rewards — and they cost no GPU because they are just drawing.
    """
    name = "card"
    kinds = ("card", "title", "bullets", "bullet", "quote")

    def render(self, intent, out_path: Path, ctx: dict[str, Any]) -> RenderedVisual:
        spec = dict(intent.spec)
        kind = intent.kind
        footer = spec.pop("footer", self.footer)

        if kind in ("bullets", "bullet"):
            cards.bullet_card(
                out_path, self.size, self.theme,
                heading=spec.get("heading") or spec.get("title"),
                bullets=spec.get("bullets") or [],
                kicker=spec.get("kicker"), footer=footer,
            )
        elif kind == "quote":
            cards.quote_card(
                out_path, self.size, self.theme,
                quote=spec.get("quote") or spec.get("text") or "",
                attribution=spec.get("attribution"), footer=footer,
            )
        else:
            cards.title_card(
                out_path, self.size, self.theme,
                title=spec.get("title") or ctx.get("fallback_title", ""),
                kicker=spec.get("kicker"), subtitle=spec.get("subtitle"),
                footer=footer,
            )
        return RenderedVisual(
            path=out_path, provider=self.name, kind=kind,
            license="original", generated=False, photorealistic=False,
        )


@register_visual("chart")
class ChartVisual(_CardBase):
    """Bar charts drawn from the script's own data.

    Impossible to template-detect, because the data differs every video.
    """
    name = "chart"
    kinds = ("chart", "bar", "data")

    def render(self, intent, out_path: Path, ctx: dict[str, Any]) -> RenderedVisual:
        spec = intent.spec
        raw = spec.get("data") or []
        data: list[tuple[str, float]] = []
        for row in raw:
            if isinstance(row, (list, tuple)) and len(row) >= 2:
                data.append((str(row[0]), float(row[1])))
            elif isinstance(row, dict) and "label" in row:
                data.append((str(row["label"]), float(row.get("value", 0))))
        if not data:
            raise ValueError("chart intent has no usable 'data' rows")

        cards.chart_card(
            out_path, self.size, self.theme,
            heading=spec.get("heading") or spec.get("title"),
            data=data, unit=spec.get("unit", ""),
            colour=spec.get("colour") or spec.get("color"),
            kicker=spec.get("kicker"), footer=spec.get("footer", self.footer),
        )
        return RenderedVisual(
            path=out_path, provider=self.name, kind="chart",
            license="original", generated=False, photorealistic=False,
        )


@register_visual("stock")
class StockVisual(_CardBase):
    """Pick a clip or still from the local stock library.

    Licence metadata is read from a `_license.json` beside the media, so the
    manifest records where every frame came from. Stock is deliberately a
    *base layer*: the popular Pexels clips circulate widely, so a video built
    only from them is exactly the reuse that template-detection looks for.
    """
    name = "stock"
    kinds = ("stock", "footage", "broll")

    def __init__(self, cfg):
        super().__init__(cfg)
        self.root = cfg.stock_dir
        self._index: list[tuple[Path, set[str], dict]] | None = None

    def _load_index(self):
        if self._index is not None:
            return self._index
        if not self.root.exists():
            raise ProviderUnavailable(
                f"No stock library at {self.root}.\n"
                "  Create it and drop clips in, or avoid 'stock' visual intents.\n"
                "  Pexels and Pixabay both permit commercial use without attribution."
            )
        licences: dict[Path, dict] = {}
        for lic in self.root.rglob("_license.json"):
            try:
                licences[lic.parent] = json.loads(lic.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue

        index = []
        for path in sorted(self.root.rglob("*")):
            if path.suffix.lower() not in IMAGE_EXT | VIDEO_EXT:
                continue
            meta = licences.get(path.parent, {})
            index.append((path, _tokens(path.stem) | _tokens(path.parent.name), meta))
        if not index:
            raise ProviderUnavailable(f"Stock library at {self.root} contains no media files.")
        self._index = index
        return index

    def render(self, intent, out_path: Path, ctx: dict[str, Any]) -> RenderedVisual:
        index = self._load_index()
        query = _tokens(
            " ".join(str(v) for v in (
                intent.spec.get("query") or intent.spec.get("tags")
                or intent.spec.get("title") or ctx.get("narration", "")
            ) if isinstance(v, str)) if isinstance(intent.spec.get("tags"), (list, tuple))
            else str(intent.spec.get("query") or intent.spec.get("title") or ctx.get("narration", ""))
        )
        used: set[str] = ctx.get("used_paths", set())

        def score(entry):
            path, tags, _ = entry
            overlap = len(query & tags)
            penalty = 2 if str(path) in used else 0
            return (overlap - penalty, -len(tags))

        best = max(index, key=score)
        path, _, meta = best
        return RenderedVisual(
            path=path, provider=self.name, kind="stock",
            license=meta.get("license", "unknown"),
            source_url=meta.get("source_url"),
            generated=False,
            photorealistic=bool(meta.get("photorealistic", True)),
            media="video" if path.suffix.lower() in VIDEO_EXT else "image",
        )


@register_visual("scene")
class SceneVisual(_CardBase):
    """Ambient scene grounds for calm, long-form narration.

    Procedurally generated, so: deterministic from a seed, endlessly varied
    across videos, no GPU, and not photorealistic — which keeps the disclosure
    flag off. Text is optional and most sleep-paced beats carry none.
    """
    name = "scene"
    kinds = ("scene", "ambient", "mood")

    def __init__(self, cfg):
        super().__init__(cfg)
        self.default_preset = cfg.get("visuals.preset", "mythology")

    def render(self, intent, out_path: Path, ctx: dict[str, Any]) -> RenderedVisual:
        spec = intent.spec
        # Seed from the beat so a given beat always renders the same ground,
        # but no two beats share one.
        seed = int(spec.get("seed", (ctx.get("beat_index", 0) * 7919) + 13))
        scenes.scene_card(
            out_path, self.size, self.theme,
            preset=spec.get("preset", self.default_preset),
            seed=seed,
            title=spec.get("title"),
            subtitle=spec.get("subtitle"),
            align=spec.get("align", "centre"),
        )
        return RenderedVisual(
            path=out_path, provider=self.name, kind="scene",
            license="original", generated=False, photorealistic=False,
        )


@register_visual("layered")
class LayeredVisual(_CardBase):
    """Multi-layer silhouette scenes, drifted at per-layer rates by the assembler.

    Returns a flattened still *and* the layer manifest. A beat renders fine
    without parallax (the flattened frame is used), so a channel can switch
    motion on and off without touching its scripts.
    """
    name = "layered"
    kinds = ("layered", "parallax", "silhouette")

    def __init__(self, cfg):
        super().__init__(cfg)
        self.default_archetype = cfg.get("visuals.archetype", "open-field")

    def render(self, intent, out_path: Path, ctx: dict[str, Any]) -> RenderedVisual:
        spec = intent.spec
        archetype = spec.get("archetype") or spec.get("scene") or self.default_archetype
        seed = int(spec.get("seed", (ctx.get("beat_index", 0) * 7919) + 13))

        layer_dir = out_path.parent / f"{out_path.stem}-layers"
        manifest = layered.render_layers(archetype, self.size, layer_dir, seed=seed)
        # Flattened still, so the beat works with or without parallax motion.
        layered.flatten(archetype, self.size, seed=seed).save(out_path)

        return RenderedVisual(
            path=out_path, provider=self.name, kind="layered",
            license="original", generated=False, photorealistic=False,
            layers=manifest,
        )


@register_visual("colour")
class ColourVisual(_CardBase):
    """Fallback. Never fails, so one bad intent cannot lose a whole render."""
    name = "colour"
    kinds = ("colour", "color", "blank", "fallback")

    def render(self, intent, out_path: Path, ctx: dict[str, Any]) -> RenderedVisual:
        cards.colour_card(
            out_path, self.size, self.theme,
            fill=intent.spec.get("fill"),
            label=intent.spec.get("label"),
            footer=self.footer,
        )
        return RenderedVisual(
            path=out_path, provider=self.name, kind="colour",
            license="original", generated=False, photorealistic=False,
        )


# Intent kind -> provider name. Built once from each provider's declared kinds.
def kind_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for cls in (CardVisual, ChartVisual, SceneVisual, LayeredVisual,
                StockVisual, ColourVisual):
        for kind in cls.kinds:
            mapping[kind] = cls.name
    return mapping
