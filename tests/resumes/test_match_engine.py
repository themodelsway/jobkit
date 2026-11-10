"""The match-score engine: arithmetic only (no database, no model)."""
import dataclasses
import random
import unittest
from decimal import Decimal
from unittest import mock

from jobkit.resumes import match_engine as me, match_report as mrep

D = Decimal
EXEC = me.BANDS["executive"]


def req(rid, category, level, priority="required", alt=None, importance="1"):
    """A requirement; `alt` is a level of the other reading (same category and priority)."""
    other = me.Reading(category, priority, alt) if alt else None
    return me.Requirement(rid, me.Reading(category, priority, level), D(importance), other)


def director(people="partial", people_alt="substantial", strategy="substantial", strategy_alt="full"):
    """The Director of Engineering worked example: one required requirement in each of the seven categories."""
    return [req("skills", "core_skills", "full"), req("impact", "impact", "full"),
            req("tech", "functional_leadership", "full"),
            req("people", "people_leadership", people, alt=people_alt),
            req("strategy", "strategy", strategy, alt=strategy_alt),
            req("domain", "domain", "full"), req("edu", "education", "full")]


class WorkedExampleTests(unittest.TestCase):
    def test_director_of_engineering(self):
        result = me.score(director(), EXEC)
        self.assertEqual((me.round1(result.lower), me.round1(result.upper), me.round1(result.coverage)),
                         (D("83.0"), D("95.0"), D("100.0")))

    def test_a_settled_flag_counts_the_same_in_both_scores(self):
        result = me.score(director(people="substantial", people_alt=None), EXEC)
        self.assertEqual((me.round1(result.lower), me.round1(result.upper)), (D("90.0"), D("95.0")))

    def test_flag_without_higher_reading_changes_nothing(self):
        result = me.score(director(people_alt=None, strategy_alt=None), EXEC)
        self.assertEqual(me.round1(result.lower), me.round1(result.upper))

    def test_swing_of_one_flag(self):
        self.assertEqual(me.round1(me.swing(director(), EXEC, "people")), D("7.0"))
        self.assertEqual(me.round1(me.swing(director(), EXEC, "strategy")), D("5.0"))


class LevelTests(unittest.TestCase):
    def one(self, level, **kw):
        return me.score([req("a", "core_skills", level, **kw)], me.BANDS["mid-senior-ic"])

    def test_every_level_gives_its_credit(self):
        for level, expected in (("full", "100.0"), ("substantial", "75.0"), ("partial", "40.0"),
                                ("profile_miss", "0.0")):
            with self.subTest(level=level):
                result = self.one(level)
                self.assertEqual((me.round1(result.lower), me.round1(result.upper)), (D(expected), D(expected)))

    def test_all_unknown(self):
        result = self.one("unknown")
        self.assertEqual((result.lower, result.upper, result.coverage), (0, 100, 0))

    def test_unknown_adds_its_share_of_the_category_to_the_upper_score(self):
        result = me.score([req("a", "core_skills", "full"), req("b", "core_skills", "unknown")],
                          me.BANDS["mid-senior-ic"])
        self.assertEqual((me.round1(result.lower), me.round1(result.upper), me.round1(result.coverage)),
                         (D("50.0"), D("100.0"), D("50.0")))

    def test_priority_weights_mix(self):
        result = me.score([req("a", "core_skills", "full", "critical"), req("b", "core_skills", "profile_miss",
                                                                              "preferred")], EXEC)
        self.assertEqual(me.round1(result.lower), D("75.0"))

    def test_importance_scales_the_weight(self):
        result = me.score([req("a", "core_skills", "full", importance="3"),
                           req("b", "core_skills", "profile_miss", importance="1")], EXEC)
        self.assertEqual(me.round1(result.lower), D("75.0"))


class CategoryTests(unittest.TestCase):
    def test_all_full_and_all_profile_miss(self):
        full = me.score(director("full", None, "full", None), EXEC)
        miss = me.score(director("profile_miss", None, "profile_miss", None), EXEC)
        self.assertEqual(me.round1(full.lower), D("100.0"))
        self.assertEqual(me.round1(miss.lower), D("60.0"))     # the five other categories keep their .60

    def test_missing_category_is_left_out_and_weights_rescale(self):
        result = me.score([req("a", "core_skills", "full"), req("b", "people_leadership", "profile_miss")],
                          me.BANDS["mid-manager"])
        self.assertIn("impact", result.left_out)
        self.assertEqual(me.round1(result.lower), D("37.5"))   # .15 of .40 total
        self.assertEqual(me.round1(result.categories["core_skills"].weight), D("0.4"))

    def test_zero_weight_category_is_noted_not_counted(self):
        result = me.score([req("a", "core_skills", "full"), req("mentor", "people_leadership", "profile_miss")],
                          me.BANDS["junior-ic"])
        self.assertEqual(result.not_counted, ["mentor"])
        self.assertEqual(me.round1(result.lower), D("100.0"))
        self.assertEqual(result.gaps["required"], [])
        self.assertNotIn("people_leadership", result.left_out)

    def test_only_zero_weight_categories_share_equally(self):
        result = me.score([req("a", "people_leadership", "full"), req("b", "strategy", "profile_miss")],
                          me.BANDS["junior-ic"])
        self.assertTrue(result.equal_weights)
        self.assertEqual(me.round1(result.lower), D("50.0"))
        self.assertEqual(result.not_counted, [])

    def test_many_requirements_do_not_dominate(self):
        many = [req(f"s{i}", "core_skills", "full") for i in range(30)] + [req("p", "impact", "profile_miss")]
        result = me.score(many, me.BANDS["mid-senior-ic"])
        self.assertEqual(me.round1(result.lower), D("54.5"))   # .30 of .55

    def test_empty_request_is_refused(self):
        with self.assertRaises(ValueError):
            me.score([], EXEC)


class RoundingTests(unittest.TestCase):
    def test_half_up_at_exactly_point_05(self):
        reqs = [req(f"s{i}", "core_skills", "substantial") for i in range(3)] + [req("p", "core_skills", "partial")]
        result = me.score(reqs, EXEC)
        self.assertEqual(result.lower, D("66.25"))
        self.assertEqual(me.round1(result.lower), D("66.3"))
        self.assertEqual(me.whole(D("62.5")), 63)

    def test_repeated_runs_are_identical(self):
        first = me.score(director(), EXEC).to_dict()
        for _ in range(100):
            self.assertEqual(me.score(director(), EXEC).to_dict(), first)


class BandTests(unittest.TestCase):
    def test_built_in_bands_are_valid(self):
        for name, weights in me.BANDS.items():
            with self.subTest(band=name):
                self.assertEqual(me.validate_band(name, weights), weights)

    def test_bad_bands_are_rejected_with_the_problem(self):
        ok = dict(EXEC)
        for label, change, text in (
                ("total", {"impact": D("0.24")}, "total"), ("negative", {"impact": D("-0.25"), "domain": D("0.70")},
                                                            "not negative"), ("unknown", {"colour": 0}, "unknown")):
            with self.subTest(label=label), self.assertRaises(ValueError) as caught:
                me.validate_band("x", {**ok, **change})
            self.assertIn(text, str(caught.exception))
        with self.assertRaises(ValueError):
            me.validate_band("x", {k: 0 for k in me.CATEGORIES})
        with self.assertRaises(ValueError):
            me.validate_band("x", {k: v for k, v in ok.items() if k != "impact"})

    def test_weights_totalling_099_are_rejected(self):
        with self.assertRaises(ValueError):
            me.validate_band("x", {**EXEC, "domain": D("0.19")})


class GapTests(unittest.TestCase):
    def test_lists_and_ordering(self):
        reqs = [req("r1", "core_skills", "partial"), req("c1", "core_skills", "substantial", "critical"),
                req("p1", "core_skills", "profile_miss", "preferred"), req("u1", "impact", "unknown"),
                req("r2", "core_skills", "profile_miss"), req("done", "core_skills", "full", "critical")]
        gaps = me.score(reqs, me.BANDS["mid-senior-ic"]).gaps
        self.assertEqual(gaps["critical"], ["c1"])                 # substantial critical is a gap
        self.assertEqual(gaps["required"], ["u1", "r1", "r2"])     # impact share beats the skills ones
        self.assertEqual(gaps["preferred"], ["p1"])
        self.assertEqual(gaps["unassessed"], ["u1"])

    def test_confidence_never_reaches_the_engine(self):
        self.assertNotIn("confidence", {f.name for f in dataclasses.fields(me.Requirement)})


def random_requests(seed):
    """Seeded random valid requirement lists."""
    rng = random.Random(seed)
    levels = ["full", "substantial", "partial", "profile_miss"]
    return [req(f"r{i}", rng.choice(me.CATEGORIES), rng.choice(levels), rng.choice(me.PRIORITIES),
                importance=str(rng.choice([1, 2, 3])))
            for i in range(rng.randint(1, 12))]


def monotonic(seed):
    """True when raising one requirement's credit never lowers a score and bounds stay in range."""
    rng = random.Random(seed)
    band = me.BANDS[rng.choice(me.BAND_ORDER)]
    reqs = random_requests(seed)
    before = me.score(reqs, band)
    for value in (before.lower, before.upper, before.coverage):
        if not 0 <= value <= 100:
            return False
    if before.lower > before.upper:
        return False
    chain = ["profile_miss", "partial", "substantial", "full"]
    index = rng.randrange(len(reqs))
    level = reqs[index].reading.level
    if level == "full":
        return True
    higher = me.Reading(reqs[index].reading.category, reqs[index].reading.priority, chain[chain.index(level) + 1])
    raised = [me.Requirement(r.id, higher if i == index else r.reading, r.importance) for i, r in enumerate(reqs)]
    after = me.score(raised, band)
    return after.lower >= before.lower and after.upper >= before.upper


class PropertyTests(unittest.TestCase):
    def test_bounds_and_monotonic_credit(self):
        for seed in range(300):
            self.assertTrue(monotonic(seed), seed)

    def test_property_fails_when_credit_is_subtracted(self):
        broken = dict(me.CREDITS, partial=D("-0.40"))
        with mock.patch.object(me, "CREDITS", broken):
            self.assertFalse(all(monotonic(seed) for seed in range(300)))


def requirement(rid: str, category: str, level: str, priority: str = "required") -> me.Requirement:
    return me.Requirement(rid, me.Reading(category, priority, level), D(1), None)


class MustHaveTests(unittest.TestCase):
    """L6: a critical requirement is never dropped by a zero category weight."""

    SENIOR = me.BANDS["senior-executive"]       # core skills have weight 0 in this band

    def test_missing_critical_skill_lowers_the_score_and_is_listed(self):
        reqs = [requirement("strategy", "strategy", "full"), requirement("core", "core_skills", "profile_miss", "critical")]
        result = me.score(reqs, self.SENIOR)
        self.assertLess(result.lower, D(100))
        self.assertNotIn("core", result.not_counted)
        self.assertEqual(result.unmet_critical, ["core"])
        self.assertEqual(result.to_dict()["unmet_critical"], ["core"])

    def test_met_critical_requirement_is_counted_but_not_listed_as_unmet(self):
        reqs = [requirement("strategy", "strategy", "full"), requirement("core", "core_skills", "full", "critical")]
        result = me.score(reqs, self.SENIOR)
        self.assertEqual(me.round1(result.lower), D("100.0"))
        self.assertEqual(result.unmet_critical, [])

    def test_required_zero_weight_requirement_is_still_noted_not_counted(self):
        reqs = [requirement("strategy", "strategy", "full"), requirement("core", "core_skills", "profile_miss")]
        result = me.score(reqs, self.SENIOR)
        self.assertEqual(me.round1(result.lower), D("100.0"))
        self.assertEqual(result.not_counted, ["core"])

    def test_unknown_critical_requirement_is_listed_as_unmet(self):
        reqs = [requirement("strategy", "strategy", "full"), requirement("core", "core_skills", "unknown", "critical")]
        self.assertEqual(me.score(reqs, self.SENIOR).unmet_critical, ["core"])

    def test_report_names_the_unmet_must_have_next_to_the_score(self):
        reqs = [requirement("strategy", "strategy", "full"), requirement("core", "core_skills", "profile_miss", "critical")]
        result = me.score(reqs, self.SENIOR)
        items = [{"id": "strategy", "label": "Strategy"}, {"id": "core", "label": "Core skill"}]
        body = mrep.build_body(items, result, {"band": "senior-executive", "band_reason": "vp"})
        text = "\n".join(mrep._score_block(body))        # pylint: disable=protected-access
        self.assertIn("Must-haves the profile does not show: Core skill", text)
        self.assertLess(text.index("Must-haves"), text.index("The lower number"))

    def test_swing_uses_the_same_adjusted_weights(self):
        reqs = [requirement("strategy", "strategy", "full"), requirement("core", "core_skills", "profile_miss", "critical")]
        self.assertEqual(me.swing(reqs, self.SENIOR, "core"), D(0))     # no alternative reading: nothing moves


if __name__ == "__main__":
    unittest.main()
