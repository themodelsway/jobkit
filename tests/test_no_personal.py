"""Committed (or committable) files must contain nothing personal.

Checks every file git would commit (tracked + untracked, minus .gitignore) for:
  * generic leaks: home-directory paths, email addresses, phone numbers
  * anything in your personal terms (`profile terms check --all`, from ~/.jobkit or $JOBKIT_HOME)

Without a profile only the generic checks run, and the profile check is reported as skipped.
"""
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from jk import store
from tests import REAL_HOME

ROOT = Path(__file__).resolve().parents[1]

HOME_PATH = re.compile("/" + "Users/|/" + "home/[a-z]|C:" + r"\\Users", re.I)
EMAIL = re.compile(r"\b[\w.+-]+@(?!example\.)[\w-]+\.(?:com|net|org|io|dev)\b")
PHONE = re.compile(r"(?<!\d)(?:\+?\d{1,2}[ -])?\(?\d{3}\)?[ -]\d{3}[ -]\d{4}(?!\d)")
SKIP_SUFFIX = {".png", ".jpg", ".pdf", ".pyc"}


def committable():
    """Every file git would commit; fails rather than scanning nothing when git cannot list them."""
    out = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    files = [ROOT / f for f in out.splitlines() if (ROOT / f).is_file() and (ROOT / f).suffix not in SKIP_SUFFIX
             and f != "tests/test_no_personal.py"]
    if not files:
        raise AssertionError("git listed no committable files, so nothing would be checked")
    return files


class TestNoPersonalData(unittest.TestCase):
    def test_generic_leaks(self):
        bad = []
        for f in committable():
            for n, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if HOME_PATH.search(line) or EMAIL.search(line) or PHONE.search(line):
                    bad.append(f"{f.relative_to(ROOT)}:{n}")
        self.assertEqual(bad, [], "home path, email or phone number in committable files")

    def test_profile_terms(self):
        if not (Path(REAL_HOME) / "data" / "jobkit.db").is_file():
            self.skipTest("no profile in the real home: only the generic checks ran")
        done = terms_check_on_copy(Path(REAL_HOME))
        self.assertEqual(done.returncode, 0, "values from your profile found in committable files:\n" + done.stdout)

    def test_the_real_database_is_never_upgraded_or_changed(self):
        with tempfile.TemporaryDirectory(prefix="jobkit-old-home-") as folder:
            old = Path(folder)
            (old / "data").mkdir()
            conn = store._open(old / "data" / "jobkit.db")        # pylint: disable=protected-access
            store.migrate_to(conn, store.version() - 1)
            conn.close()
            before = (old / "data" / "jobkit.db").read_bytes()
            done = terms_check_on_copy(old)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertEqual(stored_version(old), store.version() - 1)      # still readable by the previous release
            self.assertEqual((old / "data" / "jobkit.db").read_bytes(), before)


def stored_version(home: Path) -> int:
    """The schema version of the database under `home`, read without changing it."""
    conn = sqlite3.connect(f"file:{home / 'data' / 'jobkit.db'}?mode=ro", uri=True)
    try:
        return int(conn.execute("PRAGMA user_version").fetchone()[0])
    finally:
        conn.close()


def terms_check_on_copy(home: Path) -> subprocess.CompletedProcess[str]:
    """Run `profile terms check --all` against a consistent copy of the database under `home`, so the original is
    never migrated or written (the command upgrades the database it opens)."""
    with tempfile.TemporaryDirectory(prefix="jobkit-terms-copy-") as folder:
        (Path(folder) / "data").mkdir()
        source = sqlite3.connect(f"file:{home / 'data' / 'jobkit.db'}?mode=ro", uri=True)
        target = sqlite3.connect(Path(folder) / "data" / "jobkit.db")
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        env = {**os.environ, "JOBKIT_HOME": folder}
        return subprocess.run([sys.executable, "-m", "jk.user.profile", "terms", "check", "--all"], cwd=ROOT, env=env,
                              capture_output=True, text=True, check=False)


if __name__ == "__main__":
    unittest.main()
