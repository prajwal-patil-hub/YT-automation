# YT-automation

A local-first, human-approved YouTube video production pipeline.

**Status: RESEARCH PHASE — nothing is built yet, by design.**

This repository currently contains *research and design documents only*. No pipeline
code, no Docker stacks, no model weights. The goal of this phase is to agree on an
architecture before writing a single line of implementation.

## The target system (as stated by the owner)

1. A prompt is entered (by a human, or injected by Claude).
2. A locally-running ecosystem does everything else: research → script → voice →
   visuals → edit → captions → thumbnail → metadata.
3. The finished video is delivered to **Telegram** for review.
4. Only after an explicit human "go ahead" does it publish to YouTube.

Design priorities, in order:
1. **Runs locally / offline** where practical.
2. **Low effort per video** once set up.
3. **Survives YouTube's monetization policies** (this is the binding constraint — see below).
4. Cheap to run.

## Read in this order

| Doc | What it answers |
|---|---|
| [`docs/00-executive-summary.md`](docs/00-executive-summary.md) | The short version and the recommended path |
| [`docs/01-youtube-policy-constraints.md`](docs/01-youtube-policy-constraints.md) | **Read first.** The rules that invalidate most "AI video" tutorials |
| [`docs/02-architecture-options.md`](docs/02-architecture-options.md) | Three candidate architectures, with honest trade-offs |
| [`docs/03-local-toolchain-catalog.md`](docs/03-local-toolchain-catalog.md) | Every component, the real options, licenses, VRAM |
| [`docs/04-hardware-tiers.md`](docs/04-hardware-tiers.md) | What is actually possible on your GPU |
| [`docs/05-content-format-playbook.md`](docs/05-content-format-playbook.md) | Which video formats are cheap AND compliant |
| [`docs/06-orchestration-choice.md`](docs/06-orchestration-choice.md) | n8n vs. plain Python vs. Claude Code |
| [`docs/07-telegram-approval-loop.md`](docs/07-telegram-approval-loop.md) | The human-in-the-loop gate, and its gotchas |
| [`docs/08-publishing-and-quotas.md`](docs/08-publishing-and-quotas.md) | YouTube API limits, disclosure, metadata |
| [`docs/09-community-findings.md`](docs/09-community-findings.md) | What Reddit / X / practitioners report actually failing |
| [`docs/10-decisions-needed.md`](docs/10-decisions-needed.md) | **Open questions blocking the build** |
| [`docs/99-sources.md`](docs/99-sources.md) | All sources |

## The one-paragraph summary

Fully-automatic "prompt in, monetized video out" is technically buildable today and
almost entirely runs on local hardware. The hard part is no longer technical — it is
that YouTube's July 2025 *inauthentic content* policy specifically demonetizes
template-driven, mass-produced, low-human-input video, which is exactly what a naive
version of this pipeline produces. The design that works treats automation as a
**production assistant that removes grunt work**, with the human supplying
judgement at two or three cheap checkpoints. That is also, conveniently, the
lowest-effort design — because it lets you skip the most expensive and least reliable
component (local text-to-video generation) entirely.

## Ground rules for this repo

- **No implementation until the architecture is explicitly approved.**
- Research and design documents may be added and pushed freely.
- Anything with a cost, an API key, or an upload capability gets discussed first.
