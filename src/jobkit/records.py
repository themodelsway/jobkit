"""The kinds of data jobkit stores, and for each how to read it from the old JSON files, write it to the
database, and export it back.

`jobkit migrate` imports every kind and then proves the import by comparing `export()` with what was read;
`jobkit export` and `jobkit status` use the same functions. Data is canonical JSON-shaped Python (dicts, lists,
strings, numbers), so two copies compare equal exactly when nothing was lost.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple

from jobkit.base import ToolError
from jobkit.interview import tables
from jobkit.resumes import tables as resume_tables
from jobkit.user import tables as user_tables

OLD_FOLDERS = ("profile", "prep", "resume-data")


class Kind(NamedTuple):
    """One kind of stored data."""

    name: str
    read: Callable[[Path], Any]
    write: Callable[[Any], None]
    export: Callable[[], Any]
    size: Callable[[Any], int]


def read_json(path: Path) -> Any:
    """Parse one old JSON file.

    Raises:
        ToolError: the file cannot be read or is not valid JSON (the message names it).
    """
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ToolError(f"Cannot read {path}: {exc}") from exc


def _file(relative: str) -> Callable[[Path], Any]:
    """A reader for one old file; None when the file does not exist."""
    def read(root: Path) -> Any:
        path = root / relative
        return read_json(path) if path.is_file() else None
    return read


def _folder(relative: str, skip: tuple[str, ...] = ("index.json",)) -> Callable[[Path], Any]:
    """A reader for a folder of JSON files: {file stem: content}, or None when there are none."""
    def read(root: Path) -> Any:
        folder = root / relative
        files = sorted(p for p in folder.glob("*.json") if p.name not in skip) if folder.is_dir() else []
        return {p.stem: read_json(p) for p in files} or None
    return read


# ---------------------------------------------------------------- writers and exporters

def _write_catalog(data: Any) -> None:
    tables.save_catalog(data)


def _write_progress(data: Any) -> None:
    tables.save_progress(data["cards"])


def _write_tracks(data: Any) -> None:
    for name, seed in data.items():
        tables.save_track(name, seed)


def _write_sessions(data: Any) -> None:
    for session in data.values():
        tables.save_session(session)


def _export_stories() -> Any:
    return tables.load_stories()


def _export_engagements() -> Any:
    return tables.load_engagements() if tables.has_engagements() else None


def _export_progress() -> Any:
    return {"cards": tables.load_progress()}


KINDS: tuple[Kind, ...] = (
    Kind("stories", _file("prep/stories.json"), tables.save_stories, _export_stories,
         lambda d: len(d["stories"])),
    Kind("engagements", _file("prep/engagements.json"), tables.save_engagements, _export_engagements,
         lambda d: len(d["engagements"])),
    Kind("themes", _file("prep/themes.json"), lambda d: tables.save_themes(d["themes"]),
         lambda: {"themes": tables.load_themes()}, lambda d: len(d["themes"])),
    Kind("arch-catalog", _file("prep/arch/catalog.json"), _write_catalog, tables.load_catalog,
         lambda d: len(d["cards"])),
    Kind("arch-progress", _file("prep/arch/progress.json"), _write_progress, _export_progress,
         lambda d: len(d["cards"])),
    Kind("arch-tracks", _folder("prep/arch/tracks"), _write_tracks,
         lambda: {n: tables.load_track(n) for n in tables.track_names()}, len),
    Kind("lead-questions", _file("prep/leadership/questions.json"), lambda d: tables.save_questions(d["questions"]),
         lambda: {"questions": tables.load_questions()}, lambda d: len(d["questions"])),
    Kind("lead-progress", _file("prep/leadership/progress.json"),
         lambda d: tables.save_lead_progress(d["questions"]),
         lambda: {"questions": tables.load_lead_progress()}, lambda d: len(d["questions"])),
    Kind("lead-scope", _file("prep/leadership/profile.json"), lambda d: tables.save_company_facts(d["companies"]),
         lambda: {"companies": tables.load_company_facts()}, lambda d: len(d["companies"])),
    Kind("sessions", _folder("prep/sessions"), _write_sessions,
         lambda: {s["id"]: s for s in tables.all_sessions()}, len),
    Kind("settings", _file("profile/profile.json"), user_tables.save_settings, user_tables.load_settings, len),
    Kind("employers", _file("profile/companies.json"), user_tables.save_employers, user_tables.load_employers, len),
    Kind("open-items", _file("profile/open_items.json"), user_tables.save_open_items,
         user_tables.load_open_items, len),
    Kind("resume-companies", _folder("resume-data/json/companies", ()), resume_tables.save_companies,
         resume_tables.load_companies, len),
    Kind("resume-skills", _file("resume-data/json/skills.json"), resume_tables.save_skills,
         resume_tables.load_skills, lambda d: sum(len(v) for v in d["groups"].values())),
    Kind("resume-profile", _file("resume-data/json/profile.json"), resume_tables.save_profile,
         resume_tables.load_profile, lambda d: sum(len(v) for v in d.values())),
    Kind("resume-index", _file("resume-data/json/index.json"), resume_tables.save_index,
         resume_tables.load_index, lambda d: len(d.get("companies", []))),
    Kind("resume-ledger", _file("resume-data/json/ledger.json"), resume_tables.save_ledger,
         resume_tables.load_ledger, len),
    Kind("resume-unparsed", _file("resume-data/json/_unparsed.json"), resume_tables.save_unparsed,
         resume_tables.load_unparsed, len),
    Kind("curated", _file("resume-data/curated.json"), lambda d: resume_tables.save_curation("curated", d),
         lambda: resume_tables.load_curation("curated"), lambda d: sum(len(v) for v in d.values())),
    Kind("curation-themes", _file("resume-data/themes.json"), lambda d: resume_tables.save_curation("themes", d),
         lambda: resume_tables.load_curation("themes"), lambda d: sum(len(v) for v in d.values())),
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


def checksum(data: Any) -> str:
    """SHA-256 of the canonical JSON of `data` (sorted keys, no spaces)."""
    text = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def count_of(entry: Kind, data: Any) -> int:
    """How many records `data` holds for this kind (0 when blank)."""
    return 0 if blank(data) else entry.size(data)


def same(left: Any, right: Any) -> bool:
    """True when two copies of a kind hold the same data (two blanks are the same)."""
    if blank(left) and blank(right):
        return True
    return checksum(left) == checksum(right)


def counts() -> dict[str, int]:
    """Records per kind in the database (for `jobkit status`)."""
    return {entry.name: count_of(entry, entry.export()) for entry in KINDS}
