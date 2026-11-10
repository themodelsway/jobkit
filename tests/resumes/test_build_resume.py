"""Tests for build-resume."""
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from jobkit.common import ToolError
from jobkit.resumes import build_resume as br, query_resume as qr, resume_data as rd, tables
from tests.resumes.match_fixtures import jd_from_bullets, line, role
from tests.resumes.test_integrity import bullet
from tests.resumes.test_resume_pipeline import PipelineCase
from tests.support import HomeCase


class BuilderTests(unittest.TestCase):
    def test_shared_figure_alone_is_not_a_duplicate(self):
        a = bullet("Increased sales conversion by 20% through pricing experiments", ["20%"])
        b = bullet("Reduced employee attrition by 20% after redesigning onboarding", ["20%"])
        self.assertEqual(len(br.pick([a, b], 4)), 2)

    def test_paraphrase_of_one_achievement_is_still_one(self):
        a = bullet("Reduced page load time by 30% through caching database queries", ["30%"])
        b = bullet("Cut page load time by 30% by caching database queries", ["30%"])
        self.assertEqual(len(br.pick([a, b], 4)), 1)

    def test_claim_not_repeated_across_companies(self):
        a = bullet("Reduced page load time by 30% through caching database queries", ["30%"])
        b = bullet("Cut page load time by 30% by caching database queries", ["30%"])
        self.assertEqual(br.pick([b], 4, already=[a]), [])

    def test_revisions_never_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            first = br.next_revision(folder, "resume")
            first.write_text("one", encoding="utf-8")
            self.assertEqual(br.next_revision(folder, "resume").name, "resume-2.md")

    def test_headline_must_relate_to_the_posting(self):
        result = qr.Analysis(need=qr.Counter({"Kubernetes": 1}), themes={"platform"}, angles={}, summaries=[],
                             ranked=[], profile={"headlines": ["Pastry chef", "Kubernetes platform lead"]})
        self.assertEqual(br.best_headline(result), "Kubernetes platform lead")
        result.profile = {"headlines": ["Pastry chef"]}
        self.assertIsNone(br.best_headline(result))

    def test_total_bullet_limit(self):
        company = {"id": "a", "name": "A", "roles": [{"end": None}], "bullets": []}
        bullets = [bullet(f"Delivered distinct project number {w} for customers", [], skills=[]) for w in
                   ("alpha", "bravo", "charlie", "delta")]
        scored = [qr.ScoredBullet(b, 1.0, []) if hasattr(qr, "ScoredBullet") else b for b in bullets]
        result = mock.Mock(ranked=[(company, scored), (company, scored)], need=qr.Counter(), covered=set(), skills={"groups": {}})
        with mock.patch.object(br, "company_bullets", side_effect=lambda c, s, o, used=(): list(bullets)):
            chosen = br.choose_experience(result, br.BuildOptions(max_bullets=3))
        self.assertEqual(sorted(len(p) for _, p in chosen), [1, 2])


class CoverageTests(unittest.TestCase):
    def test_skill_left_out_by_the_picks_is_brought_in(self):
        company = {"id": "a", "name": "A", "roles": [{"end": None}], "bullets": []}
        first = bullet("Designed serverless pipelines for event processing at scale", [], skills=["AWS"])
        second = bullet("Mentored engineers across three teams in code review practice", [], skills=["Mentoring"])
        scored = [qr.ScoredBullet(2.0, first, []), qr.ScoredBullet(1.0, second, [])]
        result = mock.Mock(ranked=[(company, scored)], need=qr.Counter({"AWS": 2, "Mentoring": 1}),
                           covered={"AWS", "Mentoring"}, skills={"groups": {}})
        with mock.patch.object(br, "company_bullets", return_value=[first]):
            chosen = br.choose_experience(result, br.BuildOptions(top=2))
        self.assertEqual({b["id"] for _, p in chosen for b in p}, {first["id"], second["id"]})


class ApprovalTests(HomeCase):
    def test_draft_approved_changed(self):
        resume = self.home / "r.md"
        resume.write_text("# Pat Example\nbody\n", encoding="utf-8")
        self.assertEqual(br.review_status(resume), "draft")
        args = mock.Mock(approve=str(resume))
        br.cmd_approve(args)
        self.assertEqual(br.review_status(resume), "approved")
        resume.write_text("# Pat Example\nedited\n", encoding="utf-8")
        self.assertEqual(br.review_status(resume), "changed")

    def test_placeholder_header_cannot_be_approved(self):
        resume = self.home / "r.md"
        resume.write_text(br.HEADER_TEMPLATE + "body\n", encoding="utf-8")
        with self.assertRaises(ToolError):
            br.cmd_approve(mock.Mock(approve=str(resume)))
        self.assertEqual(br.review_status(resume), "draft")


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


class PostingRequirementTests(HomeCase):
    """L2: a requirement the stored skills do not know is still searched, and reported when nothing shows it."""

    def setUp(self) -> None:
        super().setUp()
        companies = {"acme": {"id": "acme", "name": "Acme", "aliases": [], "roles": [role("2020-01", None, "Analyst")],
                              "bullets": [line("Built Python reports for finance", "2020-01", skills=["Python"]),
                                          line("Administered Acme CRM for the sales team", "2020-01")]}}
        tables.replace_companies(companies)
        tables.replace_skills({"groups": {"Languages": [{"name": "Python", "aliases": [], "sources": []},
                                                     {"name": "AWS", "aliases": [], "sources": []}]}})
        tables.replace_profile({"summaries": [], "education": [], "certifications": [], "profile_points": [],
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


class BuildOptionTests(PipelineCase):
    def build(self, *extra):
        jd, out = self.tmp / "jd3.txt", self.tmp / "out" / f"r{len(extra)}.md"
        jd.write_text(jd_from_bullets(self.data), encoding="utf-8")
        with mock.patch.object(br, "header_file", return_value=self.tmp / "header.md"):
            code, _, err = self.cli(br.main, str(jd), "--output", str(out), *extra)
        self.assertEqual(code, 0, err)
        return out.read_text(encoding="utf-8")

    def test_top_limits_bullets_and_title_overrides(self):
        many, few = self.build("--top", "4"), self.build("--top", "1")
        self.assertLess(len(few), len(many))
        text = self.build("--title", "acme-corp=Lead Engineer")
        self.assertIn("Lead Engineer", text)

    def test_recency_and_include_review_are_accepted(self):
        self.assertTrue(self.build("--recency", "0", "--include-review"))
