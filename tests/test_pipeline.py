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
