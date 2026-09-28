"""Provider registry.

Stages never import a concrete provider. They ask the registry for one by the
name in config, which is what keeps the visuals architecture (Option A / B / C)
a configuration change rather than a rewrite.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol


class ProviderUnavailable(RuntimeError):
    """Raised when a provider's dependency or binary is missing.

    The message must say what to install — this is the error a user is most
    likely to hit on a fresh machine.
    """


@dataclass
class RenderedVisual:
    """A resolved visual plus the provenance the publish stage needs."""
    path: Path
    provider: str
    kind: str
    license: str | None = None
    source_url: str | None = None
    generated: bool = False          # produced by a generative model
    photorealistic: bool = False     # depicts real-looking people or places
    media: str = "image"             # image | video — the assembler branches on this


class TTSProvider(Protocol):
    name: str
    def synth(self, text: str, out_path: Path) -> Path: ...


class VisualProvider(Protocol):
    name: str
    def render(self, intent, out_path: Path, ctx: dict[str, Any]) -> RenderedVisual: ...


_TTS: dict[str, Callable[..., Any]] = {}
_VISUAL: dict[str, Callable[..., Any]] = {}
_SCRIPT: dict[str, Callable[..., Any]] = {}


def register_tts(name: str):
    def deco(factory):
        _TTS[name] = factory
        return factory
    return deco


def register_visual(name: str):
    def deco(factory):
        _VISUAL[name] = factory
        return factory
    return deco


def register_script(name: str):
    def deco(factory):
        _SCRIPT[name] = factory
        return factory
    return deco


def _get(table: dict, kind: str, name: str, *args, **kwargs):
    if name not in table:
        raise ProviderUnavailable(
            f"Unknown {kind} provider '{name}'. Available: {', '.join(sorted(table)) or 'none'}"
        )
    return table[name](*args, **kwargs)


def get_tts(name: str, cfg, **kw):
    from . import tts  # noqa: F401  (import registers providers)
    return _get(_TTS, "tts", name, cfg, **kw)


def get_visual(name: str, cfg, **kw):
    from . import visuals  # noqa: F401
    return _get(_VISUAL, "visual", name, cfg, **kw)


def get_script(name: str, cfg, **kw):
    from . import script  # noqa: F401
    return _get(_SCRIPT, "script", name, cfg, **kw)


def available() -> dict[str, list[str]]:
    from . import tts, visuals, script  # noqa: F401
    return {
        "tts": sorted(_TTS),
        "visual": sorted(_VISUAL),
        "script": sorted(_SCRIPT),
    }
