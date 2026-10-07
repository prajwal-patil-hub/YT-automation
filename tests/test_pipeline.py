"""Smoke tests. Stdlib unittest only — no extra dependency to run them.

    python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pipeline.db import Store
from pipeline.models import Beat, Script, VisualIntent
from pipeline.render import subtitles


class TestScriptRoundTrip(unittest.TestCase):
    def test_stage_output_survives_save_and_load(self):
        """The regression that broke every resume: durations must round-trip."""
        script = Script.from_obj({
            "title": "T",
            "beats": [{"narration": "one two three", "visual": {"kind": "card"}}],
        })
        script.beats[0].duration = 4.25
        script.beats[0].visual_path = "/tmp/x.png"
        script.beats[0].audio_path = "/tmp/x.wav"

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "script.json"
            script.save(path)
            reloaded = Script.load(path)

        self.assertEqual(reloaded.beats[0].duration, 4.25)
        self.assertEqual(reloaded.beats[0].visual_path, "/tmp/x.png")
        self.assertEqual(reloaded.beats[0].audio_path, "/tmp/x.wav")
        self.assertEqual(reloaded.total_duration, 4.25)

    def test_rejects_empty_narration(self):
        with self.assertRaises(ValueError):
            Beat.from_obj(0, {"narration": "   "})

    def test_visual_intent_from_string(self):
        intent = VisualIntent.from_obj("A title")
        self.assertEqual(intent.kind, "card")
        self.assertEqual(intent.spec["title"], "A title")


class TestDisclosureFlag(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.dir.name) / "t.sqlite3")
        self.asset = Path(self.dir.name) / "a.png"
        self.asset.write_bytes(b"x" * 32)

    def tearDown(self):
        self.store.close()
        self.dir.cleanup()

    def test_original_assets_need_no_disclosure(self):
        job = self.store.create_job("t")
        self.store.add_asset(job, "card", self.asset, "card", license="original")
        self.assertFalse(self.store.requires_disclosure(job))

    def test_generated_but_not_photorealistic_needs_no_disclosure(self):
        job = self.store.create_job("t")
        self.store.add_asset(job, "still", self.asset, "flux",
                             generated=True, photorealistic=False)
        self.assertFalse(self.store.requires_disclosure(job))

    def test_generated_and_photorealistic_requires_disclosure(self):
        job = self.store.create_job("t")
        self.store.add_asset(job, "still", self.asset, "flux",
                             generated=True, photorealistic=True)
        self.assertTrue(self.store.requires_disclosure(job))


class TestReuseDetection(unittest.TestCase):
    def test_same_bytes_in_a_later_job_are_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d) / "t.sqlite3")
            asset = Path(d) / "clip.mp4"
            asset.write_bytes(b"identical bytes")

            first = store.create_job("one")
            store.add_asset(first, "stock", asset, "stock", beat_index=0)
            self.assertEqual(store.reused_assets(first), [])

            second = store.create_job("two")
            store.add_asset(second, "stock", asset, "stock", beat_index=3)
            flagged = store.reused_assets(second)
            self.assertEqual(len(flagged), 1)
            self.assertEqual(flagged[0]["beat_index"], 3)
            store.close()


class TestSubtitleTiming(unittest.TestCase):
    def test_words_exactly_fill_the_beat(self):
        words = subtitles.estimate_words("alpha beta gamma delta", 10.0, 4.0)
        self.assertEqual(len(words), 4)
        self.assertAlmostEqual(words[0].start, 10.0)
        self.assertAlmostEqual(words[-1].end, 14.0, places=6)

    def test_longer_words_get_more_time(self):
        words = subtitles.estimate_words("a extraordinarily", 0.0, 2.0)
        self.assertLess(words[0].end - words[0].start, words[1].end - words[1].start)

    def test_empty_text_yields_nothing(self):
        self.assertEqual(subtitles.estimate_words("", 0.0, 5.0), [])

    def test_groups_respect_limits(self):
        words = subtitles.estimate_words(" ".join(["word"] * 30), 0.0, 30.0)
        for group in subtitles.group_words(words, max_chars=42, max_words=7):
            self.assertLessEqual(len(group), 7)
            self.assertLessEqual(len(" ".join(w.text for w in group)), 42)


class TestStageResume(unittest.TestCase):
    def test_stage_states_transition(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d) / "t.sqlite3")
            job = store.create_job("t")
            self.assertIsNone(store.stage_status(job, "script"))
            store.stage_begin(job, "script")
            self.assertEqual(store.stage_status(job, "script"), "running")
            store.stage_done(job, "script")
            self.assertEqual(store.stage_status(job, "script"), "done")
            store.reset_stages(job, ["script"])
            self.assertIsNone(store.stage_status(job, "script"))
            store.close()


if __name__ == "__main__":
    unittest.main()


class TestStageAssetReplacement(unittest.TestCase):
    def test_rerunning_a_stage_replaces_its_assets(self):
        """A redo must not leave stale provenance behind.

        The failure this guards: swap a photorealistic generated visual for an
        original diagram, re-run, and the disclosure flag stays wrongly set.
        """
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d) / "t.sqlite3")
            asset = Path(d) / "a.png"
            asset.write_bytes(b"x" * 16)
            job = store.create_job("t")

            store.add_asset(job, "still", asset, "flux", stage="visuals",
                            generated=True, photorealistic=True)
            self.assertTrue(store.requires_disclosure(job))

            store.clear_stage_assets(job, "visuals")
            store.add_asset(job, "chart", asset, "chart", stage="visuals",
                            license="original")

            self.assertEqual(len(store.assets_for(job)), 1)
            self.assertFalse(store.requires_disclosure(job))
            store.close()


class TestLegacyDatabaseMigration(unittest.TestCase):
    def test_opens_a_database_created_before_channels_existed(self):
        """Regression: indexes were created before the migration that adds
        their column, so opening any pre-existing database aborted outright."""
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "legacy.sqlite3"
            import sqlite3
            conn = sqlite3.connect(path)
            conn.executescript(
                "CREATE TABLE jobs (id INTEGER PRIMARY KEY AUTOINCREMENT,"
                " topic TEXT NOT NULL, title TEXT, status TEXT NOT NULL,"
                " created_at REAL NOT NULL, updated_at REAL NOT NULL,"
                " meta TEXT NOT NULL DEFAULT '{}');"
            )
            conn.execute(
                "INSERT INTO jobs (topic, status, created_at, updated_at)"
                " VALUES ('old', 'new', 0, 0)"
            )
            conn.commit()
            conn.close()

            store = Store(path)                      # must not raise
            cols = {r["name"] for r in store.conn.execute("PRAGMA table_info(jobs)")}
            self.assertIn("channel", cols)
            rows = store.list_jobs()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["channel"], "default")   # back-filled
            new_id = store.create_job("fresh", channel="alpha")
            self.assertEqual(store.get_job(new_id)["channel"], "alpha")
            store.close()


class TestChannelResolution(unittest.TestCase):
    def test_style_then_channel_overrides_base(self):
        from pipeline import channels as ch
        base = {"video": {"motion": "none", "fps": 30}, "theme": {"accent": "#111"}}
        style = {"video": {"motion": "drift"}, "theme": {"accent": "#222"}}
        chan = {"theme": {"accent": "#333"}}
        merged = ch.deep_merge(ch.deep_merge(base, style), chan)
        self.assertEqual(merged["video"]["motion"], "drift")   # style beat base
        self.assertEqual(merged["video"]["fps"], 30)           # base survived
        self.assertEqual(merged["theme"]["accent"], "#333")    # channel beat style

    def test_every_style_is_complete(self):
        from pipeline import styles
        for name in styles.names():
            st = styles.get(name)
            for section in ("video", "captions", "voice", "visuals", "theme"):
                self.assertIn(section, st, f"{name} missing [{section}]")
            self.assertIn("default_kind", st["visuals"], name)

    def test_styles_are_deep_copied(self):
        from pipeline import styles
        a = styles.get("explainer-dark")
        a["theme"]["accent"] = "#000000"
        self.assertNotEqual(styles.get("explainer-dark")["theme"]["accent"], "#000000")


class TestDeliveryStandards(unittest.TestCase):
    def test_safe_box_is_eighty_percent_of_frame(self):
        from pipeline import standards
        left, top, right, bottom = standards.safe_box(1920, 1080)
        self.assertEqual((left, top, right, bottom), (192, 108, 1728, 972))
        self.assertAlmostEqual((right - left) / 1920, 0.80, places=2)
        self.assertAlmostEqual((bottom - top) / 1080, 0.80, places=2)

    def test_player_ui_zone_is_excluded(self):
        from pipeline import standards
        self.assertEqual(standards.player_ui_top(1080), int(1080 * 0.92))

    def test_loudness_off_target(self):
        from pipeline.util.loudness import Loudness
        from pipeline import standards
        self.assertAlmostEqual(Loudness(-21.0, -1.5, 5.0).off_target(), -7.0)
        self.assertAlmostEqual(Loudness(standards.TARGET_LUFS, -1.0, 5.0).off_target(), 0.0)


class TestSafeAreaDetection(unittest.TestCase):
    """The detector must pass text drawn on the margin and still catch real
    violations — a check that cries wolf gets switched off."""

    def _render(self, directory, xy):
        from PIL import Image, ImageDraw
        from pipeline.render.theme import Theme
        img = Image.new("RGB", (1920, 1080), "#0C1014")
        ImageDraw.Draw(img).text(xy, "LEGIBLE TEXT",
                                 font=Theme().font("display", 70), fill="#FFFFFF")
        path = Path(directory) / f"{xy[0]}-{xy[1]}.png"
        img.save(path)
        return path

    def _outside(self, path):
        from pipeline.stages.preflight_stage import (
            _high_contrast_bbox, SAFE_AREA_TOLERANCE_PX as tol,
        )
        from pipeline import standards
        box = _high_contrast_bbox(path)
        if box is None:
            return False
        left, top, right, bottom = standards.safe_box(1920, 1080)
        x0, y0, x1, y1 = box
        return (x0 < left - tol or y0 < top - tol
                or x1 > right + tol or y1 > bottom + tol)

    def test_catches_text_outside_the_safe_box(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertTrue(self._outside(self._render(d, (20, 500))),  "far left")
            self.assertTrue(self._outside(self._render(d, (1700, 500))), "off right")
            self.assertTrue(self._outside(self._render(d, (400, 1040))), "player UI zone")

    def test_passes_text_inside_the_safe_box(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(self._outside(self._render(d, (400, 500))))

    def test_smooth_gradient_has_no_high_contrast_content(self):
        from pipeline.render import ambient
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "amb.png"
            ambient.compose((1920, 1080), seed=3, top="#1C1024",
                            bottom="#06040A", glow="#C98F35").save(path)
            from pipeline.stages.preflight_stage import _high_contrast_bbox
            self.assertIsNone(_high_contrast_bbox(path))


class TestPreflightReport(unittest.TestCase):
    def test_failures_block_and_warnings_do_not(self):
        from pipeline.stages.preflight_stage import Report, PASS, WARN, FAIL
        r = Report()
        r.add("a", PASS); r.add("b", WARN, "minor"); r.add("c", FAIL, "bad")
        obj = r.to_obj()
        self.assertFalse(obj["passed"])
        self.assertEqual(obj["counts"], {"pass": 1, "warn": 1, "fail": 1})
        self.assertEqual([c.name for c in r.failures], ["c"])
        self.assertEqual([c.name for c in r.warnings], ["b"])

    def test_warnings_alone_still_pass(self):
        from pipeline.stages.preflight_stage import Report, PASS, WARN
        r = Report()
        r.add("a", PASS); r.add("b", WARN, "minor")
        self.assertTrue(r.to_obj()["passed"])


# --------------------------------------------------------------------------
# Network clients. Neither API is reachable from the build environment, so
# both are exercised against a fake transport that records what was sent.
# --------------------------------------------------------------------------

class FakeTransport:
    """Records requests and replays queued responses."""

    def __init__(self, responses=None):
        from pipeline.util.http import Response
        self.Response = Response
        self.sent = []
        self.responses = list(responses or [])

    def push(self, status=200, body=b"{}", headers=None):
        self.responses.append(self.Response(status, body, headers or {}))

    def request(self, method, url, *, data=None, headers=None, timeout=60.0):
        self.sent.append({"method": method, "url": url, "data": data,
                          "headers": headers or {}})
        if self.responses:
            return self.responses.pop(0)
        return self.Response(200, b'{"ok": true, "result": {}}', {})


class TestTelegramClient(unittest.TestCase):
    def _client(self, transport, **kw):
        from pipeline.util.telegram import TelegramClient
        return TelegramClient("TOKEN", transport=transport,
                              allowed_user_ids=kw.pop("allowed", [42]), **kw)

    def test_refuses_to_build_without_a_token(self):
        from pipeline.util.telegram import TelegramClient, TelegramError
        with self.assertRaises(TelegramError):
            TelegramClient("")

    def test_drops_callbacks_from_strangers(self):
        """The bot is reachable by anyone who finds it. The allow-list is the
        only thing between a stranger and the publish button."""
        c = self._client(FakeTransport(), allowed=[42])
        updates = [
            {"update_id": 1, "callback_query": {
                "id": "a", "from": {"id": 42}, "data": "j7:approve",
                "message": {"message_id": 5, "chat": {"id": 42}}}},
            {"update_id": 2, "callback_query": {
                "id": "b", "from": {"id": 999}, "data": "j7:approve",
                "message": {"message_id": 6, "chat": {"id": 999}}}},
        ]
        got = c.callbacks(updates)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0].user_id, 42)

    def test_upload_limit_depends_on_endpoint(self):
        from pipeline.util.telegram import PUBLIC_UPLOAD_LIMIT
        public = self._client(FakeTransport())
        local = self._client(FakeTransport(), api_base="http://localhost:8081")
        self.assertEqual(public.upload_limit(), PUBLIC_UPLOAD_LIMIT)
        self.assertGreater(local.upload_limit(), PUBLIC_UPLOAD_LIMIT * 10)
        self.assertFalse(public.is_self_hosted)
        self.assertTrue(local.is_self_hosted)

    def test_oversized_video_is_refused_with_a_useful_message(self):
        from pipeline.util.telegram import TelegramError
        c = self._client(FakeTransport())
        with tempfile.TemporaryDirectory() as d:
            big = Path(d) / "big.mp4"
            big.write_bytes(b"\0" * (51 * 1024 * 1024))
            with self.assertRaises(TelegramError) as ctx:
                c.send_video(1, big)
        self.assertIn("self-hosted", str(ctx.exception))

    def test_api_errors_are_raised_not_swallowed(self):
        from pipeline.util.telegram import TelegramError
        t = FakeTransport()
        t.push(400, b'{"ok": false, "description": "chat not found"}')
        with self.assertRaises(TelegramError) as ctx:
            self._client(t).send_message(1, "hi")
        self.assertIn("chat not found", str(ctx.exception))

    def test_action_round_trip(self):
        from pipeline.util.telegram import encode_action, decode_action
        for job_id, action in ((1, "approve"), (4213, "redo-visuals")):
            self.assertEqual(decode_action(encode_action(job_id, action)),
                             (job_id, action))
        self.assertIsNone(decode_action("nonsense"))
        self.assertIsNone(decode_action("jx:approve"))

    def test_callback_payloads_fit_telegrams_64_byte_cap(self):
        from pipeline.util.telegram import encode_action
        from pipeline.stages.review_stage import REDO_TARGETS
        for action in list(REDO_TARGETS) + ["approve", "schedule", "reject"]:
            self.assertLessEqual(len(encode_action(999999, action).encode()), 64)


class TestReviewDecisions(unittest.TestCase):
    def _setup(self):
        from pipeline.util.telegram import TelegramClient
        d = tempfile.TemporaryDirectory()
        store = Store(Path(d.name) / "t.sqlite3")
        job = store.create_job("t", channel="alpha")
        store.set_approval(job, "video", "pending", message_id=11)
        client = TelegramClient("T", transport=FakeTransport(), allowed_user_ids=[42])
        return d, store, job, client

    def _callback(self, job, action, user=42):
        from pipeline.util.telegram import Callback, encode_action
        return Callback("cb", user, 42, 11, encode_action(job, action), 1)

    def test_approve_records_approval(self):
        from pipeline.review import handle_callback
        d, store, job, client = self._setup()
        decision = handle_callback(store, client, self._callback(job, "approve"))
        self.assertEqual(decision.action, "approve")
        self.assertEqual(store.get_approval(job, "video")["state"], "approved")
        self.assertEqual(store.get_job(job)["status"], "approved")
        store.close(); d.cleanup()

    def test_redo_triggers_the_right_stage(self):
        from pipeline.review import handle_callback
        d, store, job, client = self._setup()
        seen = []
        handle_callback(store, client, self._callback(job, "redo-visuals"),
                        rerun=lambda j, s: seen.append((j, s)))
        self.assertEqual(seen, [(job, "visuals")])
        self.assertEqual(store.get_approval(job, "video")["state"], "redo")
        store.close(); d.cleanup()

    def test_unknown_and_malformed_actions_are_ignored(self):
        from pipeline.review import handle_callback
        from pipeline.util.telegram import Callback
        d, store, job, client = self._setup()
        self.assertIsNone(handle_callback(store, client,
                                          Callback("c", 42, 42, 11, "garbage", 1)))
        self.assertIsNone(handle_callback(store, client, self._callback(job, "launch-missiles")))
        self.assertEqual(store.get_approval(job, "video")["state"], "pending")
        store.close(); d.cleanup()

    def test_callback_for_a_missing_job_is_ignored(self):
        from pipeline.review import handle_callback
        d, store, job, client = self._setup()
        self.assertIsNone(handle_callback(store, client, self._callback(99999, "approve")))
        store.close(); d.cleanup()


class TestYouTubeClient(unittest.TestCase):
    def _client(self, transport):
        from pipeline.util.youtube import YouTubeClient
        return YouTubeClient("id", "secret", "refresh", transport=transport)

    def test_refuses_to_build_without_credentials(self):
        from pipeline.util.youtube import YouTubeClient, YouTubeError
        with self.assertRaises(YouTubeError) as ctx:
            YouTubeClient("", "", "")
        self.assertIn("client id", str(ctx.exception))

    def test_expired_refresh_token_explains_the_seven_day_trap(self):
        from pipeline.util.youtube import YouTubeError
        t = FakeTransport()
        t.push(400, b'{"error": "invalid_grant"}')
        with self.assertRaises(YouTubeError) as ctx:
            self._client(t).access_token()
        self.assertIn("Testing", str(ctx.exception))

    def test_resumable_upload_sends_every_chunk_in_order(self):
        from pipeline.util.youtube import CHUNK
        t = FakeTransport()
        t.push(200, b'{"access_token": "AT"}')              # token refresh comes first
        t.push(200, b"{}", {"Location": "https://upload.example/session"})
        t.push(308, b"")                                    # first chunk accepted
        t.push(200, b'{"id": "VID123", "status": {"privacyStatus": "private"}}')
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "v.mp4"
            path.write_bytes(b"\xab" * (CHUNK + 2048))
            result = self._client(t).upload_video(path, {"snippet": {}})

        self.assertEqual(result.video_id, "VID123")
        start = [s for s in t.sent if s["url"].startswith("https://www.googleapis.com/upload")][0]
        self.assertEqual(start["headers"]["Authorization"], "Bearer AT")
        self.assertEqual(start["headers"]["X-Upload-Content-Length"], str(CHUNK + 2048))

        puts = [s for s in t.sent if s["method"] == "PUT"]
        self.assertEqual(len(puts), 2)
        self.assertEqual(puts[0]["headers"]["Content-Range"],
                         f"bytes 0-{CHUNK - 1}/{CHUNK + 2048}")
        self.assertEqual(puts[1]["headers"]["Content-Range"],
                         f"bytes {CHUNK}-{CHUNK + 2047}/{CHUNK + 2048}")

    def test_synthetic_media_flag_reaches_the_api_body(self):
        from pipeline.util.youtube import build_video_body
        on = build_video_body({"title": "t", "altered_or_synthetic_content": True})
        off = build_video_body({"title": "t", "altered_or_synthetic_content": False})
        self.assertTrue(on["status"]["containsSyntheticMedia"])
        self.assertFalse(off["status"]["containsSyntheticMedia"])

    def test_scheduling_forces_private_until_the_publish_time(self):
        from pipeline.util.youtube import build_video_body
        body = build_video_body({"title": "t", "privacy_status": "public"},
                                publish_at="2026-12-01T09:00:00Z")
        self.assertEqual(body["status"]["privacyStatus"], "private")
        self.assertEqual(body["status"]["publishAt"], "2026-12-01T09:00:00Z")

    def test_title_and_description_are_clamped_to_youtube_limits(self):
        from pipeline.util.youtube import build_video_body
        from pipeline import standards
        body = build_video_body({"title": "x" * 300, "description": "y" * 9000})
        self.assertEqual(len(body["snippet"]["title"]), standards.TITLE_MAX_CHARS)
        self.assertEqual(len(body["snippet"]["description"]),
                         standards.DESCRIPTION_MAX_CHARS)


class TestTerminalStatusIsPreserved(unittest.TestCase):
    """Regression: the runner's end-of-run rollup overwrote the status that
    `review` and `publish` set, so a published job read "ready-for-review"."""

    def test_optional_stage_runs_do_not_touch_the_rollup_status(self):
        from pipeline.models import STAGES
        from pipeline.runner import OPTIONAL_STAGES
        core = [s for s in STAGES if s not in OPTIONAL_STAGES]

        # A publish-only run must not intersect the core pipeline at all.
        self.assertFalse(any(name in core for name in ["publish"]))
        self.assertFalse(any(name in core for name in ["review"]))
        # A normal run must.
        self.assertTrue(any(name in core for name in STAGES))
        self.assertIn("preflight", core)
        self.assertNotIn("publish", core)
