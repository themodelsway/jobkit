"""Tests for src/user/profile.py in a temp folder. Run: .venv/bin/python -m unittest discover -s tests -t ."""
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock


from jobkit.user import profile as up


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.resumes = self.tmp / "resumes"
        self.resumes.mkdir()
        d = self.tmp / "profile"
        for name, value in (("DIR", d), ("PROFILE_FILE", d / "profile.json"), ("COMPANIES_FILE", d / "companies.json"),
                            ("HEADER_FILE", d / "header.md"), ("OPEN_ITEMS_FILE", d / "open_items.json")):
            patcher = mock.patch.object(up, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp))

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = up.main(list(argv))
        return code, out.getvalue(), err.getvalue()

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

    def test_init_rejects_missing_folder(self):
        code, _, err = self.run_cli("init", "--resume-root", str(self.tmp / "nope"))
        self.assertEqual(code, 1)
        self.assertIn("is not a folder", err)

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

    def test_open_items_add_done_and_errors(self):
        self.assertIn("No open items", self.run_cli("open")[1])
        self.assertIn("1. fix figure", self.run_cli("open", "add", "fix figure")[1])
        self.assertIn("2. pick a number", self.run_cli("open", "add", "pick a number")[1])
        self.assertEqual(self.run_cli("open", "done", "1")[1].strip(), "2. pick a number")
        code, _, err = self.run_cli("open", "done", "99")
        self.assertEqual((code, err.strip()), (1, "No open item 99"))
        self.assertEqual(self.run_cli("open", "add")[0], 1)


if __name__ == "__main__":
    unittest.main()
