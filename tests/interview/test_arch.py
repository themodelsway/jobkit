"""Tests for src/jobkit/interview/arch.py in a temp folder (the real prep/ is never touched).
Run: .venv/bin/python -m unittest discover -s tests -t ."""
import contextlib
import io
import json
import unittest
from datetime import date, timedelta
from unittest import mock


from jobkit.interview import tables
from tests.support import HomeCase, drop_catalog
from jobkit.interview import arch

COMPANIES = {"acme": {"id": "acme", "name": "Acme", "bullets": [
    {"id": "acme-1", "text": "Built APIs on Lambda and API Gateway.", "ignored": False},
    {"id": "acme-2", "text": "Ran Lambda cost reviews.", "ignored": True}]}}
SKILLS = {"groups": {"Cloud": [{"name": "CloudFront", "aliases": []}]}}
GOOD_SOURCE = "https://docs.aws.amazon.com/lambda/latest/dg/welcome.html"


class ArchTestCase(HomeCase):
    def setUp(self):
        super().setUp()
        self.tmp = self.home
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
        return {c["id"]: c for c in tables.load_catalog()["cards"]}


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
        cat = tables.load_catalog()
        cat["cards"].append(arch.new_card("service", "my-card", "My Card", "Mine", 2))
        tables.save_catalog(cat)
        self.cli("set", "vpc", "confidence", "2")
        _, out, _ = self.cli("init")
        self.assertIn("(0 new)", out)
        self.assertIn("my-card", self.cards())
        self.assertEqual(tables.load_progress()["vpc"]["confidence"], 2)

    def test_resume_links_ignore_ignored_bullets(self):
        self.cli("init")
        links = tables.load_progress()
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
        drop_catalog()
        code, _, err = self.cli("status")
        self.assertEqual(code, 1)
        self.assertIn("run `arch init` first", err)

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
        jd.write_text("We use CloudFront and Lambda daily.", encoding="utf-8")
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
        card = arch.new_card("service", "vpc", "VPC", "Networking", 2)
        self.assertTrue(arch.valid_source(GOOD_SOURCE, card))
        for bad in ("http://docs.aws.amazon.com/x", "https://docs.aws.amazon.com", "https://evil.com/docs.aws.amazon.com/x", None):
            self.assertFalse(arch.valid_source(bad, card), bad)


ACMEDATA = {"label": "Acme Data", "source_hosts": ["docs.example.com"],
              "services": [{"area": "Compute", "name": "Turbo", "tier": 2},
                           {"area": "Governance", "name": "Data Catalog", "tier": 2, "aliases": ["UC"]},
                           {"area": "Governance", "name": "VPC", "tier": 3}],
              "pairs": [{"topic": "Tables", "name": "Format A vs Format B", "members": ["Format A", "Format B"]}],
              "scenarios": ["Design a lakehouse for streaming and BI"]}
ACMEDATA_SOURCE = "https://docs.example.com/en/compute/turbo.html"


class TrackTests(ArchTestCase):
    def register(self, seed=ACMEDATA, name="acmedata"):
        path = self.tmp / "seed.json"
        path.write_text(json.dumps(seed), encoding="utf-8")
        return self.cli("track", "add", name, "--seed", str(path))

    def test_add_and_init_two_tracks_keeps_ids_apart(self):
        self.assertEqual(self.register()[0], 0)
        self.assertEqual(self.cli("init", "--track", "aws", "--track", "acmedata")[0], 0)
        cards = self.cards()
        self.assertEqual(cards["vpc"]["track"], "aws")
        self.assertEqual(cards["acmedata-vpc"]["track"], "acmedata")      # same name, no collision
        self.assertIn("acmedata-pair-format-a-vs-format-b", cards)
        self.assertIn("acmedata-scn-design-a-lakehouse-for-streaming-and-bi", cards)

    def test_init_without_track_extends_enabled_tracks_only(self):
        self.register()
        self.cli("init", "--track", "acmedata")
        self.assertNotIn("vpc", self.cards())                                  # aws was not asked for
        self.cli("init")
        self.assertNotIn("vpc", self.cards())
        self.cli("init", "--track", "aws")
        self.cli("init")
        self.assertIn("vpc", self.cards())
        self.assertIn("acmedata-turbo", self.cards())

    def test_refresh_accepts_only_the_cards_own_docs(self):
        self.register()
        self.cli("init", "--track", "aws", "--track", "acmedata")
        self.assertEqual(self.cli("refresh", "acmedata-turbo", "--status", "active", "--source", ACMEDATA_SOURCE)[0], 0)
        code, _, err = self.cli("refresh", "acmedata-turbo", "--status", "active", "--source", GOOD_SOURCE)
        self.assertEqual(code, 1)
        self.assertIn("docs.example.com", err)
        self.assertEqual(self.cli("refresh", "vpc", "--status", "active", "--source", ACMEDATA_SOURCE)[0], 1)

    def test_filter_by_track_and_status_labels_tracks(self):
        self.register()
        self.cli("init", "--track", "aws", "--track", "acmedata")
        _, out, _ = self.cli("list", "--track", "acmedata")
        self.assertIn("acmedata-turbo", out)
        self.assertNotIn("lambda", out)
        _, status, _ = self.cli("status")
        self.assertIn("acmedata: Governance", status)
        self.assertIn("aws: ", status)

    def test_for_jd_matches_across_tracks(self):
        self.register()
        self.cli("init", "--track", "aws", "--track", "acmedata")
        jd = self.tmp / "jd.txt"
        jd.write_text("Lambda and Data Catalog experience", encoding="utf-8")
        _, out, _ = self.cli("for-jd", str(jd))
        self.assertIn("acmedata-data-catalog", out)
        self.assertIn("lambda", out)

    def test_tracks_lists_enabled_state(self):
        self.register()
        self.cli("init", "--track", "acmedata")
        _, out, _ = self.cli("tracks")
        self.assertRegex(out, r"aws\s+not enabled")
        self.assertRegex(out, r"acmedata\s+enabled\s+\d+ cards")

    def test_bad_seeds_are_rejected_with_a_reason(self):
        cases = [({**ACMEDATA, "source_hosts": ["https://docs.example.com/x"]}, "acmedata", "bare host"),
                 ({**ACMEDATA, "source_hosts": []}, "acmedata", "source_hosts"),
                 ({**ACMEDATA, "services": []}, "acmedata", "services"),
                 ({**ACMEDATA, "services": [{"area": "A", "name": "B", "tier": 1}]}, "acmedata", "tier"),
                 (ACMEDATA, "aws", "not 'aws'"),
                 (ACMEDATA, "Bad Name", "lower-case")]
        for seed, name, message in cases:
            with self.subTest(message=message):
                code, _, err = self.register(seed, name)
                self.assertEqual(code, 1)
                self.assertIn(message, err)
        self.assertEqual(self.cli("tracks")[0], 0)
        self.assertEqual(self.cli("init", "--track", "nope")[0], 1)

    def test_old_catalog_without_track_field_still_works(self):
        self.cli("init")
        cat = tables.load_catalog()
        for card in cat["cards"]:
            card.pop("track", None)
        tables.save_catalog(cat)
        self.assertEqual(self.cli("refresh", "vpc", "--status", "active", "--source", GOOD_SOURCE)[0], 0)
        self.assertEqual(self.cli("list", "--track", "aws")[0], 0)
        cat.pop("tracks", None)
        tables.save_catalog(cat)
        self.assertRegex(self.cli("tracks")[1], r"aws\s+enabled")


if __name__ == "__main__":
    unittest.main()
