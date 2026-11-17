"""Tests for plugins/jobkit/src/jk/store.py and schema.py: transactions, locking, schema upgrades and restore checks."""
import contextlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

from jk import base, common, schema, store
from jk.base import ToolError
from jk.interview import tables
from tests.support import DatabaseFileCase, HomeCase, has_meta, put_meta

HOLD = """
import sqlite3, sys, time
conn = sqlite3.connect(sys.argv[1], isolation_level=None)
conn.execute("BEGIN IMMEDIATE")
conn.execute("INSERT INTO meta(key, value) VALUES('held', '1')")
print("ready", flush=True)
time.sleep(float(sys.argv[2]))
conn.execute("COMMIT")
"""


class TransactionTests(HomeCase):
    def test_commit_keeps_changes(self):
        with store.transaction() as conn:
            conn.execute("INSERT INTO meta(key, value) VALUES('a', '1')")
        with store.transaction(write=False) as conn:
            self.assertEqual(conn.execute("SELECT value FROM meta WHERE key='a'").fetchone()[0], "1")

    def test_failure_stores_none_of_the_changes(self):
        with self.assertRaises(RuntimeError), store.transaction() as conn:
            conn.execute("INSERT INTO meta(key, value) VALUES('a', '1')")
            put_meta("x")
            raise RuntimeError("boom")
        self.assertFalse(has_meta("x"))
        with store.transaction(write=False) as conn:
            self.assertIsNone(conn.execute("SELECT 1 FROM meta WHERE key='a'").fetchone())

    def test_nested_use_joins_the_outer_transaction(self):
        with self.assertRaises(RuntimeError), store.transaction():
            put_meta("a")
            put_meta("b")
            raise RuntimeError("boom")
        self.assertFalse(has_meta("a") or has_meta("b"))

    def test_handled_nested_failure_leaves_none_of_its_own_changes(self):
        with store.transaction():
            put_meta("outer")
            with self.assertRaises(RuntimeError), store.transaction():
                put_meta("inner")
                raise RuntimeError("handled")
            put_meta("after")
        self.assertTrue(has_meta("outer") and has_meta("after"))
        self.assertFalse(has_meta("inner"))

    def test_handled_session_save_failure_inside_a_larger_change(self):
        first = {"id": "s1", "title": "old", "mode": "knowledge", "status": "open", "created": "2026-11-01T09:00:00",
                 "updated": "2026-11-01T09:00:00", "queue": [], "log": []}
        entry = {"at": "2026-11-01T10:00:00", "item": "vpc", "kind": "card", "answer": "a"}
        tables.replace_catalog({"cards": [{"id": "vpc", "kind": "topic", "name": "VPC"}]})
        tables.save_session({**first, "log": [entry]})
        with store.transaction():
            put_meta("outer")
            with self.assertRaises(common.ToolError):
                tables.save_session({**first, "title": "new", "queue": [], "log": []})
        self.assertTrue(has_meta("outer"))
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
            put_meta("x")
            raise common.ToolError("no")
        with contextlib.redirect_stderr(io.StringIO()):
            code = common.run(mock.Mock(fn=handler), lock=True)
        self.assertEqual(code, 1)
        self.assertFalse(has_meta("x"))

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
        put_meta("mine")
        self.assertGreater(time.monotonic() - started, 0.5)
        with store.transaction(write=False) as conn:
            self.assertEqual(conn.execute("SELECT value FROM meta WHERE key='held'").fetchone()[0], "1")
        self.assertTrue(has_meta("mine"))

    def test_writer_gives_up_with_a_clear_message(self):
        with mock.patch.object(store, "BUSY_TIMEOUT_MS", 200):
            store.close()
            self.hold(1.5)
            with self.assertRaisesRegex(common.ToolError, "busy"):
                put_meta("mine")

    def test_reader_is_not_blocked_by_a_writer(self):
        self.hold(1.0)
        started = time.monotonic()
        with store.transaction(write=False) as conn:
            self.assertIsNone(conn.execute("SELECT 1 FROM meta WHERE key='held'").fetchone())
        self.assertLess(time.monotonic() - started, 0.5)


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

    def test_a_failing_step_rolls_back_every_earlier_step(self):
        store.db_path().parent.mkdir(parents=True)
        with contextlib.closing(sqlite3.connect(store.db_path(), isolation_level=None)) as conn:
            store.migrate_to(conn, 3)
        steps = list(store.MIGRATIONS)
        steps[5] = mock.Mock(side_effect=RuntimeError("step failed"))
        with mock.patch.object(store, "MIGRATIONS", steps):
            with contextlib.closing(sqlite3.connect(store.db_path(), isolation_level=None)) as conn:
                tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                with self.assertRaisesRegex(RuntimeError, "step failed"):
                    store.migrate_to(conn, len(steps))
                self.assertEqual(store.stored_version(conn), 3)
                self.assertEqual({r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}, tables)

    def test_an_older_database_is_copied_to_backup_before_the_upgrade(self):
        store.db_path().parent.mkdir(parents=True)
        old = store.MIGRATIONS.index(schema.step_drop_documents)
        with contextlib.closing(sqlite3.connect(store.db_path(), isolation_level=None)) as conn:
            store.migrate_to(conn, old)
        store.connect()
        copies = list(base.backup_dir().glob(f"jobkit-before-upgrade-v{old}-*.db"))
        self.assertEqual(len(copies), 1)
        with contextlib.closing(sqlite3.connect(copies[0])) as copy:
            self.assertEqual(copy.execute("PRAGMA user_version").fetchone()[0], old)
        self.assertEqual(self.pragma_version(), store.version())

    def test_a_copy_is_never_overwritten_by_one_with_the_same_name(self):
        base.backup_dir().mkdir(parents=True)
        with mock.patch.object(store, "stamp", return_value="20260101-000000"):
            first = store._reserve_backup("jobkit-before-upgrade-v8")
            first.write_bytes(b"first copy")
            second = store._reserve_backup("jobkit-before-upgrade-v8")
        self.assertNotEqual(first, second)
        self.assertEqual(first.read_bytes(), b"first copy")

    def test_a_command_that_read_a_stale_version_makes_no_copy_and_no_second_upgrade(self):
        store.create()
        store.close()
        real, calls = store.stored_version, []

        def stale_then_real(conn):
            calls.append(1)
            return 8 if len(calls) == 1 else real(conn)

        with contextlib.closing(sqlite3.connect(store.db_path(), isolation_level=None)) as conn:
            with mock.patch.object(store, "stored_version", side_effect=stale_then_real):
                self.assertEqual(store.migrate(conn), store.version())
        self.assertEqual(list(base.backup_dir().glob("jobkit-before-upgrade-*")), [])
        self.assertEqual(self.pragma_version(), store.version())

    def test_a_backup_folder_that_is_a_file_gives_a_clear_error_and_no_traceback(self):
        store.db_path().parent.mkdir(parents=True)
        old = store.MIGRATIONS.index(schema.step_drop_documents)
        with contextlib.closing(sqlite3.connect(store.db_path(), isolation_level=None)) as conn:
            store.migrate_to(conn, old)
        base.backup_dir().write_text("not a folder", encoding="utf-8")
        with self.assertRaisesRegex(ToolError, "Could not save a copy.*Nothing was changed"):
            store.connect()
        self.assertEqual(self.pragma_version(), old)

    def test_a_new_or_current_database_makes_no_upgrade_copy(self):
        store.create()
        store.close()
        store.connect()
        self.assertEqual(list(base.backup_dir().glob("jobkit-before-upgrade-*")), [])

    def test_an_empty_version_zero_file_makes_no_upgrade_copy(self):
        store.db_path().parent.mkdir(parents=True)
        sqlite3.connect(store.db_path()).close()
        store.connect()
        self.assertEqual(list(base.backup_dir().glob("jobkit-before-upgrade-*")), [])

    def dump_tables(self, conn):
        """{table: its rows} for every table (the research step must leave all of them as they were)."""
        names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        return {n: [tuple(r) for r in conn.execute(f"SELECT * FROM {n} ORDER BY 1, 2")] for n in names}

    def test_the_research_step_upgrades_an_older_database_without_touching_its_data(self):
        store.db_path().parent.mkdir(parents=True)
        old = store.MIGRATIONS.index(schema.step_target_research)
        with contextlib.closing(sqlite3.connect(store.db_path(), isolation_level=None)) as conn:
            store.migrate_to(conn, old)
            conn.execute("INSERT INTO meta(key, value) VALUES('kept', '1')")
            conn.execute("INSERT INTO session(id, title, mode, status, created, updated, body) "
                         "VALUES('s1', 't', 'stories', 'open', 'c', 'u', '{}')")
            conn.execute("INSERT INTO session_log(session_id, at, item, kind, answered, confidence_after, tutor, quiz, body) "
                         "VALUES('s1', '2026-01-01T10:00:00', 'a', 'story', 1, 1, 0, 0, '{}')")
            before = self.dump_tables(conn)
        store.connect()
        store.close()
        with contextlib.closing(sqlite3.connect(store.db_path())) as conn:
            self.assertEqual(self.pragma_version(), len(schema.STEPS))
            after = self.dump_tables(conn)
        for name, rows in before.items():
            if name == "session_log":
                self.assertEqual([r + (None, None) for r in rows], after[name])      # new columns read as none
            else:
                self.assertEqual(rows, after[name], name)
        self.assertEqual(after["target_company"], [])
        self.assertEqual(after["target_fact"], [])

    def test_the_cards_step_renames_stored_values_and_keeps_everything_else(self):
        store.db_path().parent.mkdir(parents=True)
        old = store.MIGRATIONS.index(schema.step_cards)
        with contextlib.closing(sqlite3.connect(store.db_path(), isolation_level=None)) as conn:
            store.migrate_to(conn, old)
            conn.executescript("""
INSERT INTO meta(key, value) VALUES('arch.catalog', '{"tracks": ["people"]}');
INSERT INTO setting(key, value) VALUES('tier1_services', '["Payroll"]');
INSERT INTO session(id, title, mode, status, created, updated, body)
  VALUES('s1', 't', 'architecture', 'open', 'c', 'u', '{}'), ('s2', 't', 'tutor', 'open', 'c', 'u', '{"topic": "architecture"}'),
        ('s3', 't', 'stories', 'open', 'c', 'u', '{}');
INSERT INTO card(id, position, body) VALUES('people-payroll', 0, '{"kind": "service", "name": "Payroll"}'),
  ('people-pair-a', 1, '{"kind": "pair", "name": "A"}');
INSERT INTO track(name, body) VALUES('people', '{"name": "people", "services": [{"area": "Pay", "name": "Payroll", "tier": 2}]}');
""")
        store.connect()
        store.close()
        with contextlib.closing(sqlite3.connect(store.db_path())) as conn:
            self.assertEqual(self.pragma_version(), store.version())
            rows = {t: conn.execute(q).fetchall() for t, q in (
                ("meta", "SELECT key FROM meta WHERE key LIKE '%catalog'"), ("setting", "SELECT key, value FROM setting"),
                ("session", "SELECT id, mode, body FROM session ORDER BY id"), ("card", "SELECT id, body FROM card ORDER BY id"),
                ("track", "SELECT body FROM track"))}
        self.assertEqual(rows["meta"], [("cards.catalog",)])
        self.assertEqual(rows["setting"], [("key_topics", '["Payroll"]')])
        self.assertEqual([(i, m, json.loads(b)) for i, m, b in rows["session"]],
                         [("s1", "knowledge", {}), ("s2", "tutor", {"topic": "knowledge"}), ("s3", "stories", {})])
        self.assertEqual([(i, json.loads(b)["kind"]) for i, b in rows["card"]], [("people-pair-a", "pair"), ("people-payroll", "topic")])
        self.assertEqual(json.loads(rows["track"][0][0]), {"name": "people", "topics": [{"area": "Pay", "name": "Payroll", "tier": 2}]})

    def test_role_questions_upgrade_keeps_existing_records(self):
        store.db_path().parent.mkdir(parents=True)
        old = store.MIGRATIONS.index(schema.step_role_questions)
        with contextlib.closing(sqlite3.connect(store.db_path(), isolation_level=None)) as conn:
            store.migrate_to(conn, old)
            conn.execute("INSERT INTO meta(key, value) VALUES('kept', '1')")
            before = self.dump_tables(conn)
        store.connect()
        store.close()
        with contextlib.closing(sqlite3.connect(store.db_path())) as conn:
            after = self.dump_tables(conn)
        self.assertEqual({name: after.pop(name) for name in ("role_research", "role_question", "question_progress")},
                         {"role_research": [], "role_question": [], "question_progress": []})
        self.assertEqual(after, before)

    def test_a_new_database_is_created_at_the_new_version_with_the_research_tables(self):
        store.create()
        store.close()
        with contextlib.closing(sqlite3.connect(store.db_path())) as conn:
            self.assertEqual(self.pragma_version(), len(schema.STEPS))
            names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            columns = {r[1] for r in conn.execute("PRAGMA table_info(session_log)")}
        self.assertLessEqual({"target_company", "target_fact"}, names)
        self.assertLessEqual({"style", "company"}, columns)

    def test_log_entries_stay_append_only_after_the_research_step(self):
        store.create()
        with store.transaction() as conn:
            conn.execute("INSERT INTO session(id, title, mode, status, created, updated, body) "
                         "VALUES('s1', 't', 'stories', 'open', 'c', 'u', '{}')")
            conn.execute("INSERT INTO session_log(session_id, at, item, kind, answered, confidence_after, tutor, quiz, body, "
                         "style, company) VALUES('s1', 'x', 'a', 'story', 1, 1, 0, 0, '{}', 'carl', 'Company X')")
        with self.assertRaisesRegex(ToolError, "append-only"):
            with store.transaction() as conn:
                conn.execute("UPDATE session_log SET style='star'")

    def test_facts_are_removed_with_their_company(self):
        store.create()
        with store.transaction() as conn:
            conn.execute("INSERT INTO target_company(key, name, outcome, researched, body) "
                         "VALUES('acme', 'Acme', 'found', '2026-01-01', '{}')")
            conn.execute("INSERT INTO target_fact(company_key, id, position, kind, link, label, pulled, vetted, body) "
                         "VALUES('acme', 'v1', 0, 'value', 'https://example.test', 'company-references', '2026-01-01', 1, '{}')")
            conn.execute("DELETE FROM target_company WHERE key='acme'")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM target_fact").fetchone()[0], 0)

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


class HomeTests(unittest.TestCase):
    def test_nothing_is_resolved_from_the_source_tree(self):
        with mock.patch.dict(os.environ, {"JOBKIT_HOME": "/elsewhere"}):
            self.assertEqual(store.db_path(), Path("/elsewhere/data/jobkit.db"))
            self.assertFalse(str(base.output_dir()).startswith(str(Path(base.__file__).parents[2])))


class RestoreCheckTests(HomeCase):
    def test_look_alike_database_is_refused_and_current_data_kept(self):
        fake = self.home / "fake.db"
        with contextlib.closing(sqlite3.connect(fake)) as conn:
            conn.execute("CREATE TABLE meta (unrelated TEXT)")
            conn.execute(f"PRAGMA user_version={store.version()}")
            conn.commit()
        before = (self.home / "data" / "jobkit.db").read_bytes()
        with self.assertRaises(ToolError):
            store.restore_from(fake)
        store.close()
        self.assertEqual(store.stored_version(sqlite3.connect(self.home / "data" / "jobkit.db")), store.version())
        self.assertEqual(len(list((self.home / "backup").glob("*before-restore*"))), 0)
        self.assertTrue(before)

    def test_real_backup_is_accepted(self):
        copy = store.backup_to(self.home / "backup" / "ok.db")
        store.check_backup_file(copy)
