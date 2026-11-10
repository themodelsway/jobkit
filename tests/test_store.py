"""Tests for src/jobkit/store.py and src/jobkit/admin.py (the database and the `jobkit` command)."""
import contextlib
import io
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from jobkit import admin, base, common, schema, store
from jobkit.interview import prep, tables
from tests.support import HomeCase

HOLD = """
import sqlite3, sys, time
conn = sqlite3.connect(sys.argv[1], isolation_level=None)
conn.execute("BEGIN IMMEDIATE")
conn.execute("INSERT INTO meta(key, value) VALUES('held', '1')")
print("ready", flush=True)
time.sleep(float(sys.argv[2]))
conn.execute("COMMIT")
"""


def put(key: str) -> None:
    """Store one meta row (a small change to test transactions with)."""
    with store.transaction() as conn:
        conn.execute("INSERT INTO meta(key, value) VALUES(?, '1')", (key,))


def has(key: str) -> bool:
    """True when the meta row exists."""
    with store.transaction(write=False) as conn:
        return conn.execute("SELECT 1 FROM meta WHERE key=?", (key,)).fetchone() is not None


def run_admin(*argv: str) -> tuple[int, str, str]:
    """Run the `jobkit` command in-process; (status, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = admin.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class TransactionTests(HomeCase):
    def test_commit_keeps_changes(self):
        with store.transaction() as conn:
            conn.execute("INSERT INTO meta(key, value) VALUES('a', '1')")
        with store.transaction(write=False) as conn:
            self.assertEqual(conn.execute("SELECT value FROM meta WHERE key='a'").fetchone()[0], "1")

    def test_failure_stores_none_of_the_changes(self):
        with self.assertRaises(RuntimeError), store.transaction() as conn:
            conn.execute("INSERT INTO meta(key, value) VALUES('a', '1')")
            put("x")
            raise RuntimeError("boom")
        self.assertFalse(has("x"))
        with store.transaction(write=False) as conn:
            self.assertIsNone(conn.execute("SELECT 1 FROM meta WHERE key='a'").fetchone())

    def test_nested_use_joins_the_outer_transaction(self):
        with self.assertRaises(RuntimeError), store.transaction():
            put("a")
            put("b")
            raise RuntimeError("boom")
        self.assertFalse(has("a") or has("b"))

    def test_handled_nested_failure_leaves_none_of_its_own_changes(self):
        with store.transaction():
            put("outer")
            with self.assertRaises(RuntimeError), store.transaction():
                put("inner")
                raise RuntimeError("handled")
            put("after")
        self.assertTrue(has("outer") and has("after"))
        self.assertFalse(has("inner"))

    def test_handled_session_save_failure_inside_a_larger_change(self):
        first = {"id": "s1", "title": "old", "mode": "architecture", "status": "open", "created": "2026-11-01T09:00:00",
                 "updated": "2026-11-01T09:00:00", "queue": [], "log": []}
        entry = {"at": "2026-11-01T10:00:00", "item": "vpc", "kind": "card", "answer": "a"}
        tables.replace_catalog({"cards": [{"id": "vpc", "kind": "service", "name": "VPC"}]})
        tables.save_session({**first, "log": [entry]})
        with store.transaction():
            put("outer")
            with self.assertRaises(common.ToolError):
                tables.save_session({**first, "title": "new", "queue": [], "log": []})
        self.assertTrue(has("outer"))
        saved = tables.load_session("s1")
        assert saved is not None
        self.assertEqual((saved["title"], saved["queue"], saved["log"]), ("old", [], [entry]))

    def test_nested_read_opens_no_savepoint(self):
        statements: list[str] = []
        with store.transaction() as conn:
            conn.set_trace_callback(statements.append)
            with store.transaction(write=False):
                pass
            conn.set_trace_callback(None)
        self.assertEqual([s for s in statements if "SAVEPOINT" in s.upper()], [])

    def test_tool_error_in_run_rolls_back(self):
        def handler(_args):
            put("x")
            raise common.ToolError("no")
        with contextlib.redirect_stderr(io.StringIO()):
            code = common.run(mock.Mock(fn=handler), lock=True)
        self.assertEqual(code, 1)
        self.assertFalse(has("x"))

    def test_foreign_keys_are_enforced(self):
        with store.transaction() as conn:
            self.assertEqual(conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            self.assertEqual(conn.execute("PRAGMA journal_mode").fetchone()[0], "wal")


class ConcurrencyTests(HomeCase):
    def hold(self, seconds: float) -> subprocess.Popen[str]:
        proc = subprocess.Popen([sys.executable, "-c", HOLD, str(store.db_path()), str(seconds)],
                                stdout=subprocess.PIPE, text=True)
        assert proc.stdout is not None
        self.addCleanup(proc.stdout.close)
        self.addCleanup(proc.wait)
        self.assertEqual(proc.stdout.readline().strip(), "ready")
        return proc

    def test_second_writer_waits_and_both_changes_are_stored(self):
        self.hold(1.0)
        started = time.monotonic()
        put("mine")
        self.assertGreater(time.monotonic() - started, 0.5)
        with store.transaction(write=False) as conn:
            self.assertEqual(conn.execute("SELECT value FROM meta WHERE key='held'").fetchone()[0], "1")
        self.assertTrue(has("mine"))

    def test_writer_gives_up_with_a_clear_message(self):
        with mock.patch.object(store, "BUSY_TIMEOUT_MS", 200):
            store.close()
            self.hold(1.5)
            with self.assertRaisesRegex(common.ToolError, "busy"):
                put("mine")

    def test_reader_is_not_blocked_by_a_writer(self):
        self.hold(1.0)
        started = time.monotonic()
        with store.transaction(write=False) as conn:
            self.assertIsNone(conn.execute("SELECT 1 FROM meta WHERE key='held'").fetchone())
        self.assertLess(time.monotonic() - started, 0.5)


class DatabaseFileCase(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="jobkit-schema-"))
        self.previous = os.environ["JOBKIT_HOME"]
        os.environ["JOBKIT_HOME"] = str(self.home)
        store.close()
        self.addCleanup(self.restore)

    def restore(self):
        store.close()
        os.environ["JOBKIT_HOME"] = self.previous
        shutil.rmtree(self.home, ignore_errors=True)

    def pragma_version(self) -> int:
        with contextlib.closing(sqlite3.connect(store.db_path())) as conn:
            return conn.execute("PRAGMA user_version").fetchone()[0]


class SchemaTests(DatabaseFileCase):
    def test_fresh_database_is_at_the_current_version(self):
        self.assertTrue(store.create())
        self.assertEqual(self.pragma_version(), store.version())

    def test_upgrade_refuses_to_drop_a_document_table_that_holds_data(self):
        store.db_path().parent.mkdir(parents=True)
        with contextlib.closing(sqlite3.connect(store.db_path(), isolation_level=None)) as conn:
            before_drop = store.MIGRATIONS.index(schema.step_drop_documents)
            store.migrate_to(conn, before_drop)
            conn.execute("INSERT INTO doc VALUES('a', '{}', 't')")
        with self.assertRaisesRegex(RuntimeError, "still holds data"):
            store.connect()
        self.assertEqual(self.pragma_version(), before_drop)

    def test_older_database_is_upgraded_before_a_command_runs(self):
        store.db_path().parent.mkdir(parents=True)
        sqlite3.connect(store.db_path()).close()          # an empty database: version 0
        with store.transaction(write=False) as conn:
            self.assertEqual(store.stored_version(conn), store.version())
            conn.execute("SELECT * FROM meta")

    def test_newer_database_is_refused_and_left_alone(self):
        store.create()
        store.close()
        with contextlib.closing(sqlite3.connect(store.db_path())) as conn:
            conn.execute(f"PRAGMA user_version={store.version() + 5}")
        with self.assertRaisesRegex(common.ToolError, "only knows version"):
            store.connect()
        self.assertEqual(self.pragma_version(), store.version() + 5)

    def test_failed_upgrade_step_changes_nothing(self):
        def broken(conn):
            conn.execute("CREATE TABLE half (x)")
            raise RuntimeError("step failed")
        store.create()
        store.close()
        with mock.patch.object(store, "MIGRATIONS", [*store.MIGRATIONS, broken]):
            with self.assertRaises(RuntimeError):
                store.connect()
        store.close()
        self.assertEqual(self.pragma_version(), store.version())
        with contextlib.closing(sqlite3.connect(store.db_path())) as conn:
            self.assertIsNone(conn.execute("SELECT 1 FROM sqlite_master WHERE name='half'").fetchone())


class AdminTests(DatabaseFileCase):
    def test_init_creates_the_layout(self):
        code, out, _ = run_admin("init")
        self.assertEqual(code, 0)
        self.assertIn("Created", out)
        for folder in ("data", "backup", "output", "profile"):
            self.assertTrue((self.home / folder).is_dir(), folder)
        self.assertTrue(store.db_path().exists())

    def test_repeat_init_changes_nothing(self):
        run_admin("init")
        put("keep")
        code, out, _ = run_admin("init")
        self.assertEqual(code, 0)
        self.assertIn("Already set up", out)
        self.assertTrue(has("keep"))

    def test_commands_need_init_and_never_create_the_database(self):
        code, _, err = run_admin("status")
        self.assertEqual(code, 1)
        self.assertIn("jobkit init", err)
        self.assertFalse(store.db_path().exists())

    def test_other_commands_point_at_init(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            code = prep.main(["list"])
        self.assertEqual(code, 1)
        self.assertIn("jobkit init", err.getvalue())
        self.assertFalse(store.db_path().exists())

    def test_status_shows_location_version_and_counts(self):
        run_admin("init")
        code, out, _ = run_admin("status")
        self.assertEqual(code, 0)
        self.assertIn(str(store.db_path()), out)
        self.assertIn(f"schema version: {store.version()}", out)
        self.assertIn("stories: 0", out)

    def test_status_does_not_change_the_database(self):
        run_admin("init")
        before = store.db_path().read_bytes()
        run_admin("status")
        store.close()
        self.assertEqual(store.db_path().read_bytes(), before)


class HomeTests(unittest.TestCase):
    def test_nothing_is_resolved_from_the_source_tree(self):
        with mock.patch.dict(os.environ, {"JOBKIT_HOME": "/elsewhere"}):
            self.assertEqual(store.db_path(), Path("/elsewhere/data/jobkit.db"))
            self.assertFalse(str(base.output_dir()).startswith(str(Path(base.__file__).parents[2])))


if __name__ == "__main__":
    unittest.main()
