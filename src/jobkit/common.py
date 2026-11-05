"""Helpers shared by every tool: repo root, error type, atomic JSON files, the prep lock, small text utilities.

Standard library only. Import it as `from jobkit import common`.
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Final
from collections.abc import Iterator

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
LOCK_FILE: Final[Path] = REPO_ROOT / "prep" / ".lock"
SLUG_MAX: Final[int] = 60


class ToolError(Exception):
    """A problem the user can fix (bad argument, missing data); `run` prints it and returns status 1."""


def now() -> str:
    """Current local time as an ISO string to the second (the one timestamp format all tools write)."""
    return datetime.now().isoformat(timespec="seconds")


def slug(text: str) -> str:
    """Lowercase id made of letters, digits and dashes, at most SLUG_MAX characters."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:SLUG_MAX]


def read_text_arg(arg: str) -> str:
    """Contents of the file named by `arg`, or standard input when `arg` is "-"."""
    return sys.stdin.read() if arg == "-" else Path(arg).read_text(encoding="utf-8")


def load_json(path: Path, default: Any) -> Any:
    """Parse a JSON file; return `default` when it does not exist.

    Raises:
        ToolError: the file is not valid JSON (the message names the .bak copy when one exists).
    """
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        bak = path.with_name(path.name + ".bak")
        hint = f"Previous copy: {bak} (copy it back over the file)." if bak.exists() else "No backup exists."
        raise ToolError(f"{path} is not valid JSON ({exc}). {hint}") from exc


def save_json(path: Path, data: Any, *, backup: bool = True) -> None:
    """Atomic write: temp file, keep the previous version as .bak (unless backup is False), then replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    if backup and path.exists():
        shutil.copy2(path, path.with_name(path.name + ".bak"))
    os.replace(tmp, path)


@contextlib.contextmanager
def locked(lock_file: Path | None = None) -> Iterator[None]:
    """One exclusive lock for every prep tool, so two windows or parallel calls cannot overwrite each other."""
    target = lock_file or LOCK_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def make_parser(doc: str | None) -> argparse.ArgumentParser:
    """Argument parser whose help shows the module docstring (usage examples) as written."""
    return argparse.ArgumentParser(description=doc, formatter_class=argparse.RawDescriptionHelpFormatter)


def run(args: argparse.Namespace, *, lock: bool = False) -> int:
    """Call the chosen subcommand (`args.fn`) and return the process exit status.

    A handler may return None (success) or an int status. A ToolError is printed to standard error as
    its message and becomes status 1. With `lock`, the handler runs under the shared prep lock.
    """
    try:
        with locked() if lock else contextlib.nullcontext():
            status = args.fn(args)
    except ToolError as exc:
        print(exc, file=sys.stderr)
        return 1
    return status or 0
