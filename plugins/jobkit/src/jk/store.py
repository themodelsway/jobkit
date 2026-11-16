"""The one local database that holds all user data (standard library `sqlite3` only).

  data/jobkit.db under the home folder (`JOBKIT_HOME`, default `~/.jobkit`)

Every command runs in one transaction: its changes are stored together or not at all. Several commands may
run at the same time (WAL mode and a busy timeout). Schema upgrades are numbered steps in `MIGRATIONS`, applied together in one transaction.
Import it as `from jk import store`; it does no work at import time.
"""
from __future__ import annotations

import contextlib
import json
import shutil
import sqlite3
import tempfile
import time
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from jk import base, schema
from jk.base import ToolError

BUSY_TIMEOUT_MS: Final[int] = 5000
BUSY_CODES: Final[frozenset[int]] = frozenset({sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED})
"""SQLite's primary result codes for a database another connection holds."""
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


class StoreError(ToolError):
    """The stored data could not be used (busy, unavailable, written by a newer version); nothing was changed."""

    troubleshoot = True


class NewerDatabaseError(StoreError):
    """The database was written by a newer version of the program; nothing was changed."""


class BusyTooLong(sqlite3.OperationalError):
    """A copy waited `BUSY_TIMEOUT_MS` for another connection's lock and gave up; reads as SQLite's busy code."""

    sqlite_errorcode = sqlite3.SQLITE_BUSY


def copy_database(source: sqlite3.Connection, target: sqlite3.Connection) -> None:
    """`source.backup(target)`, giving up once it has waited `BUSY_TIMEOUT_MS` for a lock (Python's backup retries
    a busy or locked database without limit, whatever the connection's timeout).

    Raises:
        BusyTooLong: another connection held the source or the target for longer than that.
    """
    deadline = time.monotonic() + BUSY_TIMEOUT_MS / 1000

    def progress(status: int, _remaining: int, _total: int) -> None:
        if status in BUSY_CODES and time.monotonic() > deadline:
            raise BusyTooLong("database is locked")

    source.backup(target, progress=progress, sleep=0.05)


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
    """Apply the missing upgrade steps in order, all inside one transaction; return the new version.

    The version is read after taking the write lock, so two commands never upgrade (or copy) at once. An
    existing database is first copied to `backup/` (never for a new or empty one).

    Raises:
        ToolError: the database was written by a newer version of the program, or the copy failed.
    """
    if stored_version(conn) == version():
        return version()                       # nothing to do: take no write lock (readers must not wait)
    conn.execute("BEGIN IMMEDIATE")
    try:
        current = stored_version(conn)         # read again: another command may have upgraded meanwhile
        if current == version():
            conn.execute("COMMIT")
            return current
        if current > version():
            raise NewerDatabaseError(f"The database is version {current} but this program only knows version "
                            f"{version()}. Update jobkit; nothing was changed.")
        if 0 < current < version():
            _save_before_upgrade(conn, current)
        _apply_steps(conn, current, version())
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")
    return version()


def _reserve_backup(label: str) -> Path:
    """Create an empty file `backup/<label>-<timestamp>[-N].db` that no earlier copy has; return its path."""
    base.backup_dir().mkdir(parents=True, exist_ok=True)
    first = default_backup_path(label)
    for number in range(1, 1000):
        path = first if number == 1 else first.with_name(f"{first.stem}-{number}{first.suffix}")
        try:
            path.open("xb").close()
        except FileExistsError:
            continue
        return path
    raise FileExistsError(f"too many copies named {first.name}")


def _save_before_upgrade(conn: sqlite3.Connection, current: int) -> Path:
    """Copy the database to `backup/jobkit-before-upgrade-v<current>-<timestamp>.db`; return that file.

    An earlier copy is never overwritten. Raises ToolError if the copy cannot be written.
    """
    return save_committed_copy(conn, f"jobkit-before-upgrade-v{current}", "upgrading it")


def save_committed_copy(conn: sqlite3.Connection, label: str, action: str) -> Path:
    """Copy the last committed state of the database to `backup/<label>-<timestamp>.db` and return that file; safe
    while `conn` holds the write lock. An earlier copy is never overwritten. Raises ToolError (saying that nothing
    was changed before `action`) if the copy cannot be written."""
    path: Path | None = None
    try:
        path = _reserve_backup(label)
        # A second connection reads the last committed state (WAL readers are not blocked by our write lock;
        # `conn.backup` on the locked connection itself would wait forever).
        source_file = conn.execute("PRAGMA database_list").fetchone()[2]
        with contextlib.closing(sqlite3.connect(source_file, timeout=BUSY_TIMEOUT_MS / 1000)) as source, \
                contextlib.closing(sqlite3.connect(path)) as target:
            copy_database(source, target)
    except (OSError, sqlite3.Error) as err:
        if path is not None:
            with contextlib.suppress(OSError):
                path.unlink()
        raise ToolError(f"Could not save a copy of the database before {action} ({err}). "
                        "Nothing was changed.") from err
    return path


def _apply_steps(conn: sqlite3.Connection, start: int, target: int) -> None:
    """Run the steps from `start` to `target` inside the open transaction, stamping each version."""
    for number in range(start, target):
        MIGRATIONS[number](conn)
        conn.execute(f"PRAGMA user_version={number + 1}")


def migrate_to(conn: sqlite3.Connection, target: int) -> int:
    """Apply upgrade steps until the database is at `target`, all in one transaction (all or nothing).

    If any step fails, every step is rolled back and the database stays at the version it had.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        _apply_steps(conn, stored_version(conn), target)
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
        raise StoreError(f"The database is busy ({exc}). Try again in a moment.") from exc
    _STATE.depth = 1
    try:
        yield conn
        conn.execute("COMMIT")
    except sqlite3.IntegrityError as exc:
        _rollback(conn)
        raise ToolError(f"Refused, nothing was changed: {exc}.") from exc
    except sqlite3.OperationalError as exc:
        _rollback(conn)
        raise StoreError(f"The database is busy or unavailable ({exc}). Try again in a moment.") from exc
    except BaseException:
        _rollback(conn)
        raise
    finally:
        _STATE.depth = 0


@contextlib.contextmanager
def query_only(conn: sqlite3.Connection, on: bool = True) -> Iterator[None]:
    """While the block runs (when `on`), refuse every change to the database on this connection."""
    if not on:
        yield
        return
    conn.execute("PRAGMA query_only=ON")
    try:
        yield
    finally:
        conn.execute("PRAGMA query_only=OFF")


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
        copy_database(source, target)
    finally:
        target.close()
    return path


def _columns(conn: sqlite3.Connection) -> dict[str, set[str]]:
    """Every table of the database with its column names."""
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    return {t: {r[1] for r in conn.execute(f'PRAGMA table_info("{t}")')} for t in tables}


def check_backup_file(file: Path) -> None:
    """Fail unless `file` is a jobkit database this program can read and upgrade.

    The file is checked on a temporary, writable copy, together with the write-ahead log beside it (SQLite reads
    both): SQLite's integrity check, the upgrade to the current schema, and every table and column the current schema
    has. The file itself is never changed and only needs to be readable.

    Raises:
        ToolError: the file is missing, damaged, not a jobkit database, incomplete, or from a newer version.
    """
    with _checked_copy(file):
        pass


@contextlib.contextmanager
def _checked_copy(file: Path) -> Iterator[Path]:
    """`file` with the committed changes of its write-ahead log, as one temporary file at the file's own schema
    version, after a copy of exactly that file passed the checks of `check_backup_file` (the checks upgrade their
    copy, not this one, so an older backup is restored at its own version). It is removed when the block ends.

    Raises:
        ToolError: as `check_backup_file`.
    """
    if not file.is_file():
        raise ToolError(f"{file} does not exist.")
    with tempfile.TemporaryDirectory() as tmp:
        snapshot, check = Path(tmp) / "snapshot.db", Path(tmp) / "check.db"
        try:
            _snapshot(_copy_files(file, Path(tmp) / "backup.db"), snapshot)
            shutil.copyfile(snapshot, check)
            _check_copy(file, check)
        except sqlite3.DatabaseError as exc:
            raise ToolError(f"{file} is not a jobkit database ({exc}).") from exc
        yield snapshot


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


def _database_files(path: Path) -> list[Path]:
    """The database file and the write-ahead log files beside it that exist."""
    return [p for p in (path, Path(f"{path}-wal"), Path(f"{path}-shm")) if p.exists()]


def _copy_files(path: Path, saved: Path) -> Path:
    """Copy the database file and its write-ahead log as they are on disk to `saved` (and `saved`-wal); the copies
    are new writable files, whatever the originals' permissions."""
    saved.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, saved)
    wal = Path(f"{path}-wal")
    if wal.exists():
        shutil.copyfile(wal, Path(f"{saved}-wal"))
    return saved


def _snapshot(path: Path, saved: Path) -> Path:
    """Copy the database at `path` to the one file `saved` as SQLite reads it (with the committed changes of its
    write-ahead log), without upgrading it, so a database of any version or with missing tables is copied too.

    Raises:
        BusyTooLong: another connection held the database for longer than `BUSY_TIMEOUT_MS`.
    """
    saved.parent.mkdir(parents=True, exist_ok=True)
    with contextlib.closing(sqlite3.connect(path, timeout=BUSY_TIMEOUT_MS / 1000)) as source, \
            contextlib.closing(sqlite3.connect(saved)) as target:
        copy_database(source, target)
    return saved


def _is_busy(exc: sqlite3.Error) -> bool:
    """True when SQLite's primary result code says another connection holds the database (busy or locked)."""
    code = getattr(exc, "sqlite_errorcode", None)
    return isinstance(code, int) and code & 0xFF in BUSY_CODES


def _save_before_restore(path: Path) -> Path | None:
    """Keep the database a restore will replace, and return the copy (None when there is no database).

    A database SQLite can read is copied as one consistent file, whatever its version or tables. One SQLite cannot
    read is copied file by file and then removed so the restore can write a new file. A busy database fails the
    restore.

    Raises:
        StoreError: another command holds the database.
    """
    if not path.exists():
        return None
    saved = default_backup_path("jobkit-before-restore")
    close()
    try:
        return _snapshot(path, saved)
    except sqlite3.DatabaseError as exc:
        for file in _database_files(saved):
            file.unlink()                       # a partial snapshot
        if _is_busy(exc):
            raise StoreError(f"The database is busy ({exc}). Try again in a moment; nothing was changed.") from exc
    _copy_files(path, saved)
    for file in _database_files(path):
        file.unlink()
    return saved


def restore_from(file: Path) -> Path | None:
    """Replace the database with a backup, after saving the current one; returns that saved copy, or None when there
    was no database to save. What is written is the snapshot that was checked, at the backup's own schema version
    (the next command upgrades it), so the backup file is never opened by SQLite and never changed.

    Raises:
        ToolError: the file is not a usable jobkit database (the current database is left alone).
        StoreError: another command holds the database (it is not replaced).
    """
    with _checked_copy(file) as snapshot:
        path = db_path()
        saved = _save_before_restore(path)
        close()
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with contextlib.closing(sqlite3.connect(snapshot)) as source, \
                    contextlib.closing(sqlite3.connect(path, timeout=BUSY_TIMEOUT_MS / 1000)) as target:
                copy_database(source, target)
        except sqlite3.DatabaseError as exc:
            if _is_busy(exc):
                raise StoreError(f"The database is busy ({exc}). Try again in a moment; it was not replaced.") from exc
            raise
    return saved
