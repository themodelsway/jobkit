"""Tests for plugins/jobkit/src/jk/user/content_check.py and the stored-data part of `profile terms check`:
shared phrases, near-copies, values, figures, fingerprints, seeded text, ignores, removed lines and history."""
import os
import subprocess
import tempfile
from datetime import date
from pathlib import Path

from jk import base
from jk.interview import lead, questions
from jk.interview import question_tables as qt
from jk.interview import tables as interview_tables
from jk.resumes import tables as resume_tables
from jk.user import content_check as cc
from jk.user import tables
from tests.support import HomeCase
from tests.user.support import run_profile

LINE = "Rebuilt the volunteer intake process for the regional food bank network and trained every shift lead."
VARIANT = "Redesigned volunteer onboarding for the regional pantry network with a weekly mentoring circle."
STORY_TEXT = "The warehouse rota collapsed during the winter appeal, so I set up a shared roster with the drivers."


def seed_data() -> None:
    """A small, made-up career: one employer, one line with a variant, figures, a title, a story and vocabulary."""
    bullet = {"id": "acme-line-1", "text": LINE, "variants": [VARIANT], "metrics": ["41%"], "skills": [], "themes": [],
              "sources": ["a.pdf"], "role_start": "2020-01",
              "wordings": {"b.pdf": ["Grew volunteer retention by 41% across 17 pantries in two years."]}}
    resume_tables.replace_companies({"acme": {
        "id": "acme", "name": "Acme Corp", "aliases": [], "bullets": [bullet],
        "roles": [{"start": "2020-01", "end": None, "titles": ["Volunteer Programs Director"], "subtitles": [],
                   "clients": [], "sources": ["a.pdf"]}]}})
    resume_tables.replace_profile({"summaries": [], "profile_points": [], "education": ["MA Nonprofit Management"],
                                   "certifications": [{"name": "Example Certified Fundraiser"}], "projects": [],
                                   "headlines": []})
    resume_tables.replace_skills({"groups": {"People": [{"name": "Volunteer Scheduling", "aliases": [], "sources": []}]}})
    resume_tables.save_curation("themes", {"theme_words": {"food-security": ["pantry logistics"]},
                                           "positioning_words": {"focus-a": ["donor stewardship"]}})
    question = lead.SEED[0].question
    interview_tables.replace_stories({"schema_version": 2, "stories": [
        {"id": "acme-winter", "company": "acme", "company_name": "Acme Corp", "theme": "t", "headline": STORY_TEXT,
         "status": "draft", "metrics": [], "likely_questions": [question]}]})


class ContentCheckTests(HomeCase):
    def setUp(self):
        super().setUp()
        seed_data()
        self.index = cc.build()

    def kinds(self, text: str) -> list[str]:
        return [hit.kind for hit in self.index.check(text)]

    def test_a_shared_phrase_from_any_wording_is_a_hit(self):
        self.assertEqual(self.kinds("x = 'the volunteer intake process for the regional food bank'"), ["phrase"])
        self.assertEqual(self.kinds("Redesigned volunteer onboarding for the regional pantry"), ["phrase"])

    def test_a_near_copy_is_a_hit(self):
        self.assertEqual(self.kinds("Re-built a volunteer intake procedure for regional food-bank networks; trained shift leads"),
                         ["near-copy"])

    def test_titles_degrees_and_certifications_are_values(self):
        for line in ("title = 'Volunteer Programs Director'", "MA Nonprofit Management", "Example Certified Fundraiser"):
            self.assertEqual(self.kinds(line), ["value"], line)

    def test_two_stored_figures_in_one_line(self):
        self.assertEqual(self.kinds("raised retention 41 percent in 17 pantries"), ["figures"])
        self.assertEqual(self.kinds("raised retention 41 percent"), [])

    def test_three_distinctive_terms_are_a_fingerprint(self):
        self.assertEqual(self.kinds("pantry logistics, donor stewardship and volunteer scheduling"), ["fingerprint"])
        self.assertEqual(self.kinds("pantry logistics and donor stewardship"), [])

    def test_stories_are_compared(self):
        self.assertEqual(self.kinds("The warehouse rota collapsed during the winter appeal."), ["phrase"])

    def test_seeded_text_is_not_a_hit(self):
        self.assertEqual(self.kinds(lead.SEED[0].question), [])

    def test_personal_role_prompts_are_compared(self):
        question = "What did you learn when the reading group introduced a neighborhood book exchange?"
        item = questions.clean_question("Program Coordinator", {"source": "personal", "bullet": "acme-line-1",
                                                                 "question": question}, date.today())
        qt.save_questions("Program Coordinator", [item])
        self.assertEqual([h.kind for h in cc.build().check(question)], ["phrase"])

    def test_ignored_text_is_removed_before_comparing(self):
        index = cc.build(["volunteer programs director"])
        self.assertEqual(index.check("title = 'Volunteer Programs Director'"), [])

    def test_extracted_resume_text_is_compared(self):
        folder = base.output_dir()
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "a.docx.txt").write_text("Chaired the harvest festival steering group for nine market towns.\n",
                                            encoding="utf-8")
        self.assertEqual([h.kind for h in cc.build().check("the harvest festival steering group for nine")], ["phrase"])

    def test_nothing_stored_means_no_hits(self):
        self.assertTrue(cc.Index().empty())
        self.assertEqual(cc.Index().check(LINE), [])

    def test_figures_are_read_in_one_spelling(self):
        self.assertEqual(cc.numbers("$7 million for 43 years; v0.2.0 of 12 apps; 41 percent; 2021 offices"),
                         {"$7m", "43 years", "12 apps", "41%"})


class CommandTests(HomeCase):
    def setUp(self):
        super().setUp()
        seed_data()

    def test_hits_show_kind_and_source_but_never_the_stored_text(self):
        page = self.home / "page.md"
        page.write_text(f"intro\n{LINE}\n", encoding="utf-8")
        code, out, _ = run_profile("terms", "check", str(page))
        self.assertEqual(code, 1)
        self.assertIn("Checking the given files against your stored data ...", out)
        self.assertIn(f"{page}:2: phrase (resume line acme-line-1)", out)
        self.assertNotIn("volunteer intake", out.lower())

    def test_clean_file_passes(self):
        page = self.home / "page.md"
        page.write_text("A neutral sentence about scheduling meetings.\n", encoding="utf-8")
        code, out, _ = run_profile("terms", "check", str(page))
        self.assertEqual(code, 0)
        self.assertIn("personal terms and phrases: none found", out)


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.org", *args], cwd=repo, check=True,
                   capture_output=True)


class RepositoryTests(HomeCase):
    def setUp(self):
        super().setUp()
        seed_data()
        self.repo = Path(tempfile.mkdtemp(prefix="jobkit-repo-"))
        git(self.repo, "init", "-q")
        (self.repo / "a.txt").write_text(f"one\n{LINE}\n", encoding="utf-8")
        git(self.repo, "add", "a.txt")
        git(self.repo, "commit", "-q", "-m", "first")
        self.cwd = os.getcwd()
        os.chdir(self.repo)
        self.addCleanup(os.chdir, self.cwd)

    def test_removing_a_matching_line_warns_but_passes(self):
        (self.repo / "a.txt").write_text("one\n", encoding="utf-8")
        git(self.repo, "add", "a.txt")
        code, out, _ = run_profile("terms", "check", "--staged")
        self.assertEqual(code, 0)
        self.assertIn("remove 1 line(s) that match your stored data", out)

    def test_history_finds_an_old_version(self):
        (self.repo / "a.txt").write_text("one\n", encoding="utf-8")
        git(self.repo, "commit", "-q", "-am", "second")
        self.assertEqual(run_profile("terms", "check", "--all")[0], 0)
        code, out, _ = run_profile("terms", "check", "--history")
        self.assertEqual(code, 1)
        self.assertRegex(out, r"a\.txt@[0-9a-f]{8}:2: phrase \(resume line acme-line-1\)")
        self.assertIn("Checking every version of every file in the history", out)

    def test_terms_are_checked_in_history_too(self):
        tables.save_term("Zephyrine", "product", "word", False)
        (self.repo / "b.txt").write_text("Zephyrine\n", encoding="utf-8")
        git(self.repo, "add", "b.txt")
        git(self.repo, "commit", "-q", "-m", "b")
        git(self.repo, "rm", "-q", "b.txt")
        git(self.repo, "commit", "-q", "-m", "c")
        _, out, _ = run_profile("terms", "check", "--history")
        self.assertRegex(out, r"b\.txt@[0-9a-f]{8}:1: product term 'Zephyrine'")
