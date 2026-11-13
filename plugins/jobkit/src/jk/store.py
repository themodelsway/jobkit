"""The one local database that holds all user data (standard library `sqlite3` only).

  data/jobkit.db under the home folder (`JOBKIT_HOME`, default `~/.jobkit`)

Every command runs in one transaction: its changes are stored together or not at all. Several commands may
run at the same time (WAL mode and a busy timeout). Schema upgrades are numbered steps in `MIGRATIONS`.
Import it as `from jk import store`; it does no work at import time.
"""
from __future__ import annotations

import contextlib
import json
import shutil
import sqlite3
import tempfile
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from jk import base, schema
from jk.base import ToolError

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
            with _savepoint(conn, write):
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


@contextlib.contextmanager
def _savepoint(conn: sqlite3.Connection, write: bool) -> Iterator[None]:
    """A nested write: its changes are undone when it raises, so a caller that handles the error carries on clean.

    A nested read opens nothing. The outer transaction still decides whether anything is committed.
    """
    if not write:
        yield
        return
    name = f"nested_{_STATE.depth}"
    conn.execute(f"SAVEPOINT {name}")
    try:
        yield
    except BaseException:
        conn.execute(f"ROLLBACK TO {name}")
        conn.execute(f"RELEASE {name}")
        raise
    conn.execute(f"RELEASE {name}")


def _rollback(conn: sqlite3.Connection) -> None:
    """Roll back the open transaction if there still is one."""
    if conn.in_transaction:
        conn.execute("ROLLBACK")


# ---------------------------------------------------------------- shared record helpers

def dump(value: Any) -> str:
    """Compact, readable JSON for a body column (NaN and infinity are refused: they are not valid JSON)."""
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def bodies(conn: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> list[Any]:
    """The decoded first column (a `body`) of every row the query returns."""
    return [json.loads(row[0]) for row in conn.execute(sql, params)]


def meta_get(conn: sqlite3.Connection, key: str, default: Any) -> Any:
    """A value from the meta table, or `default`."""
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return default if row is None else json.loads(row[0])


def meta_put(conn: sqlite3.Connection, key: str, value: Any) -> None:
    """Store a value in the meta table."""
    conn.execute("INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                 (key, dump(value)))


def split(record: Mapping[str, Any], owned: Sequence[str]) -> tuple[tuple[Any, ...], str]:
    """The values of the `owned` fields (None when the record has none), and everything else as JSON text.

    Each record family names the fields that are real columns; the rest of the record lives in `body` only.
    """
    return (tuple(record.get(name) for name in owned),
            dump({k: v for k, v in record.items() if k not in owned}))


def merge(fields: Mapping[str, Any], body: str) -> dict[str, Any]:
    """A record from its column fields and its `body` text (the inverse of `split`)."""
    return {**fields, **json.loads(body)}


def records(conn: sqlite3.Connection, sql: str, params: Sequence[Any] = (), owned: Sequence[str] = ()) -> list[Any]:
    """Whole records: each row of the query holds the `owned` column values in order, then `body` last."""
    return [merge(dict(zip(owned, row[:-1], strict=True)), row[-1]) for row in conn.execute(sql, params)]


def keep_only(conn: sqlite3.Connection, table: str, key: str, keep: Iterable[str]) -> None:
    """Delete the rows of `table` whose `key` is not in `keep` (rows that were written are upserts)."""
    keep = list(keep)
    marks = ",".join("?" for _ in keep)
    conn.execute(f"DELETE FROM {table} WHERE {key} NOT IN ({marks})" if keep else f"DELETE FROM {table}", keep)


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


def _columns(conn: sqlite3.Connection) -> dict[str, set[str]]:
    """Every table of the database with its column names."""
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    return {t: {r[1] for r in conn.execute(f'PRAGMA table_info("{t}")')} for t in tables}


def check_backup_file(file: Path) -> None:
    """Fail unless `file` is a jobkit database this program can read and upgrade.

    The file is checked on a temporary copy: SQLite's integrity check, the upgrade to the current schema, and
    every table and column the current schema has. The file itself is never changed.

    Raises:
        ToolError: the file is missing, damaged, not a jobkit database, incomplete, or from a newer version.
    """
    if not file.is_file():
        raise ToolError(f"{file} does not exist.")
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "candidate.db"
        shutil.copyfile(file, copy)
        try:
            _check_copy(file, copy)
        except sqlite3.DatabaseError as exc:
            raise ToolError(f"{file} is not a jobkit database ({exc}).") from exc


NOT_RECORDS: Final[frozenset[str]] = frozenset({"resume_item", "curation", "unparsed", "setting", "meta"})
"""Tables whose JSON is not one object per row, so only `json_valid` applies to them."""


def _triggers(conn: sqlite3.Connection) -> set[str]:
    """Names of every trigger of the database."""
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}


def _check_records(file: Path, conn: sqlite3.Connection, have: dict[str, set[str]]) -> None:
    """Fail on a broken reference or a stored record that is not readable JSON; messages name the table only.

    Raises:
        ToolError: a foreign key points at nothing, a `body` or `value` is not valid JSON, or a record is not an object.
    """
    broken = sorted({row[0] for row in conn.execute("PRAGMA foreign_key_check")})
    if broken:
        raise ToolError(f"{file} holds records that point at missing records (table {', '.join(broken)}).")
    for table, cols in sorted(have.items()):
        for col in sorted(cols & {"body", "value"}):
            if conn.execute(f'SELECT 1 FROM "{table}" WHERE NOT json_valid("{col}") LIMIT 1').fetchone():
                raise ToolError(f"{file} holds a record in table {table} that is not readable (not valid JSON).")
            if col == "body" and table not in NOT_RECORDS and conn.execute(
                    f'SELECT 1 FROM "{table}" WHERE json_type(body) != \'object\' LIMIT 1').fetchone():
                raise ToolError(f"{file} holds a record in table {table} that is not readable (not a JSON object).")


def _check_copy(file: Path, copy: Path) -> None:
    """The checks of `check_backup_file`, run on a throw-away copy."""
    with contextlib.closing(sqlite3.connect(copy, isolation_level=None)) as conn:
        found = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='meta'").fetchone()
        found_version = stored_version(conn)
        if not found or found_version < 1:
            raise ToolError(f"{file} is not a jobkit database.")
        if found_version > version():
            raise ToolError(f"{file} is version {found_version}; this program only knows version {version()}.")
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ToolError(f"{file} is damaged (SQLite integrity check failed).")
        conn.row_factory = sqlite3.Row
        migrate_to(conn, version())
        have, triggers = _columns(conn), _triggers(conn)
        with contextlib.closing(sqlite3.connect(":memory:", isolation_level=None)) as fresh:
            migrate_to(fresh, version())
            missing = [f"{t}.{c}" for t, cols in _columns(fresh).items() for c in sorted(cols - have.get(t, set()))]
            unprotected = sorted(_triggers(fresh) - triggers)
        if missing:
            raise ToolError(f"{file} is not a complete jobkit database (missing {', '.join(missing[:5])}).")
        if unprotected:
            raise ToolError(f"{file} lacks the triggers that protect logged answers (missing trigger "
                            f"{', '.join(unprotected[:5])}).")
        _check_records(file, conn, have)


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
