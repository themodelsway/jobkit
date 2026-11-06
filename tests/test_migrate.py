"""Tests for `jobkit migrate`, `export` and `backup` (src/jobkit/legacy.py, records.py, export.py)."""
import contextlib
import hashlib
import io
import json
import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from jobkit import admin, legacy, records, store
from jobkit.interview import tables
from tests.legacy_fixture import FILES, build_old_tree
from tests.support import HomeCase


def jobkit(*argv: str) -> tuple[int, str, str]:
    """Run the `jobkit` command in-process; (status, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = admin.main(list(argv))
    return code, out.getvalue(), err.getvalue()


def snapshot(root: Path) -> dict[str, tuple[str, int]]:
    """{relative path: (sha256, mtime_ns)} for every file under root."""
    return {p.relative_to(root).as_posix(): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
            for p in sorted(root.rglob("*")) if p.is_file()}


class MigrateCase(HomeCase):
    def setUp(self):
        super().setUp()
        self.old = build_old_tree(Path(tempfile.mkdtemp(prefix="jobkit-old-")))
        self.addCleanup(shutil.rmtree, self.old, True)

    def migrate(self, *extra: str) -> tuple[int, str, str]:
        return jobkit("migrate", "--from", str(self.old), *extra)


class ImportTests(MigrateCase):
    def test_every_kind_is_imported_and_verified(self):
        code, out, err = self.migrate()
        self.assertEqual(code, 0, err)
        self.assertNotIn("MISMATCH", out)
        for name in ("stories", "engagements", "arch-catalog", "sessions", "resume-companies", "curated", "settings"):
            self.assertRegex(out, rf"{name}\s+\d+ records\s+\S+\s+ok")

    def test_export_equals_what_was_read_for_every_kind(self):
        self.migrate()
        source = legacy.read_all(self.old)
        for entry in records.KINDS:
            with self.subTest(kind=entry.name):
                self.assertTrue(records.same(source[entry.name], entry.export()))
                self.assertGreater(records.count_of(entry, entry.export()), 0)

    def test_originals_are_untouched_and_backup_is_identical(self):
        before = snapshot(self.old)
        code, out, _ = self.migrate()
        self.assertEqual(code, 0)
        self.assertEqual(snapshot(self.old), before)
        backups = sorted((self.home / "backup").glob("json-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual({k: v[0] for k, v in snapshot(backups[0]).items()}, {k: v[0] for k, v in before.items()})
        self.assertIn(str(backups[0]), out)

    def test_a_record_with_only_empty_fields_is_still_data(self):
        self.migrate()
        self.assertIn("globex", records.kind("lead-scope").export()["companies"])
        self.assertTrue(records.blank({"companies": {}}))
        self.assertFalse(records.blank({"companies": {"globex": {"title": None}}}))
        self.assertTrue(records.blank(None))

    def test_scope_facts_that_are_all_empty_are_still_imported(self):
        source = {"companies": {"acme": {"title": None, "budget": None}, "globex": {"title": None, "budget": None}}}
        (self.old / "prep" / "leadership" / "profile.json").write_text(json.dumps(source), encoding="utf-8")
        self.assertEqual(self.migrate()[0], 0)
        self.assertEqual(records.kind("lead-scope").export(), source)
        self.assertEqual(records.counts()["lead-scope"], 2)

    def test_header_is_copied_as_a_file(self):
        self.migrate()
        self.assertIn("Jane Example", (self.home / "profile" / "header.md").read_text(encoding="utf-8"))

    def test_repeat_run_adds_nothing(self):
        self.migrate()
        counts = records.counts()
        code, out, _ = self.migrate()
        self.assertEqual(code, 0)
        self.assertIn("already imported", out)
        self.assertEqual(records.counts(), counts)
        self.assertEqual(len(list((self.home / "backup").glob("json-*"))), 1)

    def test_replace_saves_the_database_first_and_imports_again(self):
        self.migrate()
        code, out, _ = self.migrate("--replace")
        self.assertEqual(code, 0)
        self.assertIn("before replacing", out)
        self.assertEqual(len(list((self.home / "backup").glob("jobkit-before-replace-*.db"))), 1)
        self.assertEqual(records.counts()["stories"], 1)

    def test_start_over_closes_the_database_before_deleting_its_files(self):
        self.migrate()
        store.connect()                                   # this process now holds the database open
        seen = []
        real = Path.unlink

        def watch(path, *args, **kwargs):
            seen.append(store._STATE.conn is None)       # Windows refuses to delete a file that is open
            return real(path, *args, **kwargs)

        with mock.patch.object(Path, "unlink", watch):
            legacy.start_over()
        self.assertEqual(seen, [True, True, True])
        self.assertTrue(store.db_path().is_file())

    def test_nothing_to_import_is_an_error(self):
        empty = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, empty, True)
        code, _, err = jobkit("migrate", "--from", str(empty))
        self.assertEqual(code, 1)
        self.assertIn("No old data", err)


class SafetyTests(MigrateCase):
    def test_a_mismatch_undoes_the_import(self):
        real = tables.save_stories

        def lossy(doc):
            real({**doc, "stories": [{k: v for k, v in s.items() if k != "headline"} for s in doc["stories"]]})
        entry = records.kind("stories")
        with mock.patch.object(records, "KINDS", tuple(entry._replace(write=lossy) if k.name == "stories" else k
                                                       for k in records.KINDS)):
            code, out, err = self.migrate()
        self.assertEqual(code, 1)
        self.assertIn("MISMATCH", out)
        self.assertIn("stories", err)
        self.assertEqual(records.counts()["stories"], 0)
        self.assertIsNone(legacy.import_record())

    def test_incomplete_backup_stops_before_importing(self):
        with mock.patch.object(shutil, "copy2", side_effect=lambda src, dst: Path(dst).write_text("x", encoding="utf-8")):
            code, _, err = self.migrate()
        self.assertEqual(code, 1)
        self.assertIn("incomplete", err)
        self.assertEqual(records.counts()["stories"], 0)

    def test_unreadable_json_names_the_file_and_changes_nothing(self):
        (self.old / "prep" / "stories.json").write_text("{oops", encoding="utf-8")
        code, _, err = self.migrate()
        self.assertEqual(code, 1)
        self.assertIn("stories.json", err)
        self.assertEqual(sum(records.counts().values()), 0)
        self.assertEqual(list((self.home / "backup").glob("json-*")), [])

    def test_progress_for_a_missing_card_is_reported_not_dropped(self):
        path = self.old / "prep" / "arch" / "progress.json"
        path.write_text(json.dumps({"cards": {"vpc": FILES["prep/arch/progress.json"]["cards"]["vpc"],
                                              "ghost": {"confidence": 1}}}), encoding="utf-8")
        code, _, err = self.migrate()
        self.assertEqual(code, 1)
        self.assertIn("ghost", err)
        self.assertEqual(records.counts()["arch-progress"], 0)

    def test_needs_an_initialised_home(self):
        shutil.rmtree(self.home / "data")
        store.close()
        code, _, err = self.migrate()
        self.assertEqual(code, 1)
        self.assertIn("jobkit init", err)


class DryRunTests(unittest.TestCase):
    def test_dry_run_writes_nothing_not_even_a_database(self):
        home = Path(tempfile.mkdtemp(prefix="jobkit-dry-"))
        old = build_old_tree(Path(tempfile.mkdtemp(prefix="jobkit-old-")))
        self.addCleanup(shutil.rmtree, home, True)
        self.addCleanup(shutil.rmtree, old, True)
        previous = os.environ["JOBKIT_HOME"]
        os.environ["JOBKIT_HOME"] = str(home)
        self.addCleanup(os.environ.__setitem__, "JOBKIT_HOME", previous)
        store.close()
        shutil.rmtree(home)
        code, out, _ = jobkit("migrate", "--from", str(old), "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("stories", out)
        self.assertFalse(home.exists())


class RemoveOldTests(MigrateCase):
    def test_remove_needs_an_import_first(self):
        code, _, err = self.migrate("--remove-old")
        self.assertEqual(code, 1)
        self.assertIn("Nothing has been imported", err)

    def test_removes_json_after_the_check_and_keeps_the_backup(self):
        self.migrate()
        code, out, _ = self.migrate("--remove-old")
        self.assertEqual(code, 0)
        self.assertIn("backup", out)
        self.assertEqual(list(self.old.rglob("*.json")), [])
        self.assertTrue((self.old / "profile" / "header.md").exists())
        self.assertTrue(list((self.home / "backup").glob("json-*/prep/stories.json")))

    def test_a_failed_check_deletes_nothing(self):
        self.migrate()
        with store.transaction() as conn:
            conn.execute("DELETE FROM story")
        before = snapshot(self.old)
        code, _, err = self.migrate("--remove-old")
        self.assertEqual(code, 1)
        self.assertIn("does not match", err)
        self.assertEqual(snapshot(self.old), before)


class ExportTests(MigrateCase):
    def setUp(self):
        super().setUp()
        self.migrate()

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


class BackupTests(MigrateCase):
    def setUp(self):
        super().setUp()
        self.migrate()

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

    def test_restore_refuses_a_newer_version(self):
        target = self.home / "future.db"
        jobkit("backup", "-o", str(target))
        with contextlib.closing(sqlite3.connect(target)) as conn:
            conn.execute(f"PRAGMA user_version={store.version() + 3}")
        code, _, err = jobkit("backup", "--restore", str(target))
        self.assertEqual(code, 1)
        self.assertIn("only knows version", err)


class StatusTests(MigrateCase):
    def test_status_shows_counts_per_kind(self):
        self.migrate()
        out = jobkit("status")[1]
        self.assertIn("stories: 1", out)
        self.assertIn("sessions: 1", out)


if __name__ == "__main__":
    unittest.main()
