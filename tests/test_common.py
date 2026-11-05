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
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
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


if __name__ == "__main__":
    unittest.main()
