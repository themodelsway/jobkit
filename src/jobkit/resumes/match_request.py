"""A match-score request (what pass 1 produces): validation, the fixed priority rules and the band choice.

Invalid input is rejected with every problem and its field path; nothing is ever repaired. Standard library
only, no database (evidence is resolved against a `ResumeFacts` snapshot).
"""
from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Final

from jobkit import common
from jobkit.resumes import match_engine as me
from jobkit.resumes.match_facts import EvidenceError, ResumeFacts, resolve

SCHEMA_VERSION: Final[int] = 1
RATED: Final[tuple[str, ...]] = ("full", "substantial", "partial")
FLAG_KINDS: Final[tuple[str, ...]] = ("level", "category", "priority")
FLAG_VALUES: Final[dict[str, tuple[str, ...]]] = {
    "level": ("full", "substantial", "partial", "profile_miss"), "category": me.CATEGORIES,
    "priority": me.PRIORITIES}
MUST_HAVE: Final[re.Pattern[str]] = re.compile(
    r"\b(must[- ]have|must|mandatory|non[- ]negotiable|essential|critical|absolutely required)\b", re.I)


@dataclass(frozen=True)
class Flag:
    """A real conflict between two readings of a requirement."""

    kind: str
    readings: tuple[str, str]


@dataclass
class Item:  # pylint: disable=too-many-instance-attributes  # mirrors the fields of a request requirement
    """One validated requirement."""

    id: str
    label: str
    quote: str
    section: str
    category: str
    priority: str
    importance: Decimal
    level: str
    reason: str
    confidence: float | None = None
    evidence: list[str] = field(default_factory=list)
    related: str = ""
    flag: Flag | None = None
    source: str = "agent"                      # who rated it: agent, code or (set later) fallback; never an app name
    contest: tuple[str, str] | None = None     # (level, reason) a reviewer gives for a code-rated item
    code_level: str | None = None              # the code pass's own level, kept when it was contested


@dataclass
class Request:
    """A validated request."""

    band: str
    band_reason: str
    band_alternatives: list[str]
    label: str
    items: list[Item]
    rules_applied: list[str] = field(default_factory=list)


def settle_priority(readings: tuple[str, str], quote: str) -> str | None:
    """The fixed priority rule for two readings, or None when the rules do not settle them.

    Preferred and required is required. Required and critical is critical only with explicit must-have wording.
    """
    pair = frozenset(readings)
    if pair == {"preferred", "required"}:
        return "required"
    if pair == {"required", "critical"}:
        return "critical" if MUST_HAVE.search(quote) else "required"
    return None


def apply_priority_rules(request: Request) -> None:
    """Settle priority flags that the fixed rules decide; the flag is dropped and the rule noted."""
    for item in request.items:
        if item.flag is None or item.flag.kind != "priority":
            continue
        decided = settle_priority(item.flag.readings, item.quote)
        if decided is not None:
            item.priority, item.flag = decided, None
            request.rules_applied.append(f"{item.id}: priority is {decided} by the fixed priority rule")


def parse_request(data: Any, facts: ResumeFacts, bands: Mapping[str, Any]) -> Request:
    """Validate pass 1 output and return it as a `Request`.

    Raises:
        ToolError: the request has problems (every one is listed with its field path); nothing is changed.
    """
    problems: list[str] = []
    if not isinstance(data, dict):
        raise common.ToolError("The request must be a JSON object.")
    head = _head(data, bands, problems)
    raw = data.get("requirements")
    if not isinstance(raw, list) or not raw:
        problems.append("requirements: there is nothing to score (the list is empty or missing)")
        raw = []
    seen: set[str] = set()
    items = [item for i, entry in enumerate(raw) if (item := _item(i, entry, seen, facts, problems))]
    if problems:
        raise common.ToolError("The request has problems, so nothing was scored:\n  " + "\n  ".join(problems))
    return Request(*head, items)


def _head(data: Mapping[str, Any], bands: Mapping[str, Any], problems: list[str]) -> tuple[str, str, list[str], str]:
    """(band, reason, alternatives, label) of a request, recording problems."""
    if data.get("schema_version") != SCHEMA_VERSION:
        problems.append(f"schema_version: must be {SCHEMA_VERSION}")
    band = data.get("band")
    if band not in bands:
        problems.append(f"band: {band!r} is not a band (bands: {', '.join(bands)})")
    alternatives = data.get("band_alternatives") or []
    bad = [a for a in alternatives if a not in me.BAND_ORDER] if isinstance(alternatives, list) else [alternatives]
    if bad:
        problems.append(f"band_alternatives: {bad!r} must be built-in bands ({', '.join(me.BAND_ORDER)})")
    reason = data.get("band_reason")
    if not isinstance(reason, str) or not reason.strip():
        problems.append("band_reason: give a one-sentence reason for the band")
    label = data.get("label")
    return (str(band), str(reason or ""), alternatives if not bad else [],
            label if isinstance(label, str) else "")


def _text(entry: Mapping[str, Any], key: str, where: str, problems: list[str], required: bool = True) -> str:
    """A string field, recording a problem when a required one is missing."""
    value = entry.get(key, "")
    if not isinstance(value, str) or (required and not value.strip()):
        problems.append(f"{where}.{key}: must be a non-empty string" if required else f"{where}.{key}: must be text")
        return ""
    return value


def _choice(entry: Mapping[str, Any], key: str, allowed: tuple[str, ...], where: str, problems: list[str]) -> str:
    """A field that must be one of `allowed`."""
    value = entry.get(key)
    if value not in allowed:
        problems.append(f"{where}.{key}: {value!r} is not one of {', '.join(allowed)}")
        return ""
    return str(value)


def _item(i: int, entry: Any, seen: set[str], facts: ResumeFacts, problems: list[str]) -> Item | None:
    """Validate one requirement; returns None when it has problems."""
    where = f"requirements[{i}]"
    if not isinstance(entry, dict):
        problems.append(f"{where}: must be an object")
        return None
    before = len(problems)
    rid = _text(entry, "id", where, problems)
    if rid in seen:
        problems.append(f"{where}.id: {rid!r} is used twice")
    seen.add(rid)
    where = f"{where} ({rid})" if rid else where
    category = _choice(entry, "category", me.CATEGORIES, where, problems)
    priority = _choice(entry, "priority", me.PRIORITIES, where, problems)
    level = _choice(entry, "level", me.LEVELS, where, problems)
    importance = _importance(entry, where, problems)
    confidence = _confidence(entry, where, problems)
    evidence = _evidence(entry, level, where, facts, problems)
    flag = _flag(entry.get("flag"), where, problems)
    item = Item(rid, _text(entry, "label", where, problems), _text(entry, "quote", where, problems),
                _text(entry, "section", where, problems, required=False), category, priority, importance, level,
                _text(entry, "reason", where, problems), confidence, evidence,
                _text(entry, "related", where, problems, required=False), flag,
                contest=_contest(entry.get("contest"), where, problems))
    return item if len(problems) == before else None


def _importance(entry: Mapping[str, Any], where: str, problems: list[str]) -> Decimal:
    """Optional importance: a finite number above zero (default 1)."""
    value = entry.get("importance", 1)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        problems.append(f"{where}.importance: {value!r} must be a finite number above 0")
        return Decimal(1)
    return Decimal(str(value))


def _confidence(entry: Mapping[str, Any], where: str, problems: list[str]) -> float | None:
    """Optional confidence from 0 to 1 (informational only)."""
    value = entry.get("confidence")
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
        problems.append(f"{where}.confidence: {value!r} must be a number from 0 to 1")
        return None
    return float(value)


def _evidence(entry: Mapping[str, Any], level: str, where: str, facts: ResumeFacts, problems: list[str]
              ) -> list[str]:
    """Evidence references: required for a credited level, not allowed for profile_miss or unknown."""
    refs = entry.get("evidence", [])
    if not isinstance(refs, list) or not all(isinstance(r, str) for r in refs):
        problems.append(f"{where}.evidence: must be a list of reference strings")
        return []
    if level in RATED and not refs:
        problems.append(f"{where}.evidence: a {level} requirement must cite at least one stored line")
    if level in ("profile_miss", "unknown") and refs:
        problems.append(f"{where}.evidence: a {level} requirement cannot cite lines (put it in 'related')")
    for j, ref in enumerate(refs):
        try:
            resolve(ref, facts)
        except EvidenceError as exc:
            problems.append(f"{where}.evidence[{j}]: {exc}")
    return list(refs)


def _contest(raw: Any, where: str, problems: list[str]) -> tuple[str, str] | None:
    """An optional contest of a code level: a valid level and a reason."""
    if raw is None:
        return None
    level = raw.get("level") if isinstance(raw, dict) else None
    reason = raw.get("reason") if isinstance(raw, dict) else None
    if level not in me.LEVELS or not isinstance(reason, str) or not reason.strip():
        problems.append(f"{where}.contest: needs a level ({', '.join(me.LEVELS)}) and a reason")
        return None
    return str(level), reason.strip()


def _flag(raw: Any, where: str, problems: list[str]) -> Flag | None:
    """An optional flag: a kind and two different readings valid for that kind."""
    if raw is None:
        return None
    kind = raw.get("kind") if isinstance(raw, dict) else None
    readings = raw.get("readings") if isinstance(raw, dict) else None
    if kind not in FLAG_KINDS or not isinstance(readings, list) or len(readings) != 2:
        problems.append(f"{where}.flag: needs kind ({', '.join(FLAG_KINDS)}) and exactly two readings")
        return None
    if readings[0] == readings[1] or any(r not in FLAG_VALUES[kind] for r in readings):
        problems.append(f"{where}.flag.readings: two different {kind} values from {', '.join(FLAG_VALUES[kind])}")
        return None
    return Flag(kind, (readings[0], readings[1]))


def choose_band(request: Request) -> tuple[str, str | None]:
    """(band, assumption): the lowest band when the posting could fit several (and the assumption in words)."""
    options = [request.band, *request.band_alternatives]
    built_in = [b for b in options if b in me.BAND_ORDER]
    if len(set(options)) < 2 or len(built_in) != len(options):
        return request.band, None
    lowest = min(built_in, key=me.BAND_ORDER.index)
    others = ", ".join(sorted(set(built_in) - {lowest}))
    return lowest, (f"The posting could fit the {others} level as well as {lowest}; I used {lowest}, "
                    "the lower one.")
