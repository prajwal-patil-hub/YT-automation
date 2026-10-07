"""Stage 07 — preflight.

Objective, niche-agnostic checks on the finished deliverable, run before any
human sees it. The point is to spend the human checkpoint on judgement —
is this interesting, is the angle right — rather than on noticing that the
audio is 7 dB quiet or that a caption sits under the progress bar.

Every check here is measurable and has a defensible threshold in
pipeline/standards.py. Nothing here has an opinion about the subject.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageFilter

from .. import standards
from ..util import ffmpeg, loudness

PASS, WARN, FAIL = "pass", "warn", "fail"


@dataclass
class Check:
    name: str
    status: str
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status != FAIL


@dataclass
class Report:
    checks: list[Check] = field(default_factory=list)

    def add(self, name: str, status: str, detail: str = "") -> None:
        self.checks.append(Check(name, status, detail))

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if c.status == FAIL]

    @property
    def warnings(self) -> list[Check]:
        return [c for c in self.checks if c.status == WARN]

    def to_obj(self) -> dict:
        return {
            "passed": not self.failures,
            "counts": {
                "pass": sum(1 for c in self.checks if c.status == PASS),
                "warn": len(self.warnings),
                "fail": len(self.failures),
            },
            "checks": [{"name": c.name, "status": c.status, "detail": c.detail}
                       for c in self.checks],
        }


def _high_contrast_bbox(path: Path, downscale: int = 4) -> tuple[int, int, int, int] | None:
    """Bounding box of locally high-contrast content — i.e. text and hard edges.

    A smooth gradient has almost no local contrast, so an ambient background
    does not trip this; rendered type does. That lets one check cover both
    card-based and scene-based visuals without knowing which it is looking at.
    """
    with Image.open(path) as im:
        img = im.convert("L")
        if downscale > 1:
            img = img.resize((img.width // downscale, img.height // downscale),
                             Image.BILINEAR)
        blurred = img.filter(ImageFilter.GaussianBlur(radius=3))
        from PIL import ImageChops
        edges = ImageChops.difference(img, blurred)
        mask = edges.point(lambda v: 255 if v > 28 else 0)
        box = mask.getbbox()
        if box is None:
            return None
        return tuple(c * downscale for c in box)  # type: ignore[return-value]


def _check_video(ctx, report: Report) -> float:
    master = ctx.master_path
    if not master.exists():
        report.add("master exists", FAIL, f"no file at {master}")
        return 0.0

    duration = ffmpeg.probe_duration(master, override=ctx.ffprobe)
    report.add("master exists", PASS, f"{duration:.1f}s, {master.stat().st_size / 1e6:.1f} MB")

    import subprocess
    out = subprocess.run(
        [ctx.ffprobe or "ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,r_frame_rate", "-of", "json", str(master)],
        capture_output=True, text=True,
    )
    try:
        st = json.loads(out.stdout)["streams"][0]
        w, h = int(st["width"]), int(st["height"])
        num, den = (int(x) for x in st["r_frame_rate"].split("/"))
        fps = num / den if den else 0
    except (KeyError, ValueError, IndexError):
        report.add("video stream", FAIL, "could not read the video stream")
        return duration

    want_w = int(ctx.cfg.get("video.width", 1920))
    want_h = int(ctx.cfg.get("video.height", 1080))
    want_fps = int(ctx.cfg.get("video.fps", 30))
    if (w, h) == (want_w, want_h):
        report.add("resolution", PASS, f"{w}x{h}")
    else:
        report.add("resolution", FAIL, f"{w}x{h}, expected {want_w}x{want_h}")
    if abs(fps - want_fps) < 0.5:
        report.add("frame rate", PASS, f"{fps:.2f} fps")
    else:
        report.add("frame rate", WARN, f"{fps:.2f} fps, expected {want_fps}")
    return duration


def _check_audio(ctx, report: Report) -> None:
    try:
        measured = loudness.measure(ctx.master_path, override=ctx.ffprobe_bin_for_measure)
    except RuntimeError as exc:
        report.add("loudness", WARN, f"could not measure: {exc}")
        return

    off = measured.off_target()
    detail = (f"{measured.integrated:.1f} LUFS "
              f"(target {standards.TARGET_LUFS}, off by {off:+.1f} LU)")
    if abs(off) <= standards.LUFS_TOLERANCE:
        report.add("loudness", PASS, detail)
    else:
        # Too quiet is the common and costly direction: YouTube never boosts.
        report.add("loudness", FAIL, detail + " — YouTube does not boost quiet audio")

    if measured.true_peak <= standards.TARGET_TRUE_PEAK_DB + 0.2:
        report.add("true peak", PASS, f"{measured.true_peak:.1f} dBTP")
    else:
        report.add("true peak", FAIL,
                   f"{measured.true_peak:.1f} dBTP exceeds {standards.TARGET_TRUE_PEAK_DB}")


def _check_pacing(ctx, report: Report) -> None:
    beats = ctx.script.beats
    missing = [b.index for b in beats if not b.audio_path or not b.visual_path]
    if missing:
        report.add("beats complete", FAIL, f"beats missing audio or visual: {missing}")
    else:
        report.add("beats complete", PASS, f"{len(beats)} beats")

    long_beats = [(b.index, b.duration) for b in beats
                  if (b.duration or 0) > standards.MAX_STATIC_SECONDS]
    if long_beats:
        report.add("beat length", WARN,
                   "beats hold one visual too long: " +
                   ", ".join(f"#{i} {d:.0f}s" for i, d in long_beats))
    else:
        report.add("beat length", PASS,
                   f"longest {max((b.duration or 0) for b in beats):.0f}s "
                   f"(limit {standards.MAX_STATIC_SECONDS:.0f}s)")

    short = [b.index for b in beats if 0 < (b.duration or 0) < standards.MIN_BEAT_SECONDS]
    if short:
        report.add("beat fragments", WARN,
                   f"beats shorter than {standards.MIN_BEAT_SECONDS}s: {short}")
    else:
        report.add("beat fragments", PASS)

    if beats:
        hook = beats[0].duration or 0
        if hook > standards.MAX_HOOK_SECONDS:
            report.add("hook length", WARN,
                       f"opening beat runs {hook:.0f}s "
                       f"(over {standards.MAX_HOOK_SECONDS:.0f}s is usually throat-clearing)")
        else:
            report.add("hook length", PASS, f"{hook:.1f}s")


# The bbox is measured on a downscaled copy, so it is quantised to the
# downscale factor, and glyph antialiasing bleeds a pixel or two beyond the
# drawn edge. Text placed exactly on the margin must not read as a violation.
SAFE_AREA_TOLERANCE_PX = 12


def _check_safe_areas(ctx, report: Report) -> None:
    w = int(ctx.cfg.get("video.width", 1920))
    h = int(ctx.cfg.get("video.height", 1080))
    left, top, right, bottom = standards.safe_box(w, h)
    tol = SAFE_AREA_TOLERANCE_PX

    offenders = []
    for beat in ctx.script.beats:
        if not beat.visual_path:
            continue
        path = Path(beat.visual_path)
        if path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
            continue
        try:
            box = _high_contrast_bbox(path)
        except OSError:
            continue
        if box is None:
            continue
        bx0, by0, bx1, by1 = box
        if (bx0 < left - tol or by0 < top - tol
                or bx1 > right + tol or by1 > bottom + tol):
            offenders.append(beat.index)

    if offenders:
        report.add("title-safe area", WARN,
                   f"high-contrast content outside the safe box on beats {offenders[:8]}"
                   + (" …" if len(offenders) > 8 else ""))
    else:
        report.add("title-safe area", PASS,
                   f"all content inside {int(standards.TITLE_SAFE_MARGIN * 100)}% margins")


def _check_captions(ctx, report: Report, duration: float) -> None:
    if not ctx.srt_path.exists():
        report.add("caption track", FAIL, "no .srt was written")
        return
    text = ctx.srt_path.read_text(encoding="utf-8")
    cues = text.strip().split("\n\n")
    if not cues or not cues[0].strip():
        report.add("caption track", FAIL, "the .srt is empty")
        return

    import re
    stamps = re.findall(r"(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->", text)
    if stamps:
        hh, mm, ss, ms = (int(x) for x in stamps[-1])
        last = hh * 3600 + mm * 60 + ss + ms / 1000
        drift = duration - last
        if drift < -1.0:
            report.add("caption sync", FAIL,
                       f"captions run {abs(drift):.1f}s past the end of the video")
        elif drift > max(15.0, duration * 0.15):
            report.add("caption sync", WARN,
                       f"captions stop {drift:.0f}s before the end")
        else:
            report.add("caption sync", PASS, f"{len(cues)} cues, ends {drift:.1f}s before")
    report.add("caption track", PASS, f"{len(cues)} cues in {ctx.srt_path.name}")


def _check_metadata(ctx, report: Report) -> None:
    if not ctx.metadata_path.exists():
        report.add("metadata", FAIL, "metadata.json was not written")
        return
    meta = json.loads(ctx.metadata_path.read_text(encoding="utf-8"))

    title = meta.get("title", "")
    if len(title) > standards.TITLE_MAX_CHARS:
        report.add("title length", FAIL,
                   f"{len(title)} chars exceeds YouTube's {standards.TITLE_MAX_CHARS}")
    elif len(title) > standards.TITLE_IDEAL_CHARS:
        report.add("title length", WARN,
                   f"{len(title)} chars — mobile search truncates past "
                   f"{standards.TITLE_IDEAL_CHARS}")
    else:
        report.add("title length", PASS, f"{len(title)} chars")

    desc = meta.get("description", "")
    report.add("description length",
               FAIL if len(desc) > standards.DESCRIPTION_MAX_CHARS else PASS,
               f"{len(desc)} chars")

    tag_chars = sum(len(t) for t in meta.get("tags", []))
    report.add("tags length",
               FAIL if tag_chars > standards.TAGS_MAX_TOTAL_CHARS else PASS,
               f"{tag_chars} chars across {len(meta.get('tags', []))} tags")

    # Thumbnails
    thumbs = [Path(p) for p in meta.get("thumbnails", [])]
    bad = []
    for t in thumbs:
        if not t.exists():
            bad.append(f"{t.name} missing")
            continue
        if t.stat().st_size > standards.THUMBNAIL_MAX_BYTES:
            bad.append(f"{t.name} over 2 MB")
        with Image.open(t) as im:
            if im.width < standards.THUMBNAIL_MIN_WIDTH or im.height < standards.THUMBNAIL_MIN_HEIGHT:
                bad.append(f"{t.name} {im.width}x{im.height} under "
                           f"{standards.THUMBNAIL_MIN_WIDTH}x{standards.THUMBNAIL_MIN_HEIGHT}")
    if not thumbs:
        report.add("thumbnails", FAIL, "none were produced")
    elif bad:
        report.add("thumbnails", FAIL, "; ".join(bad))
    else:
        report.add("thumbnails", PASS, f"{len(thumbs)} variants")

    # Legibility at feed size: does any contrast survive the shrink?
    if thumbs and thumbs[0].exists():
        with Image.open(thumbs[0]) as im:
            small = im.convert("L").resize(
                (standards.THUMBNAIL_FEED_WIDTH,
                 int(standards.THUMBNAIL_FEED_WIDTH * im.height / im.width)),
                Image.LANCZOS,
            )
        px = list(small.get_flattened_data())
        spread = max(px) - min(px)
        if spread < 60:
            report.add("thumbnail legibility", WARN,
                       f"only {spread} levels of contrast at {standards.THUMBNAIL_FEED_WIDTH}px "
                       "— likely unreadable in a feed")
        else:
            report.add("thumbnail legibility", PASS,
                       f"{spread} levels of contrast at feed size")

    # Disclosure must match what actually went into the video.
    derived = ctx.store.requires_disclosure(ctx.job_id)
    declared = bool(meta.get("altered_or_synthetic_content"))
    if derived != declared:
        report.add("disclosure flag", FAIL,
                   f"metadata says {declared}, the asset manifest implies {derived}")
    else:
        report.add("disclosure flag", PASS, "yes" if derived else "not required")


def run(ctx) -> None:
    report = Report()
    duration = _check_video(ctx, report)
    if duration:
        _check_audio(ctx, report)
        _check_captions(ctx, report, duration)
    _check_pacing(ctx, report)
    _check_safe_areas(ctx, report)
    _check_metadata(ctx, report)

    reused = ctx.store.reused_assets(ctx.job_id)
    if reused:
        where = {r["seen_channels"] for r in reused if r["seen_channels"]}
        report.add("asset reuse", WARN,
                   f"{len(reused)} asset(s) already used"
                   + (f" on {', '.join(sorted(where))}" if where else ""))
    else:
        report.add("asset reuse", PASS, "nothing repeated from an earlier job")

    path = ctx.job_dir / "preflight.json"
    path.write_text(json.dumps(report.to_obj(), indent=2), encoding="utf-8")

    counts = report.to_obj()["counts"]
    for check in report.checks:
        if check.status != PASS:
            ctx.log(f"{check.status.upper()} {check.name}: {check.detail}",
                    "warn" if check.status == WARN else "error")
    ctx.log(f"preflight: {counts['pass']} pass, {counts['warn']} warn, {counts['fail']} fail")

    if report.failures and ctx.cfg.get("preflight.block_on_fail", True):
        raise RuntimeError(
            f"preflight failed ({len(report.failures)}): "
            + "; ".join(c.name for c in report.failures)
            + f" — see {path}"
        )
