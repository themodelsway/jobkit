"""Tests for plugins/jobkit/src/jk/user/profile.py in a temp folder. Run: uv run python -m unittest discover -s tests -t ."""
import contextlib
import io
import re
import unittest

from jk.interview import styles
from jk.user import profile as up, tables as utables
from tests.support import HomeCase


class ProfileCase(HomeCase):
    def setUp(self):
        super().setUp()
        self.tmp = self.home
        self.resumes = self.tmp / "resumes"
        self.resumes.mkdir()

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = up.main(list(argv))
        return code, out.getvalue(), err.getvalue()


class ProfileTests(ProfileCase):
    def test_status_without_profile(self):
        code, out, _ = self.run_cli("status")
        self.assertEqual(code, 0)
        self.assertIn("No profile", out)

    def test_need_explains_how_to_set_up(self):
        code, _, err = self.run_cli("tier1")
        self.assertEqual(code, 1)
        self.assertIn("Ask the user where their resume files are", err)

    def test_init_then_status_and_dirs(self):
        code, _out, _ = self.run_cli("init", "--resume-root", str(self.resumes), "--resume-dir", "2026", "--name", "Pat")
        self.assertEqual(code, 0)
        self.assertEqual(up.resume_root(), self.resumes)
        self.assertEqual(up.resume_dirs(), [self.resumes / "2026"])
        _, status, _ = self.run_cli("status")
        self.assertIn("name: Pat", status)
        self.assertIn("from your resume scan", status)

    def test_folder_with_spaces_is_stored_as_given(self):
        spaced = self.tmp / "My Resumes 2026"
        spaced.mkdir()
        code, _, _ = self.run_cli("init", "--resume-root", str(spaced))
        self.assertEqual(code, 0)
        self.assertEqual(up.resume_root(), spaced)

    def test_init_rejects_missing_folder(self):
        code, _, err = self.run_cli("init", "--resume-root", str(self.tmp / "nope"))
        self.assertEqual(code, 1)
        self.assertIn("is not a folder", err)

    def test_header_is_saved_in_the_database_and_shown(self):
        self.run_cli("init", "--resume-root", str(self.resumes))
        self.assertIn("No header saved yet", self.run_cli("header")[1])
        code, out, _ = self.run_cli("header", "set", "Pat Example", "Somewhere | 555 | pat@example.test")
        self.assertEqual(code, 0)
        self.assertEqual(up.header_text(), "# Pat Example\nSomewhere | 555 | pat@example.test\n")
        self.assertIn("# Pat Example", out)
        self.assertIn("header: present", self.run_cli("status")[1])

    def test_header_set_needs_both_parts(self):
        self.run_cli("init", "--resume-root", str(self.resumes))
        self.assertEqual(self.run_cli("header", "set", "Pat Example")[0], 1)

    def test_older_header_file_is_still_read_until_a_header_is_saved(self):
        self.run_cli("init", "--resume-root", str(self.resumes))
        up.HEADER_FILE.parent.mkdir(parents=True, exist_ok=True)
        up.HEADER_FILE.write_text("# Old Name\nOld line\n", encoding="utf-8")
        self.assertEqual(up.header_text(), "# Old Name\nOld line\n")
        self.run_cli("header", "set", "New Name", "New line")
        self.assertEqual(up.header_text(), "# New Name\nNew line\n")

    def test_years_of_experience_accepts_a_plus_and_rejects_nonsense(self):
        self.run_cli("init", "--resume-root", str(self.resumes))
        self.assertEqual(self.run_cli("set", "years_experience", "12+")[0], 0)
        self.assertEqual(up.years_experience(), 12)
        self.assertEqual(self.run_cli("set", "years_experience", "lots")[0], 1)
        self.assertEqual(self.run_cli("set", "years_experience", "99")[0], 1)
        self.assertEqual(up.years_experience(), 12)

    def test_set_validates_key(self):
        self.run_cli("init", "--resume-root", str(self.resumes))
        self.assertEqual(self.run_cli("set", "colour", "red")[0], 1)
        self.assertEqual(self.run_cli("set", "name", "Sam")[0], 0)
        self.assertEqual(up.load()["name"], "Sam")

    def test_tier1_pin_and_show(self):
        self.run_cli("init", "--resume-root", str(self.resumes))
        _, out, _ = self.run_cli("tier1", "Lambda", "S3")
        self.assertEqual(out.split(), ["Lambda", "S3"])
        self.assertEqual(up.tier1_services(), ["Lambda", "S3"])

    def test_companies_registry_never_overwrites(self):
        self.assertEqual(up.add_companies({"acme": "Acme Corp"}), ["acme"])
        self.assertEqual(up.add_companies({"acme": "Other Name", "globex": "Globex"}), ["globex"])
        reg = up.company_registry()
        self.assertEqual(reg["acme"][0], "Acme Corp")
        self.assertTrue(reg["acme"][1].startswith("Acme\\ Corp"))

    def test_rename_an_employer(self):
        up.add_companies({"acme": "Acme Corp"})
        self.assertEqual(self.run_cli("companies", "rename", "acme", "Acme Inc")[0], 0)
        self.assertEqual(up.company_registry()["acme"][0], "Acme Inc")
        self.assertIn("Acme Inc", self.run_cli("companies")[1])
        self.assertEqual(self.run_cli("companies", "rename", "nope", "X")[0], 1)
        self.assertEqual(self.run_cli("companies", "rename", "acme")[0], 1)

    def test_merge_two_employers_into_one(self):
        up.add_companies({"acme": "Acme Corp", "acme-ltd": "Acme Ltd"})
        code, out, _ = self.run_cli("companies", "merge", "acme-ltd", "acme")
        self.assertEqual(code, 0, out)
        registry = up.company_registry()
        self.assertEqual(list(registry), ["acme"])
        pattern = re.compile(registry["acme"][1] + "$")
        for line in ("Acme Corp", "Acme Ltd", "Acme Ltd - Lead Engineer"):
            self.assertTrue(pattern.match(line), line)
        self.assertEqual(self.run_cli("companies", "merge", "acme", "acme")[0], 1)
        self.assertEqual(self.run_cli("companies", "merge", "acme", "gone")[0], 1)

    def test_merge_refuses_a_custom_pattern(self):
        up.add_companies({"a": "A Co", "b": "B Co"})
        employers = utables.load_employers()
        employers["b"]["regex"] = "B.*"
        utables.replace_employers(employers)
        self.assertEqual(self.run_cli("companies", "merge", "b", "a")[0], 1)

    def test_open_items_add_done_and_errors(self):
        self.assertIn("No open items", self.run_cli("open")[1])
        self.assertIn("1. fix figure", self.run_cli("open", "add", "fix figure")[1])
        self.assertIn("2. pick a number", self.run_cli("open", "add", "pick a number")[1])
        self.assertEqual(self.run_cli("open", "done", "1")[1].strip(), "2. pick a number")
        code, _, err = self.run_cli("open", "done", "99")
        self.assertEqual((code, err.strip()), (1, "No open item 99"))
        self.assertEqual(self.run_cli("open", "add")[0], 1)

class RetestWindowTests(ProfileCase):
    def test_default_is_thirty_and_status_says_so(self):
        self.assertEqual(up.reassess_days(), 30)
        self.run_cli("init", "--resume-root", str(self.resumes))
        self.assertEqual(up.reassess_days(), 30)
        self.assertIn("retest window: 30 days (default, not set)", self.run_cli("status")[1])

    def test_set_stores_the_window_and_status_shows_it(self):
        self.run_cli("init", "--resume-root", str(self.resumes))
        self.assertEqual(self.run_cli("set", "reassess_days", "45")[0], 0)
        self.assertEqual(up.reassess_days(), 45)
        self.assertIn("retest window: 45 days\n", self.run_cli("status")[1])

    def test_invalid_values_are_rejected_and_change_nothing(self):
        self.run_cli("init", "--resume-root", str(self.resumes))
        self.run_cli("set", "reassess_days", "45")
        for bad in ("0", "366", "-3", "soon", "4.5", ""):
            code, _, err = self.run_cli("set", "reassess_days", bad)
            self.assertEqual(code, 1, bad)
            self.assertIn("from 1 to 365", err)
            self.assertEqual(up.reassess_days(), 45, bad)

    def test_edges_are_accepted(self):
        self.run_cli("init", "--resume-root", str(self.resumes))
        for good in ("1", "365"):
            self.assertEqual(self.run_cli("set", "reassess_days", good)[0], 0)
            self.assertEqual(up.reassess_days(), int(good))


class AnswerStyleTests(ProfileCase):
    def test_default_is_star_and_status_says_so(self):
        self.run_cli("init", "--resume-root", str(self.resumes))
        self.assertIsNone(up.answer_style())
        self.assertIn("answer style: star (default, not set)", self.run_cli("status")[1])

    def test_set_stores_the_style_and_status_shows_it(self):
        self.run_cli("init", "--resume-root", str(self.resumes))
        self.assertEqual(self.run_cli("set", "answer_style", "carl")[0], 0)
        self.assertEqual(up.answer_style(), "carl")
        self.assertIn("answer style: carl\n", self.run_cli("status")[1])

    def test_a_value_is_accepted_in_any_letter_case(self):
        self.run_cli("init", "--resume-root", str(self.resumes))
        self.assertEqual(self.run_cli("set", "answer_style", "SOAR")[0], 0)
        self.assertEqual(up.answer_style(), "soar")

    def test_invalid_value_names_the_styles_and_changes_nothing(self):
        self.run_cli("init", "--resume-root", str(self.resumes))
        self.run_cli("set", "answer_style", "soar")
        for bad in ("bogus", "", "star soar"):
            code, _, err = self.run_cli("set", "answer_style", bad)
            self.assertEqual(code, 1, bad)
            self.assertIn("star, soar, carl", err)
            self.assertEqual(up.answer_style(), "soar", bad)

    def test_an_option_overrides_the_default_for_that_run_only(self):
        self.run_cli("init", "--resume-root", str(self.resumes))
        self.run_cli("set", "answer_style", "carl")
        self.assertEqual(styles.in_force("soar"), "soar")
        self.assertEqual(up.answer_style(), "carl")


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


    def test_replace_corrects_the_folder_and_its_parts_and_keeps_the_rest(self):
        first, second = self.home / "one", self.home / "two"
        first.mkdir()
        second.mkdir()
        self.run_cli("init", "--resume-root", str(first), "--name", "Synthetic One", "--resume-dir", "a")
        code, out = self.run_cli("init", "--replace", "--resume-root", str(second), "--resume-dir", "b", "--resume-dir", "c")
        self.assertEqual(code, 0)
        self.assertIn("Replaced the resume folder settings", out)
        profile = up.load()
        self.assertEqual((profile["resume_root"], profile["resume_dirs"], profile["name"]),
                         (str(second), ["b", "c"], "Synthetic One"))
        self.run_cli("init", "--replace", "--resume-root", str(second))
        self.assertEqual(up.load()["resume_dirs"], [], "no --resume-dir means the whole folder")

    def test_replace_still_needs_a_real_folder(self):
        root = self.home / "r"
        root.mkdir()
        self.run_cli("init", "--resume-root", str(root))
        code, _ = self.run_cli("init", "--replace", "--resume-root", str(self.home / "missing"))
        self.assertEqual(code, 1)
        self.assertEqual(up.load()["resume_root"], str(root))


class PreparingForTests(HomeCase):
    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = up.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_set_shows_and_validates_preparing_for(self):
        root = self.home / "r"
        root.mkdir()
        self.run_cli("init", "--resume-root", str(root))
        self.assertIsNone(up.preparing_for())
        self.assertIn("preparing for: (not set yet)", self.run_cli("status")[1])
        self.assertEqual(self.run_cli("set", "preparing_for", "  Backend engineer,\n Python  ")[0], 0)
        self.assertEqual(up.preparing_for(), "Backend engineer, Python")
        self.assertIn("preparing for: Backend engineer, Python", self.run_cli("status")[1])
        for bad in ("", "   ", "x" * (up.PREPARING_FOR_MAX + 1)):
            with self.subTest(bad=bad[:10]):
                self.assertEqual(self.run_cli("set", "preparing_for", bad)[0], 1)
        self.assertEqual(up.preparing_for(), "Backend engineer, Python")


class ProfileCompaniesTests(HomeCase):
    def test_lists_companies_or_says_to_scan(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(up.main(["companies"]), 0)
            self.assertIn("No scan yet", out.getvalue())
            up.add_companies({"acme": "Acme Corp"})
            out.truncate(0)
            self.assertEqual(up.main(["companies"]), 0)
        self.assertIn("Acme Corp", out.getvalue())


if __name__ == "__main__":
    unittest.main()
