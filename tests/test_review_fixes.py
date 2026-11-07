"""Regression tests for the review findings fixed together (restore check, profile init, input errors, corrupt PDF,
figure-aware merging, session filters, leadership gaps, builder selection and revisions, readiness labels).
Run: .venv/bin/python -m unittest discover -s tests -t ."""
import contextlib
import io
import sqlite3
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from jobkit import common, store
from jobkit.common import ToolError
from jobkit.interview import lead, prep, readiness, sessions, tables
from jobkit.resumes import build_resume as br
from jobkit.resumes import extract
from jobkit.resumes import process_resumes as proc
from jobkit.resumes import query_resume as qr
from jobkit.resumes import resume_data as rd
from jobkit.user import profile as up
from tests.interview.test_sessions import COMPANIES, SKILLS, SessionCase
from tests.support import HomeCase


def bullet(text: str, metrics: list[str], **extra) -> dict:
    """A minimal stored bullet."""
    return {"id": text[:8], "text": text, "metrics": metrics, "skills": [], "sources": ["a"], **extra}


class RestoreCheckTests(HomeCase):
    def test_look_alike_database_is_refused_and_current_data_kept(self):
        fake = self.home / "fake.db"
        with contextlib.closing(sqlite3.connect(fake)) as conn:
            conn.execute("CREATE TABLE meta (unrelated TEXT)")
            conn.execute(f"PRAGMA user_version={store.version()}")
            conn.commit()
        before = (self.home / "data" / "jobkit.db").read_bytes()
        with self.assertRaises(ToolError):
            store.restore_from(fake)
        store.close()
        self.assertEqual(store.stored_version(sqlite3.connect(self.home / "data" / "jobkit.db")), store.version())
        self.assertEqual(len(list((self.home / "backup").glob("*before-restore*"))), 0)
        self.assertTrue(before)

    def test_real_backup_is_accepted(self):
        copy = store.backup_to(self.home / "backup" / "ok.db")
        store.check_backup_file(copy)


class ProfileInitTests(HomeCase):
    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = up.main(list(argv))
        return code, out.getvalue()

    def test_second_init_keeps_answers(self):
        first, second = self.home / "one", self.home / "two"
        first.mkdir()
        second.mkdir()
        self.run_cli("init", "--resume-root", str(first), "--name", "Synthetic One", "--resume-dir", "a")
        code, out = self.run_cli("init", "--resume-root", str(second), "--name", "Synthetic Two", "--resume-dir", "b")
        self.assertEqual(code, 0)
        self.assertIn("Kept the existing", out)
        profile = up.load()
        self.assertEqual((profile["resume_root"], profile["name"], profile["resume_dirs"]),
                         (str(first), "Synthetic One", ["a"]))

    def test_second_init_fills_unset_name(self):
        root = self.home / "r"
        root.mkdir()
        self.run_cli("init", "--resume-root", str(root))
        self.run_cli("init", "--resume-root", str(root), "--name", "Pat")
        self.assertEqual(up.load()["name"], "Pat")


class InputErrorTests(unittest.TestCase):
    def test_unreadable_inputs_become_tool_errors(self):
        with mock.patch("pathlib.Path.read_text", side_effect=UnicodeDecodeError("utf-8", b"", 0, 1, "x")):
            with self.assertRaisesRegex(ToolError, "not a UTF-8"):
                common.read_text_arg("x.txt")
        with self.assertRaisesRegex(ToolError, "cannot read"):
            common.read_text_arg("/no/such/jd.txt")
        with self.assertRaisesRegex(ToolError, "cannot read"):
            common.read_text_arg("/")


class CorruptPdfTests(unittest.TestCase):
    def test_damaged_pdf_is_a_tool_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "broken.pdf"
            bad.write_text("not a PDF", encoding="utf-8")
            with self.assertRaises(ToolError):
                extract.extract(bad)
            with mock.patch("shutil.which", return_value=None), self.assertRaises(ToolError):
                extract.extract(bad)


class FigureMergeTests(unittest.TestCase):
    def merged(self, first: str, second: str) -> dict:
        company = {"id": "acme", "bullets": [], "roles": []}
        proc.merge_bullet(company, first, "2020-01", "a.txt")
        proc.merge_bullet(company, second, "2020-01", "b.txt")
        return company

    def test_different_figures_are_separate_bullets(self):
        company = self.merged("Reduced warehouse operating costs by 40% through route consolidation.",
                              "Reduced warehouse operating costs by 90% through route consolidation.")
        self.assertEqual(len(company["bullets"]), 2)
        self.assertEqual([b["sources"] for b in company["bullets"]], [["a.txt"], ["b.txt"]])

    def test_same_figures_still_merge(self):
        company = self.merged("Reduced warehouse operating costs by 40% through route consolidation.",
                              "Reduced warehouse operating costs by 40% through route consolidation work.")
        self.assertEqual(len(company["bullets"]), 1)


class PruneWordingTests(unittest.TestCase):
    A = "Led the migration of 40 legacy services to AWS Lambda across three regions."
    B = "Led migration of 40 legacy services to AWS Lambda across three regions."

    def data(self, *texts, strict=False):
        company = {"id": "acme", "bullets": [], "roles": []}
        for source, text in zip(("a.txt", "b.txt", "c.txt"), texts, strict=False):
            proc.merge_bullet(company, text, "2020-01", source)
        return {"companies": {"acme": company}, "skills": {"groups": {}}, "profile": rd.empty_profile()}

    def test_deleting_the_canonical_file_moves_text_to_the_remaining_wording(self):
        data = self.data(self.A, self.B)
        self.assertEqual(len(data["companies"]["acme"]["bullets"]), 1)
        proc.strip_source(data, "a.txt")
        bullet = data["companies"]["acme"]["bullets"][0]
        self.assertEqual((bullet["text"], bullet["sources"], bullet["variants"]), (self.B, ["b.txt"], []))

    def test_shared_wording_survives_one_deletion(self):
        data = self.data(self.A, self.A, self.B)
        proc.strip_source(data, "a.txt")
        bullet = data["companies"]["acme"]["bullets"][0]
        self.assertEqual((bullet["text"], bullet["sources"]), (self.A, ["b.txt", "c.txt"]))
        self.assertEqual(bullet["variants"], [self.B])

    def test_last_source_removes_the_bullet(self):
        data = self.data(self.A)
        proc.strip_source(data, "a.txt")
        self.assertEqual(data["companies"], {})

    def test_figures_follow_the_remaining_wording(self):
        data = self.data("Cut costs by 40% via rightsizing the compute fleet in every region.",
                         "Cut costs by 40% via rightsizing the compute fleet in every region now.")
        data["companies"]["acme"]["bullets"][0]["needs_review"] = True
        proc.strip_source(data, "a.txt")
        bullet = data["companies"]["acme"]["bullets"][0]
        self.assertEqual(bullet["text"].endswith("now."), True)
        self.assertFalse(bullet["needs_review"])

    def test_older_merged_data_is_flagged_for_a_rebuild(self):
        old = {"companies": {"acme": {"bullets": [{"text": "x", "sources": ["a", "b"]}]}}}
        self.assertTrue(proc.untraceable_wording(old))
        single = {"companies": {"acme": {"bullets": [{"text": "x", "sources": ["a"]}]}}}
        self.assertFalse(proc.untraceable_wording(single))
        traced = {"companies": {"acme": {"bullets": [{"text": "x", "sources": ["a", "b"], "wordings": {"a": ["x"]}}]}}}
        self.assertFalse(proc.untraceable_wording(traced))


class SessionFilterTests(SessionCase):
    def setUp(self):
        super().setUp()
        self.assertEqual(self.cli(prep.main, "init")[0], 0)
        patcher = mock.patch.object(sessions.qr, "load_or_fail", return_value=(COMPANIES, SKILLS))
        patcher.start()
        self.addCleanup(patcher.stop)

    def jd(self, text="VPC design"):
        path = self.home / "jd.txt"
        path.write_text(text, encoding="utf-8")
        return str(path)

    def test_unfiltered_jd_session_works(self):
        code, _, err = self.cli(sessions.main, "new", "x", "--mode", "jd", "--jd", self.jd())
        self.assertEqual(code, 0, err)

    def test_jd_mode_respects_filters(self):
        code, _, err = self.cli(sessions.main, "new", "x", "--mode", "jd", "--jd", self.jd(), "--track", "acmedata")
        self.assertEqual(code, 1, err)
        code, _, err = self.cli(sessions.main, "new", "x", "--jd", self.jd(), "--area", "NO SUCH AREA")
        self.assertEqual(code, 1, err)

    def test_jd_alone_means_jd_mode(self):
        code, out, err = self.cli(sessions.main, "new", "implicit", "--jd", self.jd())
        self.assertEqual(code, 0, err)
        sid = out.split("Started session ")[1].split(" ")[0]
        saved = tables.load_session(sid)
        self.assertEqual((saved["mode"], saved["jd"] is not None), ("jd", True))
        self.assertIn("vpc", [item["id"] for item in saved["queue"]])

    def test_jd_with_another_mode_is_an_error(self):
        code, _, err = self.cli(sessions.main, "new", "x", "--mode", "stories", "--jd", self.jd())
        self.assertEqual(code, 1)
        self.assertIn("--jd goes with mode jd", err)


class LeadershipTests(SessionCase):
    def test_partial_profile_still_reports_missing_scope(self):
        self.cli(lead.main, "profile", "set", "acme", "title", "Lead")
        _, out, _ = self.cli(lead.main, "status")
        self.assertIn("acme (direct_reports, indirect_team, budget)", out)
        for field in ("direct_reports", "indirect_team", "budget"):
            self.cli(lead.main, "profile", "set", "acme", field, "0")
        _, out, _ = self.cli(lead.main, "status")
        self.assertIn("Scope facts missing for: none", out)

    def test_blank_example_does_not_count_and_any_employer_is_allowed(self):
        qid = lead.cards()[0]["id"]
        self.cli(lead.main, "example", qid, "acme", "situation", "   ")
        self.assertIn("0/1 examples", self.cli(lead.main, "list")[1].splitlines()[0])
        self.cli(lead.main, "example", qid, "acme", "situation", "We moved the office.")
        self.assertIn("1/1 examples", self.cli(lead.main, "list")[1].splitlines()[0])
        code, _, err = self.cli(lead.main, "example", qid, "nobody", "situation", "x")
        self.assertEqual(code, 1)
        self.assertIn("COMPANY must be one of acme", err)


class SkipExampleTests(SessionCase):
    def test_not_applicable_counts_as_covered_but_is_shown(self):
        qid = lead.cards()[0]["id"]
        code, out, err = self.cli(lead.main, "skip", qid, "acme", "never managed managers")
        self.assertEqual(code, 0, err)
        self.assertIn("0/1 examples, 1 not applicable", self.cli(lead.main, "list")[1].splitlines()[0])
        self.assertNotIn(qid, "".join(row for row in self.cli(readiness.main)[1].splitlines() if "leadership:" in row))
        self.cli(lead.main, "example", qid, "acme", "situation", "A real one.")
        self.assertIn("1/1 examples", self.cli(lead.main, "list")[1].splitlines()[0])
        self.assertNotIn("not applicable", self.cli(lead.main, "list")[1].splitlines()[0])

    def test_unskip_and_refusal_when_an_example_exists(self):
        qid = lead.cards()[0]["id"]
        self.cli(lead.main, "skip", qid, "acme")
        self.cli(lead.main, "unskip", qid, "acme")
        self.assertIn("0/1 examples", self.cli(lead.main, "list")[1].splitlines()[0])
        self.cli(lead.main, "example", qid, "acme", "situation", "A real one.")
        self.assertEqual(self.cli(lead.main, "skip", qid, "acme")[0], 1)


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


class ReadinessLabelTests(unittest.TestCase):
    def test_old_solid_answers_read_as_aging_even_with_recent_lesson(self):
        today = date.today()
        old = (today - timedelta(days=90)).isoformat()
        evidence = {"graded2": {old}, "answered": {old}}
        self.assertEqual(readiness.label(2, today.isoformat(), evidence, 30), "aging")
        recent = {"graded2": {today.isoformat()}, "answered": {today.isoformat()}}
        self.assertEqual(readiness.label(2, today.isoformat(), recent, 30), "solid-once")

    def test_story_label_needs_a_recent_answer(self):
        story = {"id": "s", "status": "done"}
        old = (date.today() - timedelta(days=90)).isoformat()
        self.assertEqual(readiness.story_label(story, {"s": {"graded2": set(), "answered": {old}}}, 30), "done-aging")
        now = date.today().isoformat()
        self.assertEqual(readiness.story_label(story, {"s": {"graded2": set(), "answered": {now}}}, 30), "done-rehearsed")


class LessonDateTests(SessionCase):
    def test_lesson_without_quiz_keeps_the_drill_date(self):
        cards = dict(sessions.arch.progress()["cards"])
        entry = cards.setdefault("vpc", sessions.arch.blank_progress())
        entry["confidence"], entry["last_drilled"] = 2, "2000-01-01"
        tables.save_progress(cards)
        sessions.record_confidence("card", "vpc", 1, True)
        self.assertEqual(sessions.arch.progress()["cards"]["vpc"]["last_drilled"], "2000-01-01")


if __name__ == "__main__":
    unittest.main()
