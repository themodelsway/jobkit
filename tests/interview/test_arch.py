"""Tests for plugins/jobkit/src/jk/interview/arch.py and tracks.py: the knowledge catalog, tracks, families and seed."""
import json
import unittest
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from jk.interview import arch, tables
from jk.interview.aws import arch_seed
from tests.interview.support import SessionCase, drop_catalog
from tests.support import HomeCase, call

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
        """Run `arch`; (status, stdout, stderr)."""
        return call(arch.main, *argv)

    def cards(self):
        return {c["id"]: c for c in tables.load_catalog()["cards"]}

    def register(self, seed=None, name="acmedata"):
        """Add a track from a seed file (the Acme Data sample when no seed is given)."""
        path = self.tmp / "seed.json"
        path.write_text(json.dumps(ACMEDATA if seed is None else seed), encoding="utf-8")
        return self.cli("track", "add", name, "--seed", str(path))


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
        tables.replace_catalog(cat)
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
                 ({**ACMEDATA, "services": [], "pairs": [], "scenarios": []}, "acmedata", "at least one card"),
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
        tables.replace_catalog(cat)
        self.assertEqual(self.cli("refresh", "vpc", "--status", "active", "--source", GOOD_SOURCE)[0], 0)
        self.assertEqual(self.cli("list", "--track", "aws")[0], 0)
        cat.pop("tracks", None)
        tables.replace_catalog(cat)
        self.assertRegex(self.cli("tracks")[1], r"aws\s+enabled")


class ArchOptionTests(SessionCase):
    def test_next_and_list_filters(self):
        cards = tables.load_catalog()["cards"]
        tier = cards[0]["tier"]
        out = self.cli(arch.main, "list", "--tier", str(tier))[1]
        self.assertIn(cards[0]["id"], out)
        for kind in ("service", "pair", "scenario"):
            code, out, _ = self.cli(arch.main, "next", "--kind", kind, "--order", "random")
            self.assertEqual(code, 0)
            self.assertTrue(out.strip())
        self.assertEqual(self.cli(arch.main, "next", "--track", "aws", "--tier", str(tier))[0], 0)

    def test_unknown_track_filter_finds_nothing(self):
        _, out, _ = self.cli(arch.main, "list", "--track", "nosuch")
        self.assertNotIn("vpc", out)

    def test_stale_months(self):
        self.assertEqual(self.cli(arch.main, "stale", "--months", "1")[0], 0)

    def test_refresh_note(self):
        url = "https://docs.aws.amazon.com/vpc/latest/userguide/what-is-amazon-vpc.html"
        code, _, err = self.cli(arch.main, "refresh", "vpc", "--status", "active", "--source", url, "--note", "checked")
        self.assertEqual(code, 0, err)
        card = next(c for c in tables.load_catalog()["cards"] if c["id"] == "vpc")
        self.assertEqual(card["lifecycle"]["note"], "checked")


PRODUCT = {"label": "Product management", "family": "product", "country": "United Kingdom",
           "source_hosts": ["www.gov.uk"],
           "scenarios": ["Grow weekly active users of a mature app"],
           "cases": [{"title": "Sign-ups fell", "situation": "Sign-ups fell 20% last month. Find out why."}],
           "role_plays": [{"title": "Push back on a feature", "part": "a sales director who wants a feature now",
                           "goal": "agree a plan without promising a date"}]}


class FamilyTests(ArchTestCase):
    def test_every_bundled_family_has_a_label_a_description_and_a_rubric(self):
        families = arch.tracks.families()
        self.assertEqual(list(families), ["engineering", "product", "delivery", "people", "operations"])
        for name, family in families.items():
            with self.subTest(family=name):
                self.assertEqual(family["name"], name)
                self.assertTrue(family["label"].strip() and family["description"].strip())
                self.assertGreaterEqual(len(family["dimensions"]), 4)
                self.assertLessEqual(len(family["dimensions"]), arch.tracks.RUBRIC_MAX)
                self.assertTrue(all(line.strip() for line in family["dimensions"]))

    def test_families_lists_every_rubric_and_needs_no_database(self):
        drop_catalog()
        before = sorted(p.name for p in self.home.rglob("*"))
        code, out, _ = self.cli("families")
        self.assertEqual(code, 0)
        for family in arch.tracks.families().values():
            self.assertIn(f"{family['name']}: {family['label']}", out)
            self.assertIn(f"  - {family['dimensions'][0]}", out)
        self.assertEqual(sorted(p.name for p in self.home.rglob("*")), before)


class RoleTrackTests(ArchTestCase):
    def test_a_seed_without_services_holds_cases_and_role_plays(self):
        code, out, err = self.register(PRODUCT, "product")
        self.assertEqual(code, 0, err)
        self.assertIn("(product)", out)
        self.assertIn("1 cases, 1 role-plays", out)
        self.cli("init", "--track", "product")
        cards = self.cards()
        self.assertEqual(cards["product-case-sign-ups-fell"]["kind"], "case")
        self.assertEqual(cards["product-role-push-back-on-a-feature"]["kind"], "role-play")

    def test_new_seed_fields_are_checked(self):
        bad = [({**PRODUCT, "family": "sales"}, "family must be one of"),
               ({**PRODUCT, "dimensions": ["good", " "]}, "dimensions"),
               ({**PRODUCT, "dimensions": ["x"] * 13}, "at most 12"),
               ({**PRODUCT, "country": "x" * 61}, "country"),
               ({**PRODUCT, "role_plays": [{"title": "T", "goal": "G"}]}, "role_plays[0] needs a text 'part'"),
               ({**PRODUCT, "cases": [{"title": "T"}]}, "cases[0] needs a text 'situation'")]
        for seed, message in bad:
            with self.subTest(message=message):
                code, _, err = self.register(seed, "product")
                self.assertEqual(code, 1)
                self.assertIn(message, err)

    def test_role_play_and_case_cards_show_their_details_country_and_rubric(self):
        self.register(PRODUCT, "product")
        self.cli("init", "--track", "product")
        _, out, _ = self.cli("show", "product-role-push-back-on-a-feature")
        self.assertIn("the agent plays: a sales director who wants a feature now", out)
        self.assertIn("the user's goal: agree a plan without promising a date", out)
        self.assertIn("country: United Kingdom", out)
        self.assertNotIn("lifecycle", out)
        _, out, _ = self.cli("show", "product-case-sign-ups-fell")
        self.assertIn("situation: Sign-ups fell 20% last month.", out)

    def test_each_card_shows_its_own_tracks_rubric(self):
        self.register(PRODUCT, "product")
        self.cli("init", "--track", "aws", "--track", "product")
        product_rubric = arch.tracks.families()["product"]["dimensions"]
        _, out, _ = self.cli("show", "product-scn-grow-weekly-active-users-of-a-mature-app")
        self.assertIn(f"    - {product_rubric[0]}", out)
        self.assertNotIn("Cost drivers", out)
        _, out, _ = self.cli("show", "vpc")
        for line in arch.tracks.builtin_seed()["dimensions"]:
            self.assertIn(f"    - {line}", out)
        self.assertIn("lifecycle:", out)

    def test_a_seed_with_its_own_rubric_uses_it(self):
        self.register({**PRODUCT, "family": "people", "dimensions": ["Own line one", "Own line two"]}, "product")
        self.cli("init", "--track", "product")
        _, out, _ = self.cli("show", "product-case-sign-ups-fell")
        self.assertIn("    - Own line one", out)
        self.assertNotIn(arch.tracks.families()["people"]["dimensions"][0], out)

    def test_a_track_stored_before_families_counts_as_engineering(self):
        self.register()
        tables.save_track("acmedata", {k: v for k, v in ACMEDATA.items()})      # the old format, no family
        self.cli("init", "--track", "acmedata")
        _, out, _ = self.cli("show", "acmedata-turbo")
        self.assertIn(f"    - {arch.tracks.families()['engineering']['dimensions'][0]}", out)
        self.assertRegex(self.cli("tracks")[1], r"acmedata\s+enabled\s+\d+ cards\s+family: engineering")

    def test_tracks_show_the_family(self):
        self.register(PRODUCT, "product")
        self.cli("init", "--track", "aws", "--track", "product")
        out = self.cli("tracks")[1]
        self.assertRegex(out, r"aws\s+enabled\s+\d+ cards\s+family: engineering")
        self.assertRegex(out, r"product\s+enabled\s+\d+ cards\s+family: product")

    def test_filter_by_a_new_kind_and_aws_cards_keep_their_order(self):
        self.cli("init", "--track", "aws")
        before = [c["id"] for c in tables.load_catalog()["cards"]]
        self.register(PRODUCT, "product")
        self.cli("init", "--track", "product")
        after = [c["id"] for c in tables.load_catalog()["cards"] if c["track"] == "aws"]
        self.assertEqual(after, before)
        _, out, _ = self.cli("next", "--kind", "role-play")
        self.assertIn("product-role-push-back-on-a-feature", out)
        _, out, _ = self.cli("list", "--kind", "case")
        self.assertEqual(out.split()[0], "product-case-sign-ups-fell")

    def test_two_cards_of_one_seed_with_the_same_id_are_refused(self):
        seed = {**PRODUCT, "services": [{"area": "Team", "name": "Role conflict", "tier": 2}],
                "role_plays": [{"title": "Conflict", "part": "a peer", "goal": "agree"}]}
        code, _, err = self.register(seed, "product")
        self.assertEqual(code, 1)
        self.assertIn("would both be card product-role-conflict", err)

    def test_a_new_card_cannot_take_over_a_stored_card_and_its_progress(self):
        service_only = {**PRODUCT, "services": [{"area": "Team", "name": "Role conflict", "tier": 2}],
                        "role_plays": []}
        self.register(service_only, "product")
        self.cli("init", "--track", "product")
        self.cli("set", "product-role-conflict", "confidence", "2")
        swapped = {**PRODUCT, "role_plays": [{"title": "Conflict", "part": "a peer", "goal": "agree"}]}
        code, _, err = self.register(swapped, "product")
        self.assertEqual(code, 1)
        self.assertIn("already a service of track product", err)
        tables.save_track("product", arch.tracks.validate_seed(swapped, "product"))   # stored by other means
        code, _, err = self.cli("init", "--track", "product")
        self.assertEqual(code, 1)
        self.assertIn("rename it", err)
        self.assertEqual(self.cards()["product-role-conflict"]["kind"], "service")

    def test_a_long_rubric_from_an_earlier_version_still_loads_and_shows(self):
        old = {**PRODUCT, "dimensions": [f"Old line {n}" for n in range(13)]}
        tables.save_track("product", old)                     # accepted before the 12-line limit
        self.assertEqual(self.cli("init", "--track", "product")[0], 0)
        self.assertEqual(self.cli("tracks")[0], 0)
        _, out, _ = self.cli("show", "product-case-sign-ups-fell")
        self.assertIn("    - Old line 12", out)
        self.assertNotIn(arch.tracks.families()["product"]["dimensions"][0], out)

    def test_an_unreadable_stored_seed_fails_show_instead_of_using_another_rubric(self):
        self.register(PRODUCT, "product")
        self.cli("init", "--track", "product")
        tables.save_track("product", {**PRODUCT, "family": "sales"})
        code, out, err = self.cli("show", "product-case-sign-ups-fell")
        self.assertEqual(code, 1, out)
        self.assertIn("family must be one of", err)

    def test_status_counts_the_same_unverified_cards_that_stale_lists(self):
        self.register(PRODUCT, "product")
        self.register()
        self.cli("init", "--track", "product", "--track", "acmedata")
        status = self.cli("status")[1]
        stale = self.cli("stale")[1]
        self.assertIn("3 of 3 service cards have unverified facts", status)
        self.assertIn("3 service cards need a refresh", stale)

    def test_blank_names_and_fractional_tiers_are_refused_when_added(self):
        bad = [({**ACMEDATA, "services": [{"area": "A", "name": "  ", "tier": 2}]}, "services[0] needs"),
               ({**ACMEDATA, "services": [{"area": "A", "name": "Turbo", "tier": 2.0}]}, "services[0].tier"),
               ({**ACMEDATA, "pairs": [{"topic": " ", "name": "X", "members": ["a"]}]}, "pairs[0] needs")]
        for seed, message in bad:
            with self.subTest(message=message):
                code, _, err = self.register(seed)
                self.assertEqual(code, 1)
                self.assertIn(message, err)

    def test_editing_a_role_play_updates_its_card(self):
        self.register(PRODUCT, "product")
        self.cli("init", "--track", "product")
        changed = {**PRODUCT, "role_plays": [{**PRODUCT["role_plays"][0], "goal": "a new goal"}]}
        self.register(changed, "product")
        self.cli("init", "--track", "product")
        self.assertEqual(self.cards()["product-role-push-back-on-a-feature"]["goal"], "a new goal")


class SeedTests(unittest.TestCase):
    def test_service_names_are_unique(self):
        names = [s[1].lower() for s in arch_seed.SERVICES]
        self.assertEqual([n for n, c in Counter(names).items() if c > 1], [])

    def test_tiers_are_two_or_three(self):
        self.assertEqual({s[2] for s in arch_seed.SERVICES} - {2, 3}, set())

    def test_pairs_have_members(self):
        for pair in arch_seed.PAIRS:
            self.assertGreaterEqual(len(pair[2]), 2, pair)

    def test_no_urls_or_facts_in_seed(self):
        text = Path(arch_seed.__file__).read_text(encoding="utf-8")
        self.assertNotIn("http", text)                    # lifecycle facts come from `arch refresh --source`
        self.assertFalse(hasattr(arch_seed, "SEED_FACTS"))
