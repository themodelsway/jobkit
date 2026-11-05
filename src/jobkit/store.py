"""The one local database that holds all user data (standard library `sqlite3` only).

  data/jobkit.db under the home folder (`JOBKIT_HOME`, default `~/.jobkit`)

Every command runs in one transaction: its changes are stored together or not at all. Several commands may
run at the same time (WAL mode and a busy timeout). Schema upgrades are numbered steps in `MIGRATIONS`.
Import it as `from jobkit import store`; it does no work at import time.
"""
from __future__ import annotations

import contextlib
import sqlite3
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Final

from jobkit import base, schema
from jobkit.base import ToolError

BUSY_TIMEOUT_MS: Final[int] = 5000
HINT: Final[str] = "Run `jobkit init` first."

Migration = Callable[[sqlite3.Connection], None]


MIGRATIONS: list[Migration] = list(schema.STEPS)


def version() -> int:
    """The schema version this program writes."""
    return len(MIGRATIONS)


def db_path() -> Path:
    """Location of the database file."""
    return base.data_dir() / "jobkit.db"


class _State:
    """Per-process connection state (one connection per database file, one open transaction at a time)."""

    conn: sqlite3.Connection | None = None
    path: Path | None = None
    depth: int = 0


_STATE = _State()


def close() -> None:
    """Close the process's connection (tests and `init` use this; commands end with the process)."""
    if _STATE.conn is not None:
        _STATE.conn.close()
    _STATE.conn, _STATE.path, _STATE.depth = None, None, 0


def _open(path: Path) -> sqlite3.Connection:
    """A new connection with the durability and integrity settings every command needs."""
    conn = sqlite3.connect(path, isolation_level=None, timeout=BUSY_TIMEOUT_MS / 1000)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=FULL")
    return conn


def stored_version(conn: sqlite3.Connection) -> int:
    """The schema version recorded in the database."""
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def migrate(conn: sqlite3.Connection) -> int:
    """Apply the missing upgrade steps in order, each inside one transaction; return the new version.

    Raises:
        ToolError: the database was written by a newer version of the program.
    """
    current = stored_version(conn)
    if current > version():
        raise ToolError(f"The database is version {current} but this program only knows version {version()}. "
                        "Update jobkit; nothing was changed.")
    return migrate_to(conn, version())


def migrate_to(conn: sqlite3.Connection, target: int) -> int:
    """Apply upgrade steps until the database is at `target` (each step in its own transaction)."""
    for number in range(stored_version(conn), target):
        conn.execute("BEGIN IMMEDIATE")
        try:
            MIGRATIONS[number](conn)
            conn.execute(f"PRAGMA user_version={number + 1}")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")
    return target


def create() -> bool:
    """Create the home folders and the database at the current version; False when it already existed."""
    path = db_path()
    existed = path.exists()
    for folder in (path.parent, base.backup_dir(), base.output_dir(), base.header_file().parent):
        folder.mkdir(parents=True, exist_ok=True)
    close()
    conn = _open(path)
    try:
        migrate(conn)
    finally:
        conn.close()
    return not existed


def connect() -> sqlite3.Connection:
    """The process's connection, upgraded to the current schema.

    Raises:
        ToolError: the database does not exist yet (it is never created here) or is from a newer version.
    """
    path = db_path()
    if _STATE.conn is not None and _STATE.path == path:
        return _STATE.conn
    close()
    if not path.exists():
        raise ToolError(f"No database at {path}. {HINT}")
    conn = _open(path)
    try:
        migrate(conn)
    except BaseException:
        conn.close()
        raise
    _STATE.conn, _STATE.path = conn, path
    return conn


@contextlib.contextmanager
def transaction(*, write: bool = True) -> Iterator[sqlite3.Connection]:
    """One transaction: commit when the block ends, roll back when it raises. Nested uses join the outer one.

    Raises:
        ToolError: the database is busy for longer than the timeout, or does not exist.
    """
    conn = connect()
    if _STATE.depth:
        _STATE.depth += 1
        try:
            yield conn
        finally:
            _STATE.depth -= 1
        return
    try:
        conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
    except sqlite3.OperationalError as exc:
        raise ToolError(f"The database is busy ({exc}). Try again in a moment.") from exc
    _STATE.depth = 1
    try:
        yield conn
        conn.execute("COMMIT")
    except sqlite3.IntegrityError as exc:
        _rollback(conn)
        raise ToolError(f"Refused, nothing was changed: {exc}.") from exc
    except sqlite3.OperationalError as exc:
        _rollback(conn)
        raise ToolError(f"The database is busy or unavailable ({exc}). Try again in a moment.") from exc
    except BaseException:
        _rollback(conn)
        raise
    finally:
        _STATE.depth = 0


def _rollback(conn: sqlite3.Connection) -> None:
    """Roll back the open transaction if there still is one."""
    if conn.in_transaction:
        conn.execute("ROLLBACK")


# ---------------------------------------------------------------- backup and restore

def stamp() -> str:
    """A timestamp for file names: YYYYmmdd-HHMMSS."""
    return base.now().replace("-", "").replace(":", "").replace("T", "-")


def default_backup_path(label: str = "jobkit") -> Path:
    """`backup/<label>-<timestamp>.db` under the home folder."""
    return base.backup_dir() / f"{label}-{stamp()}.db"


def backup_to(path: Path) -> Path:
    """Write a consistent copy of the database to `path` (safe while other commands run)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    source = connect()
    target = sqlite3.connect(path)
    try:
        source.backup(target)
    finally:
        target.close()
    return path


def check_backup_file(file: Path) -> None:
    """Fail unless `file` is a jobkit database this program can read.

    Raises:
        ToolError: the file is missing, is not a database, is not a jobkit database, or is from a newer version.
    """
    if not file.is_file():
        raise ToolError(f"{file} does not exist.")
    try:
        with contextlib.closing(sqlite3.connect(f"file:{file}?mode=ro", uri=True)) as conn:
            found = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='meta'").fetchone()
            found_version = stored_version(conn)
    except sqlite3.DatabaseError as exc:
        raise ToolError(f"{file} is not a jobkit database ({exc}).") from exc
    if not found or found_version < 1:
        raise ToolError(f"{file} is not a jobkit database.")
    if found_version > version():
        raise ToolError(f"{file} is version {found_version}; this program only knows version {version()}.")


def restore_from(file: Path) -> Path:
    """Replace the database with a backup, after saving the current one; returns that saved copy.

    Raises:
        ToolError: the file is not a usable jobkit database (the current database is left alone).
    """
    check_backup_file(file)
    saved = backup_to(default_backup_path("jobkit-before-restore"))
    close()
    with contextlib.closing(sqlite3.connect(file)) as source, contextlib.closing(sqlite3.connect(db_path())) as target:
        source.backup(target)
    return saved
