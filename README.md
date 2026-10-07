# YT-automation

A local-first, human-approved YouTube video production pipeline.

**Status: Phase 2 — the local render pipeline works end to end.**

Stages 01–08 (prompt through packaging) run locally with no GPU and no paid API.
The review gate (Telegram) and publishing (YouTube API) are not built yet — the
pipeline stops at a finished `master.mp4` plus an upload payload, which is
deliberate: the human checkpoint belongs between packaging and publishing.

The research and design documents that produced this architecture are in `docs/`.

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

## Quick start

```bash
pip install -r requirements.txt          # Pillow, and nothing else

./run.sh styles                          # the visual registers available
./run.sh new-channel my-channel --style calm-narrative
./run.sh --channel my-channel doctor     # check FFmpeg, fonts, providers

./run.sh --channel my-channel new "a topic" --run \
        --script examples/script-generic.json

./run.sh --channel my-channel show 1
```

## Channels — the niche is a config file, not code

A channel is one TOML file under `channels/`. Settings resolve in three layers:

```
channels/_base.toml   →   style preset   →   channels/<name>.toml
```

So running several channels in different niches means several short files, and
nothing about any niche lives in the code. **The same script renders differently
on each channel** — a beat that names no visual kind gets whichever default its
channel declares.

| Style | Register |
|---|---|
| `explainer-dark` / `explainer-light` | Dense and information-forward. Cards and charts, karaoke captions burned in, no camera move. |
| `calm-narrative` | Slow, dark, low-contrast. Ambient grounds, gentle drift, captions off because on-screen text asks to be read. |
| `cinematic-layers` | Layered silhouettes with real parallax. The slowest register. |
| `documentary` | Footage-forward with supporting cards. Moderate pace, captions on. |

A style describes a *register*, never a subject — `calm-narrative` suits sleep
stories, slow history and meditation equally.

All channels share one database, deliberately: asset-reuse detection has to see
across channels, since running the same stock clip on three of them is exactly
the repetition that template detection looks for.

You also need **FFmpeg** on PATH, and a TTS provider. Start with
`voice.provider = "espeak"` to prove the pipeline runs, then install Kokoro
(`pip install kokoro soundfile`) for a voice you would actually publish.

### The commands

| Command | Does |
|---|---|
| `./run.sh channels` | list channels, their styles and job counts |
| `./run.sh new-channel <name> --style <style>` | scaffold a channel |
| `./run.sh styles` | list visual registers |
| `./run.sh --channel <c> new "<topic>" --run` | create a job and run it |
| `./run.sh --channel <c> run <id>` | run or **resume** — finished stages are skipped |
| `./run.sh --channel <c> redo <id> visuals` | re-run one stage and everything after it |
| `./run.sh show <id>` | stage states, asset count, disclosure flag, warnings |
| `./run.sh list --all` | recent jobs across every channel |
| `./run.sh doctor` | check the local toolchain |

`redo` is the important one. A 90%-good video should cost one stage, not a
whole re-render — which is also what the Telegram review buttons will call.

## How it fits together

```
  topic ──▶ script ──▶ voice ──▶ visuals ──▶ captions ──▶ assemble ──▶ package
             │          │          │                        │
        JSON beats   per-beat   provider                master.mp4
        narration +   WAV +     by intent               + 720p proxy
        visual intent duration    kind                  + metadata.json
```

Three properties worth knowing:

- **Every stage is resumable.** State lives in SQLite, so an interrupted run
  picks up where it stopped.
- **Visual providers are pluggable by intent kind.** A beat asks for a chart, a
  card or a stock clip; a provider resolves it. Adding generated stills later
  (Option B) means registering a provider, not rewriting the pipeline.
- **The disclosure flag is derived, not remembered.** Every asset records its
  provenance, so `altered_or_synthetic_content` is a SQL query over the
  manifest rather than something a human has to set.

## What is not built yet

| | |
|---|---|
| Telegram review gate | Next increment. Needs a bot token, a whitelisted user id, and a self-hosted Bot API server for the 50 MB cap. |
| YouTube publishing | After the gate. Do one **manual** upload first — it proves OAuth and catches uploads silently locked to private. |
| Forced-alignment captions | Timing is currently estimated from known script text, which is decent but drifts in long beats. WhisperX is the upgrade. |
| Generated stills (Option B) | The provider seam exists and is documented; nothing plugged into it. |

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
