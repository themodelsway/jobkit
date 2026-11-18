"""Tests for plugins/jobkit/src/jk/user/profile.py: the `profile` command and the settings it keeps."""
import contextlib
import io
import re
from unittest import mock

from jk.interview import styles
from jk.user import profile as up
from jk.user import tables as utables
from tests.support import HomeCase
from tests.user.support import run_profile


class ProfileCase(HomeCase):
    def setUp(self):
        super().setUp()
        self.tmp = self.home
        self.resumes = self.tmp / "resumes"
        self.resumes.mkdir()


class ProfileTests(ProfileCase):
    def test_status_without_profile(self):
        code, out, _ = run_profile("status")
        self.assertEqual(code, 0)
        self.assertIn("No profile", out)

    def test_need_explains_how_to_set_up(self):
        code, _, err = run_profile("key-topics")
        self.assertEqual(code, 1)
        self.assertIn("Ask the user where their resume files are", err)

    def test_init_then_status_and_dirs(self):
        code, _out, _ = run_profile("init", "--resume-root", str(self.resumes), "--resume-dir", "2026", "--name", "Pat")
        self.assertEqual(code, 0)
        self.assertEqual(up.resume_root(), self.resumes)
        self.assertEqual(up.resume_dirs(), [self.resumes / "2026"])
        _, status, _ = run_profile("status")
        self.assertIn("name: Pat", status)
        self.assertIn("from your resume scan", status)

    def test_folder_with_spaces_is_stored_as_given(self):
        spaced = self.tmp / "My Resumes 2026"
        spaced.mkdir()
        code, _, _ = run_profile("init", "--resume-root", str(spaced))
        self.assertEqual(code, 0)
        self.assertEqual(up.resume_root(), spaced)

    def test_init_rejects_missing_folder(self):
        code, _, err = run_profile("init", "--resume-root", str(self.tmp / "nope"))
        self.assertEqual(code, 1)
        self.assertIn("is not a folder", err)

    def test_set_resume_root_also_rejects_a_missing_folder(self):
        run_profile("init", "--resume-root", str(self.resumes))
        code, _, err = run_profile("set", "resume_root", str(self.tmp / "nope"))
        self.assertEqual(code, 1)
        self.assertIn("is not a folder", err)
        self.assertEqual(up.resume_root(), self.resumes)

    def test_a_windows_home_folder_path_is_understood(self):
        with mock.patch("jk.base._is_windows", return_value=True), \
                mock.patch("jk.base.Path.home", return_value=self.tmp):
            code, _, err = run_profile("init", "--resume-root", "%USERPROFILE%\\" + self.resumes.name)
            self.assertEqual(code, 0, err)
            self.assertEqual(up.resume_root(), self.resumes)

    def test_header_is_saved_in_the_database_and_shown(self):
        run_profile("init", "--resume-root", str(self.resumes))
        self.assertIn("No header saved yet", run_profile("header")[1])
        code, out, _ = run_profile("header", "set", "Pat Example", "Somewhere | 555 | pat@example.test")
        self.assertEqual(code, 0)
        self.assertEqual(up.header_text(), "# Pat Example\nSomewhere | 555 | pat@example.test\n")
        self.assertIn("# Pat Example", out)
        self.assertIn("header: present", run_profile("status")[1])

    def test_header_set_needs_both_parts(self):
        run_profile("init", "--resume-root", str(self.resumes))
        self.assertEqual(run_profile("header", "set", "Pat Example")[0], 1)

    def test_older_header_file_is_still_read_until_a_header_is_saved(self):
        run_profile("init", "--resume-root", str(self.resumes))
        up.HEADER_FILE.parent.mkdir(parents=True, exist_ok=True)
        up.HEADER_FILE.write_text("# Old Name\nOld line\n", encoding="utf-8")
        self.assertEqual(up.header_text(), "# Old Name\nOld line\n")
        run_profile("header", "set", "New Name", "New line")
        self.assertEqual(up.header_text(), "# New Name\nNew line\n")

    def test_years_of_experience_accepts_a_plus_and_rejects_nonsense(self):
        run_profile("init", "--resume-root", str(self.resumes))
        self.assertEqual(run_profile("set", "years_experience", "12+")[0], 0)
        self.assertEqual(up.years_experience(), 12)
        self.assertEqual(run_profile("set", "years_experience", "lots")[0], 1)
        self.assertEqual(run_profile("set", "years_experience", "99")[0], 1)
        self.assertEqual(up.years_experience(), 12)

    def test_set_validates_key(self):
        run_profile("init", "--resume-root", str(self.resumes))
        self.assertEqual(run_profile("set", "color", "red")[0], 1)
        self.assertEqual(run_profile("set", "name", "Sam")[0], 0)
        self.assertEqual(up.load()["name"], "Sam")

    def test_key_topics_pin_and_show(self):
        run_profile("init", "--resume-root", str(self.resumes))
        _, out, _ = run_profile("key-topics", "Payroll calendar", "Leave policy")
        self.assertEqual(out.splitlines(), ["Payroll calendar", "Leave policy"])
        self.assertEqual(up.key_topics(), ["Payroll calendar", "Leave policy"])

    def test_companies_registry_never_overwrites(self):
        self.assertEqual(up.add_companies({"Acme Corp": 1}).new, ["acme-corp"])
        utables.replace_employers({"acme-corp": {**utables.load_employers()["acme-corp"], "name": "Acme"}})
        self.assertEqual(up.add_companies({"Acme Corp": 2, "Acme 2": 1}).new, ["acme-2"])
        reg = up.company_registry()
        self.assertEqual(reg["acme-corp"][0], "Acme", "a renamed employer keeps its name")
        self.assertTrue(reg["acme-corp"][1].startswith("Acme\\ Corp"))
        self.assertEqual(up.add_companies({"Acme 3": 1}, save=False).new, ["acme-3"])
        self.assertNotIn("acme-3", up.company_registry(), "a survey saves nothing")

    def test_rename_an_employer(self):
        up.add_companies({"Acme": 1})
        self.assertEqual(run_profile("companies", "rename", "acme", "Acme Inc")[0], 0)
        self.assertEqual(up.company_registry()["acme"][0], "Acme Inc")
        self.assertIn("Acme Inc", run_profile("companies")[1])
        self.assertEqual(run_profile("companies", "rename", "nope", "X")[0], 1)
        self.assertEqual(run_profile("companies", "rename", "acme")[0], 1)

    def test_merge_two_employers_into_one(self):
        up.add_companies({"Acme": 1, "Acme Labs": 1})
        code, out, _ = run_profile("companies", "merge", "acme-labs", "acme")
        self.assertEqual(code, 0, out)
        registry = up.company_registry()
        self.assertEqual(list(registry), ["acme"])
        pattern = re.compile(registry["acme"][1] + "$")
        for line in ("Acme", "Acme Labs", "Acme Labs - Lead Designer"):
            self.assertTrue(pattern.match(line), line)
        self.assertEqual(run_profile("companies", "merge", "acme", "acme")[0], 1)
        self.assertEqual(run_profile("companies", "merge", "acme", "gone")[0], 1)

    def test_merge_refuses_a_custom_pattern(self):
        up.add_companies({"Acme": 1, "Acme Labs": 1})
        employers = utables.load_employers()
        employers["acme-labs"]["regex"] = "Acme L.*"
        utables.replace_employers(employers)
        self.assertEqual(run_profile("companies", "merge", "acme-labs", "acme")[0], 1)


class EmployerSpellingTests(HomeCase):
    """Spellings of one employer are merged by the scan; names that only look alike are listed for the user."""

    def test_spellings_that_differ_only_in_form_are_one_employer(self):
        scan = up.add_companies({"Acme Corp": 3, "ACME CORP.": 1, "Acme Corporation": 1, "The Acme Corp, Inc.": 1})
        self.assertEqual(scan.new, ["acme-corp"])
        self.assertEqual(sorted(scan.merged["acme-corp"]), ["ACME CORP.", "Acme Corporation", "The Acme Corp, Inc."])
        pattern = re.compile(up.company_registry()["acme-corp"][1] + "$")
        for line in ("Acme Corp", "ACME CORP.", "Acme Corporation - Lead Designer", "The Acme Corp, Inc."):
            self.assertTrue(pattern.match(line), line)

    def test_the_spelling_in_most_resumes_is_the_name_and_capitals_lose_a_tie(self):
        self.assertEqual(up.add_companies({"ACME WORKS": 1, "Acme Works": 1}).new, ["acme-works"])
        self.assertEqual(utables.load_employers()["acme-works"]["name"], "Acme Works")
        self.assertEqual(up.add_companies({"Acme & Sons": 1, "Acme and Sons Ltd": 4}).new, ["acme-and-sons-ltd"])
        self.assertEqual(up.add_companies({"ACME LABS, Inc.": 1, "Acme Labs": 1}).new, ["acme-labs"])

    def test_a_new_spelling_of_a_stored_employer_is_added_to_it(self):
        up.add_companies({"Acme Labs": 1})
        scan = up.add_companies({"Acme-Labs, LLC": 1, "Acme Labs": 2})
        self.assertEqual((scan.new, scan.merged), ([], {"acme-labs": ["Acme-Labs, LLC"]}))
        stored = utables.load_employers()["acme-labs"]
        self.assertEqual((stored["name"], stored["aliases"]), ("Acme Labs", ["Acme-Labs, LLC"]))
        self.assertEqual(up.add_companies({"Acme-Labs, LLC": 1}).merged, {}, "a known spelling changes nothing")

    def test_a_spelling_whose_id_an_edited_employer_holds_is_reported_not_stored(self):
        utables.replace_employers({"acme-labs": {"name": "Acme Labs", "regex": "Acme Labs Ltd"}})
        scan = up.add_companies({"Acme-Labs": 1})
        self.assertEqual((scan.new, scan.merged, scan.skipped), ([], {}, ["Acme-Labs"]))
        self.assertEqual(utables.load_employers()["acme-labs"]["regex"], "Acme Labs Ltd", "an edited pattern stays")

    def test_names_that_only_look_alike_are_listed_not_merged(self):
        up.add_companies({"Acme": 1, "Acme Labs": 1, "Acme Research Group": 1, "ARG": 1})
        self.assertEqual(len(utables.load_employers()), 4)
        out = run_profile("companies")[1]
        self.assertIn("may be one employer", out)
        for pair in ('acme "Acme" and acme-labs "Acme Labs"', 'acme "Acme" and acme-research-group',
                     'acme-research-group "Acme Research Group" and arg "ARG"'):
            self.assertIn(pair, out)
        self.assertNotIn('acme-labs "Acme Labs" and acme-research-group', out)

    def test_a_name_off_by_a_letter_looks_alike(self):
        up.add_companies({"Acme Systems": 1, "Acme Sytems": 1})
        self.assertIn('acme-systems "Acme Systems" and acme-sytems "Acme Sytems"', run_profile("companies")[1])

    def test_no_look_alike_section_when_names_differ(self):
        up.add_companies({"Acme Labs": 1, "Acme Works": 1})
        self.assertNotIn("may be one employer", run_profile("companies")[1])

    def test_open_items_add_done_and_errors(self):
        self.assertIn("No open items", run_profile("open")[1])
        self.assertIn("1. fix figure", run_profile("open", "add", "fix figure")[1])
        self.assertIn("2. pick a number", run_profile("open", "add", "pick a number")[1])
        self.assertEqual(run_profile("open", "done", "1")[1].strip(), "2. pick a number")
        code, _, err = run_profile("open", "done", "99")
        self.assertEqual((code, err.strip()), (1, "No open item 99"))
        self.assertEqual(run_profile("open", "add")[0], 1)


class RetestWindowTests(ProfileCase):
    def test_default_is_thirty_and_status_says_so(self):
        self.assertEqual(up.reassess_days(), 30)
        run_profile("init", "--resume-root", str(self.resumes))
        self.assertEqual(up.reassess_days(), 30)
        self.assertIn("retest window: 30 days (default, not set)", run_profile("status")[1])

    def test_set_stores_the_window_and_status_shows_it(self):
        run_profile("init", "--resume-root", str(self.resumes))
        self.assertEqual(run_profile("set", "reassess_days", "45")[0], 0)
        self.assertEqual(up.reassess_days(), 45)
        self.assertIn("retest window: 45 days\n", run_profile("status")[1])

    def test_invalid_values_are_rejected_and_change_nothing(self):
        run_profile("init", "--resume-root", str(self.resumes))
        run_profile("set", "reassess_days", "45")
        for bad in ("0", "366", "-3", "soon", "4.5", ""):
            code, _, err = run_profile("set", "reassess_days", bad)
            self.assertEqual(code, 1, bad)
            self.assertIn("from 1 to 365", err)
            self.assertEqual(up.reassess_days(), 45, bad)

    def test_edges_are_accepted(self):
        run_profile("init", "--resume-root", str(self.resumes))
        for good in ("1", "365"):
            self.assertEqual(run_profile("set", "reassess_days", good)[0], 0)
            self.assertEqual(up.reassess_days(), int(good))


class AnswerStyleTests(ProfileCase):
    def test_default_is_star_and_status_says_so(self):
        run_profile("init", "--resume-root", str(self.resumes))
        self.assertIsNone(up.answer_style())
        self.assertIn("answer style: star (default, not set)", run_profile("status")[1])

    def test_set_stores_the_style_and_status_shows_it(self):
        run_profile("init", "--resume-root", str(self.resumes))
        self.assertEqual(run_profile("set", "answer_style", "carl")[0], 0)
        self.assertEqual(up.answer_style(), "carl")
        self.assertIn("answer style: carl\n", run_profile("status")[1])

    def test_a_value_is_accepted_in_any_letter_case(self):
        run_profile("init", "--resume-root", str(self.resumes))
        self.assertEqual(run_profile("set", "answer_style", "SOAR")[0], 0)
        self.assertEqual(up.answer_style(), "soar")

    def test_invalid_value_names_the_styles_and_changes_nothing(self):
        run_profile("init", "--resume-root", str(self.resumes))
        run_profile("set", "answer_style", "soar")
        for bad in ("bogus", "", "star soar"):
            code, _, err = run_profile("set", "answer_style", bad)
            self.assertEqual(code, 1, bad)
            self.assertIn("star, soar, carl", err)
            self.assertEqual(up.answer_style(), "soar", bad)

    def test_an_option_overrides_the_default_for_that_run_only(self):
        run_profile("init", "--resume-root", str(self.resumes))
        run_profile("set", "answer_style", "carl")
        self.assertEqual(styles.in_force("soar"), "soar")
        self.assertEqual(up.answer_style(), "carl")


class ProfileInitTests(HomeCase):
    def test_second_init_keeps_answers(self):
        first, second = self.home / "one", self.home / "two"
        first.mkdir()
        second.mkdir()
        run_profile("init", "--resume-root", str(first), "--name", "Synthetic One", "--resume-dir", "a")
        code, out, _ = run_profile("init", "--resume-root", str(second), "--name", "Synthetic Two", "--resume-dir", "b")
        self.assertEqual(code, 0)
        self.assertIn("Kept the existing", out)
        profile = up.load()
        self.assertEqual((profile["resume_root"], profile["name"], profile["resume_dirs"]),
                         (str(first), "Synthetic One", ["a"]))

    def test_second_init_fills_unset_name(self):
        root = self.home / "r"
        root.mkdir()
        run_profile("init", "--resume-root", str(root))
        run_profile("init", "--resume-root", str(root), "--name", "Pat")
        self.assertEqual(up.load()["name"], "Pat")

    def test_replace_corrects_the_folder_and_its_parts_and_keeps_the_rest(self):
        first, second = self.home / "one", self.home / "two"
        first.mkdir()
        second.mkdir()
        run_profile("init", "--resume-root", str(first), "--name", "Synthetic One", "--resume-dir", "a")
        code, out, _ = run_profile("init", "--replace", "--resume-root", str(second), "--resume-dir", "b", "--resume-dir", "c")
        self.assertEqual(code, 0)
        self.assertIn("Replaced the resume folder settings", out)
        profile = up.load()
        self.assertEqual((profile["resume_root"], profile["resume_dirs"], profile["name"]),
                         (str(second), ["b", "c"], "Synthetic One"))
        run_profile("init", "--replace", "--resume-root", str(second))
        self.assertEqual(up.load()["resume_dirs"], [], "no --resume-dir means the whole folder")

    def test_replace_still_needs_a_real_folder(self):
        root = self.home / "r"
        root.mkdir()
        run_profile("init", "--resume-root", str(root))
        code, _, _ = run_profile("init", "--replace", "--resume-root", str(self.home / "missing"))
        self.assertEqual(code, 1)
        self.assertEqual(up.load()["resume_root"], str(root))


class PreparingForTests(HomeCase):
    def test_set_shows_and_validates_preparing_for(self):
        root = self.home / "r"
        root.mkdir()
        run_profile("init", "--resume-root", str(root))
        self.assertIsNone(up.preparing_for())
        self.assertIn("preparing for: (not set yet)", run_profile("status")[1])
        self.assertEqual(run_profile("set", "preparing_for", "  HR business partner,\n people analytics  ")[0], 0)
        self.assertEqual(up.preparing_for(), "HR business partner, people analytics")
        self.assertIn("preparing for: HR business partner, people analytics", run_profile("status")[1])
        for bad in ("", "   ", "x" * (up.PREPARING_FOR_MAX + 1)):
            with self.subTest(bad=bad[:10]):
                self.assertEqual(run_profile("set", "preparing_for", bad)[0], 1)
        self.assertEqual(up.preparing_for(), "HR business partner, people analytics")


class ProfileCompaniesTests(HomeCase):
    def test_lists_companies_or_says_to_scan(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(up.main(["companies"]), 0)
            self.assertIn("No scan yet", out.getvalue())
            up.add_companies({"Acme Corp": 1})
            out.truncate(0)
            self.assertEqual(up.main(["companies"]), 0)
        self.assertIn("Acme Corp", out.getvalue())
