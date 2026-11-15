"""The pieces every module needs and that depend on nothing else: the error type, the home folder, the clock.

Import these through `common` (`common.ToolError`, `common.home()`); `store` imports this module directly so
that `common` can use `store` without a cycle.
"""
from __future__ import annotations

import os
import re
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path, PurePath
from typing import Final

HOME_ENV: Final[str] = "JOBKIT_HOME"
TROUBLESHOOT_HINT: Final[str] = "For help, read setup/troubleshoot.md in the plugin folder."


class ToolError(Exception):
    """A problem the user can fix (bad argument, missing data); `run` prints it and returns status 1.

    A subclass sets `troubleshoot` when its message alone does not say what to fix; `run` then adds
    TROUBLESHOOT_HINT on the next line.
    """

    troubleshoot: bool = False


def _home_forms(user_home: PurePath, windows: bool) -> list[str]:
    """Patterns for one home folder: either slash, and on Windows also the Git Bash form (`/c/...` for `C:\\...`)."""
    text = str(user_home)
    parts = [re.escape(p) for p in re.split(r"[\\/]+", text) if p]
    forms = [(r"[\\/]" if text[:1] in "\\/" else "") + r"[\\/]+".join(parts)]
    if windows and re.fullmatch(r"[A-Za-z]:", parts[0] if parts else ""):
        forms.append("/" + parts[0][0] + "/" + "/".join(parts[1:]))
    return forms


def _home_pattern(homes: Sequence[PurePath], windows: bool) -> re.Pattern[str]:
    """The user's home folders as they may appear in text (on Windows in any letter case). A match must start and end
    where a folder name does, so a home `/srv/hellouser1` matches neither in `/srv/hellouser10` nor in
    `/x/srv/hellouser1`; longer forms are tried first, so a linked `/people/NAME` cannot match inside `/var/people/NAME`."""
    forms = sorted({f for h in homes for f in _home_forms(h, windows)}, key=len, reverse=True)
    return re.compile(r"(?<![\w.-])(?:" + "|".join(forms) + r")(?![\w.-])", re.IGNORECASE if windows else 0)


def _known_homes() -> list[PurePath]:
    """The home folder as Python reports it and, when it is reached through a link, where it really is."""
    home_dir = Path.home()
    try:
        real = home_dir.resolve()
    except OSError:
        real = home_dir
    return [home_dir] if real == home_dir else [home_dir, real]


WINDOWS_HOME: Final[str] = "%USERPROFILE%"


def _is_windows(windows: bool | None) -> bool:
    """`windows` when given (tests), else whether this is Windows."""
    return os.name == "nt" if windows is None else windows


def hide_home(text: str, user_home: PurePath | None = None, windows: bool | None = None) -> str:
    """The text with the user's home folder written as `~` (on Windows `%USERPROFILE%`), so that no output shows
    the user's folder name."""
    homes = _known_homes() if user_home is None else [user_home]
    shown = WINDOWS_HOME if _is_windows(windows) else "~"
    return _home_pattern(homes, _is_windows(windows)).sub(lambda _: shown, text)


def user_path(text: str, user_home: Path | None = None, windows: bool | None = None) -> Path:
    """A path the user or the agent gave, where a leading `~` (and on Windows `%USERPROFILE%`, in any letter case)
    means the home folder, the way output shows it. Nothing else in the path is expanded."""
    if _is_windows(windows) and text[:len(WINDOWS_HOME)].upper() == WINDOWS_HOME:
        return (Path.home() if user_home is None else user_home) / text[len(WINDOWS_HOME):].lstrip("\\/")
    return Path(text).expanduser()


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
