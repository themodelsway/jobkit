"""Tests for plugins/jobkit/src/jk/common.py. Run: uv run python -m unittest discover -s tests -t ."""
import argparse
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path, PurePosixPath, PureWindowsPath
from unittest import mock

from jk import base, common, store
from jk.interview import arch
from jk.common import ToolError


class HomeTests(unittest.TestCase):
    def test_default_and_override(self):
        with mock.patch.dict("os.environ", {"JOBKIT_HOME": "/somewhere"}):
            self.assertEqual(common.home(), Path("/somewhere"))
            self.assertEqual(common.data_dir(), Path("/somewhere/data"))
            self.assertEqual(common.header_file(), Path("/somewhere/profile/header.md"))
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertEqual(common.home(), Path.home() / ".jobkit")


class TextTests(unittest.TestCase):
    def test_slug(self):
        self.assertEqual(common.slug("Amazon  S3 (Glacier)!"), "amazon-s3-glacier")
        self.assertEqual(len(common.slug("x" * 100)), common.SLUG_MAX)

    def test_now_format(self):
        self.assertRegex(common.now(), r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d$")

    def test_read_text_arg(self):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False) as f:
            f.write("jd text")
        self.addCleanup(lambda: Path(f.name).unlink())
        self.assertEqual(common.read_text_arg(f.name), "jd text")
        old = sys.stdin
        sys.stdin = io.StringIO("from stdin")
        try:
            self.assertEqual(common.read_text_arg("-"), "from stdin")
        finally:
            sys.stdin = old


class RunTests(unittest.TestCase):
    @staticmethod
    def ns(fn):
        return argparse.Namespace(fn=fn)

    def test_none_is_success_and_int_is_passed_through(self):
        self.assertEqual(common.run(self.ns(lambda a: None)), 0)
        self.assertEqual(common.run(self.ns(lambda a: 3)), 3)

    def test_tool_error_prints_and_returns_one(self):
        def fail(a):
            raise common.ToolError("bad input")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(common.run(self.ns(fail)), 1)
        self.assertEqual(err.getvalue(), "bad input\n")

    def test_an_unexpected_error_shows_one_line_and_the_hint_never_a_stack_trace(self):
        def boom(a):
            raise KeyError(f"no {Path.home() / 'secret.txt'}")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(common.run(self.ns(boom)), 1)
        self.assertNotIn("Traceback", err.getvalue())
        self.assertNotIn(str(Path.home()), err.getvalue())
        self.assertEqual(err.getvalue(), f"error: KeyError: 'no {Path('~') / 'secret.txt'}'\n{common.TROUBLESHOOT_HINT}\n")

    def test_a_tool_error_hides_the_home_folder(self):
        def fail(a):
            raise common.ToolError(f"{Path.home() / 'resumes'} is not a folder")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            common.run(self.ns(fail))
        self.assertEqual(err.getvalue(), f"{Path('~') / 'resumes'} is not a folder\n")

    def test_a_storage_problem_adds_the_hint_and_a_plain_mistake_does_not(self):
        def busy(a):
            raise store.StoreError("The database is busy (locked). Try again in a moment.")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(common.run(self.ns(busy)), 1)
        self.assertEqual(err.getvalue(), "The database is busy (locked). Try again in a moment.\n"
                         + common.TROUBLESHOOT_HINT + "\n")
        self.assertTrue(store.NewerDatabaseError.troubleshoot)
        self.assertFalse(ToolError.troubleshoot)

    def test_the_hint_names_a_guide_that_ships_with_the_plugin(self):
        name = common.TROUBLESHOOT_HINT.split("read ", 1)[1].split(" in the plugin folder", 1)[0]
        self.assertTrue((Path(__file__).resolve().parents[1] / "plugins" / "jobkit" / name).is_file(), name)


class HomeFolderTests(unittest.TestCase):
    def test_mac_and_linux_home_becomes_tilde_only_at_a_folder_end(self):
        home = PurePosixPath("/srv/people/hellouser1")
        tilde = lambda s: common.hide_home(s, home, windows=False)  # noqa: E731
        self.assertEqual(tilde("cannot read /srv/people/hellouser1/.jobkit/data/jobkit.db"),
                         "cannot read ~/.jobkit/data/jobkit.db")
        self.assertEqual(tilde("/srv/people/hellouser1"), "~")
        self.assertEqual(tilde("/srv/people/hellouser2/x, /srv/people/hellouser10/x and /srv/people/hellouser1.old"),
                         "/srv/people/hellouser2/x, /srv/people/hellouser10/x and /srv/people/hellouser1.old")
        self.assertEqual(tilde("/srv/People/hellouser1/x"), "/srv/People/hellouser1/x", "case counts on Mac and Linux")

    def test_windows_home_becomes_userprofile_in_any_case_slash_or_git_bash_form(self):
        home = PureWindowsPath(r"D:\Profiles\Hellouser1")
        hide = lambda s: common.hide_home(s, home, windows=True)  # noqa: E731
        self.assertEqual(hide(r"cannot read D:\Profiles\Hellouser1\.jobkit\data"), r"cannot read %USERPROFILE%\.jobkit\data")
        self.assertEqual(hide(r"d:\profiles\HELLOUSER1\x"), r"%USERPROFILE%\x")
        self.assertEqual(hide("D:/Profiles/Hellouser1/x"), "%USERPROFILE%/x")
        self.assertEqual(hide("/d/Profiles/Hellouser1/x"), "%USERPROFILE%/x")
        self.assertNotIn("~", hide(r"D:\Profiles\Hellouser1\x"))
        self.assertEqual(hide(r"D:\Profiles\Hellouser2\x and D:\Profiles\Hellouser10\x"),
                         r"D:\Profiles\Hellouser2\x and D:\Profiles\Hellouser10\x")

    def test_a_home_reached_through_a_link_is_hidden_in_both_forms(self):
        with tempfile.TemporaryDirectory() as tmp:
            real = Path(tmp) / "real-home"
            real.mkdir()
            link = Path(tmp) / "linked-home"
            link.symlink_to(real, target_is_directory=True)
            with mock.patch.object(Path, "home", return_value=link):
                text = common.hide_home(f"cannot read {link / 'a.txt'} or {real.resolve() / 'b.txt'}", windows=False)
        self.assertEqual(text, f"cannot read {Path('~') / 'a.txt'} or {Path('~') / 'b.txt'}")

    def test_the_longer_home_form_wins_and_a_match_starts_at_a_folder_name(self):
        homes = [PurePosixPath("/people/hellouser1"), PurePosixPath("/var/people/hellouser1")]
        with mock.patch.object(base, "_known_homes", return_value=homes):
            self.assertEqual(common.hide_home("/var/people/hellouser1/x and /people/hellouser1/y", windows=False),
                             "~/x and ~/y")
            self.assertEqual(common.hide_home("/x/people/hellouser1/z", windows=False), "/x/people/hellouser1/z")

    def test_messages_printed_outside_run_hide_the_home_folder(self):
        out = io.StringIO()
        with mock.patch.object(arch.qr, "load", side_effect=OSError(f"cannot open {Path.home() / 'r.txt'}")), \
                contextlib.redirect_stdout(out):
            arch.load_resume_context()
        self.assertNotIn(str(Path.home()), out.getvalue())
        self.assertIn(str(Path("~") / "r.txt"), out.getvalue())

    def test_a_printed_path_is_read_back_from_the_home_folder(self):
        self.assertEqual(common.user_path("~/x.md"), Path.home() / "x.md")
        self.assertEqual(common.user_path("rel/x.md"), Path("rel/x.md"))
        home = Path("profile-home")
        forms = ["%userprofile%/.jobkit/x.md", "%USERPROFILE%/.jobkit/x.md"]
        if sys.platform == "win32":                        # a backslash separates folders only on Windows
            forms.append(r"%USERPROFILE%\.jobkit\x.md")
        for given in forms:
            with self.subTest(given=given):
                self.assertEqual(common.user_path(given, home, windows=True), home / ".jobkit" / "x.md")
        self.assertEqual(common.user_path("%USERPROFILE%/x", home, windows=False), Path("%USERPROFILE%/x"),
                         "only Windows reads %USERPROFILE%")
        self.assertEqual(common.user_path("a%TEMP%b", home, windows=True), Path("a%TEMP%b"), "nothing else is expanded")


class InputErrorTests(unittest.TestCase):
    def test_unreadable_inputs_become_tool_errors(self):
        with mock.patch("pathlib.Path.read_text", side_effect=UnicodeDecodeError("utf-8", b"", 0, 1, "x")):
            with self.assertRaisesRegex(ToolError, "not a UTF-8"):
                common.read_text_arg("x.txt")
        with self.assertRaisesRegex(ToolError, "cannot read"):
            common.read_text_arg("/no/such/jd.txt")
        with self.assertRaisesRegex(ToolError, "cannot read"):
            common.read_text_arg("/")


if __name__ == "__main__":
    unittest.main()


class Utf8OutputTests(unittest.TestCase):
    def test_a_legacy_code_page_console_can_print_a_long_dash(self):
        raw = io.BytesIO()
        console = io.TextIOWrapper(raw, encoding="cp1252", errors="strict")
        with mock.patch.object(sys, "stdout", console), mock.patch.object(sys, "stderr", io.StringIO()):
            common.use_utf8_output()
            print("one \u2014 two \u2192 three")
            console.flush()
        self.assertEqual(raw.getvalue().decode("utf-8"), "one \u2014 two \u2192 three\n")

    def test_a_utf8_stream_is_left_alone(self):
        console = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
        with mock.patch.object(sys, "stdout", console):
            common.use_utf8_output()
            self.assertEqual(console.errors, "strict")
