"""Drill tracks: a technology or field a user is preparing for (AWS, Acme Data, product management, ...).

A track is a seed of topics (services, decision pairs, scenarios, cases, role-plays) plus the hosts that
count as a source for facts. Each track belongs to a role family (`families.json`), whose default rubric it
uses unless its seed gives its own. AWS is bundled as the worked example (`jk.interview.aws.arch_seed`).
Any other track is a seed stored in the database, added with `arch track add`;
no code is needed. A seed holds topic names only, never facts: facts are researched and recorded
with a source URL by `arch refresh`.
"""
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from functools import cache
from importlib import resources
from typing import Final, NotRequired, TypedDict
from urllib.parse import urlparse

from jk.interview import tables
from jk.common import ToolError, slug
from jk.interview.aws import arch_seed

BUILTIN: Final[str] = "aws"
NAME_PATTERN: Final[re.Pattern[str]] = re.compile(r"[a-z][a-z0-9-]{1,30}")
HOST_PATTERN: Final[re.Pattern[str]] = re.compile(r"[a-z0-9]([a-z0-9.-]*[a-z0-9])?\.[a-z]{2,}")
DEFAULT_FAMILY: Final[str] = "engineering"
RUBRIC_MAX: Final[int] = 12
COUNTRY_MAX: Final[int] = 60
# The part of a card id that names its kind (services have none): `<track>-<marker><slug of the name>`.
ID_MARKERS: Final[dict[str, str]] = {"service": "", "pair": "pair-", "scenario": "scn-", "case": "case-",
                                     "role-play": "role-"}


class Family(TypedDict):
    """A role family: who it fits and the rubric its tracks use by default."""

    name: str
    label: str
    description: str
    dimensions: list[str]


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


class CaseSeed(TypedDict):
    """A case: an open question the interviewer develops over several turns."""

    title: str
    situation: str
    area: NotRequired[str]


class RolePlaySeed(TypedDict):
    """A role-play: the agent plays a part and the user pursues a goal."""

    title: str
    part: str
    goal: str
    area: NotRequired[str]


class TrackSeed(TypedDict):
    """The seed for one track."""

    name: str
    label: str
    source_hosts: list[str]
    services: list[ServiceSeed]
    pairs: list[PairSeed]
    scenarios: list[str]
    dimensions: NotRequired[list[str]]
    family: NotRequired[str]
    country: NotRequired[str]
    cases: NotRequired[list[CaseSeed]]
    role_plays: NotRequired[list[RolePlaySeed]]


@cache
def families() -> dict[str, Family]:
    """The bundled role families by name, in file order."""
    text = resources.files("jk.interview").joinpath("families.json").read_text(encoding="utf-8")
    return {row["name"]: row for row in json.loads(text)}


def family_of(seed: TrackSeed) -> str:
    """The track's role family (engineering when the seed names none)."""
    return seed.get("family") or DEFAULT_FAMILY


def rubric(seed: TrackSeed) -> list[str]:
    """The lines to grade the track's answers against: the seed's own, else its family's default."""
    return seed.get("dimensions") or families()[family_of(seed)]["dimensions"]


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


def _text(row: dict[str, object], key: str, where: str, limit: int = 0) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip() or (limit and len(value.strip()) > limit):
        raise ToolError(f"{where} needs a text {key!r}" + (f" of at most {limit} characters" if limit else ""))
    return value.strip()


def _rows(raw: dict[str, object], key: str) -> list[dict[str, object]]:
    rows = raw.get(key) or []
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        raise ToolError(f"{key} must be a list of objects")
    return rows


def _check_case(row: dict[str, object], index: int) -> CaseSeed:
    where = f"cases[{index}]"
    case: CaseSeed = {"title": _text(row, "title", where), "situation": _text(row, "situation", where)}
    if row.get("area"):
        case["area"] = _text(row, "area", where)
    return case


def _check_role_play(row: dict[str, object], index: int) -> RolePlaySeed:
    where = f"role_plays[{index}]"
    play: RolePlaySeed = {"title": _text(row, "title", where), "part": _text(row, "part", where),
                          "goal": _text(row, "goal", where)}
    if row.get("area"):
        play["area"] = _text(row, "area", where)
    return play


def _add_role_fields(seed: TrackSeed, raw: dict[str, object]) -> None:
    """Family, rubric, country, cases and role-plays: the fields every role family may use."""
    if raw.get("family") is not None:
        if raw["family"] not in families():
            raise ToolError(f"family must be one of: {', '.join(families())}")
        seed["family"] = str(raw["family"])
    if raw.get("dimensions"):
        seed["dimensions"] = _text_list(raw["dimensions"], "dimensions")
    if raw.get("country") is not None:
        seed["country"] = _text(raw, "country", "The seed", COUNTRY_MAX)
    seed["cases"] = [_check_case(row, i) for i, row in enumerate(_rows(raw, "cases"))]
    seed["role_plays"] = [_check_role_play(row, i) for i, row in enumerate(_rows(raw, "role_plays"))]


def card_count(seed: TrackSeed) -> int:
    """How many cards the seed makes, of every kind."""
    return sum(len(seed.get(key) or []) for key in ("services", "pairs", "scenarios", "cases", "role_plays"))


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
    if not isinstance(services, list):
        raise ToolError("'services' must be a list")
    seed: TrackSeed = {
        "name": name, "label": str(raw.get("label") or name), "source_hosts": _check_hosts(raw.get("source_hosts")),
        "services": [_check_service(row, i) for i, row in enumerate(services)],
        "pairs": [_check_pair(row, i) for i, row in enumerate(raw.get("pairs") or [])],
        "scenarios": _text_list(raw["scenarios"], "scenarios") if raw.get("scenarios") else [],
    }
    _add_role_fields(seed, raw)
    if not card_count(seed):
        raise ToolError("The seed needs at least one card: services, pairs, scenarios, cases or role_plays")
    return seed


def card_id(kind: str, track: str, name: str) -> str:
    """The id of a seeded card: the track's prefix, the kind's marker and the slug of the card's name."""
    return prefix(track) + ID_MARKERS[kind] + slug(name)


def seed_cards(seed: TrackSeed) -> list[tuple[str, str, str]]:
    """(id, kind, name) of every card the seed makes, in seed order."""
    rows = [("service", row["name"]) for row in seed["services"]] + [("pair", row["name"]) for row in seed["pairs"]]
    rows += [("scenario", text) for text in seed["scenarios"]]
    rows += [("case", row["title"]) for row in seed.get("cases", [])]
    rows += [("role-play", row["title"]) for row in seed.get("role_plays", [])]
    return [(card_id(kind, seed["name"], name), kind, name) for kind, name in rows]


def check_card_ids(seed: TrackSeed, stored: Mapping[str, tuple[str, str]]) -> None:
    """Fail when two cards of the seed get the same id, or one gets the id of a stored card (`stored` maps id to
    (kind, track)) of another kind or track: one card would replace the other and take over its progress."""
    mine: dict[str, tuple[str, str]] = {}
    for cid, kind, name in seed_cards(seed):
        if cid in mine:
            raise ToolError(f"The {kind} {name!r} and the {mine[cid][0]} {mine[cid][1]!r} would both be card {cid}: "
                            "rename one of them.")
        mine[cid] = (kind, name)
        if cid in stored and stored[cid] != (kind, seed["name"]):
            other_kind, other_track = stored[cid]
            raise ToolError(f"The {kind} {name!r} would be card {cid}, which is already a {other_kind} of track "
                            f"{other_track}: rename it.")


def _check_new_rows(seed: TrackSeed) -> None:
    """Checks that apply to a seed being added, but not to one stored by an earlier version."""
    if len(seed.get("dimensions") or []) > RUBRIC_MAX:
        raise ToolError(f"dimensions may have at most {RUBRIC_MAX} lines")
    for index, service in enumerate(seed["services"]):
        if not service["name"] or not service["area"]:
            raise ToolError(f"services[{index}] needs a text 'area' and 'name'")
        if not isinstance(service["tier"], int):    # 2.0 equals 2 but is not a tier
            raise ToolError(f"services[{index}].tier must be 2 (core) or 3 (optional); tier 1 comes from your resumes")
    for index, pair in enumerate(seed["pairs"]):
        if not pair["name"] or not pair["topic"]:
            raise ToolError(f"pairs[{index}] needs a text 'topic' and 'name'")


def validate_new_seed(raw: object, name: str, stored: Mapping[str, tuple[str, str]]) -> TrackSeed:
    """`validate_seed` plus the checks for a seed being added now: a rubric of at most RUBRIC_MAX lines, names that
    are not blank, whole-number tiers, and card ids that clash neither with each other nor with `stored` cards.

    A stored seed is read with `validate_seed` alone, so a track an earlier version accepted keeps working.
    """
    seed = validate_seed(raw, name)
    _check_new_rows(seed)
    check_card_ids(seed, stored)
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
