"""Visual styles — reusable registers, deliberately independent of topic.

A style bundles the decisions that have to agree with one another: palette,
pacing, motion, caption treatment and which provider resolves an unspecified
visual. A channel picks a style and overrides what it likes, so starting a new
channel in a new niche is a config file rather than a code change.

Styles describe a *register*, never a subject. "calm-narrative" suits sleep
stories, slow history and meditation equally; nothing here knows what the
channel is about.
"""
from __future__ import annotations

from typing import Any

STYLES: dict[str, dict[str, Any]] = {
    # Dense, high-contrast, information-forward. Charts and bullet cards,
    # karaoke captions burned in, no camera move.
    "explainer-dark": {
        "video": {"motion": "none"},
        "captions": {"burn_in": True},
        "voice": {"beat_gap": 0.35, "speed": 1.0},
        "visuals": {"default_kind": "card", "preset": "space"},
        "theme": {
            "bg": "#0C1014", "surface": "#141A20", "ink": "#E6EBEF",
            "ink_2": "#91A0AB", "ink_3": "#6C7C88", "line": "#27313A",
            "accent": "#49C0E4", "good": "#46C67E", "warn": "#E0A93F", "bad": "#F07B70",
        },
    },
    "explainer-light": {
        "video": {"motion": "none"},
        "captions": {"burn_in": True, "primary": "&H00202020", "outline": "&H00F2F2F2"},
        "voice": {"beat_gap": 0.35, "speed": 1.0},
        "visuals": {"default_kind": "card", "preset": "archive"},
        "theme": {
            "bg": "#F4F5F7", "surface": "#FFFFFF", "ink": "#12181D",
            "ink_2": "#4E5A64", "ink_3": "#76838E", "line": "#D6DCE2",
            "accent": "#0B6E93", "good": "#1B7A45", "warn": "#8A5B07", "bad": "#A52F2A",
        },
    },
    # Slow, dark, low-contrast. Ambient grounds, gentle drift, captions off
    # because on-screen text asks to be read.
    "calm-narrative": {
        "video": {"motion": "drift", "motion_rate": 0.055},
        "captions": {"burn_in": False},
        "voice": {"beat_gap": 1.5, "speed": 0.92, "espeak_wpm": 118},
        "visuals": {"default_kind": "scene", "preset": "mythology"},
        "theme": {
            "bg": "#0A0810", "surface": "#120E18", "ink": "#D9DEE4",
            "ink_2": "#8D97A2", "ink_3": "#636E79", "line": "#1E232C",
            "accent": "#C98F35", "good": "#5A9E72", "warn": "#C79A4A", "bad": "#C4766C",
        },
    },
    # Layered silhouettes with real parallax. The slowest register.
    "cinematic-layers": {
        "video": {"motion": "parallax", "motion_rate": 0.05},
        "captions": {"burn_in": False},
        "voice": {"beat_gap": 1.8, "speed": 0.9, "espeak_wpm": 112},
        "visuals": {"default_kind": "layered", "archetype": "open-field"},
        "theme": {
            "bg": "#07040A", "surface": "#100B14", "ink": "#D6D2DC",
            "ink_2": "#8A8494", "ink_3": "#5F5A69", "line": "#1B1622",
            "accent": "#C07A2E", "good": "#5E9A74", "warn": "#C4954A", "bad": "#BE7066",
        },
    },
    # Footage-forward with supporting cards. Moderate pace, captions on.
    "documentary": {
        "video": {"motion": "drift", "motion_rate": 0.10},
        "captions": {"burn_in": True},
        "voice": {"beat_gap": 0.7, "speed": 0.97, "espeak_wpm": 140},
        "visuals": {"default_kind": "stock", "preset": "archive"},
        "theme": {
            "bg": "#0D0B09", "surface": "#161310", "ink": "#E8E2D9",
            "ink_2": "#9A9188", "ink_3": "#6E665E", "line": "#272220",
            "accent": "#C08A4A", "good": "#5B9A63", "warn": "#C9983F", "bad": "#C26E5E",
        },
    },
}

DEFAULT_STYLE = "explainer-dark"


def get(name: str) -> dict[str, Any]:
    if name not in STYLES:
        raise KeyError(
            f"Unknown style '{name}'. Available: {', '.join(sorted(STYLES))}"
        )
    # Return a deep copy so callers can merge into it without mutating the table.
    import copy
    return copy.deepcopy(STYLES[name])


def names() -> list[str]:
    return sorted(STYLES)
