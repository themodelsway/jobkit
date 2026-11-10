"""Tests for src/jobkit/user/terms.py (personal terms and the commit scan) in a temp home folder."""
import contextlib
import io
import subprocess
import unittest

from jobkit import store
from jobkit.user import profile as up, tables as utables, terms
from tests.support import HomeCase

HEADER = "# Pat Example\nCity, ST | 5550001234 | pat@example.org | linkedin.com/in/patexample\n"


class DeriveTests(unittest.TestCase):
    def test_header_gives_name_and_contact_but_not_city(self):
        found = {t.text: t.kind for t in terms.derive(None, None, HEADER, [])}
        self.assertEqual(found, {"Pat Example": "name", "5550001234": "contact", "pat@example.org": "contact",
                                 "linkedin.com/in/patexample": "contact"})

    def test_resume_folders_give_company_names(self):
        files = ["2026/Acme Air/me.docx", "2025/Acme_Co_ACME/me.pdf", "2025/top-level.docx", "me.docx"]
        self.assertEqual(terms.folder_names(files), sorted({"Acme Air", "Acme", "Co", "ACME"}))
        found = {t.text: t.match for t in terms.derive(None, None, None, [], terms.folder_names(files))}
        self.assertEqual(found["Acme Air"], "phrase")
        self.assertNotIn("top-level.docx", found)

    def test_other_folder_layouts(self):
        files = ["Acme Air/me.docx", "2026/Q1/Acme/me.docx", "Resumes/old.docx", "2026/me.docx",
                 "2026/Acme Co/October/me.pdf", "2025/Acme Co/Oct 2025/me.pdf"]
        self.assertEqual(terms.folder_names(files, skip=["Resumes"]), ["Acme", "Acme Air", "Acme Co"])

    def test_short_employer_is_a_whole_word(self):
        found = terms.derive(None, "/data/resumes", None, ["ACME", "Acme Corp"])
        short = next(t for t in found if t.text == "ACME")
        self.assertEqual(short.match, "word")
        self.assertEqual(terms.scan("ACMEX scores and ACME Health", [short]), [(1, short)])
        self.assertEqual(terms.scan("cvss only", [short]), [])

    def test_ignored_row_hides_a_derived_term(self):
        derived = terms.derive(None, None, None, ["Acme Air"])
        merged = terms.merge(derived, [{"text": "acme air", "kind": "other", "match": "phrase", "ignored": 1}])
        self.assertTrue(merged[0].ignored)
        self.assertEqual(terms.scan("Acme Air", [t for t in merged if not t.ignored]), [])

    def test_grep_style_whole_word_pattern(self):
        rx = terms.pattern(terms.Term("(^|[^[:alnum:]])ACME([^[:alnum:]]|$)", "other", "regex", "stored"))
        self.assertTrue(rx.search("worked at ACME, then"))
        self.assertFalse(rx.search("they said ACMEX"))

    def test_a_patterns_own_text_is_a_hit(self):
        term = terms.Term("acme[ _.-]?ai", "client", "regex", "stored")
        self.assertEqual(terms.scan("add acme[ _.-]?ai here", [term]), [(1, term)])

    def test_pattern_and_guess(self):
        self.assertEqual(terms.guess_match("acme[ _.-]?ai"), "regex")
        self.assertEqual(terms.guess_match("ACME"), "word")
        self.assertEqual(terms.guess_match("acme.ai"), "phrase")
        rx = terms.pattern(terms.Term("acme[ _.-]?ai", "client", "regex", "stored"))
        self.assertTrue(rx.search("ACME AI"))


class CommandTests(HomeCase):
    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = up.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def setUp(self):
        super().setUp()
        self.run_cli("init", "--resume-root", str(self.home / "resumes"))
        self.run_cli("header", "set", "Pat Example", "City, ST | 5550001234 | pat@example.org")
        utables.replace_employers({"e1": {"name": "Acme Corp", "regex": "acme"}})

    def test_list_shows_derived_and_stored(self):
        self.run_cli("terms", "add", "acme.ai", "--kind", "product")
        _, out, _ = self.run_cli("terms")
        self.assertIn("Acme Corp", out)
        self.assertIn("derived", out)
        self.assertRegex(out, r"product\s+phrase\s+stored\s+acme.ai")

    def test_bad_pattern_is_refused(self):
        code, _, err = self.run_cli("terms", "add", "(oops", "--match", "regex")
        self.assertEqual(code, 1)
        self.assertIn("valid pattern", err)

    def test_check_paths_finds_and_ignore_clears(self):
        page = self.home / "page.txt"
        page.write_text("fine\nworked at acme corp once\n", encoding="utf-8")
        code, out, _ = self.run_cli("terms", "check", str(page))
        self.assertEqual(code, 1)
        self.assertIn(":2: employer term 'Acme Corp'", out)
        self.run_cli("terms", "ignore", "Acme Corp")
        self.assertEqual(self.run_cli("terms", "check", str(page))[0], 0)
        self.run_cli("terms", "rm", "Acme Corp")
        self.assertEqual(self.run_cli("terms", "check", str(page))[0], 1)

    def test_exhaustive_includes_ignored_common_words(self):
        page = self.home / "page.txt"
        page.write_text("an acme of the sun\n", encoding="utf-8")
        self.run_cli("terms", "ignore", "Acme")
        self.assertEqual(self.run_cli("terms", "check", str(page))[0], 0)
        code, out, _ = self.run_cli("terms", "check", "--exhaustive", str(page))
        self.assertEqual(code, 1)
        self.assertIn("Word: Acme", out)
        self.assertIn("page.txt (1)", out)
        self.assertIn("common word", self.run_cli("terms")[1])

    def test_common_words_are_one_block_per_word(self):
        (self.home / "a.txt").write_text("acme\nacme again\n", encoding="utf-8")
        (self.home / "b.txt").write_text("x\nacme\nacme\nacme\n", encoding="utf-8")
        self.run_cli("terms", "ignore", "Acme")
        _, out, _ = self.run_cli("terms", "check", "--exhaustive", str(self.home / "a.txt"), str(self.home / "b.txt"))
        out = out.replace(str(self.home) + "/", "")
        self.assertEqual(out.count("Word: Acme"), 1)
        self.assertIn("\n  a.txt (1, 2)\n", out)
        self.assertIn("\n  b.txt (multiple lines: 3)\n", out)

    def test_exhaustive_with_no_common_words_says_so(self):
        page = self.home / "page.txt"
        page.write_text("nothing here\n", encoding="utf-8")
        code, out, _ = self.run_cli("terms", "check", "--exhaustive", str(page))
        self.assertEqual(code, 0)
        self.assertIn("No common words are recorded", out)

    def test_import_file(self):
        source = self.home / "terms.txt"
        source.write_text("Acme Air\n# comment\nacme[ _.-]?ai\n\n", encoding="utf-8")
        _, out, _ = self.run_cli("terms", "import", str(source))
        self.assertIn("Imported 2", out)
        self.assertEqual(sorted(r["match"] for r in utables.load_terms()), ["phrase", "regex"])

    def test_staged_files_are_read_as_staged(self):
        repo = self.home / "repo"
        repo.mkdir()
        for cmd in (["init", "-q"], ["config", "user.email", "t@example.org"], ["config", "user.name", "t"]):
            subprocess.run(["git", *cmd], cwd=repo, check=True)
        (repo / "a.txt").write_text("Acme Corp\n", encoding="utf-8")
        subprocess.run(["git", "add", "a.txt"], cwd=repo, check=True)
        (repo / "a.txt").write_text("clean now\n", encoding="utf-8")      # the working copy is clean; the staged one is not
        with contextlib.chdir(repo):
            code, out, _ = self.run_cli("terms", "check", "--staged")
        self.assertEqual(code, 1)
        self.assertIn("a.txt:1", out)

    def test_a_renamed_staged_file_is_checked_under_its_new_name(self):
        repo = self.home / "repo-rename"
        repo.mkdir()
        for cmd in (["init", "-q"], ["config", "user.email", "t@example.org"], ["config", "user.name", "t"],
                    ["config", "diff.renames", "true"]):
            subprocess.run(["git", *cmd], cwd=repo, check=True)
        (repo / "before.txt").write_text("".join(f"line {n}\n" for n in range(100)), encoding="utf-8")
        subprocess.run(["git", "add", "before.txt"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "first"], cwd=repo, check=True)
        subprocess.run(["git", "mv", "before.txt", "after.txt"], cwd=repo, check=True)
        with (repo / "after.txt").open("a", encoding="utf-8") as handle:
            handle.write("Acme Corp\n")
        subprocess.run(["git", "add", "after.txt"], cwd=repo, check=True)
        status = subprocess.run(["git", "diff", "--cached", "--name-status"], cwd=repo, capture_output=True, text=True, check=True)
        self.assertTrue(status.stdout.startswith("R"), status.stdout)      # git really reports a rename
        (repo / "after.txt").write_text("clean now\n", encoding="utf-8")   # the working copy is clean; the staged one is not
        with contextlib.chdir(repo):
            code, out, _ = self.run_cli("terms", "check", "--staged")
        self.assertEqual(code, 1)
        self.assertIn("after.txt:101", out)

    def test_nothing_staged_says_so(self):
        with contextlib.chdir(self.home):
            subprocess.run(["git", "init", "-q"], check=True)
            code, out, _ = self.run_cli("terms", "check", "--staged")
        self.assertEqual(code, 0)
        self.assertIn("no files to check", out)

    def test_check_without_a_database_is_skipped(self):
        store.close()
        (self.home / "data" / "jobkit.db").rename(self.home / "data" / "gone.db")
        code, out, _ = self.run_cli("terms", "check", "--staged")
        self.assertEqual(code, 0)
        self.assertIn("skipped", out)
