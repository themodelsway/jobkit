"""Tests for `jobkit status --summary` (plugins/jobkit/src/jk/summary.py)."""
import contextlib
import io
import platform
import sys
from datetime import date
from importlib.metadata import version
from pathlib import Path
from unittest import mock

from jk import admin, common, setup_state, store, summary
from jk.common import TROUBLESHOOT_HINT
from jk.user import profile
from tests.seed_data import seed
from tests.support import HomeCase, add_resumes, jobkit


class SummaryTests(HomeCase):
    def test_without_a_database_only_the_setup_and_folder_lines_are_shown(self):
        store.close()
        store.db_path().unlink()
        code, out, err = jobkit("status", "--summary")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual([x.split(":")[0] for x in out.splitlines()],
                         ["setup", "JOBKIT_HOME", "JOBKIT_COMMANDS_DIR", "JOBKIT_PROGRAM_DIR"])
        self.assertFalse(store.db_path().exists())

    def test_the_folder_lines_report_the_running_copy_with_hide_home(self):
        with mock.patch.object(sys, "argv", [str(Path.home() / "tools" / "bin" / "jobkit")]):
            lines = dict(x.split(": ", 1) for x in jobkit("status", "--summary")[1].splitlines()[:4])
        self.assertEqual(lines["JOBKIT_HOME"], f"{common.hide_home(str(common.home()))} (the data folder)")
        self.assertEqual(lines["JOBKIT_COMMANDS_DIR"],
                         f"{Path('~') / 'tools' / 'bin'} (uv's launchers for the jobkit commands)")
        self.assertTrue(lines["JOBKIT_PROGRAM_DIR"].startswith(common.hide_home(sys.prefix) + " "))
        self.assertIn(f"jobkit {version('jobkit')}, Python {platform.python_version()}", lines["JOBKIT_PROGRAM_DIR"])
        self.assertNotIn(str(Path.home()), "\n".join(lines.values()))

    def test_a_failed_check_still_shows_the_folders(self):
        with mock.patch.object(setup_state, "_stage", side_effect=RuntimeError("boom")):
            code, out, err = jobkit("status", "--summary")
        self.assertEqual(code, 1)
        self.assertEqual(out.splitlines()[0], "setup: failed")
        self.assertTrue(out.splitlines()[1].startswith("JOBKIT_HOME: "))
        self.assertTrue(err.endswith(TROUBLESHOOT_HINT + "\n"))

    def test_ready_data_lists_sessions_retests_and_research(self):
        seed()
        add_resumes()
        profile.main(["set", "preparing_for", "HR business partner, people analytics"])
        code, out, _ = jobkit("status", "--summary")
        self.assertEqual(code, 0)
        lines = out.splitlines()
        self.assertEqual(lines[0], "setup: ready")
        for start in ("open sessions: ", "due for a retest: ", "company research: "):
            self.assertTrue(any(x.startswith(start) for x in lines), (start, out))
        self.assertIn("latest open session: s1", out)
        self.assertEqual(lines[-1], "suggested next: continue-session s1")

    def test_nothing_is_suggested_until_setup_is_ready(self):
        seed()
        add_resumes()
        out = jobkit("status", "--summary")[1]
        self.assertIn("setup: no-target", out)
        self.assertEqual(out.splitlines()[-1], "suggested next: none")

    def test_the_suggestion_is_the_first_step_that_applies(self):
        today = date(2026, 11, 17)
        session = [{"id": "s9"}]
        with mock.patch.object(summary, "_fresh_default_company", return_value="Acme Corp"):
            self.assertEqual(summary.suggested_next(session, 4, today), "continue-session s9")
            self.assertEqual(summary.suggested_next([], 4, today), "retest 4")
            self.assertEqual(summary.suggested_next([], 0, today), "prepare-for Acme Corp")
        with mock.patch.object(summary, "_fresh_default_company", return_value=None):
            self.assertEqual(summary.suggested_next([], 0, today), "none")

    def test_only_a_freshly_researched_default_company_is_suggested(self):
        today = date(2026, 11, 17)
        companies = [{"name": "Acme Corp"}]
        with mock.patch.object(summary.target_tables, "load_companies", return_value=companies), \
                mock.patch.object(summary.profile, "target_company", return_value="acme corp"):
            for state, wanted in (("fresh", "acme corp"), ("stale", None), ("none found", None)):
                with mock.patch.object(summary.targets, "state", return_value=state):
                    self.assertEqual(summary._fresh_default_company(today), wanted, state)
        with mock.patch.object(summary.profile, "target_company", return_value=None):
            self.assertIsNone(summary._fresh_default_company(today))

    def test_setup_and_summary_cannot_be_combined(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            admin.main(["status", "--setup", "--summary"])
