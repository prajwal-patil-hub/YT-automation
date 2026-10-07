"""Channel profiles.

A channel is a TOML file under `channels/`. Settings resolve in three layers,
each overriding the one before:

    channels/_base.toml   →   style preset   →   channels/<name>.toml

So a new channel in a new niche is a short file naming a style and an identity,
and nothing about the niche lives in code. Jobs from every channel share one
database, which is deliberate: asset-reuse detection has to see across channels,
since running the same stock clip on three channels is exactly the repetition
that template detection looks for.
"""
from __future__ import annotations

import copy
import tomllib
from pathlib import Path
from typing import Any

from . import styles
from .config import Config, _load_env

REPO_ROOT = Path(__file__).resolve().parent.parent
CHANNELS_DIR = REPO_ROOT / "channels"
BASE_FILE = "_base.toml"


class ChannelNotFound(FileNotFoundError):
    pass


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursive dict merge. Scalars and lists from `override` win outright."""
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def available(root: Path | None = None) -> list[str]:
    d = root or CHANNELS_DIR
    if not d.exists():
        return []
    return sorted(
        p.stem for p in d.glob("*.toml") if p.name != BASE_FILE
    )


def _read(path: Path) -> dict[str, Any]:
    with path.open("rb") as fh:
        return tomllib.load(fh)


def load(name: str, *, root: Path | None = None) -> Config:
    """Resolve a channel profile into a Config."""
    repo = root or REPO_ROOT
    channels_dir = repo / "channels"
    channel_file = channels_dir / f"{name}.toml"
    if not channel_file.exists():
        found = available(channels_dir)
        raise ChannelNotFound(
            f"No channel '{name}' at {channel_file}.\n"
            f"  Available: {', '.join(found) if found else '(none yet)'}\n"
            f"  Create one with:  ./run.sh new-channel {name}"
        )

    base_file = channels_dir / BASE_FILE
    base = _read(base_file) if base_file.exists() else {}
    channel = _read(channel_file)

    style_name = channel.get("style") or base.get("style") or styles.DEFAULT_STYLE
    merged = deep_merge(base, styles.get(style_name))
    merged = deep_merge(merged, channel)
    merged["style"] = style_name
    merged.setdefault("channel", {})["slug"] = name

    _load_env(repo / ".env")
    return Config(raw=merged, root=repo)


def scaffold(name: str, *, style: str = styles.DEFAULT_STYLE,
             root: Path | None = None) -> Path:
    """Write a starter channel file. Niche-neutral on purpose."""
    repo = root or REPO_ROOT
    channels_dir = repo / "channels"
    channels_dir.mkdir(parents=True, exist_ok=True)
    path = channels_dir / f"{name}.toml"
    if path.exists():
        raise FileExistsError(f"{path} already exists")
    if style not in styles.STYLES:
        raise KeyError(f"Unknown style '{style}'. Available: {', '.join(styles.names())}")

    title = name.replace("-", " ").replace("_", " ").title()
    path.write_text(
        f'''# Channel: {name}
# Inherits channels/_base.toml, then the "{style}" style, then this file.
# The niche lives here, not in code — change it freely.

style = "{style}"

[channel]
name          = "{title}"
# What this channel is about. Used in prompts and packaging; set it when you
# decide the niche. Nothing in the pipeline depends on its value.
niche         = ""
tags          = []
category_id   = "27"        # 27 Education · 28 Science & Tech · 24 Entertainment
made_for_kids = false       # see docs/05 — this flag cuts RPM by 50-80%

[script]
# "file" while you write scripts yourself or paste them from Claude.
# "ollama" once you want them generated locally.
provider = "file"
beats    = 12

[voice]
provider = "kokoro"

# Anything from channels/_base.toml can be overridden here, e.g.:
# [video]
# motion_rate = 0.04
''',
        encoding="utf-8",
    )
    return path
