# 00 — Executive Summary

## The finding that reframes the project

You asked for the easiest, lowest-effort way to run a local YouTube video factory.
The research turned up something more useful than a tool list: **the low-effort path
and the policy-safe path are the same path, and it is not the path the tutorials sell.**

On 15 July 2025, YouTube renamed its "repetitious content" policy to **"inauthentic
content"** and made mass-produced, templated, low-human-input video **ineligible for
monetization**. That is a precise description of what a naive "prompt → video → upload"
pipeline produces. The tutorials, GitHub projects and Gumroad packages that dominate
search results for this topic were built for the previous era; the two most popular
open-source projects in this space (ShortGPT, MoneyPrinterTurbo) are architected for
exactly the throughput model that is now a liability, and ShortGPT's maintenance has stalled.

The upside: because volume is no longer the goal, **you don't need the hard parts.**

## What you don't need

| Thing you might have assumed | Verdict |
|---|---|
| A big GPU | **Not needed.** The recommended architecture runs on CPU-only or Apple Silicon. |
| Local text-to-video (Wan / LTX / Hunyuan) | **Skip it.** 5-second clips, high re-roll rate, no continuity, 24–48 GB VRAM for the good models — and it produces exactly the aesthetic enforcement is aimed at. LTX-2's own minimum is **32 GB VRAM**. |
| ComfyUI, on day one | **Defer it.** Its steep learning curve is the most-cited practical complaint in the community. Phase 3, not Phase 1. |
| n8n | **Optional.** Its one great feature here is durable Telegram approval — worth ~80 lines of Python. Use it if you like it; don't install it to feel productive. |
| High upload volume | **Actively harmful now.** Target 1–3/week. |
| Quota engineering | **Non-problem.** You'll use <1% of the YouTube API quota. |

## What you do need

> **Script → local TTS → original diagrams & charts + stock footage → karaoke captions
> → programmatic assembly → Telegram review → YouTube.**

Every stage runs locally. Two human checkpoints, both cheap:

- **Checkpoint A — the script (2 minutes).** The highest-leverage moment in the whole
  system. This is where your original human input actually enters the video, which is
  precisely what the monetization policy measures. It is also where fixing a bad angle
  costs 2 minutes instead of a full re-render.
- **Checkpoint B — the finished video in Telegram.** Approve, schedule, or redo *one
  stage* — granular redo buttons matter far more than a binary approve/reject, because
  a 90%-good video shouldn't cost you the whole render.

## The recommended stack

| Stage | Choice | Why |
|---|---|---|
| Research + script | **Claude** (once per video) | Quality is load-bearing and audible. This is the "Claude injects the prompt" part of your vision. |
| Mechanical text (visual prompts, tags, titles) | **Ollama + local LLM** | High volume, low stakes, zero cost. |
| Voice | **Kokoro** (Apache-2.0, 82M, CPU, faster than realtime) → **Chatterbox** (MIT, cloning, emotion dial) later | No GPU needed to start. ⚠️ Avoid **F5-TTS** — CC-BY-NC, illegal for a monetized channel. |
| Visuals | **Your own diagrams/charts** + local stock library (Pexels/Pixabay, commercial-safe, no attribution) | Original visual artefacts are the policy's definition of added value. Also the cheapest thing in this table. |
| Captions | **WhisperX** → word-level `.ass` karaoke → FFmpeg burn-in | Align against your *known* script text, not open transcription — accuracy jumps. |
| Assembly | **Remotion** or **Revideo**, on FFmpeg | Remotion for ecosystem depth (BUSL, free under $1M ARR); Revideo is OSS and purpose-built for automated pipelines. |
| Approval | **Telegram bot** | ⚠️ Standard Bot API caps uploads at **50 MB**. Self-host `tdlib/telegram-bot-api` for 2 GB, *and* send a compressed proxy. |
| Orchestration | **Python service + cron**, n8n optional later | Submit-and-callback HTTP interface so either works. |
| Publish | **YouTube Data API v3** | Auto-derive the synthetic-content disclosure flag from the asset manifest. Three-strike enforcement makes this cheap insurance. |

## Format and niche

**8–14 minute explainer or analytical video, long-form first.**

The money and the policy safety coincide: **cybersecurity/privacy, AI & tech
explainers, personal finance (RPM $15–30+, the top bracket), business case studies,
career development.** History/documentary is $5–12 RPM and research-heavy.

Shorts RPM is **50–70% lower** than long-form, but Shorts-using channels grow **~41%
faster** — so long-form is the revenue engine and Shorts are the acquisition engine.
Build long-form first, add a clipping stage later. **Do not build a Shorts-first
pipeline**: lowest value, highest template-detection exposure.

One non-negotiable: **pick a niche you have real opinions about.** Checkpoint A only
adds value if you can actually judge the script. Automating a topic you don't
understand reduces you to a rubber stamp — the exact failure mode the policy punishes.

## The plan

```
Phase 0  ✅ Research (this repo)
Phase 1  ⬜ Manual dry run — make ONE video semi-manually, upload by hand.
            Proves the OAuth flow, the upload restrictions, the render settings,
            and whether you actually like the output. This is the step people skip.
Phase 2  ⬜ Automate the loop: pipeline service, Telegram approval, auto-upload
Phase 3  ⬜ Add generated stills (ComfyUI + Qwen-Image / FLUX.1 schnell — both Apache-2.0)
Phase 4  ⬜ Optional: Shorts clipping; 3-second AI accent clips
```

## Two honest caveats

1. **`support.google.com` is blocked by this environment's egress proxy.** The policy
   details throughout are reconstructed from multiple agreeing secondary sources
   (TechCrunch, TubeBuddy, AIR Media-Tech and others). Since the entire design rests on
   them, **read the two official pages yourself** — listed in
   `docs/01-youtube-policy-constraints.md` §6. Ten minutes, well spent.
2. **You asked for Reddit and X specifically.** Search here surfaced aggregated and
   secondary coverage well but very little raw thread or post content — most queries
   resolved to blogs, vendor pages and Gumroad listings. The community findings in
   `docs/09-community-findings.md` are directional, not quoted, and labelled as such.
   An hour of your own reading in `r/n8n`, `r/comfyui`, `r/NewTubers` and
   `r/PartneredYoutube` would be the highest-value addition; paste anything surprising
   back and I'll fold it in.

## Next step

**Nothing gets built yet.** `docs/10-decisions-needed.md` lists what's blocking:
your hardware, your niche, and your sign-off on the architecture. Three answers and
we can write the build plan.
