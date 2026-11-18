#!/usr/bin/env python3
"""The jobkit home folder and its database.

  jobkit init       # create ~/.jobkit (or $JOBKIT_HOME) and an empty database; safe to repeat
  jobkit status     # where the data is, the schema version, size and how many records
  jobkit status --setup   # one word: no-database, no-resumes, no-target or ready (or why the check failed)
  jobkit status --summary # the setup stage, open sessions, retests due, company research and the suggested next step
  jobkit export     # view the data as JSON or Markdown (--format, --only KIND, -o DIR)
  jobkit backup     # save a copy of the database (-o FILE) or restore one (--restore FILE)
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from collections.abc import Sequence
from datetime import date
from importlib.metadata import version
from pathlib import Path

from jk import common, export, records, setup_state, store, summary


def cmd_init(args: argparse.Namespace) -> None:
    """Create the home folders and the database."""
    del args
    path = store.db_path()
    created = store.create()
    if created:
        print(f"Created {shown(path)} (schema version {store.version()}). Home folder: {shown(common.home())}")
    else:
        print(f"Already set up: {shown(path)} (nothing changed).")
    if _synced(common.home()):
        print("Warning: this folder looks synced (iCloud, Dropbox, ...). Keep the database on a local disk.")


def shown(path: Path | str) -> str:
    """A path for output, with the home folder written as `~` (on Windows `%USERPROFILE%`)."""
    return common.hide_home(str(path))


def _synced(folder: Path) -> bool:
    """True when the folder path runs through a well-known cloud-sync folder."""
    text = str(folder)
    return any(mark in text for mark in ("Mobile Documents", "Dropbox", "OneDrive", "Google Drive"))


def _print_report(lines: Sequence[str], problem: str | None) -> int:
    """Print the lines; on an error, the error line and the troubleshooting hint on standard error, and 1."""
    for line in lines:
        print(line)
    if not problem:
        return 0
    print(problem, file=sys.stderr)
    print(common.TROUBLESHOOT_HINT, file=sys.stderr)
    return 1


def cmd_status(args: argparse.Namespace) -> int:
    """Show the location, version, size and per-kind record counts; or only the setup stage; or the summary."""
    if args.setup:
        word, problem = setup_state.report()
        return _print_report([word], problem)
    if args.summary:
        return _print_report(*summary.summary(date.today()))
    path = store.db_path()
    with store.transaction(write=False) as conn:
        print(f"database: {shown(path)}")
        print(f"schema version: {store.stored_version(conn)} (program knows {store.version()})")
        print(f"size: {path.stat().st_size} bytes; SQLite {sqlite3.sqlite_version}")
        for kind, number in records.counts().items():
            print(f"{kind}: {number}")
    return 0


def cmd_export(args: argparse.Namespace) -> None:
    """Print the data, or write one file per kind into a folder."""
    fmt = export.check_format(args.format)
    if args.output:
        for path in export.export_to_folder(common.user_path(args.output), fmt, args.only):
            print(f"Wrote {shown(path)}")
    else:
        print(export.export_text(fmt, args.only), end="")


def cmd_backup(args: argparse.Namespace) -> None:
    """Save a copy of the database, or restore one."""
    if args.restore:
        saved = store.restore_from(common.user_path(args.restore))
        kept = f"The previous database was saved as {shown(saved)}." if saved else "There was no database before."
        print(f"Restored {shown(args.restore)}. {kept}")
        return
    path = store.backup_to(common.user_path(args.output) if args.output else store.default_backup_path())
    print(f"Backup written to {shown(path)} ({path.stat().st_size} bytes).")


def build_parser() -> argparse.ArgumentParser:
    """The command-line parser."""
    parser = common.make_parser(__doc__)
    parser.add_argument("--version", action="version", version=f"jobkit {version('jobkit')}")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="create the home folder and the database").set_defaults(fn=cmd_init)
    status = sub.add_parser("status", help="show the database location, version and counts")
    view = status.add_mutually_exclusive_group()
    view.add_argument("--setup", action="store_true",
                      help="print one word: no-database, no-resumes, no-target or ready; when the check fails, "
                           "blocked, busy, too-new or failed (exit 1, the error on standard error)")
    view.add_argument("--summary", action="store_true",
                      help="the setup stage, open sessions, retests due, company research and the suggested next step")
    status.set_defaults(fn=cmd_status)
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
    """`init` and `backup` create, replace or copy the database file, and `status --setup` and `--summary` must
    also answer when there is no database or it cannot be opened, so none of them can run inside one transaction."""
    return args.fn in (cmd_init, cmd_backup) or getattr(args, "setup", False) or getattr(args, "summary", False)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point; returns the exit status."""
    args = build_parser().parse_args(argv)
    if not manages_its_own_transactions(args):
        return common.run(args)
    try:
        return args.fn(args) or 0
    except Exception as exc:  # pylint: disable=broad-exception-caught  # every failure ends in a status
        return common.report_failure(exc)


if __name__ == "__main__":
    raise SystemExit(main())
