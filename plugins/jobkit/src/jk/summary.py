"""An overview in one call, for `jobkit status --summary`: setup stage, folders, open sessions, retests, research.

Read by the skills to greet a returning user ("continue your last session?") and when something goes wrong.
It changes nothing. The folder lines report where this running copy keeps its data, its launchers and its
Python environment; past the setup stage it reads the same tables as `sessions list`, `readiness --due` and
`target show`.
"""
from __future__ import annotations

import platform
import sys
from datetime import date
from importlib.metadata import version
from pathlib import Path

from jk import common, setup_state
from jk.interview import readiness, sessions_tables, target_tables, targets
from jk.user import profile


def _folder_lines() -> list[str]:
    """Where this running copy keeps its data, its launchers and its Python environment, the home folder hidden."""
    def shown(path: Path) -> str:
        return common.hide_home(str(path))
    commands = Path(sys.argv[0]).absolute().parent      # the launcher that started this command, links not followed
    return [f"JOBKIT_HOME: {shown(common.home())} (the data folder)",
            f"JOBKIT_COMMANDS_DIR: {shown(commands)} (uv's launchers for the jobkit commands)",
            f"JOBKIT_PROGRAM_DIR: {shown(Path(sys.prefix))} (uv's environment that runs them; "
            f"jobkit {version('jobkit')}, Python {platform.python_version()})"]


def _session_lines() -> list[str]:
    """How many sessions are open, and the most recently used one."""
    open_rows = [r for r in sessions_tables.session_rows() if r["status"] == "open"]
    lines = [f"open sessions: {len(open_rows)}"]
    if open_rows:
        r = open_rows[0]                          # rows come newest update first
        lines.append(f"latest open session: {r['id']} | {r['title']} | {r['mode']} | "
                     f"{r['logged']}/{r['total']} items | last {r['updated'][:16]}")
    return lines


def _retest_line() -> str:
    """How many practised items are due for a retest."""
    days = profile.reassess_days()
    return f"due for a retest: {len(readiness.due_items(readiness.attempts(), days))} (older than {days} days)"


def _research_line(today: date) -> str:
    """Each researched company with its state (fresh, stale or none found)."""
    window = targets.research_days()
    found = [f"{c['name']} {targets.state(c, window, today)}" for c in target_tables.load_companies()]
    return "company research: " + (", ".join(found) if found else "none")


def summary(today: date) -> tuple[list[str], str | None]:
    """(lines for standard output, error line or None): the setup stage and the folders, always; past `no-resumes`
    also sessions, retests and research."""
    word, problem = setup_state.report()
    lines = [f"setup: {word}", *_folder_lines()]
    if problem or word in ("no-database", "no-resumes"):
        return lines, problem
    lines += [*_session_lines(), _retest_line(), _research_line(today)]
    company = profile.target_company()
    if company:
        lines.append(f"default target company: {company}")
    return lines, None
