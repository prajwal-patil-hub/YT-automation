"""Card and chart rendering with Pillow.

These are the original visual artefacts the whole Option A argument rests on:
generated from the script's own data, different every video, and costing no
GPU. Every renderer returns a full-frame PNG at the configured resolution.
"""
from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any, Sequence

from PIL import Image, ImageDraw

from .theme import Theme

# Layout constants, expressed as fractions of frame width so any resolution works.
MARGIN = 0.072
RULE_W = 3


def _new_frame(size: tuple[int, int], theme: Theme) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", size, theme.bg)
    return img, ImageDraw.Draw(img)


def _wrap(draw, text: str, font, max_w: int) -> list[str]:
    """Greedy wrap measured against the real font, not a character count."""
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


def _draw_kicker(draw, x: int, y: int, text: str, theme: Theme, size: int) -> int:
    font = theme.font("mono", size)
    draw.text((x, y), text.upper(), font=font, fill=theme.ink_3)
    return y + int(size * 1.9)


def _footer(draw, size: tuple[int, int], theme: Theme, text: str | None) -> None:
    if not text:
        return
    w, h = size
    m = int(w * MARGIN)
    font = theme.font("mono", max(14, int(w * 0.0105)))
    draw.text((m, h - int(h * 0.088)), text, font=font, fill=theme.ink_3)


def title_card(
    path: Path, size: tuple[int, int], theme: Theme, *,
    title: str, kicker: str | None = None, subtitle: str | None = None,
    footer: str | None = None,
) -> Path:
    img, draw = _new_frame(size, theme)
    w, h = size
    m = int(w * MARGIN)
    max_w = w - 2 * m

    title_font = theme.font("display", int(w * 0.062))
    sub_font = theme.font("body", int(w * 0.0245))

    lines = _wrap(draw, title, title_font, max_w)
    line_h = int(title_font.size * 1.16)
    sub_lines = _wrap(draw, subtitle, sub_font, max_w) if subtitle else []
    sub_h = int(sub_font.size * 1.45)

    block_h = len(lines) * line_h + (int(w * 0.022) + len(sub_lines) * sub_h if sub_lines else 0)
    y = (h - block_h) // 2
    if kicker:
        y = max(y, int(h * 0.22))
        _draw_kicker(draw, m, y - int(w * 0.045), kicker, theme, max(14, int(w * 0.0115)))

    # Accent rule anchored to the title block — the one spot of colour.
    draw.rectangle([m, y - int(w * 0.018), m + int(w * 0.055), y - int(w * 0.018) + RULE_W],
                   fill=theme.accent)

    for ln in lines:
        draw.text((m, y), ln, font=title_font, fill=theme.ink)
        y += line_h
    if sub_lines:
        y += int(w * 0.022)
        for ln in sub_lines:
            draw.text((m, y), ln, font=sub_font, fill=theme.ink_2)
            y += sub_h

    _footer(draw, size, theme, footer)
    img.save(path)
    return path


def bullet_card(
    path: Path, size: tuple[int, int], theme: Theme, *,
    heading: str | None = None, bullets: Sequence[str] = (),
    kicker: str | None = None, footer: str | None = None,
) -> Path:
    img, draw = _new_frame(size, theme)
    w, h = size
    m = int(w * MARGIN)
    max_w = w - 2 * m

    y = int(h * 0.18)
    if kicker:
        y = _draw_kicker(draw, m, y, kicker, theme, max(14, int(w * 0.0115)))
    if heading:
        hf = theme.font("display", int(w * 0.040))
        for ln in _wrap(draw, heading, hf, max_w):
            draw.text((m, y), ln, font=hf, fill=theme.ink)
            y += int(hf.size * 1.2)
        y += int(w * 0.018)
        draw.rectangle([m, y, m + int(w * 0.055), y + RULE_W], fill=theme.accent)
        y += int(w * 0.030)

    bf = theme.font("body", int(w * 0.0235))
    gap = int(bf.size * 0.85)
    dot_r = max(3, int(w * 0.0035))
    for item in bullets:
        lines = _wrap(draw, str(item), bf, max_w - int(w * 0.035))
        cy = y + bf.size // 2
        draw.ellipse(
            [m + 2, cy - dot_r, m + 2 + dot_r * 2, cy + dot_r],
            fill=theme.accent,
        )
        for i, ln in enumerate(lines):
            draw.text((m + int(w * 0.035), y), ln, font=bf, fill=theme.ink if i == 0 else theme.ink_2)
            y += int(bf.size * 1.34)
        y += gap

    _footer(draw, size, theme, footer)
    img.save(path)
    return path


def chart_card(
    path: Path, size: tuple[int, int], theme: Theme, *,
    heading: str | None = None,
    data: Sequence[tuple[str, float]] = (),
    unit: str = "",
    colour: str | None = None,
    kicker: str | None = None,
    footer: str | None = None,
) -> Path:
    """Horizontal bar chart drawn to a single scale.

    Every bar is measured against one maximum and every bar is labelled with the
    value it reaches, so the picture and the numbers cannot disagree.
    """
    img, draw = _new_frame(size, theme)
    w, h = size
    m = int(w * MARGIN)

    y = int(h * 0.17)
    if kicker:
        y = _draw_kicker(draw, m, y, kicker, theme, max(14, int(w * 0.0115)))
    if heading:
        hf = theme.font("display", int(w * 0.037))
        for ln in _wrap(draw, heading, hf, w - 2 * m):
            draw.text((m, y), ln, font=hf, fill=theme.ink)
            y += int(hf.size * 1.2)
        y += int(w * 0.030)

    rows = [(str(k), float(v)) for k, v in data]
    if not rows:
        _footer(draw, size, theme, footer)
        img.save(path)
        return path

    label_font = theme.font("body", int(w * 0.0195))
    value_font = theme.font("mono", int(w * 0.0185))

    label_w = max(draw.textlength(k, font=label_font) for k, _ in rows)
    label_w = int(min(label_w, w * 0.26))
    value_w = int(max(draw.textlength(f"{v:g}{unit}", font=value_font) for _, v in rows)) + int(w * 0.012)

    track_x0 = m + label_w + int(w * 0.022)
    track_x1 = w - m - value_w
    track_w = max(track_x1 - track_x0, int(w * 0.1))

    peak = max(v for _, v in rows) or 1.0
    bar_h = max(10, int(w * 0.0165))
    step = int(bar_h * 2.55)
    bar_colour = theme.series_colour(colour)

    for name, value in rows:
        cy = y + bar_h // 2
        draw.text((track_x0 - int(w * 0.014) - draw.textlength(name, font=label_font), y - 2),
                  name, font=label_font, fill=theme.ink_2)
        # Recessive track, then the bar itself.
        draw.rounded_rectangle([track_x0, y, track_x1, y + bar_h],
                               radius=bar_h // 2, fill=theme.line)
        bar_w = int(track_w * (value / peak))
        if bar_w > 2:
            draw.rounded_rectangle([track_x0, y, track_x0 + bar_w, y + bar_h],
                                   radius=bar_h // 2, fill=bar_colour)
        draw.text((track_x1 + int(w * 0.010), y - 1), f"{value:g}{unit}",
                  font=value_font, fill=theme.ink)
        y += step

    _footer(draw, size, theme, footer)
    img.save(path)
    return path


def quote_card(
    path: Path, size: tuple[int, int], theme: Theme, *,
    quote: str, attribution: str | None = None, footer: str | None = None,
) -> Path:
    img, draw = _new_frame(size, theme)
    w, h = size
    m = int(w * MARGIN)
    qf = theme.font("display", int(w * 0.040))
    lines = _wrap(draw, quote, qf, w - 2 * m - int(w * 0.04))
    line_h = int(qf.size * 1.30)
    y = (h - len(lines) * line_h) // 2

    draw.rectangle([m, y - int(w * 0.005), m + RULE_W, y + len(lines) * line_h], fill=theme.accent)
    for ln in lines:
        draw.text((m + int(w * 0.028), y), ln, font=qf, fill=theme.ink)
        y += line_h
    if attribution:
        af = theme.font("mono", int(w * 0.0165))
        draw.text((m + int(w * 0.028), y + int(w * 0.014)), f"— {attribution}",
                  font=af, fill=theme.ink_3)
    _footer(draw, size, theme, footer)
    img.save(path)
    return path


def colour_card(
    path: Path, size: tuple[int, int], theme: Theme, *,
    fill: str | None = None, label: str | None = None, footer: str | None = None,
) -> Path:
    """Last-resort visual so a missing asset never hard-fails a render."""
    img, draw = _new_frame(size, theme)
    if fill:
        draw.rectangle([0, 0, size[0], size[1]], fill=fill)
    if label:
        w = size[0]
        font = theme.font("mono", int(w * 0.015))
        draw.text((int(w * MARGIN), int(size[1] * 0.5)), label, font=font, fill=theme.ink_3)
    _footer(draw, size, theme, footer)
    img.save(path)
    return path
