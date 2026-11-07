"""The code pass: requirements rated from stored facts without a model."""
import copy
import unittest
from datetime import date
from decimal import Decimal

from jobkit.resumes import match_codepass as cp
from jobkit.resumes import match_engine as me
from jobkit.resumes import match_facts as mf
from jobkit.resumes import match_request as mr
from tests.resumes.match_fixtures import facts, request

FACTS = facts()
TODAY = date(2026, 1, 1)


def by_id(posting, fact=FACTS):
    return {i["id"]: i for i in cp.code_pass(posting, fact, TODAY)}


class SkillTests(unittest.TestCase):
    def test_alias_is_rated_from_the_stored_skill(self):
        item = by_id("We use k8s every day.")["code:skill:kubernetes"]
        self.assertEqual(item["level"], "substantial")           # one stored line shows Kubernetes
        self.assertIn("skill:Kubernetes", item["evidence"])
        self.assertTrue(item["evidence"][0].startswith("bullet:"))

    def test_two_lines_give_full_and_none_give_partial(self):
        found = by_id("Amazon Web Services and Python are needed.")
        self.assertEqual(found["code:skill:aws"]["level"], "full")
        self.assertEqual(found["code:skill:python"]["level"], "partial")
        self.assertEqual(found["code:skill:python"]["evidence"], ["skill:Python"])

    def test_nothing_named_gives_no_skill_items(self):
        self.assertEqual(by_id("A friendly team and free lunch."), {})


class DegreeTests(unittest.TestCase):
    def test_level_met_with_field(self):
        item = by_id("Bachelor's degree in Computer Science.")["code:degree:1"]
        self.assertEqual((item["level"], item["evidence"]), ("full", ["education:1"]))

    def test_level_met_but_field_not_named_in_resume(self):
        self.assertEqual(by_id("Master's degree in Biology.")["code:degree:2"]["level"], "partial")

    def test_level_not_met(self):
        item = by_id("A PhD is required.")["code:degree:3"]
        self.assertEqual((item["level"], item["evidence"]), ("profile_miss", []))

    def test_related_field_wording_is_left_to_pass_one(self):
        self.assertEqual(by_id("Bachelor's degree in Computer Science or a related field."), {})


class CertificationTests(unittest.TestCase):
    def test_associate_against_professional_is_partial(self):
        item = by_id("Example Certified Developer - Professional preferred.")["code:cert:example-certified-developer"]
        self.assertEqual(item["level"], "partial")

    def test_same_or_lower_level_asked_is_full(self):
        found = by_id("Example Certified Developer Associate is a plus.")
        self.assertEqual(found["code:cert:example-certified-developer"]["level"], "full")

    def test_unnamed_level_is_full_and_unheld_certification_is_left_alone(self):
        self.assertEqual(len([i for i in by_id("Example Certified Developer required. PMP preferred.").values()
                              if i["kind"] == "certification"]), 1)


class YearsTests(unittest.TestCase):
    def level(self, asked):
        return by_id(f"{asked}+ years of experience.").get("code:years")

    def test_share_of_asked_years(self):       # the fixture shows about 11.1 years
        for asked, expected in ((11, "full"), (14, "substantial"), (22, "partial"), (60, "profile_miss")):
            with self.subTest(asked=asked):
                self.assertEqual(self.level(asked)["level"], expected)

    def test_thresholds_at_100_80_50_and_20_percent(self):
        for share, expected in (("1.0", "full"), ("0.8", "substantial"), ("0.5", "partial"), ("0.2", "profile_miss")):
            self.assertEqual(cp.years_level(Decimal(share) * 10, Decimal(10)), expected)

    def test_overlapping_roles_count_once(self):
        both = copy.deepcopy(FACTS.companies)
        both["acme"]["roles"].append({"start": "2016-01", "end": "2019-12", "titles": [], "subtitles": [],
                                      "clients": [], "sources": []})
        months, owners = cp.months_covered(mf.ResumeFacts(both, FACTS.skills, [], []), TODAY)
        self.assertEqual(months, 72 + 61)
        self.assertEqual(owners[0], "globex")

    def test_skill_specific_years_are_left_unrated(self):
        for text in ("5 years of AWS experience.", "10+ years of experience in software development."):
            with self.subTest(text=text):
                self.assertNotIn("code:years", by_id(text))

    def test_no_years_named_gives_no_item(self):
        self.assertNotIn("code:years", by_id("Great culture."))


class ApplyCodeTests(unittest.TestCase):
    def test_code_level_replaces_claudes(self):
        data = request()
        data["requirements"][0].update(id="code:skill:aws", level="partial", evidence=["bullet:b1"],
                                       flag={"kind": "level", "readings": ["partial", "full"]})
        parsed = mr.parse_request(data, FACTS, me.BANDS)
        notes = cp.apply_code(parsed, cp.code_pass("Amazon Web Services is needed.", FACTS, TODAY))
        item = parsed.items[0]
        self.assertEqual((item.level, item.source, item.flag), ("full", "code", None))
        self.assertEqual(len(notes), 1)
        self.assertIn("pass 1 said partial", notes[0])

    def test_sentences_find_the_heading(self):
        parts = cp.sentences("About us\n\nQualifications:\n- Bachelor's degree\n- Python.\n")
        self.assertIn(("Bachelor's degree", "Qualifications"), parts)


if __name__ == "__main__":
    unittest.main()
