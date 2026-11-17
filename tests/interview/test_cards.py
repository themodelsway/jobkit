"""Tests for plugins/jobkit/src/jk/interview/cards.py and tracks.py: the knowledge catalog, tracks, families and seed."""
import json
import unittest
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from jk.interview import cards, readiness, sessions, tables
from jk.interview.aws import aws_seed
from tests.interview.support import SessionCase, drop_catalog
from tests.support import HomeCase, call

COMPANIES = {"acme": {"id": "acme", "name": "Acme", "bullets": [
    {"id": "acme-line-1", "text": "Built APIs on Lambda and API Gateway.", "ignored": False},
    {"id": "acme-line-2", "text": "Ran Lambda cost reviews.", "ignored": True}]}}
SKILLS = {"groups": {"Cloud": [{"name": "CloudFront", "aliases": []}]}}
GOOD_SOURCE = "https://docs.aws.amazon.com/lambda/latest/dg/welcome.html"


class CardsTestCase(HomeCase):
    def setUp(self):
        super().setUp()
        self.tmp = self.home
        self.pinned = []
        patcher = mock.patch.object(cards.qr, "load", return_value=(COMPANIES, SKILLS))
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch.object(cards.up, "key_topics", side_effect=lambda: self.pinned)
        patcher.start()
        self.addCleanup(patcher.stop)

    def cli(self, *argv):
        """Run `arch`; (status, stdout, stderr)."""
        return call(cards.main, *argv)

    def cards(self):
        return {c["id"]: c for c in tables.load_catalog()["cards"]}

    def register(self, seed=None, name="people-ops"):
        """Add a track from a seed file (the made-up people-operations sample when no seed is given)."""
        path = self.tmp / "seed.json"
        path.write_text(json.dumps(PEOPLE_OPS if seed is None else seed), encoding="utf-8")
        return self.cli("track", "add", name, "--seed", str(path))


class InitTests(CardsTestCase):
    def test_init_without_a_track_names_how_to_choose_one_and_loads_nothing(self):
        code, _, err = self.cli("init")
        self.assertEqual(code, 1)
        self.assertIn("cards init --track NAME", err)
        self.assertIsNone(tables.load_catalog())

    def test_init_creates_cards_and_tiers_from_resume(self):
        code, out, _ = self.cli("init", "--track", "aws")
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
        self.cli("init", "--track", "aws")
        cards = self.cards()
        self.assertEqual(cards["vpc"]["tier"], 1)
        self.assertEqual(cards["cloudfront"]["tier"], 2)

    def test_init_is_idempotent_and_keeps_hand_added_cards_and_progress(self):
        self.cli("init", "--track", "aws")
        cat = tables.load_catalog()
        cat["cards"].append(cards.new_card("topic", "my-card", "My Card", "Mine", 2))
        tables.replace_catalog(cat)
        self.cli("set", "vpc", "confidence", "2")
        _, out, _ = self.cli("init", "--track", "aws")
        self.assertIn("(0 new)", out)
        self.assertIn("my-card", self.cards())
        self.assertEqual(tables.load_progress()["vpc"]["confidence"], 2)

    def test_resume_links_ignore_ignored_bullets(self):
        self.cli("init", "--track", "aws")
        links = tables.load_progress()
        lam = next(c for c in self.cards().values() if c["name"] == "Lambda")
        self.assertEqual(links[lam["id"]]["links"], {"acme": ["acme-line-1"]})

    def test_missing_resume_data_warns_and_continues(self):
        with mock.patch.object(cards.qr, "load", side_effect=FileNotFoundError("no data")):
            code, out, _ = self.cli("init", "--track", "aws")
        self.assertEqual(code, 0)
        self.assertIn("Warning: resume data not loaded", out)


class CommandTests(CardsTestCase):
    def setUp(self):
        super().setUp()
        self.cli("init", "--track", "aws")

    def test_requires_init(self):
        drop_catalog()
        code, _, err = self.cli("status")
        self.assertEqual(code, 1)
        self.assertIn("run `cards init` first", err)

    def test_set_validates(self):
        self.assertEqual(self.cli("set", "vpc", "confidence", "5")[0], 1)
        self.assertEqual(self.cli("set", "nope", "notes", "x")[2].strip(), "No card nope")
        self.assertEqual(self.cli("set", "vpc", "color", "x")[0], 2)          # argparse choice
        self.assertEqual(self.cli("set", "vpc", "notes", "my note")[0], 0)
        self.assertIn("notes: my note", self.cli("show", "vpc")[1])

    def test_next_prefers_tier_one_and_weakest(self):
        _, out, _ = self.cli("next")
        first = out.split("]")[0].lstrip("[")
        self.assertEqual(self.cards()[first]["tier"], 1)
        self.assertIn("Nothing left", self.cli("next", "--area", "no such area")[1])

    def test_list_and_status_and_for_jd(self):
        self.assertIn("vpc", self.cli("list", "--kind", "topic", "--area", "edge")[1])
        self.assertIn("not drilled", self.cli("status")[1])
        jd = self.tmp / "jd.txt"
        jd.write_text("We use CloudFront and Lambda daily.", encoding="utf-8")
        out = self.cli("for-jd", str(jd))[1]
        self.assertIn("cloudfront", out)
        self.assertIn("topics from the catalog appear in the JD", out)

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
        card = cards.new_card("topic", "vpc", "VPC", "Networking", 2)
        self.assertTrue(cards.valid_source(GOOD_SOURCE, card))
        for bad in ("http://docs.aws.amazon.com/x", "https://docs.aws.amazon.com", "https://evil.com/docs.aws.amazon.com/x", None):
            self.assertFalse(cards.valid_source(bad, card), bad)


PEOPLE_OPS = {"label": "People operations", "family": "people", "source_hosts": ["handbook.example.org"],
              "topics": [{"area": "Pay", "name": "Payroll calendar", "tier": 2},
                         {"area": "Policy", "name": "Leave policy", "tier": 2, "aliases": ["PTO"]},
                         {"area": "Policy", "name": "Benefits enrollment", "tier": 3}],
              "pairs": [{"topic": "Hiring", "name": "Panel vs one-to-one interviews", "members": ["Panel", "One-to-one"]}],
              "scenarios": ["Design an onboarding plan for a remote team"]}
HANDBOOK_SOURCE = "https://handbook.example.org/policies/leave"


class TrackTests(CardsTestCase):
    def test_add_and_init_two_tracks_keeps_ids_apart(self):
        shared_name = {**PEOPLE_OPS, "topics": [*PEOPLE_OPS["topics"], {"area": "Other", "name": "VPC", "tier": 3}]}
        self.assertEqual(self.register(shared_name)[0], 0)
        self.assertEqual(self.cli("init", "--track", "aws", "--track", "people-ops")[0], 0)
        cards = self.cards()
        self.assertEqual(cards["vpc"]["track"], "aws")
        self.assertEqual(cards["people-ops-vpc"]["track"], "people-ops")      # same name, no collision
        self.assertIn("people-ops-pair-panel-vs-one-to-one-interviews", cards)
        self.assertIn("people-ops-scn-design-an-onboarding-plan-for-a-remote-team", cards)

    def test_init_without_track_extends_enabled_tracks_only(self):
        self.register()
        self.cli("init", "--track", "people-ops")
        self.assertNotIn("vpc", self.cards())                                  # aws was not asked for
        self.cli("init")
        self.assertNotIn("vpc", self.cards())
        self.cli("init", "--track", "aws")
        self.cli("init")
        self.assertIn("vpc", self.cards())
        self.assertIn("people-ops-payroll-calendar", self.cards())

    def test_refresh_accepts_only_the_cards_own_docs(self):
        self.register()
        self.cli("init", "--track", "aws", "--track", "people-ops")
        self.assertEqual(self.cli("refresh", "people-ops-payroll-calendar", "--status", "active", "--source", HANDBOOK_SOURCE)[0], 0)
        code, _, err = self.cli("refresh", "people-ops-payroll-calendar", "--status", "active", "--source", GOOD_SOURCE)
        self.assertEqual(code, 1)
        self.assertIn("handbook.example.org", err)
        self.assertEqual(self.cli("refresh", "vpc", "--status", "active", "--source", HANDBOOK_SOURCE)[0], 1)

    def test_filter_by_track_and_status_labels_tracks(self):
        self.register()
        self.cli("init", "--track", "aws", "--track", "people-ops")
        _, out, _ = self.cli("list", "--track", "people-ops")
        self.assertIn("people-ops-payroll-calendar", out)
        self.assertNotIn("lambda", out)
        _, status, _ = self.cli("status")
        self.assertIn("people-ops: Policy", status)
        self.assertIn("aws: ", status)

    def test_for_jd_matches_across_tracks(self):
        self.register()
        self.cli("init", "--track", "aws", "--track", "people-ops")
        jd = self.tmp / "jd.txt"
        jd.write_text("Lambda and leave policy experience", encoding="utf-8")
        _, out, _ = self.cli("for-jd", str(jd))
        self.assertIn("people-ops-leave-policy", out)
        self.assertIn("lambda", out)

    def test_tracks_lists_enabled_state(self):
        self.register()
        self.cli("init", "--track", "people-ops")
        _, out, _ = self.cli("tracks")
        self.assertRegex(out, r"aws\s+not enabled")
        self.assertRegex(out, r"people-ops\s+enabled\s+\d+ cards")

    def test_bad_seeds_are_rejected_with_a_reason(self):
        cases = [({**PEOPLE_OPS, "source_hosts": ["https://handbook.example.org/x"]}, "people-ops", "bare host"),
                 ({**PEOPLE_OPS, "source_hosts": []}, "people-ops", "source_hosts"),
                 ({**PEOPLE_OPS, "topics": [], "pairs": [], "scenarios": []}, "people-ops", "at least one card"),
                 ({**PEOPLE_OPS, "topics": [{"area": "A", "name": "B", "tier": 1}]}, "people-ops", "tier"),
                 (PEOPLE_OPS, "aws", "not 'aws'"),
                 (PEOPLE_OPS, "Bad Name", "lower-case")]
        for seed, name, message in cases:
            with self.subTest(message=message):
                code, _, err = self.register(seed, name)
                self.assertEqual(code, 1)
                self.assertIn(message, err)
        self.assertEqual(self.cli("tracks")[0], 0)
        self.assertEqual(self.cli("init", "--track", "nope")[0], 1)

    def test_old_catalog_without_track_field_still_works(self):
        self.cli("init", "--track", "aws")
        cat = tables.load_catalog()
        for card in cat["cards"]:
            card.pop("track", None)
        tables.replace_catalog(cat)
        self.assertEqual(self.cli("refresh", "vpc", "--status", "active", "--source", GOOD_SOURCE)[0], 0)
        self.assertEqual(self.cli("list", "--track", "aws")[0], 0)
        cat.pop("tracks", None)
        tables.replace_catalog(cat)
        self.assertRegex(self.cli("tracks")[1], r"aws\s+enabled")


class EveryFamilyTests(SessionCase):
    def test_one_track_per_family_goes_through_every_step(self):
        for name, family in cards.tracks.families().items():
            with self.subTest(family=name):
                track = f"sample-{name}"
                seed = {"label": family["label"], "family": name, "source_hosts": ["handbook.example.org"],
                        "topics": [{"area": "Basics", "name": f"{family['examples'][0]} basics", "tier": 2}],
                        "scenarios": [f"Plan the first month in a new {family['label'].lower()} role"]}
                code, _, err = call(cards.main, "track", "add", track, "--seed", "-", stdin=json.dumps(seed))
                self.assertEqual(code, 0, err)
                self.assertEqual(call(cards.main, "init", "--track", track)[0], 0)
                _, out, _ = call(cards.main, "next", "--track", track)
                self.assertIn(f"    - {family['dimensions'][0]}", out)
                code, _, err = call(sessions.main, "new", f"{name} round", "--track", track, "--mode", "knowledge")
                self.assertEqual(code, 0, err)
                self.assertEqual(call(readiness.main)[0], 0)


class CardOptionTests(SessionCase):
    def test_next_and_list_filters(self):
        stored = tables.load_catalog()["cards"]
        tier = stored[0]["tier"]
        out = self.cli(cards.main, "list", "--tier", str(tier))[1]
        self.assertIn(stored[0]["id"], out)
        for kind in ("topic", "pair", "scenario"):
            code, out, _ = self.cli(cards.main, "next", "--kind", kind, "--order", "random")
            self.assertEqual(code, 0)
            self.assertTrue(out.strip())
        self.assertEqual(self.cli(cards.main, "next", "--track", "aws", "--tier", str(tier))[0], 0)

    def test_unknown_track_filter_finds_nothing(self):
        _, out, _ = self.cli(cards.main, "list", "--track", "nosuch")
        self.assertNotIn("vpc", out)

    def test_stale_months(self):
        self.assertEqual(self.cli(cards.main, "stale", "--months", "1")[0], 0)

    def test_refresh_note(self):
        url = "https://docs.aws.amazon.com/vpc/latest/userguide/what-is-amazon-vpc.html"
        code, _, err = self.cli(cards.main, "refresh", "vpc", "--status", "active", "--source", url, "--note", "checked")
        self.assertEqual(code, 0, err)
        card = next(c for c in tables.load_catalog()["cards"] if c["id"] == "vpc")
        self.assertEqual(card["lifecycle"]["note"], "checked")


PRODUCT = {"label": "Product management", "family": "product", "country": "United Kingdom",
           "source_hosts": ["www.gov.uk"],
           "scenarios": ["Grow weekly active users of a mature app"],
           "cases": [{"title": "Sign-ups fell", "situation": "Sign-ups fell 20% last month. Find out why."}],
           "role_plays": [{"title": "Push back on a feature", "part": "a sales director who wants a feature now",
                           "goal": "agree a plan without promising a date"}]}


class FamilyTests(CardsTestCase):
    def test_every_bundled_family_has_a_label_a_description_and_a_rubric(self):
        families = cards.tracks.families()
        self.assertEqual(sorted(families), ["delivery", "design", "engineering", "finance", "operations", "people",
                                            "product", "sales-marketing", "strategy"])
        for name, family in families.items():
            with self.subTest(family=name):
                self.assertEqual(family["name"], name)
                self.assertTrue(family["label"].strip() and family["description"].strip() and family["sources"].strip())
                self.assertGreaterEqual(len(family["examples"]), 3)
                self.assertGreaterEqual(len(family["dimensions"]), 4)
                self.assertLessEqual(len(family["dimensions"]), cards.tracks.RUBRIC_MAX)
                self.assertTrue(all(line.strip() for line in family["dimensions"]))

    def test_families_lists_every_rubric_and_needs_no_database(self):
        drop_catalog()
        before = sorted(p.name for p in self.home.rglob("*"))
        code, out, _ = self.cli("families")
        self.assertEqual(code, 0)
        for family in cards.tracks.families().values():
            self.assertIn(f"{family['name']}: {family['label']}", out)
            self.assertIn(f"  - {family['dimensions'][0]}", out)
        self.assertEqual(sorted(p.name for p in self.home.rglob("*")), before)


class RoleTrackTests(CardsTestCase):
    def test_a_seed_without_topics_holds_cases_and_role_plays(self):
        code, out, err = self.register(PRODUCT, "product")
        self.assertEqual(code, 0, err)
        self.assertIn("(product)", out)
        self.assertIn("1 cases, 1 role-plays", out)
        self.cli("init", "--track", "product")
        cards = self.cards()
        self.assertEqual(cards["product-case-sign-ups-fell"]["kind"], "case")
        self.assertEqual(cards["product-role-push-back-on-a-feature"]["kind"], "role-play")

    def test_new_seed_fields_are_checked(self):
        bad = [({**PRODUCT, "family": "sales"}, "family' is required and must be one of"),
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
        product_rubric = cards.tracks.families()["product"]["dimensions"]
        _, out, _ = self.cli("show", "product-scn-grow-weekly-active-users-of-a-mature-app")
        self.assertIn(f"    - {product_rubric[0]}", out)
        self.assertNotIn("Cost drivers", out)
        _, out, _ = self.cli("show", "vpc")
        for line in cards.tracks.builtin_seed()["dimensions"]:
            self.assertIn(f"    - {line}", out)
        self.assertIn("lifecycle:", out)

    def test_a_seed_with_its_own_rubric_uses_it(self):
        self.register({**PRODUCT, "family": "people", "dimensions": ["Own line one", "Own line two"]}, "product")
        self.cli("init", "--track", "product")
        _, out, _ = self.cli("show", "product-case-sign-ups-fell")
        self.assertIn("    - Own line one", out)
        self.assertNotIn(cards.tracks.families()["people"]["dimensions"][0], out)

    def test_no_family_is_the_default(self):
        without = {k: v for k, v in PEOPLE_OPS.items() if k != "family"}
        code, _, err = self.register(without)
        self.assertEqual(code, 1)
        self.assertIn("'family' is required", err)
        self.register()
        self.cli("init", "--track", "people-ops")
        _, out, _ = self.cli("show", "people-ops-payroll-calendar")
        self.assertIn(f"    - {cards.tracks.families()['people']['dimensions'][0]}", out)
        self.assertNotIn(cards.tracks.families()["engineering"]["dimensions"][0], out)
        self.assertRegex(self.cli("tracks")[1], r"people-ops\s+enabled\s+\d+ cards\s+family: people")

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
        seed = {**PRODUCT, "topics": [{"area": "Team", "name": "Role conflict", "tier": 2}],
                "role_plays": [{"title": "Conflict", "part": "a peer", "goal": "agree"}]}
        code, _, err = self.register(seed, "product")
        self.assertEqual(code, 1)
        self.assertIn("would both be card product-role-conflict", err)

    def test_a_new_card_cannot_take_over_a_stored_card_and_its_progress(self):
        topic_only = {**PRODUCT, "topics": [{"area": "Team", "name": "Role conflict", "tier": 2}],
                        "role_plays": []}
        self.register(topic_only, "product")
        self.cli("init", "--track", "product")
        self.cli("set", "product-role-conflict", "confidence", "2")
        swapped = {**PRODUCT, "role_plays": [{"title": "Conflict", "part": "a peer", "goal": "agree"}]}
        code, _, err = self.register(swapped, "product")
        self.assertEqual(code, 1)
        self.assertIn("already a topic of track product", err)
        tables.save_track("product", cards.tracks.validate_seed(swapped, "product"))   # stored by other means
        code, _, err = self.cli("init", "--track", "product")
        self.assertEqual(code, 1)
        self.assertIn("rename it", err)
        self.assertEqual(self.cards()["product-role-conflict"]["kind"], "topic")

    def test_a_long_rubric_from_an_earlier_version_still_loads_and_shows(self):
        old = {**PRODUCT, "dimensions": [f"Old line {n}" for n in range(13)]}
        tables.save_track("product", old)                     # accepted before the 12-line limit
        self.assertEqual(self.cli("init", "--track", "product")[0], 0)
        self.assertEqual(self.cli("tracks")[0], 0)
        _, out, _ = self.cli("show", "product-case-sign-ups-fell")
        self.assertIn("    - Old line 12", out)
        self.assertNotIn(cards.tracks.families()["product"]["dimensions"][0], out)

    def test_an_unreadable_stored_seed_fails_show_instead_of_using_another_rubric(self):
        self.register(PRODUCT, "product")
        self.cli("init", "--track", "product")
        tables.save_track("product", {**PRODUCT, "family": "sales"})
        code, out, err = self.cli("show", "product-case-sign-ups-fell")
        self.assertEqual(code, 1, out)
        self.assertIn("family' is required and must be one of", err)

    def test_status_counts_the_same_unverified_cards_that_stale_lists(self):
        self.register(PRODUCT, "product")
        self.register()
        self.cli("init", "--track", "product", "--track", "people-ops")
        status = self.cli("status")[1]
        stale = self.cli("stale")[1]
        self.assertIn("3 of 3 topic cards have unverified facts", status)
        self.assertIn("3 topic cards need a refresh", stale)

    def test_blank_names_and_fractional_tiers_are_refused_when_added(self):
        bad = [({**PEOPLE_OPS, "topics": [{"area": "A", "name": "  ", "tier": 2}]}, "topics[0] needs"),
               ({**PEOPLE_OPS, "topics": [{"area": "A", "name": "Payroll calendar", "tier": 2.0}]}, "topics[0].tier"),
               ({**PEOPLE_OPS, "pairs": [{"topic": " ", "name": "X", "members": ["a"]}]}, "pairs[0] needs")]
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
        names = [s[1].lower() for s in aws_seed.SERVICES]
        self.assertEqual([n for n, c in Counter(names).items() if c > 1], [])

    def test_tiers_are_two_or_three(self):
        self.assertEqual({s[2] for s in aws_seed.SERVICES} - {2, 3}, set())

    def test_pairs_have_members(self):
        for pair in aws_seed.PAIRS:
            self.assertGreaterEqual(len(pair[2]), 2, pair)

    def test_no_urls_or_facts_in_seed(self):
        text = Path(aws_seed.__file__).read_text(encoding="utf-8")
        self.assertNotIn("http", text)                    # lifecycle facts come from `cards refresh --source`
        self.assertFalse(hasattr(aws_seed, "SEED_FACTS"))
