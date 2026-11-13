"""The pieces every module needs and that depend on nothing else: the error type, the home folder, the clock.

Import these through `common` (`common.ToolError`, `common.home()`); `store` imports this module directly so
that `common` can use `store` without a cycle.
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Final

HOME_ENV: Final[str] = "JOBKIT_HOME"


class ToolError(Exception):
    """A problem the user can fix (bad argument, missing data); `run` prints it and returns status 1."""


def home() -> Path:
    """The folder that holds all user data: `JOBKIT_HOME`, else `~/.jobkit` (read at call time)."""
    return Path(os.environ.get(HOME_ENV) or Path.home() / ".jobkit")


def data_dir() -> Path:
    """Folder of the database file."""
    return home() / "data"


def backup_dir() -> Path:
    """Folder for database and old-JSON backups."""
    return home() / "backup"


def output_dir() -> Path:
    """Folder for generated resumes and extracted text."""
    return home() / "output"


def header_file() -> Path:
    """The name and contact lines for generated resumes (a file the user writes)."""
    return home() / "profile" / "header.md"


def now() -> str:
    """Current local time as an ISO string to the second (the one timestamp format all tools write)."""
    return datetime.now().isoformat(timespec="seconds")
