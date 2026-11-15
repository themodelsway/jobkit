"""How far setup has got, as one word, for `jobkit status --setup` and `--summary`.

The skills act on the word: create the database, import the resumes, ask what the user is preparing for,
or carry on. When the check itself fails, the word says why, decided from the error's type and SQLite's
numbered result code, never from message text: `blocked` (saving is not allowed), `busy` (another command
holds the database), `too-new` (written by a newer version) or `failed` (anything else). The check never
creates the database; like every command, opening an existing one from an older version upgrades it first.
"""
from __future__ import annotations

import os
import sqlite3
from typing import Final

from jk import store
from jk.base import hide_home
from jk.resumes import tables as resume_tables
from jk.user import profile
from jk.user import tables as user_tables

STAGES: Final[tuple[str, ...]] = ("no-database", "no-resumes", "no-target", "ready")
FAILURES: Final[tuple[str, ...]] = ("blocked", "busy", "too-new", "failed")
_BUSY: Final[frozenset[int]] = frozenset({sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED})
_BLOCKED: Final[frozenset[int]] = frozenset({sqlite3.SQLITE_READONLY, sqlite3.SQLITE_CANTOPEN, sqlite3.SQLITE_PERM})


def _has_resumes() -> bool:
    """True once a profile exists and a resume import has stored its data."""
    return user_tables.has_settings() and resume_tables.has_resume_data()


def _has_preparation() -> bool:
    """True once "what are you preparing for" has finished: its last step saves `preparing_for`.

    Stories, leadership questions or drill cards alone do not count, since that step may have stopped part way.
    """
    return profile.preparing_for() is not None


def _stage() -> str:
    """The first setup stage that is not done yet, or `ready`.

    Raises:
        PermissionError: the database file or its folder cannot be written.
    """
    path = store.db_path()
    if not path.exists():
        return "no-database"
    if not (os.access(path, os.W_OK) and os.access(path.parent, os.W_OK)):
        raise PermissionError(f"cannot write to {path}")
    if not _has_resumes():
        return "no-resumes"
    return "ready" if _has_preparation() else "no-target"


def setup_stage() -> str:
    """The setup stage, one of STAGES; errors propagate (see `report` for the classified form)."""
    return _stage()


def _sqlite_cause(exc: BaseException) -> sqlite3.Error | None:
    """The SQLite error that `exc` is or was raised from, if any."""
    seen: BaseException | None = exc
    while seen is not None:
        if isinstance(seen, sqlite3.Error):
            return seen
        seen = seen.__cause__ or seen.__context__
    return None


def classify(exc: BaseException) -> str:
    """One of FAILURES for an error, by its type and SQLite's primary result code; unknown errors are `failed`."""
    if isinstance(exc, store.NewerDatabaseError):
        return "too-new"
    if isinstance(exc, PermissionError):
        return "blocked"
    code = getattr(_sqlite_cause(exc), "sqlite_errorcode", None)
    if isinstance(code, int):
        primary = code & 0xFF                     # extended codes keep the primary code in the low byte
        if primary in _BUSY:
            return "busy"
        if primary in _BLOCKED:
            return "blocked"
    return "failed"


def error_line(word: str, exc: BaseException) -> str:
    """One line for standard error: the word, the error's type (and SQLite name) and message, home shown as ~."""
    shown: BaseException = _sqlite_cause(exc) or exc
    name = getattr(shown, "sqlite_errorname", None)
    kind = type(shown).__name__ + (f" ({name})" if isinstance(name, str) else "")
    return f"{word}: {kind}: {hide_home(str(shown))}"


def report() -> tuple[str, str | None]:
    """(word, error line or None): the stage when it can be told, otherwise the classified failure."""
    try:
        return _stage(), None
    except Exception as exc:  # pylint: disable=broad-exception-caught  # every failure must become a word
        word = classify(exc)
        return word, error_line(word, exc)
