"""Compare what the parser read from a resume with what was read from its pages as images.

  READING_SCHEMA           the JSON a visual reading must return (printed by `process-resumes visual schema`)
  compare(parsed, reading) -> list[Difference]

The visual reading decides structure (which employer, which dates, which section); wording is judged against the
text layer, so a difference in wording is reported with both versions and never merged. Library module with no file
access.
"""
from __future__ import annotations

import json
import re
from typing import Any, Final, NamedTuple

from jk import common
from jk.resumes import parse_resume as pr

SIMILAR_BULLET: Final[float] = 0.85          # two bullets this alike are the same claim
SIMILAR_ITEM: Final[float] = 0.8             # two education, certification or skill lines this alike are the same
READING_SCHEMA: Final[str] = json.dumps({
    "employers": [{"name": "Employer name as printed", "title": "Job title as printed",
                   "start": "YYYY-MM, or YYYY when only a year is printed", "end": "YYYY-MM, YYYY, or null when current",
                   "bullets": ["One string per bullet, exactly as printed, without the bullet mark"]}],
    "skills": ["One skill per string, as printed"],
    "certifications": ["One certification per string, as printed"],
    "education": ["One degree or school per string, as printed"],
    "summary": "The opening summary paragraph as printed, or an empty string",
}, indent=2)


class Difference(NamedTuple):
    """One place where the two readings disagree: the section, what differs, and each side's value."""

    section: str
    kind: str          # "missing" (only the visual reading has it), "extra" (only the parser has it) or "different"
    parsed: str
    visual: str


def _key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def read_reading(raw: str) -> dict[str, Any]:
    """The visual reading from JSON text, checked against the schema; raises ToolError for a mistake."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as error:
        raise common.ToolError(f"The reading is not valid JSON ({error}). Run `process-resumes visual schema` "
                               "for the shape.") from error
    if not isinstance(data, dict) or not isinstance(data.get("employers"), list):
        raise common.ToolError("The reading must be a JSON object with an 'employers' list "
                               "(see `process-resumes visual schema`).")
    for field in ("skills", "certifications", "education"):
        if not all(isinstance(item, str) for item in data.get(field, [])):
            raise common.ToolError(f"'{field}' must be a list of strings.")
    for employer in data["employers"]:
        if not isinstance(employer, dict) or not isinstance(employer.get("name"), str) \
                or not all(isinstance(b, str) for b in employer.get("bullets", [])):
            raise common.ToolError("Each employer needs a 'name' and a list of string 'bullets'.")
    return data


def _same_employer(name: str, entry: pr.WorkEntry) -> bool:
    registered = pr.COMPANIES.get(entry["company_id"], (entry["company_id"], ""))[0]
    return _key(name) in (_key(registered), _key(entry["company_id"])) or _key(registered).startswith(_key(name))


def _match_role(visual: dict[str, Any], parsed: list[pr.WorkEntry], used: set[int]) -> int | None:
    """Index of the parsed role that is this visual one: the same employer and start date, else the same employer."""
    same = [i for i, e in enumerate(parsed) if i not in used and _same_employer(visual["name"], e)]
    return next((i for i in same if parsed[i]["start"] == visual.get("start")), same[0] if same else None)


def _bullet_differences(label: str, parsed: list[str], visual: list[str]) -> list[Difference]:
    """Bullets of one role: each visual bullet is matched to the most alike parsed one."""
    out: list[Difference] = []
    left = list(parsed)
    for text in visual:
        best = max(left, key=lambda p: pr.similar(p, text), default=None)
        score = pr.similar(best, text) if best is not None else 0.0
        if best is None or score < SIMILAR_BULLET:
            out.append(Difference(label, "missing", "", text))
            continue
        left.remove(best)
        if _key(best) != _key(text):
            out.append(Difference(label, "different", best, text))
    return out + [Difference(label, "extra", text, "") for text in left]


def _role_differences(visual: dict[str, Any], entry: pr.WorkEntry) -> list[Difference]:
    label = f"{visual['name']} {visual.get('start') or '?'}"
    out = [Difference(f"{label} {field}", "different", str(entry[field] or ""), str(visual.get(field) or ""))
           for field in ("title", "start", "end") if _key(str(entry[field] or "")) != _key(str(visual.get(field) or ""))]
    return out + _bullet_differences(f"{label} bullets", entry["bullets"], visual.get("bullets", []))


def _employer_differences(parsed: list[pr.WorkEntry], visual: list[dict[str, Any]]) -> list[Difference]:
    out: list[Difference] = []
    used: set[int] = set()
    for role in visual:
        index = _match_role(role, parsed, used)
        if index is None:
            out.append(Difference("employers", "missing", "", f"{role['name']} {role.get('start') or ''}".strip()))
            continue
        used.add(index)
        out += _role_differences(role, parsed[index])
    return out + [Difference("employers", "extra", f"{pr.COMPANIES.get(e['company_id'], (e['company_id'],))[0]} "
                             f"{e['start'] or ''}".strip(), "") for i, e in enumerate(parsed) if i not in used]


def _item_differences(section: str, parsed: list[str], visual: list[str]) -> list[Difference]:
    """Lists of short items (skills, education, certifications): matched by likeness, order ignored."""
    out: list[Difference] = []
    left = list(parsed)
    for text in visual:
        best = max(left, key=lambda p: pr.similar(p, text), default=None)
        if best is None or pr.similar(best, text) < SIMILAR_ITEM:
            out.append(Difference(section, "missing", "", text))
        else:
            left.remove(best)
    return out + [Difference(section, "extra", text, "") for text in left]


def compare(parsed: pr.Resume, reading: dict[str, Any]) -> list[Difference]:
    """Every difference between a parsed resume and a visual reading of the same file."""
    found = _employer_differences(parsed["work"], reading["employers"])
    skills = [item["name"] for group in parsed["skills"].values() for item in group]
    found += _item_differences("skills", skills, reading.get("skills", []))
    for section in ("certifications", "education"):
        found += _item_differences(section, parsed[section], reading.get(section, []))
    visual_summary = str(reading.get("summary") or "")
    if visual_summary and pr.similar(parsed["summary"], visual_summary) < SIMILAR_BULLET:
        found.append(Difference("summary", "different", parsed["summary"], visual_summary))
    return found


def format_report(name: str, differences: list[Difference]) -> str:
    """The differences as plain lines, grouped by section, for the person and the agent to walk through."""
    if not differences:
        return f"{name}: the visual reading and the parser agree."
    lines = [f"{name}: {len(differences)} difference(s)"]
    for item in differences:
        lines.append(f"  [{item.kind}] {item.section}")
        lines += [f"      parser: {item.parsed}" if item.parsed else "      parser: (nothing)",
                  f"      visual: {item.visual}" if item.visual else "      visual: (nothing)"]
    return "\n".join(lines)
