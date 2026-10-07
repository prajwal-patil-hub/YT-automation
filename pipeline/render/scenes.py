"""Scene cards for calm narrative video.

Unlike the explainer cards, these are built to be *looked past*: a soft ambient
ground, generous margins, low-contrast type, and nothing that asks to be read
quickly. Text is optional — most beats in a sleep-paced video carry none.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from .. import standards
from . import ambient
from .theme import Theme

# Named ambient palettes. A preset is a look, not a topic — the same preset
# serves any subject with the right mood.
PRESETS: dict[str, dict] = {
    "mythology": dict(top="#1C1024", bottom="#06040A", glow="#C98F35", haze=True),
    "temple":    dict(top="#1A0E12", bottom="#070406", glow="#D08A3C", haze=True),
    "ocean":     dict(top="#04161F", bottom="#01050A", glow="#1E6A88", haze=True),
    "space":     dict(top="#070C1C", bottom="#02030A", glow="#3D4C9E", stars=True),
    "archive":   dict(top="#18130E", bottom="#070605", glow="#8A6031", haze=True),
    "forest":    dict(top="#0A1710", bottom="#030705", glow="#3E7A4E", haze=True),
    "dusk":      dict(top="#1E1220", bottom="#080509", glow="#B4644C", haze=True),
}


def background(
    size: tuple[int, int], preset: str, *, seed: int,
) -> Image.Image:
    kwargs = PRESETS.get(preset, PRESETS["mythology"])
    return ambient.compose(size, seed=seed, **kwargs)


def _wrap(draw, text: str, font, max_w: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for word in words:
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def scene_card(
    path: Path, size: tuple[int, int], theme: Theme, *,
    preset: str = "mythology", seed: int = 0,
    title: str | None = None, subtitle: str | None = None,
    align: str = "centre",
) -> Path:
    """An ambient ground with optional, deliberately quiet typography."""
    img = background(size, preset, seed=seed)
    w, h = size

    if title or subtitle:
        # Text sits on its own soft shadow so it stays legible over any ground
        # without needing a hard outline, which would read as harsh.
        layer = Image.new("RGB", size, (0, 0, 0))
        mask = Image.new("L", size, 0)
        d_mask = ImageDraw.Draw(mask)
        draw = ImageDraw.Draw(img)

        m = int(w * standards.TITLE_SAFE_MARGIN)
        max_w = w - 2 * m
        title_font = theme.font("display", int(w * 0.040))
        sub_font = theme.font("body", int(w * 0.0205))

        lines = _wrap(draw, title, title_font, max_w) if title else []
        sub_lines = _wrap(draw, subtitle, sub_font, max_w) if subtitle else []
        line_h = int(title_font.size * 1.28)
        sub_h = int(sub_font.size * 1.5)
        block = len(lines) * line_h + (int(w * 0.02) + len(sub_lines) * sub_h if sub_lines else 0)
        y0 = (h - block) // 2

        def place(draw_target, lines_, font, y, fill):
            for ln in lines_:
                tw = draw_target.textlength(ln, font=font)
                x = (w - tw) / 2 if align == "centre" else m
                draw_target.text((x, y), ln, font=font, fill=fill)
                y += int(font.size * (1.28 if font is title_font else 1.5))
            return y

        # Shadow pass into the mask, then blur it.
        y = place(d_mask, lines, title_font, y0, 255)
        if sub_lines:
            place(d_mask, sub_lines, sub_font, y + int(w * 0.02), 200)
        mask = mask.filter(ImageFilter.GaussianBlur(radius=max(w // 140, 4)))
        img = Image.composite(layer, img, mask.point(lambda v: int(v * 0.75)))

        # Image.composite returns a NEW image, so the old draw handle now points
        # at a discarded object. Rebind before drawing the text itself.
        draw = ImageDraw.Draw(img)

        # Then the text itself, low contrast.
        y = place(draw, lines, title_font, y0, theme.ink)
        if sub_lines:
            place(draw, sub_lines, sub_font, y + int(w * 0.02), theme.ink_2)

    img.save(path)
    return path
