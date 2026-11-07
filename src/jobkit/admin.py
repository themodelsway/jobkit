#!/usr/bin/env python3
"""The jobkit home folder and its database.

  jobkit init       # create ~/.jobkit (or $JOBKIT_HOME) and an empty database; safe to repeat
  jobkit status     # where the data is, the schema version, size and how many records
  jobkit export     # view the data as JSON or Markdown (--format, --only KIND, -o DIR)
  jobkit backup     # save a copy of the database (-o FILE) or restore one (--restore FILE)
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from collections.abc import Sequence
from importlib.metadata import version
from pathlib import Path

from jobkit import common, export, records, store


def cmd_init(args: argparse.Namespace) -> None:
    """Create the home folders and the database."""
    del args
    path = store.db_path()
    created = store.create()
    if created:
        print(f"Created {path} (schema version {store.version()}). Home folder: {common.home()}")
    else:
        print(f"Already set up: {path} (nothing changed).")
    if _synced(common.home()):
        print("Warning: this folder looks synced (iCloud, Dropbox, ...). Keep the database on a local disk.")


def _synced(folder: Path) -> bool:
    """True when the folder path runs through a well-known cloud-sync folder."""
    text = str(folder)
    return any(mark in text for mark in ("Mobile Documents", "Dropbox", "OneDrive", "Google Drive"))


def cmd_status(args: argparse.Namespace) -> None:
    """Show the location, version, size and per-kind record counts."""
    del args
    path = store.db_path()
    with store.transaction(write=False) as conn:
        print(f"database: {path}")
        print(f"schema version: {store.stored_version(conn)} (program knows {store.version()})")
        print(f"size: {path.stat().st_size} bytes; SQLite {sqlite3.sqlite_version}")
        for kind, number in records.counts().items():
            print(f"{kind}: {number}")


def cmd_export(args: argparse.Namespace) -> None:
    """Print the data, or write one file per kind into a folder."""
    fmt = export.check_format(args.format)
    if args.output:
        for path in export.export_to_folder(Path(args.output), fmt, args.only):
            print(f"Wrote {path}")
    else:
        print(export.export_text(fmt, args.only), end="")


def cmd_backup(args: argparse.Namespace) -> None:
    """Save a copy of the database, or restore one."""
    if args.restore:
        saved = store.restore_from(Path(args.restore))
        print(f"Restored {args.restore}. The previous database was saved as {saved}.")
        return
    path = store.backup_to(Path(args.output) if args.output else store.default_backup_path())
    print(f"Backup written to {path} ({path.stat().st_size} bytes).")


def build_parser() -> argparse.ArgumentParser:
    """The command-line parser."""
    parser = common.make_parser(__doc__)
    parser.add_argument("--version", action="version", version=f"jobkit {version('jobkit')}")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="create the home folder and the database").set_defaults(fn=cmd_init)
    sub.add_parser("status", help="show the database location, version and counts").set_defaults(fn=cmd_status)
    export_cmd = sub.add_parser("export", help="show the stored data as JSON or Markdown")
    export_cmd.add_argument("--format", default="json", help="json or md")
    export_cmd.add_argument("--only", help="one kind of data, for example stories")
    export_cmd.add_argument("-o", "--output", help="folder to write one file per kind into")
    export_cmd.set_defaults(fn=cmd_export)
    backup = sub.add_parser("backup", help="save or restore a copy of the database")
    backup.add_argument("-o", "--output", help="file to write the backup to")
    backup.add_argument("--restore", metavar="FILE", help="replace the database with this backup")
    backup.set_defaults(fn=cmd_backup)
    return parser


def manages_its_own_transactions(args: argparse.Namespace) -> bool:
    """`init` and `backup` create, replace or copy the database file, so they cannot run inside a transaction."""
    return args.fn in (cmd_init, cmd_backup)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point; returns the exit status."""
    args = build_parser().parse_args(argv)
    if not manages_its_own_transactions(args):
        return common.run(args)
    try:
        return args.fn(args) or 0
    except common.ToolError as exc:
        print(exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
