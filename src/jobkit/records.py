"""The kinds of data jobkit stores, and for each how to write it to the database, export it back, and count it.

`jobkit export` and `jobkit status` use these functions. Data is canonical JSON-shaped Python (dicts, lists,
strings, numbers).
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any, NamedTuple

from jobkit.base import ToolError
from jobkit.interview import tables
from jobkit.resumes import match_tables
from jobkit.resumes import tables as resume_tables
from jobkit.user import tables as user_tables


class Kind(NamedTuple):
    """One kind of stored data."""

    name: str
    export: Callable[[], Any]
    size: Callable[[Any], int]


# ---------------------------------------------------------------- exporters

def _export_stories() -> Any:
    return tables.load_stories()


def _export_engagements() -> Any:
    return tables.load_engagements() if tables.has_engagements() else None


def _export_progress() -> Any:
    return {"cards": tables.load_progress()}


KINDS: tuple[Kind, ...] = (
    Kind("stories", _export_stories, lambda d: len(d["stories"])),
    Kind("engagements", _export_engagements, lambda d: len(d["engagements"])),
    Kind("themes", lambda: {"themes": tables.load_themes()}, lambda d: len(d["themes"])),
    Kind("arch-catalog", tables.load_catalog, lambda d: len(d["cards"])),
    Kind("arch-progress", _export_progress, lambda d: len(d["cards"])),
    Kind("arch-tracks", lambda: {n: tables.load_track(n) for n in tables.track_names()}, len),
    Kind("lead-questions", lambda: {"questions": tables.load_questions()}, lambda d: len(d["questions"])),
    Kind("lead-progress", lambda: {"questions": tables.load_lead_progress()}, lambda d: len(d["questions"])),
    Kind("lead-scope", lambda: {"companies": tables.load_company_facts()}, lambda d: len(d["companies"])),
    Kind("sessions", lambda: {s["id"]: s for s in tables.all_sessions()}, len),
    Kind("settings", user_tables.load_settings, len),
    Kind("employers", user_tables.load_employers, len),
    Kind("open-items", user_tables.load_open_items, len),
    Kind("resume-companies", resume_tables.load_companies, len),
    Kind("resume-skills", resume_tables.load_skills, lambda d: sum(len(v) for v in d["groups"].values())),
    Kind("resume-profile", resume_tables.load_profile, lambda d: sum(len(v) for v in d.values())),
    Kind("resume-index", resume_tables.load_index, lambda d: len(d.get("companies", []))),
    Kind("resume-ledger", resume_tables.load_ledger, len),
    Kind("resume-unparsed", resume_tables.load_unparsed, len),
    Kind("curated", lambda: resume_tables.load_curation("curated"), lambda d: sum(len(v) for v in d.values())),
    Kind("curation-themes", lambda: resume_tables.load_curation("themes"), lambda d: sum(len(v) for v in d.values())),
    Kind("match-results", match_tables.load_results, len),
)


def kind(name: str) -> Kind:
    """The kind with this name.

    Raises:
        ToolError: there is no such kind (the message lists the names).
    """
    for entry in KINDS:
        if entry.name == name:
            return entry
    raise ToolError(f"Unknown kind {name!r}. Kinds: {', '.join(k.name for k in KINDS)}.")


# ---------------------------------------------------------------- comparing

def blank(data: Any, top: bool = True) -> bool:
    """True for nothing at all: None (at the top), or lists and dicts holding only empty lists and dicts.

    A record whose fields are all None is data, not nothing: it is kept and compared.
    """
    if data is None:
        return top
    if isinstance(data, dict):
        return all(blank(v, False) for v in data.values())
    return isinstance(data, list) and not data


def count_of(entry: Kind, data: Any) -> int:
    """How many records `data` holds for this kind (0 when blank)."""
    return 0 if blank(data) else entry.size(data)


def counts() -> dict[str, int]:
    """Records per kind in the database (for `jobkit status`)."""
    return {entry.name: count_of(entry, entry.export()) for entry in KINDS}
