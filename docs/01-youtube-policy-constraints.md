# 01 — YouTube Policy Constraints (read this first)

Every technical decision downstream is shaped by this document. If you read only one
file, read this one. Most "AI YouTube automation" content on the internet was written
before or in ignorance of these rules and is now actively misleading.

---

## 1. The Inauthentic Content policy (the big one)

On **15 July 2025**, YouTube renamed its "repetitious content" policy to
**"inauthentic content"** and expanded it. The effect: *mass-produced, templated,
low-human-input video is ineligible for monetization in the YouTube Partner Program
(YPP)*.

Reported categories of inauthentic content that cannot be monetized:

1. **Generic, repetitive, or template-based content** — videos that follow a fixed
   template with little variation, reproduced at scale, with no real author input.
2. **Off-putting or distressing content.**
3. **Content where AI personas are used to discuss topics** (i.e. a synthetic
   presenter as the channel's voice of authority).

### What this does and does not mean

| Claim | True? |
|---|---|
| "YouTube banned AI content" | **False.** AI content is allowed and monetizable. |
| "Faceless channels are demonetized" | **False as a category.** Faceless channels with original scripting, real curation and consistent style remain fully eligible. |
| "You can run 5 videos/day from one template and get paid" | **This is the thing that is now dead.** |
| "AI is fine if a human adds real value" | **This is the actual rule.** YouTube pays for AI-assisted video when a human adds genuine original value. |

### The practical test your pipeline must pass

Practitioners converging on an "originality checklist" per video:

- Original scripting (not a scraped/reworded article, not a bare LLM dump)
- Verified voiceover (checked, not blindly rendered)
- **Mixed** visual sources (not one template with swapped stock clips)
- Clear source attribution
- Significant original commentary, distinct educational overlays, or creative
  visual curation

**Design consequence:** the pipeline must produce *variation* and must have a
human-judgement checkpoint that is more than a rubber stamp. This is a feature
of the design, not a limitation of it — see `docs/02-architecture-options.md`.

---

## 2. The AI disclosure requirement

YouTube requires creators to **disclose when AI is used to meaningfully alter or
generate photorealistic content** — specifically content that:

- makes real people appear to say or do things they did not, or
- alters real footage of real events/places.

Enforcement is a **three-strike system**: warning → 90-day monetization suspension →
permanent YPP removal.

### Design consequences

- The publish step **must** set the "altered or synthetic content" flag when the
  video contains photorealistic synthetic footage or a cloned/synthetic voice
  presented as real. This needs to be a first-class field in the metadata model,
  not an afterthought.
- This is a strong argument for **non-photorealistic visual styles** (diagrams,
  motion graphics, data visualisation, illustrated/stylised imagery, screen
  recordings, archival footage with attribution). Non-photorealistic content
  largely sidesteps the disclosure question and looks more deliberate — a double win.
- Do **not** clone a real person's voice. A synthetic voice that is clearly a
  narrator, not an impersonation, is the safe zone.

---

## 3. The collateral-damage problem

Reporting through 2026 documents that YouTube's AI-slop enforcement has caught
**human creators who simply never showed their face** as collateral damage. One
creator (Doctor NOS) reported that most peers doing comparable faceless content
were getting demonetized.

**Design consequence:** compliance is not just about *being* legitimate, it is about
being *legibly* legitimate to an automated classifier. Concretely, bias the design toward:

- Visual variety within and across videos (classifiers detect template reuse)
- On-screen original artefacts — your own diagrams, charts, annotated screenshots
- Real citations shown on screen and in the description
- Genuine variation in length, structure, and pacing between uploads
- A modest upload cadence (see below)

---

## 4. Cadence and scale

The "97% never monetize" figure circulating for automation/faceless channels is
marketing-adjacent and should be treated as directional, not precise. But the
underlying direction is well-supported: volume is no longer the winning strategy,
and high-volume templated output is now an active *risk* factor.

**Design consequence:** target **1–3 genuinely good videos per week**, not 5 per day.
This radically reduces the engineering burden — it means:

- Local generation can be slow (overnight batch is fine)
- YouTube API upload quota is a non-issue (see `docs/08-publishing-and-quotas.md`)
- A human review gate per video is affordable in time
- You can spend real compute per video instead of optimising for throughput

This is the single most important realisation in this research: **the policy
constraint and the low-effort goal point in the same direction.**

---

## 5. Things that will get you killed, ranked

1. One fixed template + swapped topic, published daily.
2. Undisclosed photorealistic synthetic footage of real people/events.
3. An "AI persona" presented as an authority (a synthetic host with a name and face).
4. Reworded scraped articles as scripts.
5. Reused stock footage that thousands of other channels also use, as the *only*
   visual layer.
6. Robotic single-voice TTS with no prosody variation over a static slideshow.

---

## 6. Verification note

`support.google.com` is blocked by this environment's network egress proxy, so the
official policy pages could not be fetched directly during this research pass. The
policy content above is reconstructed from multiple independent secondary sources
(TechCrunch, AIR Media-Tech, TubeBuddy, and several creator-economy analyses) that
agree on the substance and dates.

**Action for the owner:** before build, read these two pages directly in a browser
and confirm nothing has shifted:

- YouTube channel monetization policies — https://support.google.com/youtube/answer/1311392
- Disclosing altered or synthetic content — search YouTube Help for "altered or synthetic content"

Policy is the foundation of this design; it is worth 10 minutes of primary-source
verification.
