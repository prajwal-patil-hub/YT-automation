"""Thin FFmpeg/FFprobe wrappers.

Everything here shells out; nothing parses media itself. Commands are built as
argument lists (never shell strings) so filenames with spaces and quotes are
safe.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


class FFmpegMissing(RuntimeError):
    pass


def _binary(name: str, override: str | None = None) -> str:
    if override:
        return override
    found = shutil.which(name)
    if not found:
        raise FFmpegMissing(
            f"{name} not found on PATH. Install FFmpeg, or set paths.{name} in config.toml."
        )
    return found


def run(args: list[str], *, binary: str = "ffmpeg", override: str | None = None) -> str:
    cmd = [_binary(binary, override), "-hide_banner", "-loglevel", "error", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"{binary} failed ({proc.returncode})\n"
            f"  cmd: {' '.join(cmd[:14])}{' ...' if len(cmd) > 14 else ''}\n"
            f"  err: {proc.stderr.strip()[:1500]}"
        )
    return proc.stdout


def probe_duration(path: str | Path, *, override: str | None = None) -> float:
    """Duration in seconds. Raises if the file is unreadable."""
    out = subprocess.run(
        [
            _binary("ffprobe", override), "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json", str(path),
        ],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {path}: {out.stderr.strip()[:500]}")
    try:
        return float(json.loads(out.stdout)["format"]["duration"])
    except (KeyError, ValueError, TypeError) as exc:
        raise RuntimeError(f"No duration in ffprobe output for {path}") from exc


def concat_audio(parts: list[Path], out_path: Path, *, override: str | None = None) -> Path:
    """Concatenate audio files losslessly via the concat demuxer."""
    if not parts:
        raise ValueError("concat_audio called with no parts")
    listing = out_path.with_suffix(".concat.txt")
    listing.write_text(
        "".join(f"file '{p.resolve().as_posix()}'\n" for p in parts), encoding="utf-8"
    )
    run(
        ["-y", "-f", "concat", "-safe", "0", "-i", str(listing),
         "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "1", str(out_path)],
        override=override,
    )
    listing.unlink(missing_ok=True)
    return out_path


def normalise_audio(src: Path, dst: Path, *, override: str | None = None) -> Path:
    """Resample to a single known format so concat never re-encodes oddly."""
    run(
        ["-y", "-i", str(src), "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", str(dst)],
        override=override,
    )
    return dst


def silence(duration: float, dst: Path, *, override: str | None = None) -> Path:
    run(
        ["-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono",
         "-t", f"{max(duration, 0.05):.3f}", "-c:a", "pcm_s16le", str(dst)],
        override=override,
    )
    return dst
