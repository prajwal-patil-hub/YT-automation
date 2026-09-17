# 10 — Decisions Needed Before Building

Nothing gets built until these are settled. Ordered by how much they change the design.

---

## 🔴 Blocking

### 1. Hardware
What machine will this run on?

- OS (Linux / Windows / macOS)?
- GPU and **VRAM**? (or Apple Silicon + unified memory size)
- System RAM?
- Free SSD space? (see `docs/04-hardware-tiers.md` — models + stock library want **1 TB+**)
- Is the machine always-on, or a laptop that sleeps? (This decides whether we need a
  job queue that survives sleep/wake, and whether scheduled publishing can be local.)

**Why blocking:** it determines whether Option B/C are ever on the table, and whether
we need offloading. It does **not** block Phase 1 — Option A runs on everything — but
it changes the roadmap.

### 2. Niche
What single topic will the first channel cover?

The research says the money and the policy safety are both in: **cybersecurity/privacy,
AI & tech explainers, personal finance ($15–30 RPM), business case studies, career
development.**

But the binding requirement is this: **it must be something you have real opinions
about.** Checkpoint A (script approval) is where your originality enters the system,
and you can't add original value to a topic you don't understand. Pick from the
intersection of "high RPM" and "I actually know this."

**Why blocking:** determines the visual template library, the research sources, the
tone, and the entire graphics vocabulary.

### 3. Approve the architecture
Confirm: **Option A (Curated Assembly) as the Phase 1 backbone**, with a pluggable
visual-provider interface so Option B can be added later without a rewrite.

The alternative you might reasonably prefer: you specifically *want* AI-generated
visuals because that's the appeal of the project. If so, say so — we'd go Option B
from the start, accepting a higher build cost and a GPU dependency. I'd still advise
against Option C as a backbone for the reasons in `docs/02-architecture-options.md`.

---

## 🟡 Should decide, sensible defaults available

### 4. Orchestrator
- **Default recommendation: pure Python service + Telegram bot + cron.** Fewer moving
  parts; Claude maintains the code.
- **Alternative: n8n self-hosted** if you want visual run history and click-to-edit
  workflows, or if you already know n8n and like it.

Either way the pipeline exposes the same HTTP job interface, so this is reversible.
See `docs/06-orchestration-choice.md`.

### 5. Assembly layer
- **Remotion** — React, deepest ecosystem, frame-level control. **BUSL licensed:**
  free under $1M ARR, $50/mo at $1–10M. Free at your scale but not OSS.
- **Revideo** — open source, explicitly built for automated pipelines, smaller
  learning curve, thinner community.

Default: **Remotion** if you're comfortable in React/TS; **Revideo** if the BUSL
license bothers you on principle. Both sit on FFmpeg.

### 6. Voice
Default: **Kokoro** (Apache-2.0, CPU, zero setup cost) for Phase 1, **Chatterbox**
(MIT, ~5 s cloning, emotion dial) as the Phase 2 upgrade when you want a signature voice.

**Constraint regardless of choice:** do not clone a real person's voice, and do not
present the narrator as a named AI persona. Both run into policy.

### 7. Video length and cadence
Default: **8–14 minutes, 1–3 per week.** Long-form first; add Shorts clipping later.
See `docs/05-content-format-playbook.md`.

### 8. Script quality vs. cost
Default: **Claude for research + script** (once per video, where quality is
load-bearing), **local LLM via Ollama for mechanical text** (per-beat visual prompts,
tags, slugs, title variants). Near-zero token spend, high quality where it's heard.

Alternative: fully local scripting. Cheaper and fully offline, noticeably worse scripts.

---

## 🟢 Can be deferred

9. Multi-channel support.
10. Shorts/Reels/TikTok clipping and cross-posting.
11. A/B testing thumbnails.
12. Analytics feedback loop (using YouTube Analytics to steer topic selection).
13. Local music library and automatic ducking/mood selection.
14. Option C accent clips.

---

## Things I will do before any build, once approved

1. **Verify the two YouTube policy pages directly** (blocked from this environment —
   you'll need to read them, or I read them from a different network). Everything
   depends on them.
2. **Manual end-to-end dry run:** one video, made semi-manually with the chosen tools,
   uploaded by hand. Proves the OAuth flow, the upload restrictions, the render
   settings, and — most importantly — whether you actually like the output before we
   automate producing it.
3. **Confirm licenses** for every model actually adopted (several are
   non-commercial — F5-TTS is CC-BY-NC, FLUX.1 dev needs checking).
4. **Then** write the plan, get it approved, and build Phase 1.

Step 2 is the one people skip. It is also the one that most often reveals that the
whole plan was aimed at output you don't want.
