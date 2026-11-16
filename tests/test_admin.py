"""Tests for the `jobkit` command: init, status, export and backup (plugins/jobkit/src/jk/admin.py, records.py, export.py)."""
import contextlib
import io
import json
import os
import sqlite3
import threading
from datetime import date
from pathlib import Path
from unittest import mock

from jk import records, store
from jk.interview import prep, target_tables, targets
from tests.seed_data import seed
from tests.support import DatabaseFileCase, HomeCase, has_meta, jobkit, put_meta


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


class ResearchExportTests(HomeCase):
    """The researched companies are their own kind (all data fictional)."""

    def test_fresh_database_has_the_kind_empty(self):
        data = json.loads(jobkit("export")[1])
        self.assertEqual(data["research"], {"companies": []})
        self.assertIn("research: 0", jobkit("status")[1])

    def test_researched_company_and_none_found_are_exported_with_every_fact_field(self):
        today = date.today().isoformat()
        facts = [{"id": f"v{n}", "kind": "value", "name": f"Value {n}", "wording": "w", "quote": "q",
                  "link": f"https://example.com/{n}", "label": "company-references", "pulled": today, "vetted": True}
                 for n in range(3)]
        save = {"name": "Company X", "facts": facts, "suggested_style": {"style": "soar", "basis": "inferred",
                                                                          "facts": ["v0"]}}
        target_tables.save_company(targets.merge_save(None, save, date.today()))
        target_tables.save_company({"key": "small co", "name": "Small Co", "outcome": "none found",
                                    "researched": today, "style": None, "style_basis": None, "style_facts": [],
                                    "facts": []})
        companies = {c["name"]: c for c in json.loads(jobkit("export")[1])["research"]["companies"]}
        first = companies["Company X"]["facts"][0]
        self.assertEqual({k: first[k] for k in ("link", "quote", "label", "pulled", "vetted")},
                         {"link": "https://example.com/0", "quote": "q", "label": "company-references",
                          "pulled": today, "vetted": True})
        self.assertEqual((companies["Company X"]["style"], companies["Company X"]["style_basis"]), ("soar", "inferred"))
        self.assertEqual((companies["Small Co"]["outcome"], companies["Small Co"]["researched"]), ("none found", today))
        self.assertIn("research: 2", jobkit("status")[1])


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

    def good_backup(self) -> Path:
        target = self.home / "good.db"
        self.assertEqual(jobkit("backup", "-o", str(target))[0], 0)
        store.close()
        return target

    def assert_restored(self, saved_expected: bool) -> None:
        code, out, err = jobkit("backup", "--restore", str(self.home / "good.db"))
        self.assertEqual(code, 0, err)
        self.assertEqual(records.counts()["stories"], 1)
        saved = list((self.home / "backup").glob("jobkit-before-restore-*.db"))
        self.assertEqual(len(saved), int(saved_expected))
        self.assertIn("previous database was saved" if saved_expected else "no database before", out)

    def test_restore_works_when_there_is_no_database(self):
        self.good_backup()
        store.db_path().unlink()
        self.assert_restored(saved_expected=False)

    def test_restore_works_over_a_damaged_database_and_keeps_its_bytes(self):
        self.good_backup()
        for extra in store._database_files(store.db_path())[1:]:
            extra.unlink()
        store.db_path().write_bytes(b"damaged" * 100)
        self.assert_restored(saved_expected=True)
        saved = next((self.home / "backup").glob("jobkit-before-restore-*.db"))
        self.assertEqual(saved.read_bytes(), b"damaged" * 100)

    def test_restore_works_over_a_database_from_a_newer_version(self):
        self.good_backup()
        with contextlib.closing(sqlite3.connect(store.db_path())) as conn:
            conn.execute(f"PRAGMA user_version={store.version() + 3}")
        self.assert_restored(saved_expected=True)
        with store.transaction(write=False) as conn:
            self.assertEqual(store.stored_version(conn), store.version())

    def test_restore_works_over_an_old_database_with_missing_tables(self):
        self.good_backup()
        for file in store._database_files(store.db_path()):
            file.unlink()
        with contextlib.closing(sqlite3.connect(store.db_path())) as conn:
            conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
            conn.execute("PRAGMA user_version=1")
            conn.commit()
        self.assert_restored(saved_expected=True)
        saved = next((self.home / "backup").glob("jobkit-before-restore-*.db"))
        with contextlib.closing(sqlite3.connect(saved)) as conn:
            self.assertEqual(store.stored_version(conn), 1)

    def backup_with_log(self, sql: str) -> tuple[Path, sqlite3.Connection]:
        """A backup whose last change (`sql`) is committed only in its write-ahead log, kept there by an open reader."""
        target = self.good_backup()
        reader = sqlite3.connect(target, isolation_level=None)
        self.addCleanup(reader.close)
        reader.execute("PRAGMA journal_mode=WAL")
        reader.execute("SELECT COUNT(*) FROM story").fetchone()
        with contextlib.closing(sqlite3.connect(target, isolation_level=None)) as writer:
            writer.execute(sql)
        self.assertTrue(Path(f"{target}-wal").stat().st_size)
        return target, reader

    def test_restore_checks_the_changes_in_the_backups_log(self):
        target, _ = self.backup_with_log(f"PRAGMA user_version={store.version() + 3}")
        code, _, err = jobkit("backup", "--restore", str(target))
        self.assertEqual(code, 1)
        self.assertIn("only knows version", err)
        self.assertEqual(records.counts()["stories"], 1)

    def test_restore_writes_what_was_checked_and_leaves_the_backup_alone(self):
        target, _ = self.backup_with_log("DELETE FROM story")
        before = target.read_bytes(), Path(f"{target}-wal").read_bytes()
        code, _, err = jobkit("backup", "--restore", str(target))
        self.assertEqual(code, 0, err)
        self.assertEqual(records.counts()["stories"], 0)
        self.assertEqual((target.read_bytes(), Path(f"{target}-wal").read_bytes()), before)


class RestoreVersionAndLockTests(SeededCase):
    def old_read_only_backup(self) -> Path:
        """An empty jobkit database one schema version older than this program, made read-only."""
        old = self.home / "old.db"
        conn = store._open(old)
        store.migrate_to(conn, store.version() - 1)
        conn.close()
        old.chmod(0o444)
        self.addCleanup(old.chmod, 0o644)
        return old

    def test_restore_accepts_a_read_only_backup_that_needs_an_upgrade(self):
        old = self.old_read_only_backup()
        before = old.read_bytes(), old.stat().st_mode
        code, _, err = jobkit("backup", "--restore", str(old))
        self.assertEqual(code, 0, err)
        self.assertEqual((old.read_bytes(), old.stat().st_mode), before)

    def test_restore_writes_an_older_backup_at_its_own_version(self):
        old = self.old_read_only_backup()
        self.assertEqual(jobkit("backup", "--restore", str(old))[0], 0)
        with contextlib.closing(sqlite3.connect(f"file:{store.db_path()}?mode=ro", uri=True)) as conn:
            self.assertEqual(store.stored_version(conn), store.version() - 1)    # the older release can open it
        self.assertEqual(records.counts()["stories"], 0)                        # the next command upgrades it
        with store.transaction(write=False) as conn:
            self.assertEqual(store.stored_version(conn), store.version())

    def test_restore_gives_up_on_a_database_another_command_holds(self):
        target = self.home / "good.db"
        self.assertEqual(jobkit("backup", "-o", str(target))[0], 0)
        with store.transaction() as conn:
            conn.execute("DELETE FROM story")
        store.close()
        with contextlib.closing(sqlite3.connect(store.db_path(), isolation_level=None)) as conn:
            conn.execute("PRAGMA journal_mode=DELETE")                  # where a held lock blocks readers too
        holder = sqlite3.connect(store.db_path(), isolation_level=None, check_same_thread=False)
        holder.execute("BEGIN EXCLUSIVE")
        timer = threading.Timer(10, holder.rollback)   # a restore that waits without limit then succeeds and fails here
        timer.start()
        try:
            with mock.patch.object(store, "BUSY_TIMEOUT_MS", 100):
                code, _, err = jobkit("backup", "--restore", str(target))
        finally:
            timer.cancel()
            holder.rollback()
            holder.close()
        self.assertEqual(code, 1)
        self.assertIn("busy", err)
        self.assertEqual(records.counts()["stories"], 0)
        self.assertEqual(list((self.home / "backup").glob("jobkit-before-restore-*")), [])


class StatusTests(SeededCase):
    def test_status_shows_counts_per_kind(self):
        out = jobkit("status")[1]
        self.assertIn("stories: 1", out)
        self.assertIn("sessions: 1", out)


class AdminTests(DatabaseFileCase):
    def test_init_creates_the_layout(self):
        code, out, _ = jobkit("init")
        self.assertEqual(code, 0)
        self.assertIn("Created", out)
        for folder in ("data", "backup", "output", "profile"):
            self.assertTrue((self.home / folder).is_dir(), folder)
        self.assertTrue(store.db_path().exists())

    def test_repeat_init_changes_nothing(self):
        jobkit("init")
        put_meta("keep")
        code, out, _ = jobkit("init")
        self.assertEqual(code, 0)
        self.assertIn("Already set up", out)
        self.assertTrue(has_meta("keep"))

    def test_commands_need_init_and_never_create_the_database(self):
        code, _, err = jobkit("status")
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
        jobkit("init")
        code, out, _ = jobkit("status")
        self.assertEqual(code, 0)
        self.assertIn(str(store.db_path()), out)
        self.assertIn(f"schema version: {store.version()}", out)
        self.assertIn("stories: 0", out)

    def test_status_does_not_change_the_database(self):
        jobkit("init")
        before = store.db_path().read_bytes()
        jobkit("status")
        store.close()
        self.assertEqual(store.db_path().read_bytes(), before)


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
