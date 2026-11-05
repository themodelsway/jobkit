"""Tests for src/common.py. Run: .venv/bin/python -m unittest discover -s tests -t ."""
import argparse
import contextlib
import io
import re
import sys
import tempfile
import unittest
from pathlib import Path


from jobkit import common


class JsonTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.dir))

    def test_missing_file_returns_default(self):
        self.assertEqual(common.load_json(self.dir / "nope.json", {"x": 1}), {"x": 1})

    def test_save_creates_parents_and_round_trips(self):
        f = self.dir / "a" / "b.json"
        common.save_json(f, {"name": "é"})
        self.assertEqual(common.load_json(f, None), {"name": "é"})
        self.assertTrue(f.read_text().endswith("\n"))

    def test_second_save_keeps_backup_and_no_temp_file(self):
        f = self.dir / "d.json"
        common.save_json(f, {"v": 1})
        common.save_json(f, {"v": 2})
        self.assertEqual(common.load_json(f.with_name("d.json.bak"), None), {"v": 1})
        self.assertFalse(f.with_name("d.json.tmp").exists())

    def test_invalid_json_names_backup(self):
        f = self.dir / "bad.json"
        common.save_json(f, {"v": 1})
        common.save_json(f, {"v": 2})
        f.write_text("{oops")
        with self.assertRaisesRegex(common.ToolError, r"not valid JSON.*Previous copy"):
            common.load_json(f, None)
        g = self.dir / "worse.json"
        g.write_text("{oops")
        with self.assertRaisesRegex(common.ToolError, "No backup exists"):
            common.load_json(g, None)


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

    def test_lock_wrapper_runs_handler(self):
        lock = Path(tempfile.mkdtemp()) / "sub" / ".lock"
        with common.locked(lock):
            pass
        self.assertTrue(lock.exists())

    def test_repo_root_is_project_folder(self):
        self.assertTrue((common.REPO_ROOT / "src" / "jobkit" / "common.py").exists())
        self.assertTrue(re.match(r".*/prep/\.lock$", str(common.LOCK_FILE)))


if __name__ == "__main__":
    unittest.main()
