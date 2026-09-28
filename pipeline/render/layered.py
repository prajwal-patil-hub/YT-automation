"""Layered silhouette scenes with real parallax.

An exploration of depth without any generative model. A scene is built as
several transparent layers — sky, far ridge, mid ridge, near ground, figures,
foreground — which the assembler then drifts at different rates. Because the
layers move relative to one another, a still becomes genuine depth rather than
a pan across a flat picture.

Shadow theatre is not an arbitrary choice for this material: the Mahabharata
and Ramayana were performed as shadow puppetry (tholu bommalata) for
centuries, so silhouette against a lit ground is native to the source, not a
stylistic import.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from . import ambient


@dataclass
class Layer:
    image: Image.Image
    depth: float          # 0 = infinitely far (still), 1 = nearest (fastest)
    name: str


def _ridge(
    size: tuple[int, int], *, seed: int, base_y: float, amplitude: float,
    roughness: int = 5, colour: tuple[int, int, int, int] = (0, 0, 0, 255),
    jitter: float = 0.0,
) -> Image.Image:
    """A mountain/hill silhouette built from summed sine waves."""
    w, h = size
    rng = random.Random(seed)
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)

    waves = [(rng.uniform(0, math.tau), rng.uniform(0.6, 1.0) * (i + 1), 1.0 / (i + 1))
             for i in range(roughness)]
    points = [(0, h)]
    step = max(w // 340, 1)
    for x in range(0, w + step, step):
        u = x / w
        v = sum(amp * math.sin(phase + freq * u * math.tau) for phase, freq, amp in waves)
        v /= sum(a for _, _, a in waves)
        y = base_y * h - v * amplitude * h
        if jitter:
            y += rng.uniform(-jitter, jitter) * h
        points.append((x, y))
    points.append((w, h))
    draw.polygon(points, fill=colour)
    return layer


def _archer(size: tuple[int, int], *, scale: float, x: float, ground: float,
            colour=(0, 0, 0, 255)) -> Image.Image:
    """A stylised archer at full draw, in profile, facing right.

    Silhouettes read from pose, not detail, so everything here serves the
    read: a tapered torso rather than a box, asymmetric arms, an open gap
    between bow-arm and body, and a braced stance. The bow curves away from
    the archer with the string drawn back to the face — which is what makes
    it legible as archery rather than a figure holding a hoop.
    """
    w, h = size
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    s = scale * h
    cx, cy = x * w, ground * h          # cy is the ground line under the feet

    shoulder = (cx + 0.02 * s, cy - 0.80 * s)
    grip = (cx + 0.45 * s, cy - 0.70 * s)
    draw_pt = (cx + 0.09 * s, cy - 0.76 * s)
    limb = max(int(s * 0.052), 2)

    # --- bow: arc bulging away from the archer, string drawn back ---------
    bow_c = (cx + 0.05 * s, cy - 0.70 * s)
    bow_r = 0.40 * s
    d.arc([bow_c[0] - bow_r, bow_c[1] - bow_r, bow_c[0] + bow_r, bow_c[1] + bow_r],
          start=-70, end=70, fill=colour, width=max(int(s * 0.030), 2))
    tip_dx = bow_r * math.cos(math.radians(70))
    tip_dy = bow_r * math.sin(math.radians(70))
    top_tip = (bow_c[0] + tip_dx, bow_c[1] - tip_dy)
    bot_tip = (bow_c[0] + tip_dx, bow_c[1] + tip_dy)
    string_w = max(int(s * 0.012), 1)
    d.line([top_tip, draw_pt], fill=colour, width=string_w)
    d.line([bot_tip, draw_pt], fill=colour, width=string_w)
    # the arrow, resting on the grip
    d.line([draw_pt, (grip[0] + 0.06 * s, grip[1] - 0.02 * s)],
           fill=colour, width=string_w)

    # --- legs: braced, front foot forward ---------------------------------
    hip = (cx, cy - 0.42 * s)
    d.line([hip, (cx + 0.26 * s, cy)], fill=colour, width=int(limb * 1.15))
    d.line([hip, (cx - 0.22 * s, cy)], fill=colour, width=int(limb * 1.15))

    # --- torso: tapered, leaning very slightly into the draw --------------
    d.polygon([
        (shoulder[0] - 0.13 * s, shoulder[1] - 0.03 * s),
        (shoulder[0] + 0.12 * s, shoulder[1] + 0.01 * s),
        (hip[0] + 0.09 * s, hip[1]),
        (hip[0] - 0.09 * s, hip[1]),
    ], fill=colour)

    # --- head, set forward over the front foot ----------------------------
    hr = 0.082 * s
    head_c = (cx + 0.06 * s, cy - 0.93 * s)
    d.ellipse([head_c[0] - hr, head_c[1] - hr * 1.12,
               head_c[0] + hr, head_c[1] + hr * 1.12], fill=colour)

    # --- arms: one extended to the grip, one drawn back past the jaw ------
    d.line([shoulder, grip], fill=colour, width=limb)
    elbow = (cx - 0.17 * s, cy - 0.83 * s)
    d.line([shoulder, elbow], fill=colour, width=limb)
    d.line([elbow, draw_pt], fill=colour, width=limb)
    return layer


def _standing_figures(size: tuple[int, int], *, seed: int, count: int,
                      ground: float, scale: float, colour=(0, 0, 0, 255)) -> Image.Image:
    """A scattered line of small figures — an army at rest, read at distance."""
    w, h = size
    rng = random.Random(seed)
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for _ in range(count):
        x = rng.uniform(0.02, 0.98) * w
        s = scale * h * rng.uniform(0.8, 1.2)
        y = ground * h + rng.uniform(-0.004, 0.004) * h
        d.ellipse([x - s * 0.13, y - s * 1.0, x + s * 0.13, y - s * 0.74], fill=colour)
        d.polygon([(x - s * 0.17, y - s * 0.76), (x + s * 0.17, y - s * 0.76),
                   (x + s * 0.11, y), (x - s * 0.11, y)], fill=colour)
    return layer


def _spears(size: tuple[int, int], *, seed: int, count: int, ground: float,
            scale: float, colour=(0, 0, 0, 255)) -> Image.Image:
    w, h = size
    rng = random.Random(seed)
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for _ in range(count):
        x = rng.uniform(0, 1) * w
        s = scale * h * rng.uniform(0.7, 1.35)
        lean = rng.uniform(-0.035, 0.035) * h
        d.line([(x, ground * h), (x + lean, ground * h - s)],
               fill=colour, width=max(int(h * 0.0022), 1))
    return layer


def _embers(size: tuple[int, int], *, seed: int, count: int, colour=(255, 178, 92)) -> Image.Image:
    """A field of drifting points, scrolled vertically by the assembler."""
    w, h = size
    rng = random.Random(seed)
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for _ in range(count):
        x, y = rng.uniform(0, w), rng.uniform(0, h)
        mag = rng.random() ** 2.0
        r = 0.8 + mag * (w / 700)
        a = int(28 + mag * 150)
        d.ellipse([x - r, y - r, x + r, y + r], fill=(*colour, a))
    return layer.filter(ImageFilter.GaussianBlur(radius=max(w // 900, 1)))


# --- scene archetypes -------------------------------------------------------

def scene_battlefield_night(size: tuple[int, int], *, seed: int) -> list[Layer]:
    """The night before Kurukshetra: ridges, distant camp, spears, embers."""
    sky = ambient.compose(size, seed=seed, top="#1B1020", bottom="#07040A",
                          glow="#C07A2E", haze=True, glow_centre=(0.5, 0.62),
                          vignette_strength=0.66).convert("RGBA")
    return [
        Layer(sky, 0.00, "sky"),
        Layer(_ridge(size, seed=seed + 1, base_y=0.74, amplitude=0.13,
                     colour=(10, 7, 14, 255)), 0.12, "far-ridge"),
        Layer(_spears(size, seed=seed + 9, count=70, ground=0.795, scale=0.05,
                      colour=(6, 4, 9, 230)), 0.28, "spears"),
        Layer(_standing_figures(size, seed=seed + 4, count=26, ground=0.80,
                                scale=0.055, colour=(5, 3, 7, 255)), 0.34, "camp"),
        Layer(_ridge(size, seed=seed + 2, base_y=0.90, amplitude=0.07,
                     colour=(4, 3, 6, 255)), 0.60, "near-ridge"),
        Layer(_embers(size, seed=seed + 7, count=150), 0.85, "embers"),
    ]


def scene_lone_archer(size: tuple[int, int], *, seed: int) -> list[Layer]:
    """One figure against a wide sky — Arjuna before the war."""
    sky = ambient.compose(size, seed=seed, top="#221430", bottom="#080510",
                          glow="#D69140", haze=True, glow_centre=(0.62, 0.55),
                          vignette_strength=0.62).convert("RGBA")
    return [
        Layer(sky, 0.00, "sky"),
        Layer(_ridge(size, seed=seed + 3, base_y=0.855, amplitude=0.055,
                     colour=(9, 6, 12, 255)), 0.14, "far-ridge"),
        # Small on purpose: see docs/11 — primitives read as a figure at
        # distance and as a pictogram up close.
        Layer(_archer(size, scale=0.115, x=0.30, ground=0.842,
                      colour=(3, 2, 5, 255)), 0.40, "archer"),
        Layer(_standing_figures(size, seed=seed + 11, count=5, ground=0.851,
                                scale=0.055, colour=(4, 3, 6, 235)), 0.44, "companions"),
        Layer(_ridge(size, seed=seed + 5, base_y=0.94, amplitude=0.05,
                     colour=(3, 2, 4, 255)), 0.72, "foreground"),
    ]


def scene_open_field(size: tuple[int, int], *, seed: int) -> list[Layer]:
    """Empty ground and sky — a resting shot with nothing to look at."""
    sky = ambient.compose(size, seed=seed, top="#141B2A", bottom="#05070C",
                          glow="#4A6690", stars=True, glow_centre=(0.4, 0.48),
                          vignette_strength=0.70).convert("RGBA")
    return [
        Layer(sky, 0.00, "sky"),
        Layer(_ridge(size, seed=seed + 6, base_y=0.86, amplitude=0.08,
                     colour=(6, 8, 13, 255)), 0.16, "far-ridge"),
        Layer(_ridge(size, seed=seed + 8, base_y=0.96, amplitude=0.04,
                     colour=(3, 4, 7, 255)), 0.55, "foreground"),
    ]


ARCHETYPES = {
    "battlefield-night": scene_battlefield_night,
    "lone-archer": scene_lone_archer,
    "open-field": scene_open_field,
}


def render_layers(archetype: str, size: tuple[int, int], out_dir: Path, *, seed: int) -> list[dict]:
    """Write each layer as a PNG and return the manifest the assembler needs."""
    out_dir.mkdir(parents=True, exist_ok=True)
    builder = ARCHETYPES.get(archetype, scene_open_field)
    manifest = []
    for i, layer in enumerate(builder(size, seed=seed)):
        path = out_dir / f"{i:02d}-{layer.name}.png"
        layer.image.save(path)
        manifest.append({"path": str(path), "depth": layer.depth, "name": layer.name})
    return manifest


def flatten(archetype: str, size: tuple[int, int], *, seed: int) -> Image.Image:
    """Composite all layers into one frame — for stills and previews."""
    builder = ARCHETYPES.get(archetype, scene_open_field)
    layers = builder(size, seed=seed)
    base = layers[0].image.convert("RGBA")
    for layer in layers[1:]:
        base = Image.alpha_composite(base, layer.image)
    return base.convert("RGB")
