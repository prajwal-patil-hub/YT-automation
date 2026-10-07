"""Loudness measurement and normalisation (EBU R128).

Two-pass `loudnorm` rather than one: the single-pass form works from a running
estimate and routinely lands a decibel or two off, while the two-pass form
measures the whole file first and then applies an exact, linear gain. Since the
whole point is hitting a number, the extra pass is worth it.
"""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .. import standards
from . import ffmpeg


@dataclass
class Loudness:
    integrated: float      # LUFS
    true_peak: float       # dBTP
    lra: float             # LU

    def off_target(self, target: float = standards.TARGET_LUFS) -> float:
        return self.integrated - target


def measure(path: str | Path, *, override: str | None = None) -> Loudness:
    """Measure a file with ebur128. Raises if nothing could be read."""
    proc = subprocess.run(
        [override or "ffmpeg", "-hide_banner", "-nostats",
         "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    tail = proc.stderr[-4000:]

    def grab(label: str) -> float | None:
        # The summary block prints "I: -21.0 LUFS" etc.
        m = re.findall(rf"{label}:\s*(-?\d+(?:\.\d+)?)", tail)
        return float(m[-1]) if m else None

    integrated = grab("I")
    peak = grab("Peak")
    lra = grab("LRA")
    if integrated is None:
        raise RuntimeError(f"Could not measure loudness of {path}")
    return Loudness(integrated, peak if peak is not None else 0.0,
                    lra if lra is not None else 0.0)


def _measure_for_loudnorm(path: Path, *, override: str | None = None) -> dict:
    """Pass one: loudnorm's own JSON measurement of the source."""
    proc = subprocess.run(
        [override or "ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
         "-af",
         f"loudnorm=I={standards.TARGET_LUFS}:TP={standards.TARGET_TRUE_PEAK_DB}"
         f":LRA={standards.TARGET_LRA}:print_format=json",
         "-f", "null", "-"],
        capture_output=True, text=True,
    )
    start = proc.stderr.rfind("{")
    end = proc.stderr.rfind("}")
    if start == -1 or end <= start:
        raise RuntimeError(f"loudnorm produced no measurement for {path}")
    return json.loads(proc.stderr[start:end + 1])


def normalise(src: Path, dst: Path, *, override: str | None = None) -> Loudness:
    """Normalise to the delivery target and return the achieved loudness."""
    m = _measure_for_loudnorm(src, override=override)
    af = (
        f"loudnorm=I={standards.TARGET_LUFS}"
        f":TP={standards.TARGET_TRUE_PEAK_DB}"
        f":LRA={standards.TARGET_LRA}"
        f":measured_I={m['input_i']}"
        f":measured_TP={m['input_tp']}"
        f":measured_LRA={m['input_lra']}"
        f":measured_thresh={m['input_thresh']}"
        f":offset={m['target_offset']}"
        f":linear=true:print_format=summary"
    )
    ffmpeg.run(
        ["-y", "-i", str(src), "-af", af,
         "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", str(dst)],
        override=override,
    )
    return measure(dst, override=override)
