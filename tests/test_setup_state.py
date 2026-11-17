"""Tests for `jobkit status --setup` (plugins/jobkit/src/jk/setup_state.py, admin.py)."""
import contextlib
import os
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest import mock

from jk import setup_state, store
from jk.common import TROUBLESHOOT_HINT, ToolError
from jk.interview import practice_tables
from jk.user import profile
from jk.user import tables as user_tables
from tests.support import HomeCase, add_resumes, jobkit


class SetupStageTests(HomeCase):
    def test_no_database_is_reported_and_not_created(self):
        store.close()
        store.db_path().unlink()
        self.assertEqual(jobkit("status", "--setup"), (0, "no-database\n", ""))
        self.assertFalse(store.db_path().exists(), "the check created the database")

    def test_empty_database_has_no_resumes(self):
        self.assertEqual(setup_state.setup_stage(), "no-resumes")

    def test_profile_without_resume_data_has_no_resumes(self):
        user_tables.replace_settings({"resume_root": "resumes"})
        self.assertEqual(setup_state.setup_stage(), "no-resumes")

    def test_resumes_without_preparation_have_no_target(self):
        add_resumes()
        self.assertEqual(setup_state.setup_stage(), "no-target")

    def test_saving_what_they_prepare_for_makes_it_ready(self):
        add_resumes()
        self.assertEqual(profile.main(["set", "preparing_for", "HR business partner, people analytics"]), 0)
        self.assertEqual(setup_state.setup_stage(), "ready")
        self.assertEqual(jobkit("status", "--setup"), (0, "ready\n", ""))

    def test_a_preparation_that_stopped_part_way_is_not_ready(self):
        add_resumes()
        practice_tables.replace_questions([{"id": "q1", "text": "Tell me about a conflict."}])   # as after `lead init`
        self.assertEqual(setup_state.setup_stage(), "no-target")
        with store.transaction() as conn:                                                     # and `prep init`, `cards init`
            store.meta_put(conn, "prep.stories", {"schema_version": 1})
            store.meta_put(conn, "cards.catalog", {"tracks": []})
        self.assertEqual(setup_state.setup_stage(), "no-target", "only the step's last save marks it done")

    def test_every_answer_is_one_of_the_four_words(self):
        self.assertEqual(set(setup_state.STAGES), {"no-database", "no-resumes", "no-target", "ready"})
        self.assertIn(setup_state.setup_stage(), setup_state.STAGES)

    def test_plain_status_is_unchanged(self):
        code, out, _ = jobkit("status")
        self.assertEqual(code, 0)
        self.assertIn("database:", out)
        self.assertNotIn("no-resumes", out)


def raised_from(code: int) -> ToolError:
    """A ToolError wrapping an SQLite error with this result code, as the store raises it."""
    cause = sqlite3.OperationalError("simulated")
    cause.sqlite_errorcode = code
    error = ToolError("The database is busy or unavailable (simulated). Try again in a moment.")
    error.__cause__ = cause
    return error


class ClassifyTests(unittest.TestCase):
    def test_sqlite_result_codes_decide_the_word(self):
        cases = {sqlite3.SQLITE_BUSY: "busy", sqlite3.SQLITE_LOCKED: "busy", sqlite3.SQLITE_BUSY_SNAPSHOT: "busy",
                 sqlite3.SQLITE_READONLY: "blocked", sqlite3.SQLITE_CANTOPEN: "blocked", sqlite3.SQLITE_PERM: "blocked",
                 sqlite3.SQLITE_IOERR: "failed", sqlite3.SQLITE_CORRUPT: "failed"}
        for code, word in cases.items():
            with self.subTest(code=code):
                self.assertEqual(setup_state.classify(raised_from(code)), word)

    def test_types_decide_the_word_and_unknown_errors_fail(self):
        self.assertEqual(setup_state.classify(store.NewerDatabaseError("newer")), "too-new")
        self.assertEqual(setup_state.classify(PermissionError("no")), "blocked")
        self.assertEqual(setup_state.classify(ToolError("something else")), "failed")
        self.assertEqual(setup_state.classify(RuntimeError("bug")), "failed")

    def test_the_error_line_names_the_type_and_hides_the_home_folder(self):
        cause = sqlite3.OperationalError("disk I/O error")
        cause.sqlite_errorcode = sqlite3.SQLITE_IOERR
        cause.sqlite_errorname = "SQLITE_IOERR"
        line = setup_state.error_line("failed", RuntimeError(f"cannot read {Path.home() / 'x.db'}"))
        self.assertEqual(line, "failed: RuntimeError: cannot read ~/x.db")
        error = ToolError("unavailable")
        error.__cause__ = cause
        self.assertEqual(setup_state.error_line("failed", error), "failed: OperationalError (SQLITE_IOERR): disk I/O error")


class SetupFailureTests(HomeCase):
    def test_a_newer_database_is_too_new(self):
        store.close()
        with contextlib.closing(sqlite3.connect(store.db_path())) as conn:
            conn.execute(f"PRAGMA user_version={store.version() + 1}")
        code, out, err = jobkit("status", "--setup")
        self.assertEqual((code, out), (1, "too-new\n"))
        self.assertTrue(err.startswith("too-new: "), err)
        self.assertTrue(err.endswith(TROUBLESHOOT_HINT + "\n"), err)

    @unittest.skipIf(sys.platform == "win32" or os.geteuid() == 0, "needs file permissions that apply to this user")
    def test_a_read_only_database_is_blocked(self):
        store.close()
        path = store.db_path()
        path.chmod(0o444)
        self.addCleanup(path.chmod, 0o644)
        code, out, err = jobkit("status", "--setup")
        self.assertEqual((code, out), (1, "blocked\n"), err)

    def test_an_unexpected_error_fails_without_a_traceback(self):
        with mock.patch.object(setup_state, "_stage", side_effect=RuntimeError("boom")):
            code, out, err = jobkit("status", "--setup")
        self.assertEqual((code, out, err), (1, "failed\n", f"failed: RuntimeError: boom\n{TROUBLESHOOT_HINT}\n"))

    def test_a_known_stage_has_no_hint_and_a_plain_mistake_has_none_either(self):
        self.assertEqual(jobkit("status", "--setup")[2], "")
        code, _, err = jobkit("backup", "--restore", "no-such-file.db")
        self.assertEqual(code, 1)
        self.assertNotIn(TROUBLESHOOT_HINT, err)
