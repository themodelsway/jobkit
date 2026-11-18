"""An overview in one call, for `jobkit status --summary`: setup stage, folders, open sessions, retests, research
and the suggested next step.

Read by the skills to start a returning user's next step (the `suggested next` line) and when something goes wrong.
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


def _open_sessions() -> list[sessions_tables.Record]:
    """The open sessions, most recently used first."""
    return [r for r in sessions_tables.session_rows() if r["status"] == "open"]


def _session_lines(open_rows: list[sessions_tables.Record]) -> list[str]:
    """How many sessions are open, and the most recently used one."""
    lines = [f"open sessions: {len(open_rows)}"]
    if open_rows:
        r = open_rows[0]                          # rows come newest update first
        lines.append(f"latest open session: {r['id']} | {r['title']} | {r['mode']} | "
                     f"{r['logged']}/{r['total']} items | last {r['updated'][:16]}")
    return lines


def _due_count() -> int:
    """How many practised items are due for a retest."""
    return len(readiness.due_items(readiness.attempts(), profile.reassess_days()))


def _research_line(today: date) -> str:
    """Each researched company with its state (fresh, stale or none found)."""
    window = targets.research_days()
    found = [f"{c['name']} {targets.state(c, window, today)}" for c in target_tables.load_companies()]
    return "company research: " + (", ".join(found) if found else "none")


def _fresh_default_company(today: date) -> str | None:
    """The saved default company when its research is fresh, else None."""
    name = profile.target_company()
    found = [c for c in target_tables.load_companies() if name and c["name"].lower() == name.lower()]
    return name if found and targets.state(found[0], targets.research_days(), today) == "fresh" else None


def suggested_next(open_rows: list[sessions_tables.Record], due: int, today: date) -> str:
    """The one next step the stored data points to, first that applies: `continue-session ID` (the most recently
    used open session), `retest N` (items due for a retest), `prepare-for COMPANY` (the default company, freshly
    researched) or `none`. The skills start it without asking what to do (see setup/welcome.md)."""
    if open_rows:
        return f"continue-session {open_rows[0]['id']}"
    if due:
        return f"retest {due}"
    company = _fresh_default_company(today)
    return f"prepare-for {company}" if company else "none"


def summary(today: date) -> tuple[list[str], str | None]:
    """(lines for standard output, error line or None): the setup stage and the folders, always; past `no-resumes`
    also sessions, retests, research and the suggested next step (`none` until setup is `ready`)."""
    word, problem = setup_state.report()
    lines = [f"setup: {word}", *_folder_lines()]
    if problem or word in ("no-database", "no-resumes"):
        return lines, problem
    open_rows, due = _open_sessions(), _due_count()
    lines += [*_session_lines(open_rows), f"due for a retest: {due} (older than {profile.reassess_days()} days)",
              _research_line(today)]
    company = profile.target_company()
    if company:
        lines.append(f"default target company: {company}")
    lines.append(f"suggested next: {suggested_next(open_rows, due, today) if word == 'ready' else 'none'}")
    return lines, None
