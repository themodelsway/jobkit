"""Tests for the logic-review fixes (change fix-logic-review-findings), one class per finding.
Run: .venv/bin/python -m unittest discover -s tests -t ."""
import contextlib
import dataclasses
import io
import json
import unittest
from datetime import date
from decimal import Decimal
from typing import Any
from unittest import mock

from jobkit.common import ToolError
from jobkit.interview import lead, sessions
from jobkit.interview import tables as itables
from jobkit.resumes import build_resume as br
from jobkit.resumes import evidence
from jobkit.resumes import match_codepass as cp
from jobkit.resumes import match_engine as me
from jobkit.resumes import match_facts as mf
from jobkit.resumes import match_report as mrep
from jobkit.resumes import match_request as mr
from jobkit.resumes import match_score as ms
from jobkit.resumes import match_tables
from jobkit.resumes import parse_resume as pr
from jobkit.resumes import process_resumes as proc
from jobkit.resumes import query_resume as qr
from jobkit.resumes import resume_data as rd
from jobkit.resumes import tables
from tests.interview.test_sessions import SessionCase
from tests.resumes.match_fixtures import facts, request
from tests.resumes.test_match_codepass import FACTS
from tests.resumes.test_match_score import MatchCase, seed
from tests.support import HomeCase


def role(start: str, end: str | None, title: str) -> dict[str, Any]:
    """A stored role."""
    return {"start": start, "end": end, "titles": [title], "subtitles": [], "clients": [], "sources": ["a"]}


def line(text: str, role_start: str | None = None, **extra: Any) -> dict[str, Any]:
    """A stored bullet."""
    return {"id": text[:8], "text": text, "role_start": role_start, "skills": [], "themes": [], "metrics": [],
            "sources": ["a"], **extra}


class RoleRenderingTests(unittest.TestCase):
    """L1: each role keeps its own title and dates; the gap stays visible."""

    def render(self, company: dict[str, Any], picks: list[dict[str, Any]], titles: dict[str, str] | None = None) -> str:
        options = br.BuildOptions(titles=titles or {})
        return "\n".join(br.render_experience(None, options, [(company, picks)]))   # type: ignore[arg-type]

    def company(self) -> dict[str, Any]:
        return {"id": "acme", "name": "Acme", "aliases": [], "bullets": [],
                "roles": [role("2020-01", "2021-01", "Analyst"), role("2023-01", None, "Manager")]}

    def test_promotion_keeps_two_dated_roles_and_the_gap(self):
        out = self.render(self.company(), [line("Led a team of six", "2023-01"), line("Built the weekly report", "2020-01")])
        self.assertIn("Manager | 01/2023 - Present", out)
        self.assertIn("Analyst | 01/2020 - 01/2021", out)
        self.assertNotIn("01/2020 - Present", out)
        self.assertLess(out.index("Led a team of six"), out.index("Analyst"))        # newest role first
        self.assertLess(out.index("Analyst"), out.index("Built the weekly report"))   # bullet sits under its role

    def test_title_override_applies_to_latest_role_only(self):
        out = self.render(self.company(), [line("Led a team of six", "2023-01"), line("Built the weekly report", "2020-01")],
                          {"acme": "Head of Data"})
        self.assertIn("Head of Data | 01/2023 - Present", out)
        self.assertIn("Analyst | 01/2020 - 01/2021", out)

    def test_bullet_without_a_role_goes_under_the_latest_role(self):
        out = self.render(self.company(), [line("Mystery bullet", None)])
        self.assertIn("Manager | 01/2023 - Present", out)
        self.assertNotIn("Analyst", out)
        self.assertEqual(br.unplaced([(self.company(), [line("Mystery bullet", None)])]), 1)

    def test_employer_with_no_bullet_keeps_its_latest_role_line(self):
        out = self.render(self.company(), [])
        self.assertIn("### Acme", out)
        self.assertIn("Manager | 01/2023 - Present", out)
        self.assertNotIn("Analyst", out)

    def test_title_override_applies_to_employer_with_no_bullet(self):
        out = self.render(self.company(), [], {"acme": "Head of Data"})
        self.assertIn("Head of Data | 01/2023 - Present", out)

    def test_build_names_the_employer_with_no_bullet(self):
        company = self.company()
        with mock.patch.object(br.qr, "analyze") as analyze, \
                mock.patch.object(br, "choose_experience", return_value=[(company, [])]):
            analyze.return_value = mock.MagicMock(summaries=[], need=[], covered=[], hidden=0, possible=[],
                                                  ranked=[(company, [])], profile=rd.empty_profile(), skills={"groups": {}})
            md, notes = br.build("jd", br.BuildOptions(), header="# A\nB")
        self.assertEqual(notes.no_bullets, ["Acme"])
        self.assertIn("Manager | 01/2023 - Present", md)

    def test_only_roles_with_bullets_are_shown(self):
        out = self.render(self.company(), [line("Led a team of six", "2023-01")])
        self.assertNotIn("Analyst", out)


class CredentialsTests(unittest.TestCase):
    """L9: every education entry is kept; relevant projects get their own section."""

    def profile(self, education: list[str], projects: list[str]) -> dict[str, Any]:
        return {"summaries": [], "profile_points": [], "education": education, "certifications": [],
                "projects": projects}

    def test_both_degrees_are_listed(self):
        out = "\n".join(br.render_credentials(self.profile(["BSc Physics, State University", "MBA, City College"], []),
                                              {"Python": 1}))
        self.assertIn("BSc Physics, State University", out)
        self.assertIn("MBA, City College", out)

    def test_relevant_project_gets_a_section_and_others_do_not(self):
        projects = ["Open source Python library for survey weights", "Community garden volunteer scheduling"]
        out = "\n".join(br.render_credentials(self.profile(["BSc Physics"], projects), {"Python": 1}))
        self.assertIn("## Projects", out)
        self.assertIn("Open source Python library", out)
        self.assertNotIn("Community garden", out)

    def test_no_relevant_project_means_no_section(self):
        out = "\n".join(br.render_credentials(self.profile(["BSc Physics"], ["Community garden volunteer scheduling"]),
                                              {"Python": 1}))
        self.assertNotIn("## Projects", out)


def python_facts(*bullets: dict[str, Any]):
    """Facts where one company holds the given bullets, all tagged Python."""
    fixture = facts()
    fixture.companies["acme"]["bullets"] = [{**b, "skills": ["Python"]} for b in bullets]
    fixture.companies["globex"]["bullets"] = []
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

    def test_phrases(self):
        self.assertEqual(evidence.use_state("Never used Python in a job", "Python"), evidence.NOT_DEMONSTRATED)
        self.assertEqual(evidence.use_state("Took a beginner course in Python", "Python"), evidence.CONFIRM_USE)
        self.assertEqual(evidence.use_state("Built a Python service used by ten teams", "Python"), evidence.OK)
        self.assertFalse(evidence.admissible(line("x", ignored=True)))


class ContestTests(unittest.TestCase):
    """L5: a reviewer can contest a code level with a reason."""

    def parse(self, contest: dict[str, Any] | None):
        data = request()
        data["requirements"][0].update({"id": "code:skill:aws", "level": "full"})
        if contest is not None:
            data["requirements"][0]["contest"] = contest
        return mr.parse_request(data, FACTS, me.BANDS)

    def test_contest_replaces_the_level_and_keeps_both_in_the_report(self):
        req = self.parse({"level": "partial", "reason": "both lines are old coursework"})
        notes = cp.apply_code(req, cp.code_pass("Strong Amazon Web Services skills.", FACTS))
        entry = req.items[0]
        self.assertEqual(entry.level, "partial")
        self.assertEqual(entry.code_level, "full")
        self.assertIn("both lines are old coursework", entry.reason)
        self.assertEqual(entry.source, "code, contested")
        self.assertTrue(any("contested" in n for n in notes))

    def test_uncontested_code_level_stands(self):
        req = self.parse(None)
        cp.apply_code(req, cp.code_pass("Strong Amazon Web Services skills.", FACTS))
        self.assertEqual(req.items[0].level, "full")
        self.assertIsNone(req.items[0].code_level)

    def test_contest_needs_a_reason(self):
        with self.assertRaises(ToolError):
            self.parse({"level": "partial"})


D = Decimal


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


def degrees(posting: str, *education: str) -> dict[str, dict[str, Any]]:
    held = dataclasses.replace(facts(), education=list(education))
    return {i["id"]: i for i in cp.code_pass(posting, held) if i["kind"] == "degree"}


class DegreeFieldTests(unittest.TestCase):
    """L7: the whole field is compared, not one shared word."""

    def test_political_science_is_not_computer_science(self):
        item = degrees("Bachelor degree in Computer Science.", "Bachelor of Political Science, State U")["code:degree:1"]
        self.assertEqual(item["level"], "partial")

    def test_same_field_is_full(self):
        item = degrees("Bachelor degree in Computer Science.", "BSc Computer Science, State U")["code:degree:1"]
        self.assertEqual(item["level"], "full")

    def test_related_field_is_substantial(self):
        item = degrees("Bachelor degree in Computer Science.", "Bachelor of Software Engineering, State U")["code:degree:1"]
        self.assertEqual(item["level"], "substantial")

    def test_two_different_same_level_degrees_are_rated_separately(self):
        found = degrees("Bachelor degree in Finance. Also a bachelor degree in Law.",
                        "Bachelor of Finance, A", "Bachelor of Politics, B")
        self.assertEqual(sorted(found), ["code:degree:1", "code:degree:1:law"])
        self.assertEqual(found["code:degree:1"]["level"], "full")
        self.assertEqual(found["code:degree:1:law"]["level"], "partial")

    def test_no_field_named_stays_full_at_the_level(self):
        self.assertEqual(degrees("A bachelor degree is required.", "Bachelor of Arts")["code:degree:1"]["level"], "full")


def fingerprint_after(change) -> str:
    fixture = facts()
    change(fixture.companies["acme"]["bullets"][0])
    return mf.resume_fingerprint(fixture)


class CacheKeyTests(MatchCase):
    """L8: every scoring input is in the cache key, and an earlier result is kept."""

    def test_each_evidence_input_changes_the_resume_fingerprint(self):
        base = mf.resume_fingerprint(facts())
        changes = {"needs_review": lambda b: b.update(needs_review=True), "ignored": lambda b: b.update(ignored=True),
                   "skill tag": lambda b: b["skills"].append("Python"),
                   "manual tag": lambda b: b.update(skills_manual=["Python"])}
        seen = {base}
        for name, change in changes.items():
            with self.subTest(name):
                value = fingerprint_after(change)
                self.assertNotIn(value, seen)
                seen.add(value)
        self.assertEqual(fingerprint_after(lambda b: None), base)

    def test_tag_order_does_not_change_the_fingerprint(self):
        one = fingerprint_after(lambda b: b.update(skills=["AWS", "Python"]))
        two = fingerprint_after(lambda b: b.update(skills=["Python", "AWS"]))
        self.assertEqual(one, two)

    def test_a_flagged_line_means_the_old_result_is_not_returned(self):
        first = self.run_json()["key"]
        seed(lambda c: c["acme"]["bullets"][0].update(needs_review=True))
        self.assertFalse(json.loads(self.cli("extract", "--jd", self.posting)[1])["cached"])
        self.assertNotEqual(self.run_json()["key"], first)

    def test_a_later_day_means_the_old_result_is_not_returned(self):
        with mock.patch.object(ms, "today", return_value=date(2026, 1, 1)):
            self.run_json()
            self.assertTrue(json.loads(self.cli("extract", "--jd", self.posting)[1])["cached"])
        with mock.patch.object(ms, "today", return_value=date(2026, 2, 1)):
            self.assertFalse(json.loads(self.cli("extract", "--jd", self.posting)[1])["cached"])

    def test_another_band_keeps_the_earlier_result_as_history(self):
        first = self.run_json()
        second = self.run_json("--band", "executive")
        self.assertNotEqual(first["key"], second["key"])
        rows = match_tables.list_results()
        self.assertEqual({r["band"] for r in rows}, {"mid-manager", "executive"})
        self.assertEqual(json.loads(self.cli("extract", "--jd", self.posting)[1])["report"].count("Level of the role"), 1)

    def test_same_inputs_the_same_day_reuse_one_row(self):
        with mock.patch.object(ms, "today", return_value=date(2026, 1, 1)):
            self.assertEqual(self.run_json()["key"], self.run_json()["key"])
        self.assertEqual(len(match_tables.list_results()), 1)


class ShortSkillNameTests(unittest.TestCase):
    """L2: short names are recognised as whole words, and only where they are the skill."""

    TERMS = pr.skill_terms({"Languages": [{"name": "R", "aliases": []}, {"name": "Go", "aliases": []},
                                          {"name": "HR", "aliases": []}, {"name": "SQL", "aliases": []},
                                          {"name": "AWS", "aliases": []}, {"name": "API", "aliases": []}]})

    def test_stored_short_names_are_kept(self):
        self.assertTrue({"R", "Go", "HR"} <= set(self.TERMS))

    def test_r_go_and_hr_are_found(self):
        self.assertEqual(pr.tag_skills("Experience with R and Go, plus HR systems.", self.TERMS), ["Go", "HR", "R"])

    def test_lower_case_long_names_are_found(self):
        self.assertEqual(pr.tag_skills("aws, sql and api work", self.TERMS), ["API", "AWS", "SQL"])

    def test_letters_inside_other_words_are_not_found(self):
        for text in ("Go-to-market strategy for retail", "R&D budget", "Brought a trust fund to Gotham", "go to the shop",
                     "r is a letter"):
            with self.subTest(text):
                self.assertEqual(pr.tag_skills(text, self.TERMS), [])

    def test_jd_skills_counts_short_names(self):
        counts = qr.jd_skills("We use R. Candidates know R and aws.", self.TERMS)
        self.assertEqual((counts["R"], counts["AWS"]), (2, 1))


class PostingRequirementTests(HomeCase):
    """L2: a requirement the stored skills do not know is still searched, and reported when nothing shows it."""

    def setUp(self) -> None:
        super().setUp()
        companies = {"acme": {"id": "acme", "name": "Acme", "aliases": [], "roles": [role("2020-01", None, "Analyst")],
                              "bullets": [line("Built Python reports for finance", "2020-01", skills=["Python"]),
                                          line("Administered Acme CRM for the sales team", "2020-01")]}}
        tables.save_companies(companies)
        tables.save_skills({"groups": {"Languages": [{"name": "Python", "aliases": [], "sources": []},
                                                     {"name": "AWS", "aliases": [], "sources": []}]}})
        tables.save_profile({"summaries": [], "education": [], "certifications": [], "profile_points": [],
                             "projects": []})

    def test_unknown_skill_without_a_requirement_is_not_seen(self):
        result = qr.analyze("Must have Python and Acme CRM.")
        self.assertEqual(set(result.need), {"Python"})

    def test_requirement_with_no_evidence_is_a_gap(self):
        result = qr.analyze("Must have Python and Kafka.", requirements=["Kafka"])
        self.assertEqual(set(result.need), {"Python", "Kafka"})
        self.assertIn("Python", result.covered)
        self.assertNotIn("Kafka", result.covered)

    def test_requirement_shown_in_a_bullet_text_is_covered(self):
        result = qr.analyze("Must have Python and Acme CRM.", requirements=["Acme CRM"])
        self.assertIn("Acme CRM", result.covered)

    def test_requirement_already_in_the_vocabulary_is_not_counted_twice(self):
        result = qr.analyze("Must have Python.", requirements=["python"])
        self.assertEqual(dict(result.need), {"Python": 1})

    def test_a_requirement_named_in_a_chosen_bullet_counts_as_shown(self):
        _, notes = br.build("Must have Python and Acme CRM.", br.BuildOptions(requirements=("Acme CRM",)),
                            header="# A\nB")
        self.assertEqual(notes.not_shown, [])
        self.assertEqual((notes.shown_count, notes.need_count), (2, 2))

    def test_build_reports_the_gap_and_the_note(self):
        _, notes = br.build("Must have Python and Kafka.", br.BuildOptions(requirements=("Kafka",)), header="# A\nB")
        self.assertEqual(notes.missing, ["Kafka"])
        self.assertTrue(notes.requirements_given)
        _, plain = br.build("Must have Python and Kafka.", br.BuildOptions(), header="# A\nB")
        self.assertFalse(plain.requirements_given)

    def test_one_direct_skill_match_is_listed(self):
        ctx = qr.JdContext(qr.Counter({"Python": 1}), {"python"}, set(), {"p": 0.5}, 0.0)
        self.assertIsNotNone(qr.score_bullet(line("Used Python", id="p", skills=["Python"]), ctx))
        self.assertIsNone(qr.score_bullet(line("Planned the office move", id="p"), ctx))


class RetagTests(unittest.TestCase):
    """L2: a rebuild tags older bullets with short names and loses no existing tag."""

    def test_retag_adds_short_names_and_keeps_the_rest(self):
        bullets = [line("Built Python models in R for forecasting", skills=["Python"]),
                   line("Wrote Go services with SQL storage", skills=["SQL"], skills_manual=["Kafka"]),
                   line("Planned the R&D budget", skills=[])]
        data = {"companies": {"a": {"bullets": bullets}},
                "skills": {"groups": {"Languages": [{"name": n, "aliases": []} for n in ("Python", "R", "Go", "SQL")]}}}
        before = {b["id"]: set(b["skills"]) for b in bullets}
        proc.retag(data)       # type: ignore[arg-type]
        after = {b["id"]: set(b["skills"]) for b in bullets}
        for key, old in before.items():
            self.assertLessEqual(old, after[key])
        self.assertEqual(after[bullets[0]["id"]], {"Python", "R"})
        self.assertEqual(after[bullets[1]["id"]], {"Go", "SQL", "Kafka"})
        self.assertEqual(after[bullets[2]["id"]], set())


class RankingProvenanceTests(HomeCase):
    """L3: role dates drive recency; file dates and repeats are provenance only."""

    def companies(self) -> dict[str, Any]:
        return {"acme": {"id": "acme", "name": "Acme", "aliases": [], "bullets": [
            line("Old work in Python", "2015-01", id="old", skills=["Python"]),
            line("New work in Python", "2023-01", id="new", skills=["Python"])],
            "roles": [role("2015-01", "2018-01", "Analyst"), role("2023-01", None, "Manager")]}}

    def test_recency_follows_the_role_date(self):
        scores = qr.recency_scores(self.companies())
        self.assertEqual((scores["new"], scores["old"]), (1.0, 0.0))

    def test_resaving_a_file_changes_nothing(self):
        companies = self.companies()
        before = qr.recency_scores(companies)
        tables.save_ledger({"a.docx": {"mtime": 1.0, "size": 1, "sha256": "x", "processed_at": "t", "kind": "resume"}})
        self.assertEqual(qr.recency_scores(companies), before)
        tables.save_ledger({"a.docx": {"mtime": 9e9, "size": 1, "sha256": "x", "processed_at": "t", "kind": "resume"}})
        self.assertEqual(qr.recency_scores(companies), before)

    def ctx(self) -> qr.JdContext:
        return qr.JdContext(qr.Counter({"Python": 1}), {"python"}, set(), {"one": 0.5, "many": 0.5}, 2.0)

    def test_repeats_add_only_a_small_capped_amount(self):
        once = qr.score_bullet(line("Used Python", id="one", skills=["Python"], sources=["a"]), self.ctx())
        many = qr.score_bullet(line("Used Python", id="many", skills=["Python"], sources=list("abcdefghij")), self.ctx())
        assert once is not None and many is not None
        self.assertGreater(many.score, once.score)
        self.assertLessEqual(many.score - once.score, 0.5)

    def test_more_than_the_cap_of_repeats_adds_nothing(self):
        six = qr.score_bullet(line("Used Python", id="one", skills=["Python"], sources=list("abcdef")), self.ctx())
        fifty = qr.score_bullet(line("Used Python", id="many", skills=["Python"], sources=[str(i) for i in range(50)]),
                                self.ctx())
        assert six is not None and fifty is not None
        self.assertEqual(six.score, fifty.score)

    def test_provenance_label_says_files(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            qr.show(line("Used Python", id="one", sources=["a", "b"]))
        self.assertIn("in 2 resume file(s)", out.getvalue())


class QueueTests(SessionCase):
    """L14: default queues include finished and strong material, after the unfinished and weak."""

    def args(self, *extra: str):
        return sessions.build_parser().parse_args(["new", "t", *extra])

    def set_card(self, card_id: str, confidence: int, drilled: str | None) -> None:
        cards = dict(sessions.arch.progress()["cards"])
        entry = cards.setdefault(card_id, sessions.arch.blank_progress())
        entry["confidence"], entry["last_drilled"] = confidence, drilled
        itables.save_progress(cards)

    def ids(self, queue) -> list[str]:
        return [item["id"] for item in queue]

    def test_aging_solid_card_is_queued_after_weak_ones_and_keeps_its_confidence(self):
        self.set_card("vpc", 2, "2000-01-01")
        queue = self.ids(sessions.card_queue(self.args()))
        self.assertIn("vpc", queue)
        self.assertEqual(queue[-1], "vpc")
        self.assertEqual(sessions.arch.progress()["cards"]["vpc"]["confidence"], 2)

    def test_old_solid_card_comes_before_a_freshly_solid_one(self):
        cards = [c["id"] for c in sessions.arch.catalog()["cards"]][:2]
        self.set_card(cards[0], 2, date.today().isoformat())
        self.set_card(cards[1], 2, "2000-01-01")
        queue = self.ids(sessions.card_queue(self.args()))
        self.assertLess(queue.index(cards[1]), queue.index(cards[0]))

    def test_only_open_leaves_solid_cards_out(self):
        self.set_card("vpc", 2, "2000-01-01")
        self.assertNotIn("vpc", self.ids(sessions.card_queue(self.args("--only-open"))))

    def stories(self):
        return [{"id": "done-one", "status": "done", "company": "acme", "engagement": "e"},
                {"id": "draft-one", "status": "draft", "company": "acme", "engagement": "e"}]

    def test_finished_story_is_queued_after_unfinished_ones(self):
        with mock.patch.object(sessions.prep, "stories", return_value=self.stories()):
            self.assertEqual(self.ids(sessions.story_queue(self.args())), ["draft-one", "done-one"])

    def test_only_open_leaves_finished_stories_out(self):
        with mock.patch.object(sessions.prep, "stories", return_value=self.stories()):
            self.assertEqual(self.ids(sessions.story_queue(self.args("--only-open"))), ["draft-one"])

    def test_solid_leadership_question_is_queued_last_unless_only_open(self):
        first = lead.cards()[0]["id"]
        questions = dict(lead.prog()["questions"])
        entry = questions.setdefault(first, lead.blank())
        entry["confidence"], entry["last_drilled"] = 2, "2000-01-01"
        itables.save_lead_progress(questions)
        everything = self.ids(sessions.build_queue(self.args("--mode", "leadership"))[0])
        only_open = self.ids(sessions.build_queue(self.args("--mode", "leadership", "--only-open"))[0])
        self.assertIn(first, everything)
        self.assertEqual(everything[-1], first)
        self.assertNotIn(first, only_open)


class AmbiguousNameTests(unittest.TestCase):
    """Names that are also ordinary words (Go, Make, Rust ...) count only when they read as the skill."""

    TERMS = pr.skill_terms({"Tools": [{"name": n, "aliases": []} for n in ("Go", "Make", "Rust", "Ruby", "Python")]})

    def found(self, text: str) -> list[str]:
        return pr.tag_skills(text, self.TERMS)

    def test_skill_uses_are_found(self):
        self.assertEqual(self.found("Experience with Go and Python."), ["Go", "Python"])
        self.assertEqual(self.found("We write Rust and Ruby services."), ["Ruby", "Rust"])
        self.assertEqual(self.found("Tools: Make, Docker"), ["Make"])
        self.assertEqual(self.found("Skills\n- Go\n- Python"), ["Go", "Python"])
        self.assertEqual(self.found("Wrote Go services for billing"), ["Go"])

    def test_ordinary_words_are_not_skills(self):
        for text in ("Go to market strategy for retail.", "Make sure the plan is sound.", "Rust never sleeps.",
                     "The rust on the car", "make it work", "Make-or-buy analysis", "Go-to-market plan"):
            with self.subTest(text):
                self.assertEqual(self.found(text), [])

    def test_sentence_start_use_is_listed_as_possible_with_its_sentence(self):
        found = pr.possible_matches("Go to market strategy for retail. We use Go and Python.", self.TERMS)
        self.assertEqual(found, [])        # Go is already found properly in the second sentence
        found = pr.possible_matches("Go to market strategy for retail. Make sure it ships.", self.TERMS)
        self.assertEqual([(n, q.split()[0]) for n, q in found], [("Go", "Go"), ("Make", "Make")])
        self.assertIn("Go to market strategy", found[0][1])

    def test_lower_case_words_are_never_possible_matches(self):
        self.assertEqual(pr.possible_matches("go to the shop and make tea", self.TERMS), [])

    def test_jd_analysis_lists_possible_matches(self):
        companies = {"a": {"id": "a", "name": "A", "aliases": [], "roles": [role("2020-01", None, "T")], "bullets": []}}
        with mock.patch.object(qr, "load_or_fail",
                               return_value=(companies, {"groups": {"Tools": [{"name": "Go", "aliases": []}]}})), \
             mock.patch.object(qr.rd, "load_profile", return_value=qr.rd.empty_profile()), \
             mock.patch.object(qr, "recency_scores", return_value={}):
            result = qr.analyze("Go to market strategy for retail.")
        self.assertEqual(dict(result.need), {})
        self.assertEqual([n for n, _ in result.possible], ["Go"])


if __name__ == "__main__":
    unittest.main()
