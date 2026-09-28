"""Script providers.

A script is a title plus an ordered list of beats, each carrying narration and
a visual *intent*. The file provider is the one to use while Claude writes the
script in a chat window; the Ollama provider is the fully-local path.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from . import ProviderUnavailable, register_script
from ..models import Script

PROMPT = """You are writing a YouTube narration script.

TOPIC: {topic}

Return ONLY valid JSON, no prose and no code fence, in this exact shape:
{{
  "title": "concise video title",
  "description": "two-sentence description",
  "sources": ["https://..."],
  "beats": [
    {{"narration": "one or two spoken sentences",
      "visual": {{"kind": "card", "title": "on-screen title", "kicker": "SECTION"}}}},
    {{"narration": "...",
      "visual": {{"kind": "bullets", "heading": "heading", "bullets": ["a", "b"]}}}},
    {{"narration": "...",
      "visual": {{"kind": "chart", "heading": "what the chart shows",
                  "data": [["label", 12], ["label", 30]], "unit": " GB"}}}}
  ]
}}

Rules:
- {beats} beats. Each narration is 2-4 sentences of natural spoken English.
- Vary the visual kinds. Do not use the same kind for more than three beats running.
- Only use "chart" when you have real numbers. Never invent figures.
- Put any factual claim's source in "sources".
"""


@register_script("file")
class FileScript:
    """Read a script JSON written by hand or pasted from Claude."""
    name = "file"

    def __init__(self, cfg):
        self.cfg = cfg

    def generate(self, topic: str, *, path: str | Path | None = None, **_: Any) -> Script:
        if not path:
            raise ProviderUnavailable(
                "The 'file' script provider needs --script PATH pointing at a script JSON."
            )
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"No script file at {p}")
        return Script.load(p)


@register_script("ollama")
class OllamaScript:
    """Fully-local scripting via Ollama's OpenAI-compatible endpoint."""
    name = "ollama"

    def __init__(self, cfg):
        self.cfg = cfg
        self.host = cfg.get("script.ollama_host", "http://localhost:11434").rstrip("/")
        self.model = cfg.get("script.ollama_model", "qwen3")
        self.beats = int(cfg.get("script.beats", 12))
        self.timeout = int(cfg.get("script.timeout", 600))

    def generate(self, topic: str, **_: Any) -> Script:
        payload = json.dumps({
            "model": self.model,
            "prompt": PROMPT.format(topic=topic, beats=self.beats),
            "stream": False,
            "format": "json",
        }).encode()
        req = urllib.request.Request(
            f"{self.host}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read())
        except urllib.error.URLError as exc:
            raise ProviderUnavailable(
                f"Cannot reach Ollama at {self.host} ({exc.reason}).\n"
                "  Start it with `ollama serve`, or set script.provider = \"file\"."
            ) from exc

        text = body.get("response", "")
        return Script.from_obj(_extract_json(text))


def _extract_json(text: str) -> dict[str, Any]:
    """Local models wrap JSON in prose or fences more often than they should."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError as exc:
            raise ValueError(f"Model did not return usable JSON: {text[:300]}") from exc
    raise ValueError(f"Model did not return JSON at all: {text[:300]}")
