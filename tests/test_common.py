"""Tests for src/jobkit/common.py. Run: .venv/bin/python -m unittest discover -s tests -t ."""
import argparse
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from jobkit import common
from jobkit.common import ToolError


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

    def test_other_exceptions_are_not_swallowed(self):
        def boom(a):
            raise KeyError("x")
        with self.assertRaises(KeyError):
            common.run(self.ns(boom))


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
