"""Move the old JSON data files (`profile/`, `prep/`, `resume-data/`) into the database, safely.

`jobkit migrate` copies the old files to a backup folder and checks the copy; imports every kind of data in
one transaction; proves the import by exporting it again and comparing count and checksum per kind with
what was read; and keeps the whole import only when every kind matches. The old files are never touched
until `jobkit migrate --remove-old`, which first checks the database against the backup copy.
"""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Any, NamedTuple

from jobkit import base, records, store
from jobkit.base import ToolError
from jobkit.interview import tables

RECORD_KEY = "import.record"
REMOVABLE_SUFFIXES = (".json", ".bak", ".tmp")


class Row(NamedTuple):
    """The verification result for one kind of data."""

    name: str
    records: int
    checksum: str
    ok: bool


def find_source(path: Path) -> Path:
    """The folder that holds the old data.

    Raises:
        ToolError: none of the old folders exists under `path`.
    """
    if not any((path / folder).is_dir() for folder in records.OLD_FOLDERS):
        raise ToolError(f"No old data under {path}: expected {', '.join(records.OLD_FOLDERS)}. "
                        "Use --from to name the folder that holds them.")
    return path


def old_files(root: Path) -> list[Path]:
    """Every file under the old data folders."""
    return sorted(f for folder in records.OLD_FOLDERS for f in (root / folder).rglob("*") if f.is_file())


def read_all(root: Path) -> dict[str, Any]:
    """{kind name: data read from the old files} (a ToolError names any file that cannot be read)."""
    return {entry.name: entry.read(root) for entry in records.KINDS}


def verify(data: dict[str, Any]) -> list[Row]:
    """Compare what was read with what the database exports, per kind."""
    rows = []
    for entry in records.KINDS:
        exported = entry.export()
        source = data.get(entry.name)
        rows.append(Row(entry.name, records.count_of(entry, exported),
                        records.checksum(exported)[:12] if not records.blank(exported) else "-",
                        records.same(source, exported)))
    return rows


def print_rows(rows: list[Row]) -> None:
    """The per-kind report."""
    for row in rows:
        print(f"  {row.name:<16} {row.records:>6} records  {row.checksum:<12}  {'ok' if row.ok else 'MISMATCH'}")


def print_counts(data: dict[str, Any]) -> None:
    """What a dry run would import."""
    for entry in records.KINDS:
        print(f"  {entry.name:<16} {records.count_of(entry, data.get(entry.name)):>6} records")


# ---------------------------------------------------------------- backup of the old files

def tree_sums(root: Path, files: list[Path]) -> dict[str, str]:
    """{path relative to root: sha256 of the content} for the given files."""
    return {f.relative_to(root).as_posix(): hashlib.sha256(f.read_bytes()).hexdigest() for f in files}


def backup_old(root: Path) -> Path:
    """Copy the old files to `backup/json-<timestamp>/` and check the copy file by file.

    Raises:
        ToolError: a file is missing from the copy or differs from its original.
    """
    dest = base.backup_dir() / f"json-{store.stamp()}"
    files = old_files(root)
    for file in files:
        target = dest / file.relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file, target)
    if tree_sums(root, files) != tree_sums(dest, old_files(dest)):
        raise ToolError(f"The backup in {dest} is incomplete, so nothing was imported.")
    return dest


# ---------------------------------------------------------------- import

def import_record() -> dict[str, Any] | None:
    """What the last import recorded (source, backup, counts), or None when nothing was imported."""
    with store.transaction(write=False) as conn:
        return tables.meta_get(conn, RECORD_KEY, None)


def import_all(data: dict[str, Any], root: Path, backup: Path) -> list[Row]:
    """Write every kind in one transaction and keep it only when every kind verifies."""
    with store.transaction() as conn:
        for entry in records.KINDS:
            if not records.blank(data.get(entry.name)):
                entry.write(data[entry.name])
        rows = verify(data)
        bad = [r.name for r in rows if not r.ok]
        if bad:
            print_rows(rows)
            raise ToolError(f"Verification failed for {', '.join(bad)}: nothing was imported. "
                            f"Your old files and the backup in {backup} are untouched.")
        tables.meta_put(conn, RECORD_KEY, {"at": base.now(), "source": str(root), "backup": str(backup),
                                           "counts": {r.name: r.records for r in rows}})
    return rows


def start_over() -> Path:
    """Save the current database, then replace it with an empty one (for `--replace`)."""
    saved = store.backup_to(store.default_backup_path("jobkit-before-replace"))
    store.close()
    for suffix in ("", "-wal", "-shm"):
        store.db_path().with_name(store.db_path().name + suffix).unlink(missing_ok=True)
    store.create()
    return saved


def copy_header(root: Path) -> None:
    """Bring the old `profile/header.md` along (it stays a file) unless one already exists."""
    old, new = root / "profile" / "header.md", base.header_file()
    if old.is_file() and not new.exists():
        new.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(old, new)


def migrate(source: Path, *, dry_run: bool, replace: bool) -> int:
    """Import the old data; returns the exit status."""
    root = find_source(source)
    data = read_all(root)
    if dry_run:
        print(f"Dry run: would import from {root} (nothing written):")
        print_counts(data)
        return 0
    store.connect()
    if import_record() is not None:
        if not replace:
            print("The data is already imported (nothing changed). Use `jobkit migrate --replace` to import again.")
            return 0
        print(f"Saved the current database to {start_over()} before replacing it.")
    backup = backup_old(root)
    print(f"Backed up {len(old_files(root))} old files to {backup}")
    rows = import_all(data, root, backup)
    copy_header(root)
    print(f"Imported into {store.db_path()}; every kind verified:")
    print_rows(rows)
    print("Your old files were not changed. After you have checked the data (`jobkit export`), "
          "`jobkit migrate --remove-old` deletes them; the backup stays.")
    return 0


# ---------------------------------------------------------------- remove the old files

def remove_old() -> int:
    """Delete the old JSON files after checking the database against the backup copy."""
    record = import_record()
    if record is None:
        raise ToolError("Nothing has been imported yet: run `jobkit migrate` first.")
    backup, root = Path(record["backup"]), Path(record["source"])
    if not backup.is_dir():
        raise ToolError(f"The backup {backup} is missing, so no old file was deleted.")
    rows = verify(read_all(backup))
    if not all(r.ok for r in rows):
        print_rows(rows)
        raise ToolError("The database does not match the backup, so no old file was deleted.")
    removed = delete_old_json(root)
    print(f"Removed {removed} old JSON files from {root}. The backup {backup} is kept.")
    return 0


def delete_old_json(root: Path) -> int:
    """Delete the old data files (JSON and the copies the old version kept) and the folders left empty."""
    removed = 0
    for file in old_files(root):
        if file.suffix in REMOVABLE_SUFFIXES or file.name == ".lock":
            file.unlink()
            removed += 1
    for folder in sorted((p for f in records.OLD_FOLDERS for p in (root / f).rglob("*") if p.is_dir()),
                         key=lambda p: len(p.parts), reverse=True):
        if not any(folder.iterdir()):
            folder.rmdir()
    return removed
