"""Text-to-speech providers.

Contract: `synth(text, out_path)` writes a mono 48 kHz WAV and returns the path.
Duration is measured from the file afterwards, never estimated — the assembly
timeline depends on it being exact.

Rendering happens per beat, not per video: exact per-beat durations come free,
and a bad line is a two-second re-render instead of a full one.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from . import ProviderUnavailable, register_tts
from ..util import ffmpeg


class _Base:
    name = "base"

    def __init__(self, cfg):
        self.cfg = cfg
        self.ffmpeg_bin = cfg.get("paths.ffmpeg")

    def _finalise(self, src: Path, out_path: Path) -> Path:
        """Force every provider's output into one known format."""
        if src != out_path:
            ffmpeg.normalise_audio(src, out_path, override=self.ffmpeg_bin)
            src.unlink(missing_ok=True)
        return out_path


@register_tts("kokoro")
class KokoroTTS(_Base):
    """Kokoro — 82M, Apache-2.0, faster than realtime on CPU.

    The recommended default: it is the reason the whole pipeline needs no GPU.
    Install with `pip install kokoro soundfile`.
    """
    name = "kokoro"

    def __init__(self, cfg):
        super().__init__(cfg)
        self.voice = cfg.get("voice.kokoro_voice", "af_heart")
        self.lang = cfg.get("voice.kokoro_lang", "a")
        self.speed = float(cfg.get("voice.speed", 1.0))
        self._pipeline = None

    def _load(self):
        if self._pipeline is not None:
            return self._pipeline
        try:
            from kokoro import KPipeline  # type: ignore
        except ImportError as exc:
            raise ProviderUnavailable(
                "Kokoro is not installed. Run: pip install kokoro soundfile\n"
                "  (or set voice.provider to 'piper' / 'espeak' in config.toml)"
            ) from exc
        self._pipeline = KPipeline(lang_code=self.lang)
        return self._pipeline

    def synth(self, text: str, out_path: Path) -> Path:
        import numpy as np  # noqa: F401 — kokoro pulls these in
        import soundfile as sf

        pipeline = self._load()
        chunks = [audio for _, _, audio in pipeline(text, voice=self.voice, speed=self.speed)]
        if not chunks:
            raise RuntimeError(f"Kokoro produced no audio for: {text[:80]!r}")
        import numpy as np
        raw = out_path.with_suffix(".raw.wav")
        sf.write(raw, np.concatenate(chunks), 24000)
        return self._finalise(raw, out_path)


@register_tts("piper")
class PiperTTS(_Base):
    """Piper — MIT, CPU, very fast. Good for draft renders while iterating."""
    name = "piper"

    def __init__(self, cfg):
        super().__init__(cfg)
        self.model = cfg.get("voice.piper_model")
        self.binary = cfg.get("voice.piper_binary", "piper")

    def synth(self, text: str, out_path: Path) -> Path:
        if not shutil.which(self.binary):
            raise ProviderUnavailable(
                "piper not found on PATH. Install from "
                "https://github.com/rhasspy/piper, or set voice.piper_binary."
            )
        if not self.model:
            raise ProviderUnavailable(
                "voice.piper_model is not set in config.toml (path to a .onnx voice)."
            )
        raw = out_path.with_suffix(".raw.wav")
        proc = subprocess.run(
            [self.binary, "--model", str(self.model), "--output_file", str(raw)],
            input=text, text=True, capture_output=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"piper failed: {proc.stderr.strip()[:500]}")
        return self._finalise(raw, out_path)


@register_tts("espeak")
class EspeakTTS(_Base):
    """espeak-ng — robotic, but it is everywhere and needs no model download.

    For pipeline testing only. It is audibly not good enough to publish, which
    is deliberate: it should never be mistaken for a finished render.
    """
    name = "espeak"

    def __init__(self, cfg):
        super().__init__(cfg)
        self.voice = cfg.get("voice.espeak_voice", "en-us")
        self.wpm = int(cfg.get("voice.espeak_wpm", 170))

    def synth(self, text: str, out_path: Path) -> Path:
        binary = shutil.which("espeak-ng") or shutil.which("espeak")
        if not binary:
            raise ProviderUnavailable(
                "espeak-ng not found. Install it (apt install espeak-ng / brew install espeak-ng)."
            )
        raw = out_path.with_suffix(".raw.wav")
        proc = subprocess.run(
            [binary, "-v", self.voice, "-s", str(self.wpm), "-w", str(raw), text],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"espeak-ng failed: {proc.stderr.strip()[:500]}")
        return self._finalise(raw, out_path)


@register_tts("silence")
class SilenceTTS(_Base):
    """Silent audio timed from word count. For tests and dry runs."""
    name = "silence"

    def __init__(self, cfg):
        super().__init__(cfg)
        self.wpm = float(cfg.get("voice.silence_wpm", 150))

    def synth(self, text: str, out_path: Path) -> Path:
        words = max(len(text.split()), 1)
        ffmpeg.silence(words / self.wpm * 60.0, out_path, override=self.ffmpeg_bin)
        return out_path
