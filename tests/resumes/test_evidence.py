"""Tests for plugins/jobkit/src/jk/resumes/evidence.py: when a line counts as evidence of a skill (not_demonstrated,
confirm_use), and the one rule ranking, building and scoring share."""
import unittest
from typing import Any

from jk.resumes import build_resume as br
from jk.resumes import evidence
from jk.resumes import match_codepass as cp
from jk.resumes import query_resume as qr
from tests.resumes.match.support import MatchCase, facts, request, seed
from tests.resumes.support import line

OK, CONFIRM, DENIED = evidence.OK, evidence.CONFIRM_USE, evidence.NOT_DEMONSTRATED


def python_item(*bullets: dict[str, Any]) -> dict[str, Any]:
    """The code-pass item for Python when one company holds the given bullets."""
    fixture = facts()
    fixture.companies["acme"]["bullets"] = list(bullets)
    fixture.companies["acme-2"]["bullets"] = []
    return {i["id"]: i for i in cp.code_pass("Python is required.", fixture)}["code:skill:python"]


class UseStateTests(unittest.TestCase):
    def test_explicit_denials(self):
        for text in ("Never used Python in a job", "No production use of Python", "No experience with Python"):
            self.assertEqual(evidence.use_state(text, "Python"), DENIED, text)

    def test_training_wording_asks_for_confirmation(self):
        for text in ("Took a beginner course in Python", "Completed a Python bootcamp", "Python, coursework only"):
            self.assertEqual(evidence.use_state(text, "Python"), CONFIRM, text)

    def test_wording_that_is_neither(self):
        for text in ("Led a beginner-friendly Python workshop for ten engineers", "Self-taught Python at home, then "
                     "automated reports at work", "Built a Python service used by ten teams"):
            self.assertEqual(evidence.use_state(text, "Python"), OK, text)

    def test_denial_about_another_skill_does_not_count(self):
        text = "Did not use Java in production; built Python services"
        tagged = ["Java", "Python"]
        self.assertEqual(evidence.use_state(text, "Java", tagged), DENIED)
        self.assertEqual(evidence.use_state(text, "Python", tagged), OK)

    def test_denial_naming_no_skill_in_a_one_skill_line(self):
        self.assertEqual(evidence.use_state("No production use", "Python", ["Python"]), DENIED)

    def test_denial_naming_no_skill_in_a_two_skill_line_is_not_applied(self):
        self.assertEqual(evidence.use_state("No production use; built Python and Java tools", "Python",
                                            ["Python", "Java"]), OK)

    def test_denial_wins_over_training_in_one_clause(self):
        self.assertEqual(evidence.use_state("Took a Python course, never used Python at work", "Python"), DENIED)


class CodePassTests(unittest.TestCase):
    def test_denied_line_earns_nothing_and_is_listed(self):
        item = python_item(line("No production use of Python", id="a", skills=["Python"]))
        self.assertEqual(item["level"], "partial")
        self.assertIn("not demonstrated in your profile", item["reason"])
        self.assertIn("No production use of Python", item["set_aside"][0])

    def test_training_only_is_partial_and_cites_the_line(self):
        item = python_item(line("Completed a Python bootcamp", id="a", skills=["Python"]))
        self.assertEqual(item["level"], "partial")
        self.assertIn("read like training", item["reason"])
        self.assertTrue(any(ref.startswith("bullet:") for ref in item["evidence"]))
        self.assertIn("worth confirming", item["set_aside"][0])

    def test_training_plus_ordinary_line_rates_from_the_ordinary_line(self):
        item = python_item(line("Completed a Python bootcamp", id="a", skills=["Python"]),
                           line("Used Python for scripts", id="b", skills=["Python"]))
        self.assertEqual(item["level"], "substantial")
        self.assertEqual(len(item["set_aside"]), 1)

    def test_training_line_never_makes_two_mentions(self):
        item = python_item(line("Completed a Python bootcamp", id="a", skills=["Python"]),
                           line("Finished a Python tutorial", id="c", skills=["Python"]),
                           line("Used Python for scripts", id="b", skills=["Python"]))
        self.assertEqual(item["level"], "substantial")


class RankingAndBuildingTests(unittest.TestCase):
    def ctx(self):
        return qr.JdContext(qr.Counter({"Python": 1}), {"python"}, set(), {"d": 0.0, "t": 0.0, "o": 0.0}, 0.0)

    def test_ranking_keeps_training_and_drops_denial(self):
        denied = line("No production use of Python", id="d", skills=["Python"])
        training = line("Completed a Python bootcamp", id="t", skills=["Python"])
        ordinary = line("Used Python for reports", id="o", skills=["Python"])
        self.assertIsNone(qr.score_bullet(denied, self.ctx()))
        self.assertIsNotNone(qr.score_bullet(training, self.ctx()))
        self.assertIsNotNone(qr.score_bullet(ordinary, self.ctx()))

    def test_build_shows_training_but_not_denial(self):
        self.assertFalse(br.shows(line("No production use of Python", id="d", skills=["Python"]), "Python"))
        self.assertTrue(br.shows(line("Completed a Python bootcamp", id="t", skills=["Python"]), "Python"))
        self.assertTrue(br.shows(line("Used Python for reports", id="o", skills=["Python"]), "Python"))

    def test_other_skills_survive_a_denial_about_one(self):
        text = line("Did not use Java in production; built Python services", id="m", skills=["Java", "Python"])
        self.assertFalse(br.shows(text, "Java"))
        self.assertTrue(br.shows(text, "Python"))


class BuildListingTests(unittest.TestCase):
    def test_both_kinds_are_listed_with_the_line_text(self):
        company = {"name": "Acme", "bullets": [
            line("No production use of Python", id="d", skills=["Python"]),
            line("Completed a Python bootcamp", id="t", skills=["Python"]),
            line("Used Python for reports", id="o", skills=["Python"]),
            line("Did not use Java in production; built Python services", id="m", skills=["Java", "Python"])]}
        notes = br.set_aside_lines([company], ["Python", "Java"])
        text = "\n".join(notes)
        self.assertEqual(len(notes), 3, notes)      # the mixed line is only set aside for Java
        self.assertIn("not demonstrated in your profile", text)
        self.assertIn("reads like training", text)
        self.assertIn("Completed a Python bootcamp", text)
        self.assertNotIn("Used Python for reports", text)
        self.assertIn("Java: not demonstrated", text)

    def test_a_flagged_line_is_not_listed_here(self):
        company = {"name": "Acme", "bullets": [line("No use of Python", id="f", skills=["Python"], needs_review=True)]}
        self.assertEqual(br.set_aside_lines([company], ["Python"]), [])


class ReportTests(MatchCase):
    def edit(self, text: str):
        def change(companies):
            companies["acme"]["bullets"][0]["text"] = text
            companies["acme-2"]["bullets"] = []
        return change

    def run_with(self, text: str):
        seed(self.edit(text))
        data = request()
        data["requirements"][0]["id"] = "code:skill:aws"
        self.write_request(data)
        return self.run_json()

    def test_training_line_is_listed_as_an_assumption_and_nothing_is_asked(self):
        body = self.run_with("Completed an AWS bootcamp")
        row = next(r for r in body["requirements"] if r["id"] == "code:skill:aws")
        self.assertEqual(row["level"], "partial")
        notes = [a for a in body["assumptions"] if "reads like training" in a]
        self.assertEqual(len(notes), 1)
        self.assertNotIn("?", notes[0])

    def test_denied_line_is_listed_as_not_demonstrated(self):
        body = self.run_with("No production use of AWS")
        self.assertTrue(any("not demonstrated in your profile" in a for a in body["assumptions"]))


def python_facts(*bullets: dict[str, Any]):
    """Facts where one company holds the given bullets, all tagged Python."""
    fixture = facts()
    fixture.companies["acme"]["bullets"] = [{**b, "skills": ["Python"]} for b in bullets]
    fixture.companies["acme-2"]["bullets"] = []
    return fixture


def python_level(*bullets: dict[str, Any]) -> str:
    return {i["id"]: i for i in cp.code_pass("Python is required.", python_facts(*bullets))}["code:skill:python"]["level"]


class AdmissibleEvidenceTests(unittest.TestCase):
    """L5: one evidence rule for ranking, building and scoring."""

    def test_flagged_line_gives_no_credit(self):
        self.assertEqual(python_level(line("Wrote Python tools", id="a"), line("Python ETL jobs", id="b", needs_review=True)),
                         "substantial")                                    # one admissible line, not two

    def test_negated_line_gives_no_more_than_partial(self):
        self.assertEqual(python_level(line("No production use of Python; completed a Python introduction.", id="a")),
                         "partial")

    def test_one_strong_line_is_as_high_as_two_plain_mentions(self):
        strong = python_level(line("Cut report time 60% with Python automation", id="a", metrics=["60%"]))
        plain = python_level(line("Used Python for scripts", id="b"), line("Python for tests", id="c"))
        self.assertEqual(plain, "full")
        self.assertEqual(strong, "full")

    def test_reason_says_why_a_mentioned_skill_earned_no_credit(self):
        found = {i["id"]: i for i in cp.code_pass("Python is required.", python_facts(
            line("No production use of Python; completed an introduction.", id="a")))}
        self.assertIn("not demonstrated in your profile", found["code:skill:python"]["reason"])

    def test_one_plain_line_stays_substantial(self):
        self.assertEqual(python_level(line("Used Python for scripts", id="a")), "substantial")

    def test_ranking_ignores_a_negated_skill_line(self):
        ctx = qr.JdContext(qr.Counter({"Python": 1, "SQL": 1}), {"python", "sql"}, set(), {"n": 0.0, "p": 0.0}, 0.0)
        negated = line("No production use of Python or SQL; completed an introduction.", id="n", skills=["Python", "SQL"])
        plain = line("Used Python and SQL for reports", id="p", skills=["Python", "SQL"])
        self.assertIsNone(qr.score_bullet(negated, ctx))
        self.assertIsNotNone(qr.score_bullet(plain, ctx))

    def test_an_ignored_line_is_not_admissible(self):
        self.assertFalse(evidence.admissible(line("x", ignored=True)))


class EvidenceEdgeCaseTests(unittest.TestCase):
    """Fixes from the 2026-11-09 adversarial review."""

    def result(self, ranked, need):
        from unittest import mock
        return mock.Mock(ranked=ranked, need=qr.Counter(need), covered=set(need), skills={"groups": {}})

    def test_negated_downtime_is_not_a_denial(self):
        for text in ("Deployed Python services without production downtime", "Ran Python jobs with no production outages"):
            self.assertEqual(evidence.use_state(text, "Python", ["Python"]), OK, text)
        for text in ("Without production experience in Python", "No professional use of Python", "Not any work experience"):
            self.assertEqual(evidence.use_state(text, "Python", ["Python"]), DENIED, text)

    def test_alias_in_a_denial_clause_applies_to_its_skill(self):
        text = "Never used k8s in production; built Python services reducing latency by 40%"
        terms = {"Kubernetes": "Kubernetes", "k8s": "Kubernetes", "Python": "Python"}
        self.assertEqual(evidence.use_state(text, "Kubernetes", ["Kubernetes", "Python"], terms), DENIED)
        self.assertEqual(evidence.use_state(text, "Python", ["Kubernetes", "Python"], terms), OK)

    def test_denied_tag_is_not_counted_as_shown(self):
        denied = line("Did not use Java in production; built Python services", skills=["Java", "Python"])
        self.assertEqual(br.shown_skills([({}, [denied])], ["Java"]), {"Python"})  # type: ignore[list-item]

    def test_old_employer_cap_holds_during_coverage_repair(self):
        company = {"id": "old", "name": "Old", "roles": [{"end": "2015"}], "bullets": []}
        texts = {"Python": "Built Python automation for billing reconciliation", "Kubernetes":
                 "Operated Kubernetes clusters for streaming workloads", "SQL": "Tuned SQL warehouse queries for finance reports"}
        bullets = [line(t, id=k, skills=[k]) for k, t in texts.items()]
        scored = [qr.ScoredBullet(1.0, b, []) for b in bullets]
        result = self.result([(company, scored)], dict.fromkeys(texts, 1))
        chosen = br.choose_experience(result, br.BuildOptions())
        self.assertLessEqual(len(chosen[0][1]), br.OLD_COMPANY_BULLETS)

    def test_total_limit_below_the_minimum_is_rejected(self):
        from jk import common
        companies = [{"id": i, "name": i, "roles": [{"end": None}], "bullets": []} for i in ("a", "b")]
        texts = {"a": "Migrated billing databases to a managed cloud platform", "b": "Mentored junior engineers through code review"}
        ranked = [(c, [qr.ScoredBullet(1.0, line(texts[c["id"]], id=c["id"]), [])]) for c in companies]
        with self.assertRaises(common.ToolError):
            br.choose_experience(self.result(ranked, {}), br.BuildOptions(max_bullets=1))
