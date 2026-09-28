"""Visual identity for rendered cards.

One place for colour and type so every card in every video looks like it came
from the same channel. Overridable from config under [theme].
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from PIL import ImageFont

# Candidate font files, in preference order, per role. First hit wins.
FONT_CANDIDATES = {
    "display": [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ],
    "body": [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ],
    "mono": [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
        "/System/Library/Fonts/Supplemental/Menlo.ttc",
        "C:/Windows/Fonts/consola.ttf",
    ],
}


class FontsUnavailable(RuntimeError):
    pass


@dataclass
class Theme:
    bg: str = "#0C1014"
    surface: str = "#141A20"
    ink: str = "#E6EBEF"
    ink_2: str = "#91A0AB"
    ink_3: str = "#6C7C88"
    line: str = "#27313A"
    accent: str = "#49C0E4"
    good: str = "#46C67E"
    warn: str = "#E0A93F"
    bad: str = "#F07B70"
    font_paths: dict[str, str] = field(default_factory=dict)

    @staticmethod
    def from_config(section: dict) -> "Theme":
        known = {f.name for f in Theme.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        kwargs = {k: v for k, v in section.items() if k in known and k != "font_paths"}
        theme = Theme(**kwargs)
        theme.font_paths = dict(section.get("font_paths") or {})
        return theme

    def font_file(self, role: str) -> str:
        override = self.font_paths.get(role)
        if override and Path(override).exists():
            return override
        for candidate in FONT_CANDIDATES.get(role, []):
            if Path(candidate).exists():
                return candidate
        raise FontsUnavailable(
            f"No font found for role '{role}'. Install DejaVu or Liberation fonts, "
            f"or set theme.font_paths.{role} in config.toml to a .ttf path."
        )

    def font(self, role: str, size: int) -> ImageFont.FreeTypeFont:
        return ImageFont.truetype(self.font_file(role), size)

    # Semantic colour lookup used by chart series, with a safe default.
    def series_colour(self, name: str | None) -> str:
        return {
            "accent": self.accent, "good": self.good,
            "warn": self.warn, "bad": self.bad,
        }.get(name or "accent", self.accent)
