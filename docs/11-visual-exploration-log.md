# 11 — Visual Exploration Log

A record of what was actually tried and what it showed, as opposed to what was
predicted. Each entry is a thing that was built and looked at.

---

## E1 — Procedural ambient grounds (kept)

Gradient + radial glow + starfield + mist + vignette, composed from a seed.

**Result: works well.** Deterministic per beat, varied across videos,
milliseconds on CPU, mean luminance 16–20/255 which is right for sleep. Not
photorealistic, so it never touches the disclosure flag.

Two bugs found by looking rather than by reasoning:
- The vignette's ellipse boundary was visible as a hard oval. Fixed by
  oversizing the ellipse 1.38× so its own edge falls outside the frame.
- `scene_card` drew text through an `ImageDraw` handle bound *before*
  `Image.composite` returned a new image, so only the drop shadow survived.

## E2 — Layered silhouettes with parallax (kept)

Scenes built as separate transparent layers (sky, far ridge, spears, camp,
near ridge, embers), each drifted at a rate proportional to its depth by an
FFmpeg filtergraph.

**Result: works, and is the strongest thing in the repo visually.** Measured
differential motion over 7 seconds: sky 0.06, mid 0.33, near 0.45 — the near
layer travels **7.5× further** than the sky. That gradient is genuine motion
parallax, not a pan across a flat picture.

Cost: ~3 s/s of output at 1080p30 on 4 CPU cores, one FFmpeg input per layer.

Shadow theatre is not an arbitrary style choice for this material — the
Mahabharata and Ramayana were performed as shadow puppetry (*tholu bommalata*)
for centuries, so silhouette against a lit ground is native to the source.

## E3 — Procedural human figures (constrained, not abandoned)

An archer drawn from primitives: arc bow with string and arrow, tapered torso,
braced stance, bent draw arm.

**Result: the read depends almost entirely on scale.** The same figure rendered
at three sizes:

| Scale | Verdict |
|---|---|
| Large (hero shot, ~50% frame height) | **Fails.** Reads as a crude pictogram. Boxy torso, stiff limbs, wrong proportions. |
| Medium (~25%) | Borderline. |
| Small (~10%, figure on a ridge) | **Works.** The eye fills in what isn't drawn. |

Three iterations were spent improving the large figure before accepting that
this is a ceiling, not a tuning problem. **Procedural primitives are good at
landscapes and bad at people.** Landscapes are noise and silhouette, which
generate well; faces and bodies are proportion and gesture, which do not.

**Design consequence, adopted:** figures stay small in a large landscape. This
is a real cinematic language, not a consolation — the lone figure against vast
ground is exactly the register calm mythology wants. `scene_lone_archer` was
rescaled from 0.30 to 0.115 and improved markedly.

**Open route, not yet tried:** hero shots need real artwork — hand-drawn or
commissioned character assets composited into procedural environments, or
generated stills. Neither was testable here: this container has **no GPU**
(4 CPU cores, 15 GB RAM, no CUDA, no torch), so local diffusion could not be
explored at all. That is a limit of the exploration environment, not a finding
about the approach.

---

## Not explored, and why

- **Rigged 2D puppets** (Iki, Inochi Creator) — ruled out by the owner.
- **Local diffusion for character art** — no GPU in this container. Needs to be
  tried on the owner's own machine.
- **Generated video** (Wan, LTX) — ruled out earlier on VRAM, continuity and
  policy grounds; see `docs/02`.
