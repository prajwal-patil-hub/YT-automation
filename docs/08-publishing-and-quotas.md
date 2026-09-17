# 08 — Publishing, Quotas and Metadata

Good news: **this stage is a non-problem at your cadence.** Documented here so it
doesn't get rediscovered as a surprise.

---

## YouTube Data API v3 quotas

- Every Google Cloud project gets a default **10,000 units/day**, resetting at
  **midnight Pacific Time**.
- Costs: read = **1** unit, write = **50**, search = **100**, video upload = up to
  **1,600**.
- **Under the old model, 1,600 units per upload capped a project at ~6 uploads/day.**
- **Since Google's June 2026 change, uploads and searches no longer draw from the
  shared pool.** A project gets roughly **100 uploads/day** by default, and uploading
  no longer competes with reading.
- Quota increases are **free** but approval is merit- and compliance-based.

**Verdict:** at 1–3 videos/week you will use well under 1% of quota under either
model. **Do not spend any engineering effort on quota management.** Just don't put
a `search.list` call in a polling loop — search is 100 units a shot and that is the
only realistic way to burn the pool.

⚠️ The June 2026 change is reported by a secondary source; confirm against Google's
own `determine_quota_cost` documentation before relying on the 100-uploads figure.
It doesn't change any decision at your scale either way.

---

## OAuth setup

1. Google Cloud project → enable **YouTube Data API v3**.
2. OAuth consent screen. While in "Testing", add your own Google account as a test user.
3. Create an **OAuth Desktop** client → `client_secret.json`.
4. Run a one-time local auth flow → store the **refresh token**.
5. The pipeline uses the refresh token from then on; no browser needed.

Gotchas:
- Tokens for apps stuck in "Testing" can **expire after 7 days**. Either publish the
  consent screen (a self-review is sufficient for a personal single-user app) or
  expect to re-auth weekly. Publish it — weekly re-auth will break your unattended pipeline.
- A brand-new channel or API project can have upload restrictions until the channel
  is verified. Verify the channel (phone) early.
- Videos uploaded by an API project that hasn't completed audit may be **locked as
  private**. This catches people by surprise: their pipeline "works" but nothing is
  ever public. Test with a real upload early, and check the resulting privacy status.

**Do this in Phase 1, manually, before building anything** — an upload test is 20
minutes and de-risks the whole publish stage.

---

## Metadata the pipeline must produce

| Field | Source | Notes |
|---|---|---|
| Title | 3 Claude variants, you pick | ≤100 chars. Front-load the hook. |
| Description | Template + script summary + **source list** | On-screen citations should also appear here. Sources are a policy asset — they're evidence of original research. |
| Tags | Local LLM from the script | Low SEO value now, still cheap to fill. |
| Category | Config per channel | |
| Chapters | Derived from script beats — **free** | Timestamps in the description. Real UX win, zero extra work: you already have beat boundaries from TTS durations. |
| Caption track | Clean `.srt` from WhisperX, uploaded separately | Distinct from burned-in styled captions. Accessibility + SEO. |
| Thumbnail | 3 variants, you pick | ≤2 MB, 1280×720. |
| **`selfDeclaredMadeForKids`** | Config | Must be set explicitly. Get it right — it affects monetization and comments. |
| **Altered/synthetic content flag** | **Per-video, from the asset manifest** | See below. |
| Privacy / publishAt | From the approval decision | Support "approve & schedule". |

### The synthetic content flag — make it automatic

Don't leave this to human memory. Have the pipeline **derive** it from what actually
went into the video:

```
if any asset in manifest is (photorealistic AND generated)
   or narration voice is (cloned from a real person)
   or real footage was materially altered:
       set altered_or_synthetic = True
```

Since you track every asset with its provenance in SQLite anyway, this is a query, not
a judgement call. Surface the computed value in the Telegram review message so you can
see and override it.

Rationale: the disclosure requirement is enforced with a **three-strike system**
(warning → 90-day monetization suspension → permanent YPP removal). Automating this
correctly is cheap insurance. Under Option A (diagrams, charts, stock, screen
recordings) the flag will usually be `False` and legitimately so — which is one more
argument for Option A.

---

## Publishing strategy

- **Schedule, don't insta-publish.** "Approve & schedule" should be the default
  button. It gives you a window to catch a mistake, and lets you hold a consistent
  publish slot regardless of when the render finished.
- **Keep the local master.** Never let the only copy live on YouTube. Archive
  `master.mp4` + the full job record (script, assets, manifest, decisions) per video.
  You will want to re-cut, re-use, or prove provenance later.
- **Log the upload response** — video ID, status, processing details. When something
  gets flagged you want the record.
- **Don't auto-post to other platforms in Phase 1.** Each platform has its own rules
  and its own failure modes. Long-form to YouTube first; the Shorts/Reels/TikTok
  clipping stage comes after the core loop is boring and reliable.
