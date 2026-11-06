"""Helpers shared by every tool: the home folder, error type, running a command in one transaction, small text utilities.

Standard library only. Import it as `from jobkit import common`.
"""
from __future__ import annotations

import argparse
import io
import re
import sys
from pathlib import Path
from typing import Final

from jobkit import store
from jobkit.base import ToolError, backup_dir, data_dir, header_file, home, now, output_dir

SLUG_MAX: Final[int] = 60
__all__ = ["SLUG_MAX", "ToolError", "backup_dir", "data_dir", "header_file", "home", "make_parser", "now",
           "output_dir", "read_text_arg", "run", "slug", "use_utf8_output"]


def slug(text: str) -> str:
    """Lowercase id made of letters, digits and dashes, at most SLUG_MAX characters."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:SLUG_MAX]


def read_text_arg(arg: str) -> str:
    """Contents of the file named by `arg`, or standard input when `arg` is "-"."""
    return sys.stdin.read() if arg == "-" else Path(arg).read_text(encoding="utf-8")


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


def run(args: argparse.Namespace, *, lock: bool = False) -> int:
    """Call the chosen subcommand (`args.fn`) in one database transaction and return the exit status.

    A handler may return None (success) or an int status. A ToolError is printed to standard error as
    its message and becomes status 1; its transaction is rolled back. With `lock`, the transaction takes
    the write lock at once (use it for commands that change data).
    """
    use_utf8_output()
    try:
        with store.transaction(write=lock):
            status = args.fn(args)
    except ToolError as exc:
        print(exc, file=sys.stderr)
        return 1
    return status or 0
