"""Drill tracks: the technology a user is preparing for (AWS, Acme Data, GCP, ...).

A track is a seed of topics (services, decision pairs, scenarios) plus the documentation hosts that
count as a source for facts. AWS is bundled as the worked example (`jobkit.interview.aws.arch_seed`).
Any other track is a seed stored in the database, added with `arch track add`;
no code is needed. A seed holds topic names only, never facts: facts are researched and recorded
with a source URL by `arch refresh`.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Final, NotRequired, TypedDict
from urllib.parse import urlparse

from jobkit.interview import tables
from jobkit.common import ToolError
from jobkit.interview.aws import arch_seed

BUILTIN: Final[str] = "aws"
NAME_PATTERN: Final[re.Pattern[str]] = re.compile(r"[a-z][a-z0-9-]{1,30}")
HOST_PATTERN: Final[re.Pattern[str]] = re.compile(r"[a-z0-9]([a-z0-9.-]*[a-z0-9])?\.[a-z]{2,}")


class ServiceSeed(TypedDict):
    """One service (or product, or feature area) card."""

    area: str
    name: str
    tier: int
    aliases: NotRequired[list[str]]


class PairSeed(TypedDict):
    """A "which one and why" comparison."""

    topic: str
    name: str
    members: list[str]


class TrackSeed(TypedDict):
    """The seed for one track."""

    name: str
    label: str
    source_hosts: list[str]
    services: list[ServiceSeed]
    pairs: list[PairSeed]
    scenarios: list[str]
    dimensions: NotRequired[list[str]]


def prefix(track: str) -> str:
    """Card-id prefix: none for the bundled AWS track (keeps existing ids), `<track>-` for the others."""
    return "" if track == BUILTIN else track + "-"


def builtin_seed() -> TrackSeed:
    """The bundled AWS seed as a track."""
    return {
        "name": BUILTIN, "label": "AWS", "source_hosts": list(arch_seed.SOURCE_HOSTS),
        "services": [{"area": s.area, "name": s.name, "tier": s.tier, "aliases": list(s.aliases)}
                     for s in arch_seed.SERVICES],
        "pairs": [{"topic": p.topic, "name": p.name, "members": list(p.members)} for p in arch_seed.PAIRS],
        "scenarios": list(arch_seed.SCENARIOS), "dimensions": list(arch_seed.DIMENSIONS),
    }


def _text_list(value: object, what: str) -> list[str]:
    if not isinstance(value, list) or not value or not all(isinstance(v, str) and v.strip() for v in value):
        raise ToolError(f"{what} must be a non-empty list of non-empty strings")
    return [v.strip() for v in value]


def _check_service(row: object, index: int) -> ServiceSeed:
    if not isinstance(row, dict) or not isinstance(row.get("name"), str) or not isinstance(row.get("area"), str):
        raise ToolError(f"services[{index}] needs a text 'area' and 'name'")
    if row.get("tier", 2) not in (2, 3):
        raise ToolError(f"services[{index}].tier must be 2 (core) or 3 (optional); tier 1 comes from your resumes")
    aliases = row.get("aliases") or []
    if not isinstance(aliases, list) or not all(isinstance(a, str) for a in aliases):
        raise ToolError(f"services[{index}].aliases must be a list of strings")
    return {"area": row["area"].strip(), "name": row["name"].strip(), "tier": row.get("tier", 2), "aliases": aliases}


def _check_pair(row: object, index: int) -> PairSeed:
    if not isinstance(row, dict) or not isinstance(row.get("name"), str) or not isinstance(row.get("topic"), str):
        raise ToolError(f"pairs[{index}] needs a text 'topic' and 'name'")
    return {"topic": row["topic"].strip(), "name": row["name"].strip(),
            "members": _text_list(row.get("members"), f"pairs[{index}].members")}


def _check_hosts(value: object) -> list[str]:
    hosts = [h.lower() for h in _text_list(value, "source_hosts")]
    for host in hosts:
        if not HOST_PATTERN.fullmatch(host):
            raise ToolError(f"source_hosts entry {host!r} is not a bare host name such as docs.example.com")
    return hosts


def validate_seed(raw: object, name: str) -> TrackSeed:
    """A clean TrackSeed from user-supplied JSON; raises ToolError naming the first problem."""
    if not NAME_PATTERN.fullmatch(name) or name == BUILTIN:
        raise ToolError(f"Track name {name!r} must be 2-31 lower-case letters, digits or '-', and not '{BUILTIN}'")
    if not isinstance(raw, dict):
        raise ToolError("The seed must be a JSON object")
    services = raw.get("services") or []
    if not isinstance(services, list) or not services:
        raise ToolError("The seed needs a non-empty 'services' list")
    seed: TrackSeed = {
        "name": name, "label": str(raw.get("label") or name), "source_hosts": _check_hosts(raw.get("source_hosts")),
        "services": [_check_service(row, i) for i, row in enumerate(services)],
        "pairs": [_check_pair(row, i) for i, row in enumerate(raw.get("pairs") or [])],
        "scenarios": _text_list(raw["scenarios"], "scenarios") if raw.get("scenarios") else [],
    }
    if raw.get("dimensions"):
        seed["dimensions"] = _text_list(raw["dimensions"], "dimensions")
    return seed


def save_track(seed: TrackSeed) -> None:
    """Store a validated custom seed (replacing an earlier one with the same name)."""
    tables.save_track(seed["name"], seed)


def known_tracks() -> list[str]:
    """AWS plus every custom track that has been added."""
    return [BUILTIN, *tables.track_names()]


def load_seed(name: str) -> TrackSeed:
    """The seed for a track; raises ToolError when the track is unknown."""
    if name == BUILTIN:
        return builtin_seed()
    stored = tables.load_track(name)
    if stored is None:
        known = ", ".join(known_tracks())
        raise ToolError(f"Unknown track {name!r} (known: {known}). Add one with `arch track add {name} --seed FILE`.")
    return validate_seed(stored, name)


def source_ok(url: str | None, hosts: Mapping[str, object] | list[str]) -> bool:
    """Whether url is an https page (not just the host) on one of the accepted documentation hosts."""
    parsed = urlparse(url or "")
    return parsed.scheme == "https" and (parsed.hostname or "") in hosts and len(parsed.path) > 1
