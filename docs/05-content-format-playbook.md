# 05 — Content Format Playbook

Which video formats are *simultaneously* cheap to automate and safe under the
inauthentic-content policy. This is the intersection that matters — plenty of formats
are one or the other.

---

## The scoring dimensions

- **Automation fit** — how much of it a pipeline can do without you
- **Policy fit** — how far it sits from "generic, repetitive, template-based"
- **Visual cost** — how much the visuals need generative models
- **RPM** — revenue per 1,000 views in the niche

## The formats

| Format | Automation | Policy fit | Visual cost | Notes |
|---|---|---|---|---|
| **Explainer with original diagrams** (tech, AI, cybersecurity, science) | High | **Excellent** | **Low** — diagrams/motion graphics | The best cell in this table. Your diagrams *are* the original value. Cybersecurity/privacy and AI/tech explainers are called out as among the strongest 2026 faceless niches. |
| **Data-driven / analytical** (finance, economics, business case studies) | High | **Excellent** | **Low** — charts | Charts are original artefacts, trivially generated from data, and impossible to template-detect because the data differs every time. **Personal finance RPM is $15–30+** — the highest bracket. Business case studies also named a top-2026 niche. |
| **Documentary / history long-form** (20–40 min) | Medium | Good | Medium–High | History audiences **binge** and long-form outperforms short here. But research burden is high and RPM is only $5–12 (geographically diverse audience dilutes it). |
| **Tutorial / how-to with screen recordings** | Medium | **Excellent** | **Very low** | Screen recordings are inherently original. Automation handles script/voice/captions/assembly; you supply the recording. Career development named a strong 2026 niche. |
| **Stoicism / philosophy** | High | Medium | Medium | Named a strong niche, but it is the most saturated and most templated corner of faceless YouTube. Enter only with a distinctive angle. |
| **Listicle / compilation over stock footage** | Very high | **Bad** | Low | This is the format the policy was written to kill. Avoid. |
| **AI-footage montage with synthetic narrator** | Very high | **Worst** | Very high | Avoid entirely. Triggers AI-persona rules, disclosure rules, and slop enforcement at once. |

---

## Long-form vs. Shorts

The numbers are unambiguous:

- **Shorts RPM is 50–70% lower** than long-form in the same niche. Personal finance:
  long-form **$10–15**, Shorts **$0.05–0.30** per 1,000 views.
- But channels using Shorts grow **~41% faster** on average.

**The strategy this implies:** long-form is the revenue engine, Shorts are the
subscriber acquisition engine. Build the pipeline for **long-form first**, then add a
clipping stage that slices long-form into Shorts/Reels/TikToks. That clipping stage is
cheap — it's the same assembly code with a different aspect ratio and a shorter
timeline.

This also happens to be how scaled faceless creators actually operate: AI script
generation, AI voice, AI b-roll, and short-form clipping tools to slice long-form
into vertical distribution.

⚠️ **Do not build a Shorts-first pipeline.** It is the most automatable and the
least valuable — low RPM *and* maximum template-detection exposure.

---

## The recommended starting format

> **8–14 minute explainer or analytical video, in one niche you personally know
> something about, with original diagrams/charts as the primary visual layer, stock
> footage as a secondary texture layer, karaoke captions, and on-screen citations.**

Why this specific shape:

| Requirement | How this format satisfies it |
|---|---|
| Low effort | No video generation. Diagrams and charts are code. |
| Runs locally | Every component runs on CPU (see Tier 0). |
| Policy-safe | Original visual artefacts + real citations + genuine commentary. |
| Good RPM | Tech/finance/cyber/business are the $10–30 RPM brackets. |
| Human input at the right place | You approve/edit the script — 2 minutes, and it's where originality actually lives. |
| Extensible | Add generated stills (Option B) later without redesign. |

**The niche must be one where you have real opinions.** Not for romantic reasons —
because Checkpoint A (script approval) is where your originality enters the system,
and you can only add original value to a topic you understand. Automating a niche you
know nothing about reduces you to a rubber stamp, which is exactly the failure mode
the policy punishes.

---

## Cadence

**1–3 videos per week.** See `docs/01-youtube-policy-constraints.md` §4. Higher
cadence increases risk and reduces per-video quality, and volume is no longer the
winning strategy. Lower cadence starves the algorithm.

At 1–3/week, an overnight batch render is perfectly acceptable — which is what makes
even slow local generation viable later.

---

## Addendum — the chosen direction (2026-09-28)

The owner named three channel ideas: kids storytelling, Mahabharata episodes with
animated figures, and calm/sleep "explained" video. Research on all three, and the
decision taken:

### Kids storytelling — economics are structurally bad

The **Made for Kids** flag is a revenue cut, not a label:

- **RPM $0.50–$3**, versus $3–15 general audience — **50–80% less**. COPPA forbids
  personalized ads, so only contextual ads run.
- Also lost: Super Thanks, channel memberships, end screens, cards, **comments**,
  and the notification bell. No community, no funnel, no upsell.
- Enforcement is *stricter* for kids content; "Made-for-Kids AI storylines with no
  editorial voice are harder to defend."

Consensus recommendation for AI kids content in 2026 is to build revenue on **brand
deals, licensing (Netflix / Amazon Kids+), or off-platform subscriptions** — not the
Partner Program. That is a different business from the one this repo is designed for.

**Verdict: not first. If pursued, pursue as a licensing play.**

### Mahabharata — strong niche, one precedent worth heeding

In January 2026 YouTube removed 16 channels from YPP — **4.7 billion views,
$10M/year**. One was **Imperiodejesus (5.87M subs): serialized AI-narrated biblical
stories, multiple episodes daily.**

That is structurally what "Mahabharata episodes with animated figures" describes.
The channel was not removed for being religious or AI-made; it was removed because
AI handled every step with zero human editorial input. Survivable — but only at low
cadence with real originality. **It is not a volume play.**

Also note: faceless channels went from **12% to 38%** of new monetization ventures
since 2022, so this is a late entry; and sources **disagree sharply** on Indian
devotional CPM (₹150–350 in one, ₹40–80 in another). Do not plan on a number.

### Sleep / calm long-form — best economics of the three

| | |
|---|---|
| Sleep/healing soundscape RPM | **$10.92** |
| Wellness / sleep-app / supplement CPM | **$16–20** |
| Format | 1–8 hours, enormous watch time per viewer |
| Production cost | Low — ambient audio, simple visuals |

Roughly 4–20× the kids RPM, no character-consistency problem, and the lowest visual
demand of any format considered. Caveat: sources note sleep channels should
**compose original audio**; library music may cap the ceiling.

### Decision: merge sleep + Mahabharata

One pipeline: **calm, slow, long-form mythology, told sleep-paced.** This takes the
high-RPM, high-retention mythology audience while the sleep framing supplies the
differentiation that separates it from the Imperiodejesus pattern. Low cadence is a
feature of the format rather than a compliance compromise.

### Animation: rigged puppets, not generated video

For "animated figures", the 2026 AI-consistency stack is LoRA 0.6 + PuLID 0.8 +
ControlNet OpenPose — a GPU, ComfyUI, and characters that still drift between shots.

**Rigged 2D puppets solve consistency by construction instead.** Open-source, MIT
options: **Iki** (WebGL/TypeScript, layered PNGs wired to parameters, ships an MCP
server so an agent can build the rig), plus Inochi Creator, nijigenerate and
Ayatsuri 2D.

Why it fits a serialized mythology channel: Krishna is identical in episode 40 and
episode 1 because it is the same rig; lip-sync drives off TTS timings the pipeline
already produces; it is not photorealistic so **no disclosure flag**; it renders on
CPU; and each character is built once and amortised across every episode.

**Status: researched, not built. The `scene` provider ships first; `puppet` follows.**
