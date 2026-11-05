"""Typed access to the generated resume data in resume-data/json/ (and the hand-curated files next to it).

Library module: paths, record types and loaders shared by process_resumes.py, query_resume.py and
build_resume.py. Standard library only.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Final, NotRequired, TypedDict

from jobkit import common

DATA_DIR: Final[Path] = common.REPO_ROOT / "resume-data" / "json"
CURATED_FILE: Final[Path] = common.REPO_ROOT / "resume-data" / "curated.json"
THEMES_FILE: Final[Path] = common.REPO_ROOT / "resume-data" / "themes.json"
TEXT_DIR: Final[Path] = common.REPO_ROOT / "output"
MISSING_DATA: Final[str] = "No resume data yet: run `src/resumes/process_resumes.py` first."


class Bullet(TypedDict):
    """One experience bullet, deduplicated across resumes."""

    id: str
    text: str
    role_start: str | None
    skills: list[str]
    skills_manual: NotRequired[list[str]]
    themes: list[str]
    metrics: list[str]
    sources: list[str]
    variants: NotRequired[list[str]]
    needs_review: NotRequired[bool]
    ignored: NotRequired[bool]


class Role(TypedDict):
    """One period at a company (start/end as YYYY-MM, end None = current)."""

    start: str | None
    end: str | None
    titles: list[str]
    subtitles: list[str]
    clients: list[str]
    sources: list[str]


class Company(TypedDict):
    """One employer with its roles and bullets."""

    id: str
    name: str
    aliases: list[str]
    roles: list[Role]
    bullets: list[Bullet]


class SkillEntry(TypedDict):
    """A skill with its alternative spellings and the resumes that list it."""

    name: str
    aliases: list[str]
    sources: list[str]


class Skills(TypedDict):
    """skills.json."""

    groups: dict[str, list[SkillEntry]]
    tag_only: NotRequired[list[str]]


class Summary(TypedDict):
    """One opening summary paragraph."""

    id: str
    text: str
    angles: list[str]
    sources: list[str]


class ResumeProfile(TypedDict):
    """profile.json (contains no contact details)."""

    summaries: list[Summary]
    headlines: NotRequired[list[str]]
    profile_points: list[str]
    education: list[str]
    certifications: list[Any]
    projects: list[str]


class ResumeData(TypedDict):
    """Everything the merge step works on."""

    companies: dict[str, Company]
    skills: Skills
    profile: ResumeProfile


def empty_profile() -> ResumeProfile:
    """A profile with every list present and empty."""
    return {"summaries": [], "profile_points": [], "education": [], "certifications": [], "projects": []}


def load_companies(data_dir: Path | None = None) -> dict[str, Company]:
    """{company id: company} from companies/*.json."""
    folder = (data_dir or DATA_DIR) / "companies"
    return {p.stem: common.load_json(p, None) for p in sorted(folder.glob("*.json"))}


def load_skills(data_dir: Path | None = None) -> Skills:
    """The skills vocabulary."""
    return common.load_json((data_dir or DATA_DIR) / "skills.json", {"groups": {}})


def load_profile(data_dir: Path | None = None) -> ResumeProfile:
    """Summaries, headlines, certifications and education."""
    return common.load_json((data_dir or DATA_DIR) / "profile.json", empty_profile())


def load_ledger(data_dir: Path | None = None) -> dict[str, dict[str, Any]]:
    """Which resume files were processed, with their size/mtime/hash."""
    return common.load_json((data_dir or DATA_DIR) / "ledger.json", {})


def load_curated() -> dict[str, Any]:
    """resume-data/curated.json (hand curation that survives rebuilds), or {}."""
    return common.load_json(CURATED_FILE, {})


def orphan_curation(companies: Mapping[str, Company], profile: ResumeProfile, themes: Mapping[str, Any]) -> list[str]:
    """Ids in themes.json (themes, ignore, summary_angles) that match no current bullet or summary.
    A bullet id is a hash of its text, so editing a resume can leave hand curation pointing at nothing."""
    bullets = {b["id"] for c in companies.values() for b in c["bullets"]}
    summaries = {s["id"] for s in profile.get("summaries", [])}
    orphans = [f"theme {i}" for i in themes.get("themes", {}) if i not in bullets]
    orphans += [f"ignore {i}" for i in themes.get("ignore", []) if i not in bullets]
    orphans += [f"summary angle {i}" for i in themes.get("summary_angles", {}) if i not in summaries]
    return sorted(orphans)


def newest_start(company: Company) -> str:
    """Start date of the company's most recent role ('' when unknown)."""
    return max((role["start"] or "") for role in company["roles"])


def newest_first(companies: Iterable[Company]) -> list[Company]:
    """Companies ordered by their most recent role, newest first."""
    return sorted(companies, key=newest_start, reverse=True)
