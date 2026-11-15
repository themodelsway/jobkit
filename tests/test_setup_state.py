"""Tests for `jobkit status --setup` (plugins/jobkit/src/jk/setup_state.py, admin.py)."""
import contextlib
import io
import os
import platform
import sqlite3
import sys
import unittest
from importlib.metadata import version
from pathlib import Path
from unittest import mock

from jk import admin, common, setup_state, store
from jk.common import TROUBLESHOOT_HINT, ToolError
from jk.interview import practice_tables
from jk.user import profile
from jk.user import tables as user_tables
from tests.seed_data import seed
from tests.support import HomeCase


def jobkit(*argv: str) -> tuple[int, str, str]:
    """Run the `jobkit` command in-process; (status, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = admin.main(list(argv))
    return code, out.getvalue(), err.getvalue()


def add_resumes() -> None:
    """A profile and the marker that resume data exists, as after the first import."""
    user_tables.replace_settings({"resume_root": "resumes"})
    with store.transaction() as conn:
        store.meta_put(conn, "resume.skills", {"groups": {}})


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
        self.assertEqual(profile.main(["set", "preparing_for", "Backend engineer, Python"]), 0)
        self.assertEqual(setup_state.setup_stage(), "ready")
        self.assertEqual(jobkit("status", "--setup"), (0, "ready\n", ""))

    def test_a_preparation_that_stopped_part_way_is_not_ready(self):
        add_resumes()
        practice_tables.replace_questions([{"id": "q1", "text": "Tell me about a conflict."}])   # as after `lead init`
        self.assertEqual(setup_state.setup_stage(), "no-target")
        with store.transaction() as conn:                                                     # and `prep init`, `arch init`
            store.meta_put(conn, "prep.stories", {"schema_version": 1})
            store.meta_put(conn, "arch.catalog", {"tracks": []})
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
        profile.main(["set", "preparing_for", "Backend engineer, Python"])
        code, out, _ = jobkit("status", "--summary")
        self.assertEqual(code, 0)
        lines = out.splitlines()
        self.assertEqual(lines[0], "setup: ready")
        for start in ("open sessions: ", "due for a retest: ", "company research: "):
            self.assertTrue(any(x.startswith(start) for x in lines), (start, out))
        self.assertIn("latest open session: s1", out)

    def test_setup_and_summary_cannot_be_combined(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            admin.main(["status", "--setup", "--summary"])


class NoHomeFolderInOutputTests(HomeCase):
    def test_commands_never_print_the_home_folder(self):
        with mock.patch.object(Path, "home", return_value=self.home):
            outputs = [jobkit("status"), jobkit("init"), jobkit("backup", "-o", str(self.home / "copy.db")),
                       jobkit("status", "--summary"), jobkit("backup", "--restore", str(self.home / "missing.db"))]
        for _code, out, err in outputs:
            with self.subTest(out=out[:40], err=err[:40]):
                self.assertNotIn(str(self.home), out + err)
        self.assertIn("Backup written to ~", outputs[2][1])
        self.assertTrue((self.home / "copy.db").is_file())

    def test_a_backup_path_given_with_tilde_is_written_in_the_home_folder(self):
        with mock.patch.object(Path, "home", return_value=self.home), \
                mock.patch.dict(os.environ, {"HOME": str(self.home), "USERPROFILE": str(self.home)}):
            code, out, _ = jobkit("backup", "-o", "~/copy2.db")
        self.assertEqual(code, 0)
        self.assertTrue((self.home / "copy2.db").is_file(), out)
