# 04 — Hardware Tiers

**Your hardware is currently unknown to me** — it's question #1 in
`docs/10-decisions-needed.md`. This document therefore states what is achievable at
each tier, so you can locate yourself and so the design doesn't have to wait.

The headline: **Option A (the recommended architecture) works on every tier below,
including CPU-only.** Hardware only gates the *optional* generative layers.

---

## Tier 0 — CPU-only / Apple Silicon / any laptop

**Fully viable for Option A.**

| Component | Choice |
|---|---|
| LLM | Claude (network) for scripts; skip local LLM or use a small Gemma/Qwen |
| TTS | **Kokoro** — 82M params, faster than realtime on CPU |
| Captions | **whisper.cpp** or faster-whisper (small/medium models on CPU) |
| Visuals | Stock library + Remotion/Revideo motion graphics |
| Assembly | Remotion/Revideo + FFmpeg (CPU encode, or VideoToolbox on Mac) |

Render time: minutes per video. **This tier is not a compromise for Option A** — the
recommended architecture genuinely does not need a GPU. Apple Silicon is
particularly good here (fast CPU encode, unified memory, Kokoro and whisper.cpp both
run well).

## Tier 1 — 8 GB VRAM (RTX 3060 8GB / 4060 / 2070)

Everything in Tier 0, plus:
- **Local image generation:** SDXL, FLUX.1 schnell, Qwen-Image (GGUF quantized),
  SD 3.5. Enables Option B.
- **GPU-accelerated Whisper** — captions go from minutes to seconds.
- **Chatterbox TTS** for voice cloning.
- Local video gen is *technically* possible (Wan 2.2 TI2V-5B FP8 with ComfyUI
  offloading, ~5 s 720p) but slow enough to be a novelty, not a pipeline.

## Tier 2 — 12–16 GB VRAM (RTX 4070 Ti / 4080 / 3080 12GB)

Everything above, plus:
- **FLUX.1 dev** comfortably (12 GB min, 16 GB+ comfortable) — mind the license.
- Local LLM of real quality: `gpt-oss:20b` at 128K context on 16 GB.
- HunyuanVideo with heavy optimisation (10–12 GB reported).
- Batch image generation at speed — Option B becomes pleasant rather than tolerable.

**This is the sweet spot for Option A + B.** No reason to go further unless you
specifically want Option C.

## Tier 3 — 24 GB VRAM (RTX 3090 / 4090 / 5090)

- **Wan 2.2 14B** at 480p/720p — the first tier where local video gen is real.
- The RTX 4090/24 GB is widely described as the sweet spot for serious local video:
  runs essentially every model at FP8 including HunyuanVideo and Wan 14B at 720p.
- Qwen3.6-27B (17 GB, 256K context) as a local LLM.
- Still **not** enough for LTX-2 (32 GB minimum).

## Tier 4 — 32–48 GB+ (RTX 6000 Ada, A6000, multi-GPU, or rented)

- **LTX-2 / LTX-2.3** — official minimum 32 GB, 48 GB+ for stable 4K. In exchange,
  reported **10–14× faster** than Wan 2.2.
- Qwen3.6-35B-A3B local LLM (best all-rounder at 32 GB).

**Honest note:** if you ever want Option C seriously, **renting** (Vast.ai,
RunPod, Thunder Compute) is far cheaper than buying a 48 GB card, and the workload is
bursty and batchable — exactly the shape that suits rental. That does break the
"fully local" goal, but only for an optional stage. Buying a 48 GB card to make
5-second clips that the monetization policy disfavours would be the single worst
spend in this whole project.

---

## Non-GPU hardware that actually matters more than you'd think

| Thing | Why |
|---|---|
| **Disk** | A local stock library is 50–500 GB. Model weights: FLUX ~24 GB, Wan 14B tens of GB, several LLMs. Budget **1 TB+ free, SSD.** This is the most commonly underestimated requirement. |
| **RAM** | 32 GB is comfortable; 16 GB works for Option A. Model offloading (the trick that makes big models fit small VRAM) trades VRAM for **system RAM** — offloading with 16 GB RAM thrashes. |
| **CPU** | FFmpeg encode, Remotion/Revideo rendering (which is headless Chromium — genuinely CPU-hungry), and Kokoro TTS are all CPU work. More cores = shorter renders in Option A. |
| **Upload bandwidth** | A 10-minute 1080p upload is ~200 MB–1 GB. Trivial unless your connection is slow. |

---

## What I'd tell you to do with each tier

- **CPU-only / Apple Silicon** → Build Option A. Don't buy anything yet. Ship videos,
  then decide if you actually miss generated visuals.
- **8–16 GB** → Build Option A. Add Option B when A is boring. You have everything you need.
- **24 GB** → Same. You additionally have the option of accent clips via Wan 14B later.
- **32 GB+** → Same. You have every option; use restraint anyway — the policy
  rewards diagrams over AI footage.

In all four cases the first build is identical. **This is why the build doesn't need to
wait on your hardware answer** — but the answer does determine what Phase 3 looks
like, and whether any purchase is worth considering.
