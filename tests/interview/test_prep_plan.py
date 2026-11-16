"""Tests for plugins/jobkit/src/jk/interview/prep_plan.py: synthetic data only, no database."""
import unittest
from datetime import date, timedelta

from jk.common import ToolError
from jk.interview import prep_plan as pp

TODAY = date(2026, 6, 30)
C = pp.Competency


def vocab():
    return (C("containers", "Containers", "technical"),
            C("kubernetes", "Kubernetes", "technical", aliases=("k8s",), requires=("containers",),
              related=("ecs",)),
            C("ecs", "ECS", "technical", requires=("containers",), related=("kubernetes",)),
            C("feedback", "Giving feedback", "leadership"),
            C("negotiation", "Negotiation", "general"))


def snap(**kw):
    base = {"vocabulary": vocab(), "facts": (), "stories": (), "attempts": (), "self_rated": {}}
    base.update(kw)
    return pp.Snapshot(**base)


def attempt(aid, cid, days_ago, grade, kind="drill"):
    return pp.Attempt(aid, cid, TODAY - timedelta(days=days_ago), kind, grade)


def story(sid, eng, cids, done=True, ownership="own", facts=()):
    return pp.Story(sid, eng, tuple(cids), done, ownership, tuple(facts))


def fact(eng, fid, cids, status="confirmed", ownership="own"):
    return pp.Fact(eng, fid, tuple(cids), status, ownership)


def first(actions, cid=None, kind=None):
    rows = [a for a in actions if (cid is None or a.competency == cid) and (kind is None or a.type == kind)]
    return rows[0] if rows else None


class VocabularyTests(unittest.TestCase):
    def test_seed_is_valid(self):
        pp.check_vocabulary(pp.SEED)
        self.assertEqual({c.kind for c in pp.SEED}, {"technical", "leadership", "general"})

    def test_cycle_rejected(self):
        bad = (C("a", "A", "technical", requires=("b",)), C("b", "B", "technical", requires=("a",)))
        with self.assertRaises(ToolError) as ctx:
            pp.check_vocabulary(bad)
        self.assertIn("a", str(ctx.exception))
        self.assertIn("b", str(ctx.exception))

    def test_alias_with_two_targets_rejected(self):
        bad = (C("a", "A", "technical", aliases=("x",)), C("b", "B", "technical", aliases=("x",)))
        with self.assertRaises(ToolError):
            pp.check_vocabulary(bad)

    def test_unknown_reference_rejected(self):
        with self.assertRaises(ToolError):
            pp.check_vocabulary((C("a", "A", "technical", requires=("zzz",)),))

    def test_alias_resolves_related_does_not(self):
        self.assertEqual(pp.resolve(vocab(), "K8S").id, "kubernetes")
        self.assertEqual(pp.resolve(vocab(), "kubernetes").id, "kubernetes")
        self.assertIsNone(pp.resolve(vocab(), "ecs-and-kubernetes"))
        self.assertEqual(pp.resolve(vocab(), "ECS").id, "ecs")


class PriorityTests(unittest.TestCase):
    def test_category_order_and_stable_ties(self):
        s = snap(facts=(fact("e1", "f1", ["feedback"], status="unsure"),),
                 attempts=(attempt("a1", "containers", 1, 0), attempt("a2", "ecs", 40, 2),
                           attempt("a3", "kubernetes", 1, 2), attempt("a4", "negotiation", 1, 2)))
        kinds = [(a.type, a.competency) for a in pp.plan(s, TODAY)]
        self.assertEqual(kinds[0], ("clarify_fact", "feedback"))
        self.assertLess(kinds.index(("practise_concept", "containers")), kinds.index(("reassess", "ecs")))

    def test_focus_reorders_only_within_category(self):
        s = snap(facts=(fact("e1", "f1", ["feedback"], status="unsure"),))
        plan = pp.plan(s, TODAY, focus=("negotiation",))
        self.assertEqual(plan[0].type, "clarify_fact")
        gaps = [a.competency for a in plan if a.reason_code == "profile_gap"]
        self.assertEqual(gaps[0], "negotiation")


class ClarifyTests(unittest.TestCase):
    def test_unsure_fact_gives_question_not_experience(self):
        s = snap(facts=(fact("e1", "f1", ["feedback"], status="unsure"),))
        a = first(pp.plan(s, TODAY), "feedback")
        self.assertEqual((a.type, a.reason_code), ("clarify_fact", "fact_unconfirmed"))
        self.assertIn("fact:e1/f1", a.evidence)
        self.assertEqual(pp.experience(s, "feedback").engagements, ())

    def test_unclear_story_ownership(self):
        s = snap(stories=(story("s1", "e1", ["feedback"], ownership="unclear"),))
        a = first(pp.plan(s, TODAY), "feedback")
        self.assertEqual((a.type, a.reason_code), ("clarify_fact", "ownership_unclear"))
        self.assertEqual(pp.experience(s, "feedback").engagements, ())

    def test_team_outcome_is_not_personal_experience(self):
        s = snap(facts=(fact("e1", "f1", ["feedback"], ownership="team"),))
        self.assertEqual(first(pp.plan(s, TODAY), "feedback").type, "clarify_fact")


class PrerequisiteTests(unittest.TestCase):
    def test_unmet_prerequisite_is_taught_first(self):
        a = first(pp.plan(snap(), TODAY), kind="teach_prerequisite")
        self.assertEqual((a.competency, a.target), ("containers", "ecs"))
        self.assertEqual(a.reason_code, "prerequisite_unmet")

    def test_met_prerequisite_gives_no_teach_action(self):
        s = snap(attempts=(attempt("q1", "containers", 2, 1, kind="quiz"),))
        self.assertIsNone(first(pp.plan(s, TODAY), kind="teach_prerequisite"))

    def test_known_target_ignores_prerequisite(self):
        s = snap(attempts=(attempt("a1", "kubernetes", 1, 2),))
        a = first(pp.plan(s, TODAY), "kubernetes")
        self.assertIsNone(a)


class StoryTests(unittest.TestCase):
    def test_weak_answer_with_finished_story(self):
        s = snap(stories=(story("s1", "e1", ["negotiation"], done=True),),
                 attempts=(attempt("a1", "negotiation", 3, 0),))
        a = first(pp.plan(s, TODAY), "negotiation")
        self.assertEqual((a.type, a.reason_code), ("rehearse_story", "weak_with_story"))
        self.assertIn("story:s1", a.evidence)
        self.assertIn("attempt:a1", a.observations)

    def test_later_weak_attempt_wins_over_earlier_success(self):
        s = snap(attempts=(attempt("a1", "negotiation", 20, 2), attempt("a2", "negotiation", 2, 0)))
        self.assertEqual(first(pp.plan(s, TODAY), "negotiation").reason_code, "weak")

    def test_two_stories_one_engagement_count_once(self):
        s = snap(stories=(story("s1", "e1", ["negotiation"]), story("s2", "e1", ["negotiation"])))
        self.assertEqual(pp.experience(s, "negotiation").engagements, ("e1",))
        a = first(pp.plan(s, TODAY), "negotiation")
        self.assertEqual(set(a.choices), {"s1", "s2"})

    def test_transferable_not_direct(self):
        s = snap(stories=(story("s1", "e1", ["ecs"]),),
                 attempts=(attempt("q1", "containers", 1, 1, kind="quiz"),))
        a = first(pp.plan(s, TODAY), "kubernetes")
        self.assertEqual(a.type, "rehearse_story")
        self.assertTrue(a.transferable)
        direct = first(pp.plan(s, TODAY), "ecs")
        self.assertFalse(direct.transferable)


class KnowledgeTests(unittest.TestCase):
    def test_quiz_without_work_evidence(self):
        s = snap(attempts=(attempt("q1", "negotiation", 1, 1, kind="quiz"),))
        a = first(pp.plan(s, TODAY), "negotiation")
        self.assertEqual((a.type, a.reason_code), ("clarify_fact", "profile_gap"))
        self.assertEqual(pp.experience(s, "negotiation").engagements, ())
        self.assertTrue(pp.knows(s, "negotiation"))

    def test_quiz_does_not_change_the_gap_reason(self):
        quizzed = snap(attempts=(attempt("q1", "negotiation", 1, 1, kind="quiz"),))
        plain = snap()
        self.assertEqual(first(pp.plan(quizzed, TODAY), "negotiation").reason_code,
                         first(pp.plan(plain, TODAY), "negotiation").reason_code)

    def test_only_coarse_confidence_is_a_gap_not_a_grade(self):
        s = snap(self_rated={"negotiation": 1})
        a = first(pp.plan(s, TODAY), "negotiation")
        self.assertEqual((a.reason_code, a.self_rated), ("profile_gap", 1))
        self.assertEqual(pp.graded(s, "negotiation"), [])

    def test_recorded_experience_without_drill_is_untested(self):
        s = snap(facts=(fact("e1", "f1", ["negotiation"]),))
        a = first(pp.plan(s, TODAY), "negotiation")
        self.assertEqual((a.type, a.reason_code), ("practise_concept", "untested"))

    def test_gap_wording_never_says_no_experience(self):
        a = first(pp.plan(snap(), TODAY), "negotiation")
        self.assertIn("recorded", a.reason)
        self.assertNotIn("no experience", a.reason.lower())

    def test_gap_is_not_a_blocker_or_ahead_of_prerequisites(self):
        kinds = [(a.type, a.competency) for a in pp.plan(snap(), TODAY)]
        self.assertLess(kinds.index(("teach_prerequisite", "containers")), kinds.index(("clarify_fact", "negotiation")))

    def test_gap_comes_before_plain_untested(self):
        s = snap(facts=(fact("e1", "f1", ["feedback"]),))
        codes = [a.reason_code for a in pp.plan(s, TODAY) if a.reason_code in ("profile_gap", "untested")]
        self.assertEqual(codes, sorted(codes, key=lambda c: c != "profile_gap"))
        self.assertIn("untested", codes)

    def test_weak_answer_outranks_gap_reason(self):
        s = snap(attempts=(attempt("a1", "negotiation", 2, 0),))
        self.assertEqual(first(pp.plan(s, TODAY), "negotiation").reason_code, "weak")


class LeadTests(unittest.TestCase):
    def test_lead_is_carried_and_counts_no_experience(self):
        s = snap(leads=(pp.Lead("negotiation", "bullet:b1"),))
        a = first(pp.plan(s, TODAY), "negotiation")
        self.assertEqual((a.type, a.reason_code, a.leads), ("clarify_fact", "profile_gap", ("bullet:b1",)))
        self.assertEqual(pp.experience(s, "negotiation").engagements, ())

    def test_no_lead_carries_none(self):
        self.assertEqual(first(pp.plan(snap(), TODAY), "negotiation").leads, ())

    def test_lead_does_not_change_reason_or_order(self):
        with_lead = pp.plan(snap(leads=(pp.Lead("negotiation", "bullet:b1"),)), TODAY)
        without = pp.plan(snap(), TODAY)
        self.assertEqual([(a.type, a.competency, a.reason_code) for a in with_lead],
                         [(a.type, a.competency, a.reason_code) for a in without])


class NoExpiryTests(unittest.TestCase):
    def test_old_quiz_pass_still_satisfies_a_prerequisite(self):
        s = snap(attempts=(attempt("q1", "containers", 400, 1, kind="quiz"),))
        self.assertIsNone(first(pp.plan(s, TODAY), "containers", "teach_prerequisite"))
        self.assertTrue(pp.knows(s, "containers"))

    def test_old_good_drill_is_reassessed_and_still_known(self):
        s = snap(attempts=(attempt("a1", "negotiation", 400, 2),))
        a = first(pp.plan(s, TODAY), "negotiation")
        self.assertEqual((a.type, a.age_days), ("reassess", 400))
        self.assertTrue(pp.knows(s, "negotiation"))


class ReassessTests(unittest.TestCase):
    def test_forty_day_old_good_answer(self):
        s = snap(attempts=(attempt("a1", "negotiation", 40, 2),))
        a = first(pp.plan(s, TODAY), "negotiation")
        self.assertEqual((a.type, a.age_days), ("reassess", 40))

    def test_window_is_a_parameter(self):
        s = snap(attempts=(attempt("a1", "negotiation", 40, 2),))
        self.assertIsNone(first(pp.plan(s, TODAY, reassess_days=60), "negotiation"))

    def test_fresh_good_answer_needs_nothing(self):
        s = snap(attempts=(attempt("a1", "negotiation", 5, 2),))
        self.assertIsNone(first(pp.plan(s, TODAY), "negotiation"))


class DeterminismTests(unittest.TestCase):
    def test_same_input_same_plan(self):
        s = snap(stories=(story("s1", "e1", ["negotiation"]),), attempts=(attempt("a1", "ecs", 3, 0),))
        self.assertEqual(pp.plan(s, TODAY), pp.plan(s, TODAY))

    def test_reasons_use_plain_words(self):
        s = snap(stories=(story("s1", "e1", ["negotiation"]),), attempts=(attempt("a1", "negotiation", 3, 0),))
        for a in pp.plan(s, TODAY):
            for word in ("id", "json", "database", "confidence"):
                self.assertNotIn(f" {word} ", f" {a.reason.lower()} ")
