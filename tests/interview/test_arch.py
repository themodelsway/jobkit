"""Tests for src/interview/arch.py in a temp folder (the real prep/ is never touched).
Run: .venv/bin/python -m unittest discover -s tests -t ."""
import contextlib
import io
import shutil
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock


from jobkit import common
from jobkit.interview import arch

COMPANIES = {"acme": {"id": "acme", "name": "Acme", "bullets": [
    {"id": "acme-1", "text": "Built APIs on Lambda and API Gateway.", "ignored": False},
    {"id": "acme-2", "text": "Ran Lambda cost reviews.", "ignored": True}]}}
SKILLS = {"groups": {"Cloud": [{"name": "CloudFront", "aliases": []}]}}
GOOD_SOURCE = "https://docs.aws.amazon.com/lambda/latest/dg/welcome.html"


class ArchTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(self.tmp))
        d = self.tmp / "prep" / "arch"
        for obj, name, value in ((arch, "ROOT", self.tmp), (arch, "DIR", d), (arch, "CATALOG", d / "catalog.json"),
                                 (arch, "PROGRESS", d / "progress.json"),
                                 (common, "LOCK_FILE", self.tmp / "prep" / ".lock")):
            patcher = mock.patch.object(obj, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.pinned = []
        patcher = mock.patch.object(arch.qr, "load", return_value=(COMPANIES, SKILLS))
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch.object(arch.up, "tier1_services", side_effect=lambda: self.pinned)
        patcher.start()
        self.addCleanup(patcher.stop)

    def cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = arch.main(list(argv))
            except SystemExit as exc:                      # argparse errors
                code = exc.code
        return code, out.getvalue(), err.getvalue()

    def cards(self):
        return {c["id"]: c for c in common.load_json(arch.CATALOG, None)["cards"]}


class InitTests(ArchTestCase):
    def test_init_creates_cards_and_tiers_from_resume(self):
        code, out, _ = self.cli("init")
        self.assertEqual(code, 0)
        cards = self.cards()
        self.assertEqual(cards["cloudfront"]["tier"], 1)       # named in the resume skills
        lam = next(c for c in cards.values() if c["name"] == "Lambda")
        self.assertEqual(lam["tier"], 1)                       # a resume bullet mentions it
        self.assertEqual(cards["vpc"]["tier"], 2)
        self.assertTrue(any(c["kind"] == "pair" for c in cards.values()))
        self.assertTrue(any(c["kind"] == "scenario" for c in cards.values()))
        self.assertIn("(", out)

    def test_pinned_list_overrides_resume_scan(self):
        self.pinned = ["VPC"]
        self.cli("init")
        cards = self.cards()
        self.assertEqual(cards["vpc"]["tier"], 1)
        self.assertEqual(cards["cloudfront"]["tier"], 2)

    def test_init_is_idempotent_and_keeps_hand_added_cards_and_progress(self):
        self.cli("init")
        cat = common.load_json(arch.CATALOG, None)
        cat["cards"].append(arch.new_card("service", "my-card", "My Card", "Mine", 2))
        common.save_json(arch.CATALOG, cat)
        self.cli("set", "vpc", "confidence", "2")
        _, out, _ = self.cli("init")
        self.assertIn("(0 new)", out)
        self.assertIn("my-card", self.cards())
        self.assertEqual(common.load_json(arch.PROGRESS, None)["cards"]["vpc"]["confidence"], 2)

    def test_resume_links_ignore_ignored_bullets(self):
        self.cli("init")
        links = common.load_json(arch.PROGRESS, None)["cards"]
        lam = next(c for c in self.cards().values() if c["name"] == "Lambda")
        self.assertEqual(links[lam["id"]]["links"], {"acme": ["acme-1"]})

    def test_missing_resume_data_warns_and_continues(self):
        with mock.patch.object(arch.qr, "load", side_effect=FileNotFoundError("no data")):
            code, out, _ = self.cli("init")
        self.assertEqual(code, 0)
        self.assertIn("Warning: resume data not loaded", out)


class CommandTests(ArchTestCase):
    def setUp(self):
        super().setUp()
        self.cli("init")

    def test_requires_init(self):
        arch.CATALOG.unlink()
        code, _, err = self.cli("status")
        self.assertEqual(code, 1)
        self.assertIn("run `arch.py init` first", err)

    def test_set_validates(self):
        self.assertEqual(self.cli("set", "vpc", "confidence", "5")[0], 1)
        self.assertEqual(self.cli("set", "nope", "notes", "x")[2].strip(), "No card nope")
        self.assertEqual(self.cli("set", "vpc", "colour", "x")[0], 2)          # argparse choice
        self.assertEqual(self.cli("set", "vpc", "notes", "my note")[0], 0)
        self.assertIn("notes: my note", self.cli("show", "vpc")[1])

    def test_next_prefers_tier_one_and_weakest(self):
        _, out, _ = self.cli("next")
        first = out.split("]")[0].lstrip("[")
        self.assertEqual(self.cards()[first]["tier"], 1)
        self.assertIn("Nothing left", self.cli("next", "--area", "no such area")[1])

    def test_list_and_status_and_for_jd(self):
        self.assertIn("vpc", self.cli("list", "--kind", "service", "--area", "edge")[1])
        self.assertIn("not drilled", self.cli("status")[1])
        jd = self.tmp / "jd.txt"
        jd.write_text("We use CloudFront and Lambda daily.")
        out = self.cli("for-jd", str(jd))[1]
        self.assertIn("cloudfront", out)
        self.assertIn("services from the catalog appear in the JD", out)

    def test_refresh_records_facts_with_source(self):
        code, _out, _ = self.cli("refresh", "vpc", "--status", "active", "--source", GOOD_SOURCE,
                                "--change", "2025-01-02|Added thing")
        self.assertEqual(code, 0)
        card = self.cards()["vpc"]
        self.assertEqual(card["lifecycle"], {"status": "active", "source": GOOD_SOURCE})
        self.assertEqual(card["recent_changes"][0]["summary"], "Added thing")
        self.assertEqual(card["verified_on"], date.today().isoformat())
        stale_ids = [line.split()[1] for line in self.cli("stale")[1].splitlines() if line.startswith("  t")]
        self.assertNotIn("vpc", stale_ids)
        self.assertIn("cloudfront", stale_ids)

    def test_refresh_rejects_bad_input(self):
        future = (date.today() + timedelta(days=30)).isoformat()
        cases = [(["--source", "https://example.com/x"], "--source must be"),
                 (["--source", GOOD_SOURCE, "--date", "yesterday"], "--date must be"),
                 (["--source", GOOD_SOURCE, "--date", future], "future"),
                 (["--source", GOOD_SOURCE, "--change", "nonsense"], "--change must look like"),
                 (["--source", GOOD_SOURCE, "--change", f"{future}|soon"], "in the future")]
        for extra, message in cases:
            with self.subTest(extra=extra):
                code, _, err = self.cli("refresh", "vpc", "--status", "active", *extra)
                self.assertEqual(code, 1)
                self.assertIn(message, err)
        self.assertEqual(self.cli("refresh", "vpc", "--status", "bogus", "--source", GOOD_SOURCE)[0], 2)
        self.assertEqual(self.cli("refresh", "vpc", "--status", "sunset", "--source", GOOD_SOURCE, "--date", future)[0], 0)

    def test_valid_source(self):
        self.assertTrue(arch.valid_source(GOOD_SOURCE))
        for bad in ("http://docs.aws.amazon.com/x", "https://docs.aws.amazon.com", "https://evil.com/docs.aws.amazon.com/x", None):
            self.assertFalse(arch.valid_source(bad), bad)


if __name__ == "__main__":
    unittest.main()
