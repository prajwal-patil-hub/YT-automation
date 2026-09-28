"""Karaoke subtitle generation (.ass) and a clean .srt side-car.

Two artefacts, deliberately: styled word-highlight captions burned into the
frame, and a plain .srt to upload as a real caption track for accessibility
and search.

Timing comes from *estimation* against the known script text and the measured
beat duration. Because the words are known in advance, this is far better than
it sounds — but it still drifts within a long beat. The upgrade is forced
alignment (WhisperX against the same known text), which is why `mode` exists.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

# Longer words take longer to say. Weighting by character count tracks real
# speech much better than dividing a beat evenly across its words.
MIN_WEIGHT = 2.0


@dataclass
class Word:
    text: str
    start: float
    end: float


def _ass_time(seconds: float) -> str:
    seconds = max(seconds, 0.0)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


def _srt_time(seconds: float) -> str:
    seconds = max(seconds, 0.0)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def estimate_words(text: str, start: float, duration: float) -> list[Word]:
    """Distribute a beat's duration across its words, weighted by length."""
    tokens = text.split()
    if not tokens or duration <= 0:
        return []
    weights = [max(len(t), MIN_WEIGHT) for t in tokens]
    total = sum(weights)
    out, cursor = [], start
    for token, weight in zip(tokens, weights):
        span = duration * (weight / total)
        out.append(Word(token, cursor, cursor + span))
        cursor += span
    return out


def group_words(words: Sequence[Word], max_chars: int = 42, max_words: int = 7) -> list[list[Word]]:
    """Chunk words into on-screen lines that fit comfortably."""
    groups: list[list[Word]] = []
    current: list[Word] = []
    length = 0
    for word in words:
        added = len(word.text) + (1 if current else 0)
        if current and (length + added > max_chars or len(current) >= max_words):
            groups.append(current)
            current, length = [word], len(word.text)
        else:
            current.append(word)
            length += added
    if current:
        groups.append(current)
    return groups


def _ass_header(width: int, height: int, style: dict) -> str:
    font = style.get("font", "DejaVu Sans")
    size = style.get("size", max(36, int(height * 0.052)))
    primary = style.get("primary", "&H00FFFFFF")      # unsung / base text
    highlight = style.get("highlight", "&H00E4C049")  # sung word (BGR!)
    outline = style.get("outline", "&H00101418")
    margin_v = style.get("margin_v", int(height * 0.09))
    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Karaoke,{font},{size},{highlight},{primary},{outline},{outline},-1,0,0,0,100,100,0,0,1,{style.get('border', 4)},0,2,60,60,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def write_ass(
    path: Path,
    beats: Iterable[tuple[str, float, float]],
    *,
    width: int, height: int, style: dict | None = None,
) -> Path:
    """beats: (narration, start, duration) triples."""
    style = style or {}
    lines = [_ass_header(width, height, style)]
    for text, start, duration in beats:
        for group in group_words(estimate_words(text, start, duration)):
            if not group:
                continue
            g_start, g_end = group[0].start, group[-1].end
            parts = []
            for word in group:
                cs = max(int(round((word.end - word.start) * 100)), 1)
                parts.append(f"{{\\k{cs}}}{word.text}")
            body = " ".join(parts)
            lines.append(
                f"Dialogue: 0,{_ass_time(g_start)},{_ass_time(g_end)},Karaoke,,0,0,0,,{body}"
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_srt(path: Path, beats: Iterable[tuple[str, float, float]]) -> Path:
    """One cue per beat — the readable track, not the karaoke one."""
    chunks = []
    for i, (text, start, duration) in enumerate(beats, start=1):
        chunks.append(
            f"{i}\n{_srt_time(start)} --> {_srt_time(start + duration)}\n{text.strip()}\n"
        )
    path.write_text("\n".join(chunks), encoding="utf-8")
    return path
