"""Core data shapes.

A Job owns an ordered list of Beats. A Beat is the atomic unit of the whole
pipeline: one piece of narration plus the *intent* for what should be on screen
while it plays. Providers resolve intents into Assets; the assembler lays the
resolved beats onto a timeline using the durations that TTS reports back.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Any


# Stage names, in execution order. The runner uses this list as the pipeline.
STAGES = [
    "script",
    "voice",
    "visuals",
    "captions",
    "assemble",
    "package",
    "preflight",
    "review",
    "publish",
]


@dataclass
class VisualIntent:
    """What should be on screen for a beat — never *how* to make it.

    `kind` selects a provider family; `spec` carries provider-specific detail.
    Keeping intent separate from implementation is what makes Option A / B / C
    a config change rather than a rewrite.
    """
    kind: str = "card"           # card | chart | stock | color
    spec: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_obj(obj: Any) -> "VisualIntent":
        if obj is None:
            return VisualIntent()
        if isinstance(obj, str):
            return VisualIntent(kind="card", spec={"title": obj})
        if isinstance(obj, dict):
            return VisualIntent(
                kind=obj.get("kind", "card"),
                spec={k: v for k, v in obj.items() if k != "kind"},
            )
        raise TypeError(f"Cannot read a visual intent from {type(obj).__name__}")


@dataclass
class Beat:
    index: int
    narration: str
    visual: VisualIntent = field(default_factory=VisualIntent)

    # Filled in by later stages.
    audio_path: str | None = None
    duration: float | None = None      # seconds, measured from the rendered audio
    visual_path: str | None = None
    visual_asset_id: int | None = None

    @staticmethod
    def from_obj(index: int, obj: dict[str, Any]) -> "Beat":
        narration = (obj.get("narration") or obj.get("text") or "").strip()
        if not narration:
            raise ValueError(f"Beat {index} has no narration text")
        return Beat(
            index=index,
            narration=narration,
            visual=VisualIntent.from_obj(obj.get("visual")),
            # Round-trip the fields later stages write. Without these, reloading
            # script.json silently drops durations and resolved visuals, and
            # every resume starts from a half-empty beat.
            audio_path=obj.get("audio_path"),
            duration=obj.get("duration"),
            visual_path=obj.get("visual_path"),
            visual_asset_id=obj.get("visual_asset_id"),
        )


@dataclass
class Script:
    title: str
    beats: list[Beat]
    sources: list[str] = field(default_factory=list)
    description: str = ""

    @staticmethod
    def from_obj(obj: dict[str, Any]) -> "Script":
        raw_beats = obj.get("beats") or []
        if not raw_beats:
            raise ValueError("Script has no beats")
        return Script(
            title=(obj.get("title") or "Untitled").strip(),
            beats=[Beat.from_obj(i, b) for i, b in enumerate(raw_beats)],
            sources=list(obj.get("sources") or []),
            description=(obj.get("description") or "").strip(),
        )

    @staticmethod
    def load(path) -> "Script":
        with open(path, "r", encoding="utf-8") as fh:
            return Script.from_obj(json.load(fh))

    def to_obj(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "description": self.description,
            "sources": self.sources,
            "beats": [
                {
                    "narration": b.narration,
                    "visual": {"kind": b.visual.kind, **b.visual.spec},
                    "audio_path": b.audio_path,
                    "duration": b.duration,
                    "visual_path": b.visual_path,
                    "visual_asset_id": b.visual_asset_id,
                }
                for b in self.beats
            ],
        }

    def save(self, path) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_obj(), fh, indent=2, ensure_ascii=False)

    @property
    def total_duration(self) -> float:
        return sum(b.duration or 0.0 for b in self.beats)

    @property
    def word_count(self) -> int:
        return sum(len(b.narration.split()) for b in self.beats)
