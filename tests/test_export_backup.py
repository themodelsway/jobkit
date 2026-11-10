"""Tests for `jobkit export`, `backup` and `status` (src/jobkit/admin.py, records.py, export.py)."""
import contextlib
import io
import json
import sqlite3
import unittest
from pathlib import Path

from jobkit import admin, records, store
from jobkit.common import ToolError
from tests.seed_data import seed
from tests.support import HomeCase


def jobkit(*argv: str) -> tuple[int, str, str]:
    """Run the `jobkit` command in-process; (status, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = admin.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class SeededCase(HomeCase):
    """A home folder whose database holds one sample of every kind of data."""

    def setUp(self):
        super().setUp()
        seed()


class ExportTests(SeededCase):
    def test_json_export_holds_every_record_and_counts_match_status(self):
        code, out, _ = jobkit("export")
        self.assertEqual(code, 0)
        data = json.loads(out)
        status = records.counts()
        for entry in records.KINDS:
            self.assertEqual(records.count_of(entry, data[entry.name]), status[entry.name], entry.name)
        self.assertEqual(data["stories"]["stories"][0]["headline"], "h")
        self.assertEqual(len(data["sessions"]["s1"]["log"]), 1)

    def test_only_one_kind(self):
        out = jobkit("export", "--only", "stories")[1]
        self.assertEqual(list(json.loads(out)), ["schema_version", "stories"])
        self.assertEqual(jobkit("export", "--only", "nope")[0], 1)

    def test_markdown(self):
        out = jobkit("export", "--format", "md", "--only", "stories")[1]
        self.assertTrue(out.startswith("# stories"))
        self.assertIn("**headline**: h", out)
        self.assertEqual(jobkit("export", "--format", "pdf")[0], 1)

    def test_folder_export_writes_one_file_per_kind(self):
        folder = self.home / "out"
        code, out, _ = jobkit("export", "-o", str(folder))
        self.assertEqual(code, 0)
        self.assertEqual(sorted(p.stem for p in folder.glob("*.json")), sorted(k.name for k in records.KINDS))
        self.assertIn("stories.json", out)

    def test_export_changes_nothing(self):
        files = [store.db_path(), store.db_path().with_name("jobkit.db-wal")]
        before = [(f.stat().st_mtime_ns, f.stat().st_size) for f in files if f.exists()]
        jobkit("export")
        jobkit("status")
        self.assertEqual([(f.stat().st_mtime_ns, f.stat().st_size) for f in files if f.exists()], before)
        self.assertEqual([p.name for p in self.home.iterdir() if p.is_file()], [])


class BackupTests(SeededCase):
    def test_backup_opens_cleanly_and_holds_the_data(self):
        code, out, _ = jobkit("backup")
        self.assertEqual(code, 0)
        file = next((self.home / "backup").glob("jobkit-*.db"))
        self.assertIn(str(file), out)
        with contextlib.closing(sqlite3.connect(file)) as conn:
            self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM story").fetchone()[0], 1)

    def test_backup_to_a_named_file(self):
        target = self.home / "mine.db"
        self.assertEqual(jobkit("backup", "-o", str(target))[0], 0)
        self.assertTrue(target.exists())

    def test_restore_replaces_the_data_and_keeps_the_previous_database(self):
        target = self.home / "mine.db"
        jobkit("backup", "-o", str(target))
        with store.transaction() as conn:
            conn.execute("DELETE FROM story")
        self.assertEqual(records.counts()["stories"], 0)
        code, out, _ = jobkit("backup", "--restore", str(target))
        self.assertEqual(code, 0)
        self.assertEqual(records.counts()["stories"], 1)
        self.assertEqual(len(list((self.home / "backup").glob("jobkit-before-restore-*.db"))), 1)
        self.assertIn("previous database", out)

    def test_restore_refuses_other_files_and_leaves_the_database_alone(self):
        junk = self.home / "junk.db"
        junk.write_text("not a database", encoding="utf-8")
        code, _, err = jobkit("backup", "--restore", str(junk))
        self.assertEqual(code, 1)
        self.assertIn("not a jobkit database", err)
        self.assertEqual(records.counts()["stories"], 1)
        other = self.home / "other.db"
        with contextlib.closing(sqlite3.connect(other)) as conn:
            conn.execute("CREATE TABLE x (a)")
        self.assertEqual(jobkit("backup", "--restore", str(other))[0], 1)
        self.assertEqual(jobkit("backup", "--restore", str(self.home / "missing.db"))[0], 1)

    def damaged_backup(self, sql: str) -> Path:
        """A backup of the seeded database with `sql` run on it (foreign keys off, as in any plain connection)."""
        target = self.home / "damaged.db"
        jobkit("backup", "-o", str(target))
        with contextlib.closing(sqlite3.connect(target, isolation_level=None)) as conn:
            conn.executescript(sql)
        return target

    def refused(self, target: Path) -> str:
        """Restore `target`, expect a refusal that leaves the database as it was; return the message."""
        code, _, err = jobkit("backup", "--restore", str(target))
        self.assertEqual(code, 1)
        self.assertEqual(records.counts()["stories"], 1)
        self.assertEqual(list((self.home / "backup").glob("jobkit-before-restore-*.db")), [])
        return err

    def test_restore_refuses_an_unreadable_record_and_names_only_the_table(self):
        err = self.refused(self.damaged_backup("UPDATE story SET body='{secret-token'"))
        self.assertIn("story", err)
        self.assertNotIn("secret-token", err)

    def test_restore_refuses_a_broken_reference(self):
        err = self.refused(self.damaged_backup("UPDATE story SET engagement_id='ghost'"))
        self.assertIn("story", err)

    def test_restore_refuses_a_backup_without_the_answer_protection(self):
        err = self.refused(self.damaged_backup("DROP TRIGGER session_log_no_update"))
        self.assertIn("trigger", err)

    def test_restore_refuses_a_newer_version(self):
        target = self.home / "future.db"
        jobkit("backup", "-o", str(target))
        with contextlib.closing(sqlite3.connect(target)) as conn:
            conn.execute(f"PRAGMA user_version={store.version() + 3}")
        code, _, err = jobkit("backup", "--restore", str(target))
        self.assertEqual(code, 1)
        self.assertIn("only knows version", err)


class StatusTests(SeededCase):
    def test_status_shows_counts_per_kind(self):
        out = jobkit("status")[1]
        self.assertIn("stories: 1", out)
        self.assertIn("sessions: 1", out)


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


if __name__ == "__main__":
    unittest.main()
