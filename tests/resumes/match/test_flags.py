"""Tests for plugins/jobkit/src/jk/resumes/match_flags.py: swings, fallbacks, the vague note and the assumption lines."""
import unittest
from decimal import Decimal

from jk.resumes import match_engine as me
from jk.resumes import match_flags as mfl
from jk.resumes import match_request as mr
from tests.resumes.match.support import facts, request

FACTS = facts()
WEIGHTS = me.BANDS["executive"]


def parsed(*flagged):
    """A request of one requirement per category; `flagged` maps an index to a flag."""
    cats = [("core_skills", "full"), ("impact", "full"), ("functional_leadership", "full"),
            ("people_leadership", "partial"), ("strategy", "substantial"), ("domain", "full"), ("education", "full")]
    reqs = [{"id": f"r{i}", "label": c, "quote": f"Posting sentence {i}.", "section": "", "category": c,
             "priority": "required", "level": lvl, "reason": "x",
             "evidence": ["skill:AWS"] if lvl != "profile_miss" else []} for i, (c, lvl) in enumerate(cats)]
    for index, flag in flagged:
        reqs[index]["flag"] = flag
    data = request(band="executive", requirements=reqs)
    return mr.parse_request(data, FACTS, me.BANDS)


LEVEL = {"kind": "level", "readings": ["partial", "substantial"]}


class FallbackTests(unittest.TestCase):
    def item(self, flag, section="", priority="required"):
        data = request()
        data["requirements"][0].update(flag=flag, section=section, priority=priority)
        return mr.parse_request(data, FACTS, me.BANDS).items[0]

    def test_level_takes_the_lower_reading(self):
        item = self.item({"kind": "level", "readings": ["substantial", "partial"]})
        self.assertEqual(mfl.fallback(item, item.flag), ("partial", "substantial"))

    def test_category_by_section_heading(self):
        item = self.item({"kind": "category", "readings": ["core_skills", "education"]}, section="Qualifications")
        self.assertEqual(mfl.fallback(item, item.flag)[0], "education")

    def test_category_without_a_helpful_heading_uses_the_fixed_order(self):
        item = self.item({"kind": "category", "readings": ["strategy", "functional_leadership"]}, section="About you")
        self.assertEqual(mfl.fallback(item, item.flag)[0], "functional_leadership")
        hinted = self.item({"kind": "category", "readings": ["strategy", "domain"]}, section="Strategy and goals")
        self.assertEqual(mfl.fallback(hinted, hinted.flag)[0], "strategy")

    def test_heading_that_names_neither_reading_is_ignored(self):
        item = self.item({"kind": "category", "readings": ["impact", "domain"]}, section="Qualifications")
        self.assertEqual(mfl.fallback(item, item.flag)[0], "impact")

    def test_unsettled_priority_takes_the_lower_one(self):
        item = self.item({"kind": "priority", "readings": ["critical", "preferred"]})
        self.assertEqual(mfl.fallback(item, item.flag), ("preferred", "critical"))


class SwingTests(unittest.TestCase):
    def build(self, *flagged):
        request_ = parsed(*flagged)
        reqs = mfl.build_requirements(request_)
        return request_, reqs, mfl.flag_infos(request_, reqs, WEIGHTS)

    def test_flagged_requirement_keeps_the_other_reading_for_the_upper_score(self):
        _, reqs, _ = self.build((3, LEVEL))
        self.assertEqual(reqs[3].reading.level, "partial")
        self.assertEqual(reqs[3].alt.level, "substantial")
        result = me.score(reqs, WEIGHTS)
        self.assertGreater(result.upper, result.lower)

    def test_small_swing_is_below_the_threshold(self):
        small = {"kind": "level", "readings": ["full", "substantial"]}    # education weighs .05: swing 1.25
        _, _, infos = self.build((6, small))
        self.assertFalse(infos[0].above)
        self.assertEqual(infos[0].swing, Decimal("1.25"))

    def test_large_swing_is_above_and_gains_points(self):
        _, _, infos = self.build((3, LEVEL))
        self.assertTrue(infos[0].above)
        self.assertEqual(infos[0].gain, Decimal(7))

    def test_biggest_swing_first_and_ties_keep_input_order(self):
        tie_a = {"kind": "level", "readings": ["profile_miss", "full"]}
        tie_b = {"kind": "level", "readings": ["profile_miss", "full"]}
        _, _, infos = self.build((6, tie_a), (5, tie_b), (4, {"kind": "level", "readings": ["profile_miss", "full"]}))
        self.assertEqual([i.id for i in infos], ["r4", "r5", "r6"])      # strategy .20, domain .20 (tie), education .05
        self.assertEqual(infos[0].swing, infos[1].swing)

    def test_vague_when_more_than_three_flags_are_large(self):
        big = {"kind": "level", "readings": ["profile_miss", "full"]}
        _, _, three = self.build((1, big), (3, big), (4, big))
        _, _, four = self.build((1, big), (3, big), (4, big), (5, big))
        self.assertFalse(mfl.is_vague(three))
        self.assertTrue(mfl.is_vague(four))

    def test_flag_that_cannot_raise_the_score_does_not_widen_the_range(self):
        category = {"kind": "category", "readings": ["core_skills", "people_leadership"]}
        request_, reqs, infos = self.build((0, category))
        result = me.score(reqs, WEIGHTS)
        self.assertGreaterEqual(result.upper, result.lower)
        self.assertEqual(infos[0].id, "r0")
        self.assertIsNotNone(request_)


class AssumptionTests(unittest.TestCase):
    def test_lines_name_the_sentence_and_the_points(self):
        request_ = parsed((3, LEVEL))
        reqs = mfl.build_requirements(request_)
        info = mfl.flag_infos(request_, reqs, WEIGHTS)[0]
        text = mfl.assumption(info, 7)
        self.assertIn('"Posting sentence 3"', text)
        self.assertIn("partly shown", text)
        self.assertIn("mostly shown", text)
        self.assertIn("up to 7 points higher", text)
        self.assertIn("hardly change", mfl.assumption(info, 0))
