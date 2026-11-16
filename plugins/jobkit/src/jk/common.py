"""Helpers shared by every tool: the home folder, error type, running a command in one transaction, small text utilities.

Standard library only. Import it as `from jk import common`.
"""
from __future__ import annotations

import argparse
import io
import re
import sys
from collections.abc import Callable, Collection
from typing import Final

from jk import store
from jk.base import (TROUBLESHOOT_HINT, ToolError, backup_dir, data_dir, header_file, home, hide_home, now,
                     output_dir, user_path)

SLUG_MAX: Final[int] = 60
__all__ = ["SLUG_MAX", "TROUBLESHOOT_HINT", "ToolError", "backup_dir", "data_dir", "emit", "header_file", "home",
           "hide_home", "make_parser", "now", "output_dir", "read_text_arg", "report_failure", "run", "slug",
           "use_utf8_output", "user_path"]


def slug(text: str) -> str:
    """Lowercase id made of letters, digits and dashes, at most SLUG_MAX characters."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:SLUG_MAX]


def emit(text: str, output: str | None) -> None:
    """Print the text, or write it to the `-o/--output` file and say so."""
    if output:
        user_path(output).write_text(text, encoding="utf-8")
        print(f"Wrote {hide_home(output)}")
    else:
        print(text, end="")


def read_text_arg(arg: str) -> str:
    """Contents of the file named by `arg`, or standard input when `arg` is "-".

    Raises:
        ToolError: the file is missing, unreadable, a folder, or not UTF-8 text.
    """
    if arg == "-":
        return sys.stdin.read()
    try:
        return user_path(arg).read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ToolError(f"{arg} is not a UTF-8 text file.") from exc
    except OSError as exc:
        raise ToolError(f"cannot read {arg}: {exc.strerror or exc}") from exc


def positive_int(text: str) -> int:
    """An argparse type: a whole number of 1 or more."""
    try:
        value = int(text)
    except ValueError:
        value = 0
    if value < 1:
        raise argparse.ArgumentTypeError(f"expected a whole number of 1 or more, got {text!r}")
    return value


def make_parser(doc: str | None) -> argparse.ArgumentParser:
    """Argument parser whose help shows the module docstring (usage examples) as written."""
    return argparse.ArgumentParser(description=doc, formatter_class=argparse.RawDescriptionHelpFormatter)


def use_utf8_output() -> None:
    """Make standard output and error UTF-8, so a console with another code page cannot fail on a long dash.

    Characters the console cannot show are replaced rather than raising an error.
    """
    for stream in (sys.stdout, sys.stderr):
        encoding = (getattr(stream, "encoding", None) or "utf-8").lower().replace("-", "")
        if encoding != "utf8" and isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8", errors="replace")


def run(args: argparse.Namespace, *, lock: bool = False, read_only: bool = False) -> int:
    """Call the chosen subcommand (`args.fn`) in one database transaction and return the exit status.

    A handler may return None (success) or an int status. Any error is printed to standard error by
    `report_failure` and becomes status 1; its transaction is rolled back. With `lock`, the transaction takes
    the write lock at once (use it for commands that change data). With `read_only`, it takes no write lock and
    any attempt to change data fails, so a subcommand marked read-only by mistake cannot write unlocked.
    """
    use_utf8_output()
    try:
        with store.transaction(write=lock and not read_only) as conn, store.query_only(conn, read_only):
            status = args.fn(args)
    except Exception as exc:  # pylint: disable=broad-exception-caught  # every failure ends in a status
        return report_failure(exc)
    return status or 0


def run_writer(args: argparse.Namespace, readers: Collection[Callable[..., object]] = ()) -> int:
    """`run` for a tool that changes data: its subcommands take the write lock at once, except the `readers`
    handlers, which run read-only."""
    read_only = args.fn in readers
    return run(args, lock=not read_only, read_only=read_only)


def report_failure(exc: Exception) -> int:
    """Print a failed command's error to standard error and return status 1.

    A ToolError prints its message; an unexpected error prints its type and message, never a stack trace. The
    home folder is shown as `~` (on Windows `%USERPROFILE%`). Unless the message alone says what to fix, a last line points to the
    troubleshooting guide.
    """
    if isinstance(exc, ToolError):
        print(hide_home(str(exc)), file=sys.stderr)
        if not exc.troubleshoot:
            return 1
    else:
        print(f"error: {type(exc).__name__}: {hide_home(str(exc))}", file=sys.stderr)
    print(TROUBLESHOOT_HINT, file=sys.stderr)
    return 1
