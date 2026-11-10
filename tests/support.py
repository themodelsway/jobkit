"""Shared test helpers."""
import json
import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from jobkit import store
from tests import REAL_HOME


class HomeCase(unittest.TestCase):
    """A test case with its own empty home folder and initialised database (`self.home`)."""

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


def drop_catalog() -> None:
    """Remove the architecture catalog (and with it every card's progress), as before `arch init`."""
    with store.transaction() as conn:
        conn.execute("DELETE FROM meta WHERE key='arch.catalog'")
        conn.execute("DELETE FROM card")


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


def real_personal_terms() -> set[str]:
    """Name, resume folder, employer names and header name from the real profile (empty without one)."""
    conn = open_real_database()
    if conn is None:
        return set()
    terms: set[str] = set()
    try:
        for row in conn.execute("SELECT key, value FROM setting WHERE key IN ('name', 'resume_root')"):
            terms.add(str(json.loads(row["value"])).strip())
        terms |= {row[0] for row in conn.execute("SELECT json_extract(body, '$.name') FROM employer") if row[0]}
    except sqlite3.Error:
        pass
    finally:
        conn.close()
    header = Path(REAL_HOME) / "profile" / "header.md"
    if header.is_file():
        lines = header.read_text(encoding="utf-8").splitlines()[:1]
        terms |= {line.lstrip("# ").strip() for line in lines}
    return {t for t in terms if len(t) >= 3 and t.lower() != "your name"}


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
