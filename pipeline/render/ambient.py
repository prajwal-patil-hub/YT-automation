"""Procedural ambient backgrounds for calm, long-form narration.

Sleep and slow-storytelling video has an unusual visual requirement: it must
hold for an hour without ever demanding attention. That rules out both stock
montage (too busy, and reused across thousands of channels) and generated
stills (expensive, inconsistent, and photorealistic enough to trip disclosure).

Procedural gradients solve it. They are deterministic from a seed, so a beat
renders identically every time; infinitely varied, so no two videos share a
frame; and they cost milliseconds on a CPU.
"""
from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


def _hex(colour: str) -> tuple[int, int, int]:
    c = colour.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _lerp(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))  # type: ignore[return-value]


def vertical_gradient(size: tuple[int, int], top: str, bottom: str, *, curve: float = 1.0) -> Image.Image:
    """A smooth vertical ramp. `curve` > 1 keeps the dark end darker for longer."""
    w, h = size
    top_rgb, bottom_rgb = _hex(top), _hex(bottom)
    # Build one column then stretch — far faster than per-pixel over the frame.
    column = Image.new("RGB", (1, h))
    px = column.load()
    for y in range(h):
        px[0, y] = _lerp(top_rgb, bottom_rgb, (y / max(h - 1, 1)) ** curve)
    return column.resize(size, Image.BILINEAR)


def radial_glow(
    size: tuple[int, int], colour: str, *,
    centre: tuple[float, float] = (0.5, 0.34), radius: float = 0.46, strength: float = 0.22,
) -> Image.Image:
    """A soft light source, returned as an RGB layer to be screened on."""
    w, h = size
    small = (max(w // 8, 2), max(h // 8, 2))
    layer = Image.new("L", small, 0)
    draw = ImageDraw.Draw(layer)
    cx, cy = centre[0] * small[0], centre[1] * small[1]
    r = radius * max(small)
    steps = 48
    for i in range(steps, 0, -1):
        t = i / steps
        rr = r * t
        draw.ellipse([cx - rr, cy - rr, cx + rr, cy + rr],
                     fill=int(255 * strength * (1 - t) ** 2.6))
    layer = layer.resize(size, Image.BICUBIC).filter(ImageFilter.GaussianBlur(radius=max(w // 90, 2)))
    tint = Image.new("RGB", size, _hex(colour))
    return Image.composite(tint, Image.new("RGB", size, (0, 0, 0)), layer)


def starfield(size: tuple[int, int], *, seed: int, count: int = 220, colour: str = "#FFFFFF") -> Image.Image:
    rng = random.Random(seed)
    w, h = size
    layer = Image.new("RGB", size, (0, 0, 0))
    draw = ImageDraw.Draw(layer)
    base = _hex(colour)
    for _ in range(count):
        x, y = rng.uniform(0, w), rng.uniform(0, h * 0.82)
        mag = rng.random() ** 2.4               # mostly faint, a few bright
        r = 0.6 + mag * (w / 900)
        v = 0.25 + mag * 0.75
        draw.ellipse([x - r, y - r, x + r, y + r],
                     fill=tuple(int(c * v) for c in base))
    return layer.filter(ImageFilter.GaussianBlur(radius=0.4))


def mist(size: tuple[int, int], *, seed: int, colour: str = "#FFFFFF", strength: float = 0.10) -> Image.Image:
    """Slow horizontal banding — reads as haze or distant cloud."""
    rng = random.Random(seed)
    w, h = size
    small = (max(w // 24, 8), max(h // 24, 8))
    layer = Image.new("L", small, 0)
    px = layer.load()
    phases = [(rng.uniform(0, math.tau), rng.uniform(0.4, 1.7), rng.uniform(0.3, 1.0))
              for _ in range(4)]
    for y in range(small[1]):
        for x in range(small[0]):
            v = 0.0
            for phase, freq, amp in phases:
                v += amp * math.sin(phase + freq * (x / small[0] * math.tau)
                                    + 0.6 * math.sin(y / small[1] * math.pi))
            v = (v / len(phases) + 1) / 2
            px[x, y] = int(max(0.0, min(1.0, v)) * 255 * strength)
    layer = layer.resize(size, Image.BICUBIC).filter(ImageFilter.GaussianBlur(radius=max(w // 60, 3)))
    tint = Image.new("RGB", size, _hex(colour))
    return Image.composite(tint, Image.new("RGB", size, (0, 0, 0)), layer)


def vignette(image: Image.Image, *, strength: float = 0.55) -> Image.Image:
    """Darken the edges so text sits comfortably and the eye settles centrally."""
    w, h = image.size
    small = (max(w // 10, 4), max(h // 10, 4))
    mask = Image.new("L", small, 0)
    draw = ImageDraw.Draw(mask)
    steps = 40
    # Oversize the ellipse so its own boundary falls outside the frame —
    # otherwise the falloff reads as a hard oval rather than a soft edge.
    over = 1.38
    ox, oy = small[0] * (over - 1) / 2, small[1] * (over - 1) / 2
    for i in range(steps):
        t = i / steps
        inset_x = (small[0] * over) * 0.5 * t
        inset_y = (small[1] * over) * 0.5 * t
        draw.ellipse(
            [-ox + inset_x, -oy + inset_y,
             small[0] + ox - inset_x, small[1] + oy - inset_y],
            fill=int(255 * (1 - t) ** 0.7),
        )
    mask = mask.resize(image.size, Image.BICUBIC).filter(
        ImageFilter.GaussianBlur(radius=max(w // 18, 8))
    )
    dark = Image.new("RGB", image.size, (0, 0, 0))
    return Image.blend(dark, image, 1.0).point(lambda v: v) if strength <= 0 else \
        Image.composite(image, Image.blend(image, dark, strength), mask)


def compose(
    size: tuple[int, int], *, seed: int,
    top: str, bottom: str, glow: str | None = None,
    stars: bool = False, haze: bool = False,
    glow_centre: tuple[float, float] = (0.5, 0.34),
    vignette_strength: float = 0.72,
) -> Image.Image:
    """Build one ambient frame. Deterministic for a given seed."""
    img = vertical_gradient(size, top, bottom, curve=1.25)
    if stars:
        img = Image.blend(img, Image.new("RGB", size, (0, 0, 0)), 0.0)
        img = _screen(img, starfield(size, seed=seed))
    if glow:
        img = _screen(img, radial_glow(size, glow, centre=glow_centre))
    if haze:
        img = _screen(img, mist(size, seed=seed + 977))
    if vignette_strength > 0:
        img = vignette(img, strength=vignette_strength)
    return img


def _screen(base: Image.Image, layer: Image.Image) -> Image.Image:
    """Screen blend: lightens without clipping, which keeps dark scenes calm."""
    from PIL import ImageChops
    return ImageChops.screen(base, layer)
