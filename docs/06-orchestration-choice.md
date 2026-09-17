# 06 — Orchestration: n8n vs. Python vs. Claude Code

You asked specifically whether to run n8n locally. Short answer: **yes, but for less
than you'd expect.** n8n should own the *event and approval* layer, not the media work.

---

## What each tool is actually good at

### n8n (self-hosted)
**Strengths for this project**
- **Human-in-the-loop is built in.** The Telegram Send Message node has a Response
  Type of "Approval" that adds Approve/Reject buttons, pauses the workflow, and
  resumes on your tap. Since **n8n 2.6 (Jan 2026)** approval is built into the AI
  Agent node itself, with Telegram/Slack/Gmail/Chat as channels. **This is the single
  best reason to use n8n here** — you would otherwise hand-roll a bot with persistent
  state.
- Durable pause/resume across restarts. A workflow waiting on your approval for
  8 hours is a normal thing, not a hack.
- Cron/webhook triggers, retries, credential storage, visible run history.
- Self-hosting is its strongest governance story — credentials and data stay local.

**Weaknesses**
- **Long-running jobs are awkward.** Video rendering takes minutes to hours.
  You must tune `EXECUTIONS_TIMEOUT`, and there are known issues with the env var not
  being picked up in some Docker setups. Default worker graceful-shutdown timeout is
  **30 seconds**.
- Heavy work needs **queue mode** (main process → Redis → stateless workers). For
  heavy jobs set `WORKER_CONCURRENCY=2`; n8n's general advice of concurrency ≥5 is
  for light jobs and is wrong for video. Single-instance n8n chokes under concurrency.
- Doing media manipulation *inside* n8n nodes is genuinely miserable. Binary data
  handling, no real debugger, and FFmpeg-in-a-node is a known pain point.

### Python (or Node) scripts
- The right place for **all** media work: TTS, Whisper, FFmpeg, Remotion/Revideo
  invocation, ComfyUI API calls, asset management, the timeline model.
- Testable, debuggable, version-controlled, diffable. Renders are reproducible.
- No opinion about scheduling or approval — which is fine, because n8n has those.

### Claude Code
- **Not a workflow runtime.** It is an agentic coding system. It does not replace an
  orchestration layer for recurring event-driven jobs. Industry comparisons land on:
  Claude Code wins for software-development automation, n8n wins for recurring
  business-process automation.
- **Where it genuinely belongs in your design:**
  1. **Building and maintaining the pipeline** (this repo).
  2. **The research + script stage**, invoked per video. This is the "Claude injects
     the prompt for me" part of your vision — Claude does the research, picks the
     angle, writes the script with visual directions, and hands a structured brief to
     the local pipeline.
  3. Ad-hoc debugging when a render goes wrong.
- It should **not** be the thing that runs every Tuesday at 6am. That's n8n's job.

---

## Recommended split

```
 ┌──────────────────────────────────────────────────────────────────────┐
 │ n8n  (self-hosted, Docker, queue mode)                               │
 │  · cron / webhook / Telegram command triggers                        │
 │  · calls the pipeline over HTTP, does NOT do media work               │
 │  · owns the Telegram approval gates (its best feature)               │
 │  · owns retries, run history, credentials                            │
 │  · calls the publish step after approval                             │
 └───────────────┬──────────────────────────────────────────────────────┘
                 │ HTTP  (job submit → job id; poll or webhook callback)
                 v
 ┌──────────────────────────────────────────────────────────────────────┐
 │ pipeline service  (Python, FastAPI, local)                           │
 │  · POST /jobs  -> returns job_id immediately, works async            │
 │  · stages: research, script, tts, visuals, captions, assemble, pack  │
 │  · SQLite: jobs, beats, assets (+license+source), renders, approvals │
 │  · every stage resumable and independently re-runnable               │
 │  · calls out to: Claude, Ollama, Kokoro, WhisperX, Remotion, FFmpeg, │
 │    (later) ComfyUI                                                    │
 └──────────────────────────────────────────────────────────────────────┘
```

**The critical interface rule:** n8n **never** waits synchronously for a render.
It submits a job, gets a `job_id` back in under a second, and the pipeline calls an
n8n webhook when the stage finishes. This sidesteps every n8n timeout problem in one
design decision. Practitioner lessons-learned from n8n+ComfyUI pipelines say the same
thing: **design each part to restart clean if it crashes, and log every step.**

---

## The honest alternative: skip n8n entirely

A single Python service + `python-telegram-bot` + `cron`/`systemd` timers does
everything described above in maybe 400 lines. No Docker Compose, no Redis, no
timeout tuning, no queue mode.

| | n8n | Pure Python |
|---|---|---|
| Approval gate | Built in, reliable, durable | ~80 lines + a state table |
| Scheduling | Built in | cron / systemd timer |
| Run history & retries | Built in, visual | You build it |
| Debugging media code | Painful | Native |
| Moving parts | n8n + Redis + Postgres + workers | One process + SQLite |
| Modifying a workflow | Click in a UI | Edit code (Claude does this well) |
| Learning curve | Real | You already have Claude for the code |

**My recommendation:** **start pure Python.** Add n8n in Phase 2 *only if* you find
yourself wanting the visual run history and the click-to-edit workflow. Rationale:
you asked for *easier options and less effort*, and with Claude writing and
maintaining the code, n8n's main advantage (no-code editing) is worth much less to
you than it is to a non-programmer. Its durable-approval feature is nice, but it is
genuinely ~80 lines to replicate.

Keep the HTTP-job interface above either way. That way n8n can be bolted on later
without touching the pipeline — and if you already know and like n8n, start with it;
the split is the same.

## If you do run n8n — concrete settings

```
Deployment      Docker Compose, queue mode (main + Redis + 1–2 workers)
Database        Postgres (SQLite is not appropriate for queue mode)
EXECUTIONS_TIMEOUT   set high (hours) — and verify it is actually applied
WORKER_CONCURRENCY   2   (heavy jobs; ignore the "≥5" default advice)
Graceful shutdown    raise well above the 30 s default
Pattern         submit-and-callback only; no long synchronous HTTP nodes
```
