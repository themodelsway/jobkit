"""Shared test helpers: repository paths, the command table, running a command in-process, and home-folder cases.

Helpers used by one test package only live in that package's `support.py`; a test module never imports another.
"""
import contextlib
import io
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from unittest import mock

from jk import admin, store
from jk.user import tables as user_tables
from tests import REAL_HOME

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = REPO_ROOT / "plugins" / "jobkit"

# Every command the plugin installs, and the module whose `main` it runs.
COMMANDS = {"jobkit": "jk.admin", "profile": "jk.user.profile", "process-resumes": "jk.resumes.process_resumes",
            "query-resume": "jk.resumes.query_resume", "build-resume": "jk.resumes.build_resume",
            "resume-lines": "jk.resumes.lines", "match-score": "jk.resumes.match_score",
            "cards": "jk.interview.cards", "lead": "jk.interview.lead", "prep": "jk.interview.prep",
            "sessions": "jk.interview.sessions", "readiness": "jk.interview.readiness", "target": "jk.interview.target",
            "questions": "jk.interview.questions"}
TOOLS = list(COMMANDS.values())


def call(main: Callable[[list[str]], int | None], *argv: object, stdin: str | None = None) -> tuple[int, str, str]:
    """Run a command's `main` in-process; (exit status, stdout, stderr).

    Arguments are turned into strings, an argparse error (SystemExit) becomes its exit status, and with `stdin`
    standard input reads that text.
    """
    out, err = io.StringIO(), io.StringIO()
    with contextlib.ExitStack() as stack:
        stack.enter_context(contextlib.redirect_stdout(out))
        stack.enter_context(contextlib.redirect_stderr(err))
        if stdin is not None:
            stack.enter_context(mock.patch.object(sys, "stdin", io.StringIO(stdin)))
        try:
            code = main([str(a) for a in argv])
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 2
    return code or 0, out.getvalue(), err.getvalue()


def jobkit(*argv: str) -> tuple[int, str, str]:
    """Run the `jobkit` command in-process; (status, stdout, stderr)."""
    return call(admin.main, *argv)


def put_meta(key: str) -> None:
    """Store one meta row (a small change to test transactions with)."""
    with store.transaction() as conn:
        conn.execute("INSERT INTO meta(key, value) VALUES(?, '1')", (key,))


def has_meta(key: str) -> bool:
    """True when the meta row exists."""
    with store.transaction(write=False) as conn:
        return conn.execute("SELECT 1 FROM meta WHERE key=?", (key,)).fetchone() is not None


class HomeCase(unittest.TestCase):
    """A test case with its own empty home folder and initialized database (`self.home`)."""

    def setUp(self) -> None:
        super().setUp()
        self.previous = os.environ.get("JOBKIT_HOME")
        self.home = Path(tempfile.mkdtemp(prefix="jobkit-case-"))
        os.environ["JOBKIT_HOME"] = str(self.home)
        store.close()
        store.create()
        self.addCleanup(self.restore)

    def restore(self) -> None:
        """Back to the run-wide test home."""
        store.close()
        if self.previous is None:
            os.environ.pop("JOBKIT_HOME", None)
        else:
            os.environ["JOBKIT_HOME"] = self.previous
        shutil.rmtree(self.home, ignore_errors=True)


class HomeClassCase(unittest.TestCase):
    """Like HomeCase, but one empty home folder for the whole class (for expensive shared set-up)."""

    home: Path

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls._previous = os.environ.get("JOBKIT_HOME")
        cls.home = Path(tempfile.mkdtemp(prefix="jobkit-class-"))
        os.environ["JOBKIT_HOME"] = str(cls.home)
        store.close()
        store.create()

    @classmethod
    def tearDownClass(cls) -> None:
        store.close()
        if cls._previous is None:
            os.environ.pop("JOBKIT_HOME", None)
        else:
            os.environ["JOBKIT_HOME"] = cls._previous
        shutil.rmtree(cls.home, ignore_errors=True)
        super().tearDownClass()


class DatabaseFileCase(unittest.TestCase):
    """A test case with its own empty home folder and no database yet (for creating and upgrading one)."""

    def setUp(self) -> None:
        super().setUp()
        self.home = Path(tempfile.mkdtemp(prefix="jobkit-schema-"))
        self.previous = os.environ["JOBKIT_HOME"]
        os.environ["JOBKIT_HOME"] = str(self.home)
        store.close()
        self.addCleanup(self.restore)

    def restore(self) -> None:
        """Back to the run-wide test home."""
        store.close()
        os.environ["JOBKIT_HOME"] = self.previous
        shutil.rmtree(self.home, ignore_errors=True)

    def pragma_version(self) -> int:
        """The database file's `user_version`."""
        with contextlib.closing(sqlite3.connect(store.db_path())) as conn:
            return conn.execute("PRAGMA user_version").fetchone()[0]


def open_real_database() -> sqlite3.Connection | None:
    """The user's real database, opened read-only (never written, never upgraded), or None when there is none."""
    path = Path(REAL_HOME) / "data" / "jobkit.db"
    if not path.is_file():
        return None
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        conn.execute("SELECT 1 FROM meta LIMIT 1")
    except sqlite3.Error:
        return None
    return conn


def real_resume_texts() -> dict[str, str]:
    """{record label: stored text} for the real resume data (empty without any)."""
    conn = open_real_database()
    if conn is None:
        return {}
    out: dict[str, str] = {}
    try:
        for table in ("company", "role", "bullet", "skill", "resume_item", "unparsed", "curation"):
            for number, row in enumerate(conn.execute(f"SELECT body FROM {table}")):
                out[f"{table} #{number}"] = row["body"]
    except sqlite3.Error:
        return {}
    finally:
        conn.close()
    return out


def add_resumes() -> None:
    """A profile and the marker that resume data exists, as after the first import."""
    user_tables.replace_settings({"resume_root": "resumes"})
    with store.transaction() as conn:
        store.meta_put(conn, "resume.skills", {"groups": {}})
