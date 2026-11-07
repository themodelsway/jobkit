"""The plain-language match-score report."""
import re
import unittest
from decimal import Decimal

from jobkit.resumes import match_engine as me
from jobkit.resumes import match_report as rep

D = Decimal


def make(levels, band="mid-manager", assumptions=(), vague=False):
    """A report body for requirements given as (id, category, priority, level)."""
    reqs = [me.Requirement(i, me.Reading(c, p, lv)) for i, c, p, lv in levels]
    result = me.score(reqs, me.BANDS[band])
    rows = [{"id": i, "label": f"Label {i}", "reason": "Because.", "related": "ran a platform", "evidence_text": ["A line."]}
            for i, *_ in levels]
    meta = {"label": "Test posting", "band": band, "band_reason": "duties", "assumptions": list(assumptions), "vague": vague}
    return rep.build_body(rows, result, meta)


class ReportTests(unittest.TestCase):
    def test_gaps_then_matches_then_scores_then_caveat(self):
        text = rep.report(make([("a", "core_skills", "critical", "partial"), ("b", "impact", "required", "full")]))
        order = [text.index(x) for x in ("Must-haves that are not fully shown", "Where your profile shows it",
                                         "How well your profile matches", "It is not any employer's")]
        self.assertEqual(order, sorted(order))
        self.assertTrue(text.rstrip().endswith(rep.CAVEAT))
        self.assertIn("experimental", rep.CAVEAT)

    def test_whole_numbers_with_lower_and_upper_together(self):
        text = rep.report(make([("a", "core_skills", "required", "full"), ("b", "impact", "required", "unknown")]))
        self.assertRegex(text, r"about \d+ to \d+ out of 100")

    def test_profile_miss_uses_the_agreed_words_and_never_says_lack(self):
        text = rep.report(make([("a", "core_skills", "required", "profile_miss")]))
        self.assertIn("not shown in your profile yet", text)
        self.assertIn("Related experience, not counted: ran a platform", text)
        self.assertIsNone(re.search(r"\b(lack|lacks|missing capability|not demonstrated)\b", text, re.I))

    def test_low_coverage_is_labelled_not_precise(self):
        text = rep.report(make([("a", "core_skills", "required", "unknown")]))
        self.assertIn("treat the score as not precise", text)
        self.assertNotIn("not precise", rep.report(make([("a", "core_skills", "required", "full")])))

    def test_zero_weight_requirements_are_noted_not_counted(self):
        text = rep.report(make([("a", "core_skills", "required", "full"), ("m", "people_leadership", "required",
                                                                           "profile_miss")], band="junior-ic"))
        self.assertIn("Noted, not counted at this level:\n- Label m", text)
        self.assertNotIn("Required items not fully shown", text)

    def test_left_out_categories_assumptions_and_vague_note(self):
        text = rep.report(make([("a", "core_skills", "required", "full")], assumptions=["I assumed X."], vague=True))
        self.assertIn("The posting did not ask about:", text)
        self.assertIn("What I assumed:\n- I assumed X.", text)
        self.assertIn("vague in several places", text)

    def test_equal_weights_are_explained(self):
        text = rep.report(make([("a", "people_leadership", "required", "full")], band="junior-ic"))
        self.assertIn("weighted equally", text)

    def test_never_calls_it_an_ats_score(self):
        text = rep.report(make([("a", "core_skills", "required", "full")]))
        self.assertNotIn("ATS", text)
        self.assertNotIn("ats ", text.lower().replace("stats ", ""))


if __name__ == "__main__":
    unittest.main()
