# 02 — Architecture Options

Three candidate architectures. They differ mainly in **how the visuals are made**,
because that is the expensive, slow, unreliable part. Everything else (script, voice,
captions, assembly, approval, upload) is essentially solved and near-identical across
all three.

Throughout: `[LOCAL]` = runs on your machine, no network. `[NET]` = needs internet.

---

## The pipeline stages (common to all options)

```
  ┌─ 0. TRIGGER ─────────────────────────────────────────────────┐
  │  Prompt from you (CLI / Telegram / file) or injected by      │
  │  Claude. Optionally: a topic queue in SQLite.                │
  └──────────────────────────┬───────────────────────────────────┘
                             v
  ┌─ 1. RESEARCH & ANGLE ────────────────────────────────────────┐
  │  Gather facts + citations. Decide the angle.                 │
  │  [NET] for sourcing; Claude or local LLM for synthesis.      │
  │  >> OUTPUT: research brief + source list                     │
  └──────────────────────────┬───────────────────────────────────┘
                             v
  ┌─ 2. SCRIPT ──────────────────────────────────────────────────┐
  │  Hook, beats, narration, B-roll/visual directions per beat.  │
  │  Claude (best quality) or local LLM via Ollama [LOCAL].      │
  │  >> CHECKPOINT A: you approve the script (cheap, 2 min)      │
  └──────────────────────────┬───────────────────────────────────┘
                             v
  ┌─ 3. VOICE ───────────────────────────────────────────────────┐
  │  TTS narration per beat. Kokoro / Chatterbox [LOCAL].        │
  │  >> OUTPUT: wav per beat + exact durations                   │
  └──────────────────────────┬───────────────────────────────────┘
                             v
  ┌─ 4. VISUALS ────────────── THIS IS WHERE OPTIONS DIVERGE ────┐
  │  Option A: stock + motion graphics + your own diagrams       │
  │  Option B: locally generated stills, animated (Ken Burns +)  │
  │  Option C: locally generated video clips (Wan / LTX)         │
  └──────────────────────────┬───────────────────────────────────┘
                             v
  ┌─ 5. CAPTIONS ────────────────────────────────────────────────┐
  │  WhisperX / whisper.cpp -> word-level timestamps -> .ass     │
  │  karaoke captions, burned in by FFmpeg. [LOCAL]              │
  └──────────────────────────┬───────────────────────────────────┘
                             v
  ┌─ 6. ASSEMBLE ────────────────────────────────────────────────┐
  │  Timeline from the script's beat durations. Music bed,        │
  │  ducking, transitions, lower-thirds, citations on screen.     │
  │  Remotion / Revideo / FFmpeg filtergraph. [LOCAL]            │
  └──────────────────────────┬───────────────────────────────────┘
                             v
  ┌─ 7. PACKAGE ─────────────────────────────────────────────────┐
  │  Thumbnail (3 variants), title (3 variants), description     │
  │  with sources, tags, chapters. [LOCAL] + Claude              │
  └──────────────────────────┬───────────────────────────────────┘
                             v
  ┌─ 8. TELEGRAM REVIEW ─────────────────────────────────────────┐
  │  >> CHECKPOINT B: video + thumbnails + title options sent    │
  │  to you. Buttons: Approve / Reject / Regenerate <stage>.     │
  └──────────────────────────┬───────────────────────────────────┘
                             v
  ┌─ 9. PUBLISH ─────────────────────────────────────────────────┐
  │  YouTube Data API v3 upload. Sets synthetic-content flag if  │
  │  applicable. Schedules or publishes. [NET]                   │
  └──────────────────────────────────────────────────────────────┘
```

Note the two checkpoints. **Checkpoint A (script) is the high-leverage one** — it
costs you two minutes and it is where the "real human input" that YouTube's policy
demands actually enters the system. Checkpoint B is quality control on the render.

---

## Option A — "Curated Assembly" (recommended)

**Visuals = stock footage + motion graphics + your own generated diagrams/charts,
composed programmatically.**

No local video *generation* model at all. Visuals come from:
- A **local stock library** you build once (Pexels/Pixabay bulk download, both
  permit commercial use without attribution). Cached to disk, searched locally.
- **Programmatic motion graphics** — animated text, charts, diagrams, callouts,
  maps, timelines, comparison tables, code windows. Generated from the script's data.
- **Screen recordings / archival material** where relevant, with attribution.
- Optionally a handful of locally generated *stills* for atmosphere.

| | |
|---|---|
| **Hardware** | Runs on **anything**, including CPU-only and Apple Silicon. No GPU needed except optionally for TTS/Whisper speedup. |
| **Render time** | Minutes per video. |
| **Reliability** | Very high. Deterministic. Same input → same output. |
| **Policy fit** | **Best.** Original diagrams and data-viz are exactly the "distinct educational overlays" and "creative visual curation" the policy rewards. Mostly avoids the disclosure question entirely. |
| **Effort to build** | Lowest. |
| **Weakness** | Not suited to cinematic/story content. Needs a niche where information *is* the product. Stock footage is widely reused, so it must be a base layer, not the whole layer. |

**This is the recommendation.** It is simultaneously the cheapest to build, the
cheapest to run, the most reliable, and the best-aligned with the monetization
policy. It also works today on hardware you already own, whatever that is.

---

## Option B — "Generated Stills, Animated"

**Visuals = locally generated images, animated with camera moves and compositing.**

Flux.1 / SDXL / Qwen-Image / Z-Image Turbo produce stills locally; the assembly layer
adds Ken Burns pans, parallax, 2.5D depth moves, transitions and overlays.

| | |
|---|---|
| **Hardware** | 8 GB VRAM minimum (SDXL, FLUX.1 schnell, or GGUF-quantized Qwen-Image); 12–16 GB comfortable for FLUX.1 dev. |
| **Render time** | Tens of minutes per video. Batchable overnight. |
| **Reliability** | Good. Image generation is mature and predictable; prompt→image failures are cheap to retry. |
| **Policy fit** | Good if the style is **stylised/illustrated rather than photorealistic**. Photorealistic people/places pull you into disclosure territory and template-detection risk. |
| **Effort to build** | Medium. Adds ComfyUI (or diffusers) + an API bridge + a style/consistency system. |
| **Weakness** | Visual consistency across a video takes real work (LoRAs, seeds, style locking, reference images). Illustrated slideshows are also the most template-detectable format if done lazily. |

**Verdict:** a good *additive layer on top of Option A*, not a replacement for it.
Use generated stills where a diagram won't do.

---

## Option C — "Locally Generated Video"

**Visuals = actual text-to-video / image-to-video clips from Wan 2.2, LTX-2.x, or
HunyuanVideo.**

| | |
|---|---|
| **Hardware** | Wan 2.2 **5B** runs on 6–8 GB (FP8, with offloading, ~5s 720p clips). Wan 2.2 **14B** wants **24 GB+** for good 480p/720p (GGUF quantization can squeeze 14B toward ~6 GB at 480p with quality cost). **LTX-2 official minimum is 32 GB VRAM, 48 GB+ recommended** for stable 4K. HunyuanVideo has been run on 10–12 GB with heavy optimisation. |
| **Render time** | The killer. You get **~5-second clips**. A 10-minute video needs ~120 of them, each taking minutes. Plus re-rolls for the ones that come out wrong. |
| **Reliability** | **The weak point.** Motion artefacts, prompt drift, inconsistent subjects between clips, no continuity across cuts. High re-roll rate, and re-rolls are expensive. |
| **Policy fit** | **Worst.** Photorealistic synthetic footage triggers the disclosure requirement, and AI-video-clip montages are precisely the "AI slop" aesthetic enforcement is aimed at. |
| **Effort to build** | Highest. |
| **Weakness** | Everything above. |

**Verdict: do not build this as the backbone.** Ironically the most exciting
technology here is the worst fit for the stated goals (low effort, reliable,
monetizable). Keep it as an optional generator for **short accent shots** — a
3-second atmospheric establishing clip — once the rest works. Note that LTX-2.3
is reported as 10–14× faster than Wan 2.2, so if this is ever revisited, speed
now favours LTX — but the VRAM floor is much higher.

---

## Recommended path: A now, B as a plug-in, C never as backbone

```
  Phase 1  Option A backbone, end-to-end, one niche, Telegram approval, manual upload
           -> prove the loop works and you actually like the output
  Phase 2  Add automated upload + scheduling + metadata packaging
  Phase 3  Add Option B (generated stills) as one more "visual provider"
  Phase 4  Optional: Option C for 3-second accent shots only
```

The architectural key is that **stage 4 (visuals) should be a pluggable provider
interface**. The script emits a visual *intent* per beat ("chart of X over time",
"stock: city at night", "diagram of the request flow"). A resolver picks a provider.
This way Options A/B/C are configuration, not rewrites — and you can start on
Option A today regardless of what GPU you have.
