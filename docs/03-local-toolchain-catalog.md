# 03 — Local Toolchain Catalog

Component-by-component: the real options, what they cost in hardware, and the
licensing traps. Licenses matter here because this is a **commercial** (monetized)
use case — several popular tools are non-commercial only.

---

## 1. Scriptwriting / LLM

| Option | Runs | Notes |
|---|---|---|
| **Claude (via Claude Code)** | [NET] | Best quality by a wide margin for scripts, research synthesis, titles, descriptions. This is the "Claude injects the prompt" part of your vision. |
| **Ollama + Qwen3.x** | [LOCAL] | `ollama pull`, serves an OpenAI-compatible API on `localhost:11434`, $0/token. Qwen3.6-27B needs 24 GB+; Qwen3.6-35B-A3B is the best all-rounder for 32 GB systems. |
| **Ollama + gpt-oss:20b** | [LOCAL] | Good 16 GB VRAM pick, 128K context at MXFP4. |
| **Ollama + Gemma 4 12B** | [LOCAL] | Genuinely usable on 8 GB. |

**Recommendation:** hybrid. Claude for the script and research (where quality is
load-bearing and it's once per video), local LLM for the high-volume mechanical
work — per-beat visual prompts, tag generation, filename slugs, variant titles.
This keeps token spend near zero while keeping the part the audience actually hears
at high quality.

---

## 2. Text-to-Speech (narration)

| Option | License | VRAM | Cloning | Verdict |
|---|---|---|---|---|
| **Kokoro** (82M) | Apache-2.0 | CPU-capable, faster than realtime | ❌ No | **Best default.** Tiny, fast, 54 fixed voices / 8 languages, runs on CPU. No GPU needed. |
| **Chatterbox / Chatterbox-Turbo** (0.5B) | **MIT** | Gaming GPU | ✅ ~5 s | **Best quality-with-cloning.** A blind listening study put Turbo ahead of ElevenLabs (65.3% vs 24.5% preference). Has an emotion-exaggeration dial (0.0–1.0+). |
| **XTTS (Coqui)** | check per-build | GPU | ✅ | Often named the most convincing raw clone by hands-on reviewers. Licensing varies by build — verify before commercial use. |
| **F5-TTS** | **CC-BY-NC 4.0** | GPU | ✅ | ⚠️ **Non-commercial license. Disqualified for a monetized channel.** |
| **Piper** | MIT | CPU | ❌ | Very fast, lower quality. Good for drafts/previews. |
| **Sesame CSM** | check | GPU | — | Highest open MOS reported (~4.7, vs ElevenLabs Turbo v2.5 ~4.8). The open/closed quality gap is now 0.1–0.3 MOS. |

**Recommendation:** **Kokoro** to start (zero hardware requirement, ship the pipeline),
with **Chatterbox** as the upgrade path once you want a signature voice. Avoid F5-TTS
for licensing reasons. Do **not** clone a real person's voice — see policy doc.

**Practical note:** render TTS **per script beat**, not per video. You get exact
per-beat durations for free, which the assembly stage needs, and a bad line is a
2-second re-render instead of a full re-render.

---

## 3. Captions / subtitles

| Option | Notes |
|---|---|
| **WhisperX** | Best word-level timestamp accuracy. Wraps Whisper with forced alignment. The standard choice for karaoke captions. |
| **faster-whisper** | Fast CTranslate2 backend. Great speed/quality balance. |
| **whisper.cpp** | Most portable, CPU-friendly, no Python. Karaoke `.ass` output has historically needed extra work. |

Pipeline: `audio → WhisperX → word-level JSON → .ass with karaoke timing → FFmpeg burn-in`.

Two existing reference projects worth reading rather than reinventing:
`riemensc/subtitle-whisperx` (generates ASS with karaoke timing, faster-whisper +
FFmpeg) and `hclivess/whisperer` (batch, outputs srt/vtt/ass/sub/txt/json, soft or
hardcoded burn-in).

**Important trick:** you already have the script text. Use Whisper for *alignment*
against known text, not open transcription — accuracy goes way up and proper nouns
stop getting mangled.

Also generate a clean `.srt` to upload as a real YouTube caption track (accessibility
+ SEO), separate from the burned-in styled captions.

---

## 4. Visual assets

### Stock footage (Option A base layer)
- **Pexels** — 200,000+ clips, up to 4K, Pexels License permits commercial use,
  modification and distribution **without attribution**. No account needed to download.
- **Pixabay** — Pixabay License, commercial-safe.
- **Mixkit, Coverr** — cleanest licensing terms for commercial work.

⚠️ **Everyone uses Pexels.** The popular clips circulate widely, which is both a
template-detection risk and an originality problem. Treat stock as a *base layer*,
mixed with rarer sources and your own graphics. Re-verify license terms at bulk-download
time and record the license + source URL per asset in the asset database.

### Local image generation (Option B)
| Model | License | VRAM | Strength |
|---|---|---|---|
| **FLUX.1 [dev]** (12B) | non-commercial dev license — **check carefully** | 12 GB min, 16 GB+ comfortable | Best prompt adherence + photorealism |
| **FLUX.1 [schnell]** | **Apache-2.0** | fits 8 GB | Fast, commercially safe |
| **Qwen-Image** (20B MMDiT) | **Apache-2.0** | GGUF fits 8 GB; BF16 wants a lot | **Readable text inside images** — excellent for title cards and diagrams |
| **SDXL 1.0** (3.5B) | open | 8 GB min, 12–16 GB comfortable | Deepest LoRA/style ecosystem |
| **Z-Image Turbo** (6B) | check | modest | Speed pick |
| **FLUX.2 [klein]** (4B) | check | modest | Speed pick |

**Recommendation for commercial use: Qwen-Image (Apache-2.0) and FLUX.1 schnell
(Apache-2.0).** These two are explicitly unrestricted. FLUX.1 **dev** has a
non-commercial dev license — do not build a monetized channel on it without reading
the license yourself.

### Local video generation (Option C — not recommended as backbone)
| Model | VRAM | Notes |
|---|---|---|
| **Wan 2.2 TI2V-5B** | 6–8 GB (FP8 + offloading) | ~5 s 720p clips. The realistic low-VRAM option. |
| **Wan 2.2 14B** | 24 GB+ for good 480p/720p | GGUF can push toward ~6 GB at 480p with quality loss. Native ComfyUI support, 5 built-in templates, LoRA support. |
| **LTX-2 / LTX-2.3** | **32 GB min, 48 GB+ recommended** | Reported **10–14× faster** than Wan 2.2. Open-sourced Jan 2026; 2.3 released Mar 2026. |
| **HunyuanVideo** | 10–12 GB with heavy optimisation; 720p/1080p capable | |
| **CogVideoX-1.5** | Apache-2.0, loads via HF Diffusers in a few lines | Easiest to script against. |
| **Open-Sora 2.0** | — | Most-starred open video project on GitHub. |

---

## 5. Assembly / editing

| Option | License | Verdict |
|---|---|---|
| **FFmpeg** | LGPL/GPL | The engine everything else sits on. Necessary regardless. High learning curve for animation; fine for concat, overlay, audio mix, burn-in, encode. |
| **Remotion** (React) | **BUSL** — free under $1M ARR, $50/mo at $1–10M, $200/mo above | Best-in-class for data-driven animated visuals. Uses FFmpeg underneath. Deepest ecosystem. Note the license tier — free at your scale, but it is a commercial license, not OSS. |
| **Revideo** | open source (Motion Canvas fork) | Purpose-built for *automated video pipelines*. Faster path to first rendered frame, smaller learning curve. Smaller community. |
| **MoviePy** (Python) | MIT | Easiest if you're in Python. Struggles on large files / long timelines. |
| **Motion Canvas** | open source | For hand-crafted animation, not automation. |
| **DaVinci Resolve** scripting | proprietary | ⚠️ **The Python scripting API requires Resolve *Studio* (paid).** The free version does not expose it for standalone scripts. |
| **Kdenlive** + `D-Ogi/kdenlive-api` | GPL | Interesting: a **Resolve-API-compatible** Python scripting layer for Kdenlive over D-Bus. Resolve scripts port with minimal changes. Worth watching; niche. |

**Recommendation:** **Remotion or Revideo for the animated/graphics layer, FFmpeg for
the final mux and encode.** Remotion if you want the React component model and
ecosystem depth; Revideo if you want a pipeline-first tool with less to learn.
Both are far better than hand-writing FFmpeg filtergraphs for motion graphics, and
both are far better than driving a GUI editor.

**Skip GUI editors entirely.** Resolve/Kdenlive automation means driving a desktop
app — fragile, and Resolve's API costs money. Code-first rendering is the right call
for an unattended pipeline.

---

## 6. Orchestration

Covered in depth in `docs/06-orchestration-choice.md`. Short version: **n8n for the
event/approval/state layer, Python for the media work.** ComfyUI exposes an HTTP API
in developer mode that scripts can drive unattended; `n8n-nodes-comfyui-image-to-video`
and the official ComfyUI n8n bridge template already exist if Option B/C is added later.

---

## 7. Prior art worth reading (not adopting)

| Project | Status |
|---|---|
| **MoneyPrinterTurbo** | Most popular. Short-form, stock-footage-based. Good reference for the assembly approach. |
| **MoneyPrinter** (FujiwaraChoki) | Local-first, **Ollama-first**, DB-backed generation queue. Closest in spirit to your goal. |
| **ShortGPT** | Spiritual sibling; **maintenance has stalled.** |
| **VUZA** | Free/OSS faceless video creator, AI voiceover + subtitles, includes a Pinterest video scraper. |

**Read these for their assembly code and their mistakes, do not fork them.** They are
all built for the high-volume shorts model that the July 2025 policy change made
unviable. Their architecture optimises for exactly the wrong thing.
