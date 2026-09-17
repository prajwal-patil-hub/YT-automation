# 07 — The Telegram Approval Loop

This is the part of your vision that turns a risky automation into a safe one. It is
also where a specific, annoying technical limit bites.

---

## ⚠️ The 50 MB problem (read this before designing anything)

**The standard Telegram Bot API caps bot uploads at 50 MB** (20 MB for photos).
A 10-minute 1080p video is **150 MB – 1 GB**. Your finished video *will not fit.*

Three ways out:

| Option | How | Verdict |
|---|---|---|
| **Self-hosted local Bot API server** | Run `tdlib/telegram-bot-api` in Docker. Raises the limit to **2 GB** for `sendVideo`/`sendDocument`. | **Recommended.** It's one more container, fits the local-first goal, and solves the problem permanently. |
| **Send a compressed preview** | Send a 480p/720p, lower-bitrate proxy under 50 MB for review; keep the master locally. | **Also recommended — do this regardless.** A review copy should be small and fast to load on a phone. |
| **Send a link** | Serve the file from a local HTTP server / tailnet and send a URL. | Fine if you're on the same network or a VPN; awkward on mobile data. |

**Best design: do both #1 and #2.** Send a compressed proxy by default (fast on
mobile, instant playback), with a "send master" button that uses the local Bot API
server when you actually want to scrutinise it.

---

## What the approval message should contain

A good review message lets you decide in 60 seconds, on a phone, without opening a
laptop:

```
🎬  "How TLS Actually Works"                        [job 41]
     9:12 · 1080p · 14 beats · 6 sources

     [ video proxy attached, 720p, ~18 MB ]

📝  Title options
     1. How TLS Actually Works (In 9 Minutes)
     2. The Handshake That Secures The Internet
     3. TLS, Explained Properly

🖼  [thumbnail A] [thumbnail B] [thumbnail C]

⚠️  Flags
     · beat 7 caption overlaps the chart
     · 2 stock clips reused from job 38

Buttons:
  ✅ Approve & publish    📅 Approve & schedule
  🔁 Redo visuals         🔁 Redo voice        🔁 Redo script
  ✏️  Edit title           ❌ Reject
```

Design notes:

- **Granular redo buttons matter more than approve/reject.** If your only options are
  yes and no, a 90%-good video gets rejected and you've wasted the whole render. Being
  able to say "redo visuals only" keeps the script and voice and re-renders one stage.
  This is the single highest-value feature in the review UI.
- **Surface the flags the pipeline already knows about** — asset reuse across jobs,
  caption collisions, beats where TTS duration diverged badly from the script estimate,
  low-confidence Whisper alignment. The pipeline knows these things; make it say so.
- **Thumbnail and title choice is a genuine human decision** and costs you 5 seconds.
  Always offer 3 of each; it's the highest-leverage judgement per unit of effort.
- **Reuse detection across jobs** is what keeps you out of template-detection trouble.
  Track every asset with a hash in SQLite and warn when a clip appears in consecutive videos.

---

## Implementation

### If using n8n
Telegram Send Message node → **Response Type: "Approval"** → n8n adds Approve/Reject
buttons, pauses the workflow, resumes on your tap. Then an **If** node on
`approved == true`, true branch → publish, false branch → fallback.

Since **n8n 2.6 (Jan 2026)** the AI Agent node has approval built in with Telegram as
a selectable channel. There is also a ready template: *"Create secure human-in-the-loop
approval flows with Postgres and Telegram"*.

⚠️ **Known bug to be aware of:** n8n issue
[#15492](https://github.com/n8n-io/n8n/issues/15492) — *"Telegram Human in the loop
hangs waiting for input even when input is sent."* Verify your version behaves before
relying on it. Built-in Approve/Reject is also **binary** — the granular redo buttons
above need custom inline keyboards, which means you're partly hand-rolling it anyway.
That's a point in favour of the Python approach.

### If pure Python
`python-telegram-bot` with an `InlineKeyboardMarkup` and a `CallbackQueryHandler`.
State lives in your SQLite `approvals` table keyed by `job_id`. Roughly:

```
approvals(job_id, message_id, state, decision, decided_at, notes)
```

On callback: look up `job_id`, record the decision, dispatch to the right stage.
Durable across restarts because the state is in SQLite, not in memory. ~80–120 lines
including the granular redo routing.

---

## Security

The bot is an **upload-to-your-channel trigger reachable from the internet**. Treat it that way.

- **Whitelist your own Telegram user ID.** Reject callbacks and commands from any
  other `from.id`, silently. Non-negotiable — without this, anyone who finds the bot
  can publish to your channel.
- Keep the bot token out of the repo (`.env`, gitignored). Rotate if it ever leaks.
- Have the publish step verify the approval record in the database rather than
  trusting the callback payload alone.
- Consider requiring a typed confirmation (not just a tap) for the publish action,
  so a mis-tap can't publish.
- Log every decision with a timestamp. You want an audit trail of what you approved.

---

## Second checkpoint: the script gate

Don't only review the finished video. **Review the script too** (Checkpoint A in
`docs/02-architecture-options.md`). It costs two minutes, and:

- It is where your original human input actually enters the video — the thing the
  monetization policy is measuring.
- Fixing a bad angle at the script stage costs 2 minutes. Fixing it after render
  costs a full re-render.
- Scripts are plain text — they fit in a Telegram message with no 50 MB problem.

Send the script as a message with `✅ Looks good` / `✏️ I'll edit it` / `🔁 New angle`.
If you pick edit, accept your edited text back as a reply and use it verbatim.
That reply is, literally, the human value-add that keeps the channel monetizable.
