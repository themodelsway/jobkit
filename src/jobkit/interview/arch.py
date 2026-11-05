#!/usr/bin/env python3
"""Architecture-fundamentals drill data for one or more technologies (tracks), kept in prep/arch/.
Standard library only.

  arch tracks                # tracks you can drill (aws is bundled; others you add) and which are enabled
  arch track add NAME --seed FILE|-   # register another technology from a JSON seed (see the interview-prep skill)
  arch init [--track NAME ...]   # create/extend catalog + progress for the tracks (default: enabled ones, else aws)
  arch status                # per area: cards by confidence
  arch next [--track T] [--area A] [--tier N] [--kind service|pair|scenario] [--order default|random]
  arch show ID
  arch set ID confidence|notes VALUE     # confidence: 0 none, 1 some gaps, 2 solid
  arch list [--track T] [--area A] [--tier N] [--kind K]
  arch for-jd jd.txt         # cards the JD mentions, weakest first ("-" = stdin)
  arch stale [--months 6]    # cards whose facts are unverified or old
  arch refresh ID --status active|maintenance|sunset|unverified [--date D] [--note T] --source URL
                                      [--change "DATE|SUMMARY"]...       # record researched facts (source required)

Catalog (topics + sourced facts) and progress (your confidence/notes) are separate files, so refreshing facts
never touches your progress. Sessions live in sessions.py.
"""
from __future__ import annotations

import argparse
import json
import random
import re
from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import date, timedelta
from typing import Final, NotRequired, TypedDict, cast

from jobkit import common
from jobkit.common import ToolError
from jobkit.interview import tables, tracks
from jobkit.resumes import query_resume as qr
from jobkit.resumes.resume_data import Company
from jobkit.user import profile as up

STATUSES: Final[tuple[str, ...]] = ("active", "maintenance", "sunset", "unverified")
KINDS: Final[tuple[str, ...]] = ("service", "pair", "scenario")
CONF: Final[dict[int, str]] = {0: "not drilled", 1: "some gaps", 2: "solid"}
MAX_LINKS_PER_COMPANY: Final[int] = 3

# Shared helpers re-exported under the names the other interview tools already use.
slug = common.slug


class Lifecycle(TypedDict):
    """What the vendor's documentation says about a service's availability."""

    status: str
    date: NotRequired[str]
    note: NotRequired[str]
    source: NotRequired[str]
    seeded: NotRequired[bool]


class Change(TypedDict):
    """One sourced change from the last few years."""

    date: str
    summary: str
    source: str


class Card(TypedDict):
    """A drill topic: a service, a decision pair or a design scenario."""

    id: str
    track: NotRequired[str]
    kind: str
    area: str
    name: str
    tier: int
    aliases: list[str]
    members: list[str]
    lifecycle: Lifecycle
    recent_changes: list[Change]
    verified_on: str | None


class Catalog(TypedDict):
    """prep/arch/catalog.json."""

    dimensions: list[str]
    scenarios_note: str
    tracks: NotRequired[list[str]]
    cards: list[Card]


class Progress(TypedDict):
    """The user's own state for one card."""

    confidence: int
    notes: str
    last_drilled: str | None
    links: dict[str, list[str]]


class ProgressFile(TypedDict):
    """prep/arch/progress.json."""

    cards: dict[str, Progress]


# ---------------------------------------------------------------- storage

def catalog() -> Catalog:
    """The card catalog; fails when `init` has not run."""
    cat = tables.load_catalog()
    if cat is None:
        raise ToolError("No architecture catalog yet: run `arch init` first.")
    return cast(Catalog, cat)


def progress() -> ProgressFile:
    """The user's progress per card (empty before the first change)."""
    return {"cards": cast(dict[str, Progress], tables.load_progress())}


def blank_progress() -> Progress:
    """Progress of a card nobody has drilled yet."""
    return {"confidence": 0, "notes": "", "last_drilled": None, "links": {}}


def progress_of(prog: dict[str, Progress], card_id: str) -> Progress:
    """Progress for one card, blank when there is none."""
    return prog.get(card_id) or blank_progress()


def track_of(card: Card) -> str:
    """The track a card belongs to (cards made before tracks existed are AWS)."""
    return card.get("track", tracks.BUILTIN)


def area_label(card: Card, several: bool) -> str:
    """The card's area, prefixed with its track when more than one track is in use."""
    return f"{track_of(card)}: {card['area']}" if several else card["area"]


def new_card(kind: str, cid: str, name: str, area: str, tier: int,
             aliases: Iterable[str] = (), track: str = tracks.BUILTIN) -> Card:
    """A card with no sourced facts (lifecycle unverified)."""
    return {"id": cid, "track": track, "kind": kind, "area": area, "name": name, "tier": tier, "aliases": list(aliases),
            "members": [], "lifecycle": {"status": "unverified"}, "recent_changes": [],
            "verified_on": None}


def find(cat: Catalog, cid: str) -> Card:
    """The card with this id."""
    for card in cat["cards"]:
        if card["id"] == cid:
            return card
    raise ToolError(f"No card {cid}")


# ---------------------------------------------------------------- matching

def _mention_patterns(card: Card, with_aliases: bool = True) -> list[re.Pattern[str]]:
    names = [card["name"], *(card["aliases"] if with_aliases else [])]
    return [re.compile(r"(?<![A-Za-z0-9])" + re.escape(n) + r"(?![A-Za-z0-9])", re.I) for n in names if len(n) > 1]


def resume_links(card: Card, companies: Iterable[Company]) -> dict[str, list[str]]:
    """Resume bullets that mention the service: {company_id: [bullet ids]} (max 3 each)."""
    patterns = _mention_patterns(card)
    out: dict[str, list[str]] = {}
    for company in companies:
        ids = [b["id"] for b in company["bullets"]
               if not b.get("ignored") and any(p.search(b["text"]) for p in patterns)]
        if ids:
            out[company["id"]] = ids[:MAX_LINKS_PER_COMPANY]
    return out


def matches(text: str, cat: Catalog) -> list[Card]:
    """Service cards whose name or alias appears in the text."""
    return [c for c in cat["cards"]
            if c["kind"] == "service" and any(p.search(text) for p in _mention_patterns(c))]


def flt(cards: Iterable[Card], args: argparse.Namespace) -> list[Card]:
    """Cards that pass the --area, --tier and --kind filters of `args`."""
    wanted_track = getattr(args, "track", None)
    return [c for c in cards
            if (not wanted_track or track_of(c) == wanted_track)
            and (not args.area or args.area.lower() in c["area"].lower())
            and (not args.tier or c["tier"] <= args.tier)
            and (not args.kind or c["kind"] == args.kind)]


def valid_iso(text: str | None) -> bool:
    """Whether text is a YYYY-MM-DD date."""
    try:
        date.fromisoformat(text or "")
        return True
    except ValueError:
        return False


def valid_source(url: str | None, card: Card) -> bool:
    """Whether url is an https page (not just the host) on a documentation host of the card's track."""
    hosts = tracks.load_seed(track_of(card))["source_hosts"]
    return tracks.source_ok(url, hosts)


# ---------------------------------------------------------------- init

def load_resume_context() -> tuple[list[Company] | None, set[str]]:
    """(companies, lower-case skill names) from the resume data, or (None, empty) when it is not available."""
    try:
        companies, skills = qr.load()
    except (OSError, ValueError, KeyError) as exc:
        print(f"Warning: resume data not loaded ({exc}); resume links left unchanged.")
        return None, set()
    names = {item["name"].lower() for group in skills["groups"].values() for item in group}
    return list(companies.values()), names


def _service_card(row: tracks.ServiceSeed, track: str, pinned: set[str], skill_names: set[str],
                  companies: list[Company] | None) -> Card:
    """Card for one seeded service; tier 1 when pinned, or when the resumes mention it by name."""
    aliases = row.get("aliases", [])
    card = new_card("service", tracks.prefix(track) + slug(row["name"]), row["name"], row["area"], row["tier"],
                    aliases, track=track)
    if pinned:
        card["tier"] = 1 if row["name"].lower() in pinned else row["tier"]
        return card
    name_only: Card = {**card, "aliases": []}      # aliases like 'metrics' are too loose to count
    if row["name"].lower() in skill_names or (companies is not None and resume_links(name_only, companies)):
        card["tier"] = 1
    return card


def _pair_card(pair: tracks.PairSeed, track: str) -> Card:
    """Card for one seeded decision pair."""
    card = new_card("pair", f"{tracks.prefix(track)}pair-" + slug(pair["name"]), pair["name"], "Decision pairs", 1,
                    track=track)
    card["members"] = list(pair["members"])
    return card


def build_wanted_cards(seed: tracks.TrackSeed, companies: list[Company] | None, skill_names: set[str]) -> list[Card]:
    """Every card of one track (services, decision pairs, scenarios) with tiers set from the user's profile."""
    track, pre = seed["name"], tracks.prefix(seed["name"])
    pinned = {name.lower() for name in up.tier1_services()}
    wanted = [_service_card(row, track, pinned, skill_names, companies) for row in seed["services"]]
    wanted += [_pair_card(pair, track) for pair in seed["pairs"]]
    wanted += [new_card("scenario", f"{pre}scn-" + slug(text), text, "Scenarios", 1, track=track)
               for text in seed["scenarios"]]
    return wanted


def merge_cards(existing: list[Card], wanted: list[Card]) -> tuple[list[Card], int]:
    """Update known cards in place, add new ones, keep hand-added cards. Returns (cards, number added)."""
    have = {c["id"]: c for c in existing}
    merged: list[Card] = []
    added = 0
    for card in wanted:
        old = have.pop(card["id"], None)
        if old is None:
            added += 1
            merged.append(card)
            continue
        old["name"], old["area"], old["tier"] = card["name"], card["area"], card["tier"]
        old["aliases"], old["members"], old["track"] = card["aliases"], card["members"], track_of(card)
        merged.append(old)
    return merged + list(have.values()), added


def refresh_links(prog: ProgressFile, cards: list[Card], companies: list[Company] | None) -> None:
    """Make sure every card has progress, and re-link service cards to the resume bullets that mention them."""
    for card in cards:
        entry = prog["cards"].setdefault(card["id"], blank_progress())
        if card["kind"] == "service" and companies is not None:
            entry["links"] = resume_links(card, companies)


def cmd_init(args: argparse.Namespace) -> None:
    """Create or extend the catalog and progress for the chosen tracks and the resume data."""
    companies, skill_names = load_resume_context()
    cat = cast(Catalog, tables.load_catalog() or {"dimensions": [], "scenarios_note": "", "cards": []})
    chosen = list(dict.fromkeys(args.track or cat.get("tracks") or [tracks.BUILTIN]))
    seeds = [tracks.load_seed(name) for name in chosen]
    cat["tracks"] = list(dict.fromkeys([*cat.get("tracks", []), *chosen]))
    cat["dimensions"] = seeds[0].get("dimensions") or tracks.builtin_seed().get("dimensions", [])
    added = 0
    for seed in seeds:
        cat["cards"], new = merge_cards(cat["cards"], build_wanted_cards(seed, companies, skill_names))
        added += new
    tables.save_catalog(cat)
    prog = progress()
    refresh_links(prog, cat["cards"], companies)
    tables.save_progress(prog["cards"])
    print(f"{len(cat['cards'])} cards ({added} new) stored")


# ---------------------------------------------------------------- read commands

def show(card: Card, prog: Progress) -> None:
    """Print one card with its progress and sourced facts."""
    life = card["lifecycle"]
    print(f"[{card['id']}] {card['name']} | {track_of(card)} | {card['area']} | {card['kind']} tier {card['tier']}")
    print(f"  confidence: {CONF[prog['confidence']]} | last drilled: {prog['last_drilled'] or '-'}")
    if card["members"]:
        print("  compare: " + ", ".join(card["members"]))
    print(f"  lifecycle: {life['status']}" + (f" ({life['date']})" if "date" in life else "")
          + (f" - {life['note']}" if "note" in life else ""))
    if life.get("seeded") and not card["verified_on"]:
        print("  (seeded lead from the project, NOT verified: check the vendor documentation before stating it)")
    print(f"  lifecycle/changes verified on: {card['verified_on'] or 'NEVER (check the vendor docs before correcting the user)'}"
          "  [limits, prices and features are never stored: look them up each time]")
    for change in card["recent_changes"]:
        print(f"  change {change['date']}: {change['summary']}")
    if prog["links"]:
        print("  used in resume: " + ", ".join(f"{k} ({len(v)})" for k, v in prog["links"].items()))
    if prog["notes"]:
        print(f"  notes: {prog['notes']}")


def cmd_show(args: argparse.Namespace) -> None:
    """Show one card."""
    show(find(catalog(), args.id), progress_of(progress()["cards"], args.id))


def cmd_status(args: argparse.Namespace) -> None:
    """Per area: how many cards are solid, have gaps, or are not drilled."""
    cat, prog = catalog(), progress()["cards"]
    several = len({track_of(c) for c in cat["cards"]}) > 1
    by_area: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    for card in cat["cards"]:
        by_area[area_label(card, several)][progress_of(prog, card["id"])["confidence"]] += 1
    for area, n in by_area.items():
        print(f"  {area:<30} {n[2]} solid, {n[1]} some gaps, {n[0]} not drilled")
    unverified = sum(1 for c in cat["cards"] if not c["verified_on"])
    print(f"\n{unverified} of {len(cat['cards'])} cards have unverified facts (see `stale`).")


def cmd_list(args: argparse.Namespace) -> None:
    """List cards with their tier, confidence and lifecycle status."""
    prog = progress()["cards"]
    for card in flt(catalog()["cards"], args):
        print(f"  {card['id']:<44} t{card['tier']} {CONF[progress_of(prog, card['id'])['confidence']]:<12} "
              f"{card['lifecycle']['status']}")


def cmd_next(args: argparse.Namespace) -> None:
    """Show the next card to drill: lowest tier, weakest, least recently drilled (or random)."""
    cat, prog = catalog(), progress()["cards"]
    position = {c["id"]: i for i, c in enumerate(cat["cards"])}
    todo = [c for c in flt(cat["cards"], args) if progress_of(prog, c["id"])["confidence"] < 2]
    if not todo:
        print("Nothing left in that selection.")
        return
    if getattr(args, "order", "default") == "random":
        random.shuffle(todo)
    else:
        todo.sort(key=lambda c: (c["tier"], progress_of(prog, c["id"])["confidence"],
                                 progress_of(prog, c["id"])["last_drilled"] or "", position[c["id"]]))
    show(todo[0], progress_of(prog, todo[0]["id"]))


def cmd_for_jd(args: argparse.Namespace) -> None:
    """Service cards the job description mentions, weakest first."""
    text = common.read_text_arg(args.jd)
    prog = progress()["cards"]
    hits = matches(text, catalog())
    hits.sort(key=lambda c: (progress_of(prog, c["id"])["confidence"], c["tier"]))
    for card in hits:
        status = card["lifecycle"]["status"]
        flag = "" if status in ("active", "unverified") else f"  [{status}]"
        print(f"  {card['id']:<44} {CONF[progress_of(prog, card['id'])['confidence']]}{flag}")
    print(f"\n{len(hits)} services from the catalog appear in the JD; weakest first.")


def cmd_stale(args: argparse.Namespace) -> None:
    """Service cards whose facts were never verified or are older than --months."""
    cutoff = (date.today() - timedelta(days=30 * args.months)).isoformat()
    rows = [c for c in catalog()["cards"]
            if c["kind"] == "service" and (not c["verified_on"] or c["verified_on"] < cutoff)]
    for card in sorted(rows, key=lambda c: (c["tier"], c["area"])):
        print(f"  t{card['tier']} {card['id']:<44} verified: {card['verified_on'] or 'never'}")
    print(f"\n{len(rows)} service cards need a refresh.")


# ---------------------------------------------------------------- write commands

def cmd_set(args: argparse.Namespace) -> None:
    """Set a card's confidence (0-2) or notes. Lessons never use this: confidence is the user's own override."""
    cat, prog = catalog(), progress()
    find(cat, args.id)
    entry = prog["cards"].setdefault(args.id, blank_progress())
    if args.field == "confidence":
        if args.value not in ("0", "1", "2"):
            raise ToolError("confidence must be 0, 1 or 2")
        entry["confidence"] = int(args.value)
        entry["last_drilled"] = date.today().isoformat()
    else:
        entry["notes"] = args.value
    tables.save_progress(prog["cards"])
    print(f"Updated {args.id}.{args.field}")


def parse_changes(raw: Iterable[str]) -> list[tuple[str, str]]:
    """Split "YYYY-MM-DD|summary" strings into (date, summary) pairs."""
    changes = []
    for item in raw:
        day, _, summary = item.partition("|")
        if not valid_iso(day.strip()) or not summary.strip():
            raise ToolError('--change must look like "YYYY-MM-DD|summary"')
        changes.append((day.strip(), summary.strip()))
    return changes


def check_refresh_args(args: argparse.Namespace, card: Card) -> list[tuple[str, str]]:
    """Validate the refresh arguments; returns the parsed changes."""
    if not valid_source(args.source, card):
        hosts = ", ".join(tracks.load_seed(track_of(card))["source_hosts"])
        raise ToolError(f"--source must be an https URL on one of: {hosts} (a specific page, not just the host)")
    if args.date and not valid_iso(args.date):
        raise ToolError("--date must be YYYY-MM-DD")
    changes = parse_changes(args.change)
    today = date.today().isoformat()
    if args.date and args.date > today and args.status != "sunset":
        raise ToolError("--date is in the future; only a sunset/end date may be future-dated")
    for day, _ in changes:
        if day > today:
            raise ToolError(f"change dated {day} is in the future: put scheduled dates in --note instead")
    return changes


def cmd_refresh(args: argparse.Namespace) -> None:
    """Record researched lifecycle facts for a card; a source URL is required."""
    cat = catalog()
    card = find(cat, args.id)
    changes = check_refresh_args(args, card)
    lifecycle: Lifecycle = {"status": args.status, "source": args.source}
    if args.date:
        lifecycle["date"] = args.date
    if args.note:
        lifecycle["note"] = args.note
    card["lifecycle"] = lifecycle
    card["recent_changes"] += [Change(date=d, summary=s, source=args.source) for d, s in changes]
    card["recent_changes"].sort(key=lambda change: change["date"])
    card["verified_on"] = date.today().isoformat()
    tables.save_catalog(cat)
    print(f"Refreshed {args.id} (verified {card['verified_on']}).")


# ---------------------------------------------------------------- entry point

def cmd_tracks(args: argparse.Namespace) -> None:
    """List the known tracks, which are enabled, and how many cards each has."""
    stored = tables.load_catalog() or {"cards": []}
    cards = stored["cards"]
    enabled = stored.get("tracks") or sorted({track_of(c) for c in cards})
    for name in tracks.known_tracks():
        seed = tracks.load_seed(name)
        count = sum(1 for c in cards if track_of(c) == name)
        print(f"  {name:<16} {'enabled' if name in enabled else 'not enabled':<12} {count:>4} cards   "
              f"docs: {', '.join(seed['source_hosts'])}")


def cmd_track_add(args: argparse.Namespace) -> None:
    """Validate a JSON seed and keep it as a custom track (replaces an earlier seed of that name)."""
    try:
        raw = json.loads(common.read_text_arg(args.seed))
    except json.JSONDecodeError as exc:
        raise ToolError(f"The seed is not valid JSON: {exc}") from exc
    seed = tracks.validate_seed(raw, args.name)
    tracks.save_track(seed)
    print(f"Saved track {args.name}: {len(seed['services'])} services, {len(seed['pairs'])} pairs, "
          f"{len(seed['scenarios'])} scenarios. Run `arch init --track {args.name}`.")


def _add_filters(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--track")
    parser.add_argument("--area")
    parser.add_argument("--tier", type=int)
    parser.add_argument("--kind", choices=KINDS)


def build_parser() -> argparse.ArgumentParser:
    """The command-line parser."""
    parser = common.make_parser(__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    init = sub.add_parser("init")
    init.add_argument("--track", action="append", default=[])
    init.set_defaults(fn=cmd_init)
    sub.add_parser("tracks").set_defaults(fn=cmd_tracks)
    track = sub.add_parser("track").add_subparsers(dest="track_cmd", required=True)
    add = track.add_parser("add")
    add.add_argument("name")
    add.add_argument("--seed", required=True, help="JSON seed file, or - for stdin")
    add.set_defaults(fn=cmd_track_add)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    nxt = sub.add_parser("next")
    _add_filters(nxt)
    nxt.add_argument("--order", choices=["default", "random"], default="default")
    nxt.set_defaults(fn=cmd_next)
    listing = sub.add_parser("list")
    _add_filters(listing)
    listing.set_defaults(fn=cmd_list)
    shower = sub.add_parser("show")
    shower.add_argument("id")
    shower.set_defaults(fn=cmd_show)
    setter = sub.add_parser("set")
    setter.add_argument("id")
    setter.add_argument("field", choices=["confidence", "notes"])
    setter.add_argument("value")
    setter.set_defaults(fn=cmd_set)
    for_jd = sub.add_parser("for-jd")
    for_jd.add_argument("jd", help="job description file, or - for stdin")
    for_jd.set_defaults(fn=cmd_for_jd)
    stale = sub.add_parser("stale")
    stale.add_argument("--months", type=int, default=6)
    stale.set_defaults(fn=cmd_stale)
    refresh = sub.add_parser("refresh")
    refresh.add_argument("id")
    refresh.add_argument("--status", required=True, choices=STATUSES)
    refresh.add_argument("--date")
    refresh.add_argument("--note")
    refresh.add_argument("--source", required=True)
    refresh.add_argument("--change", action="append", default=[])
    refresh.set_defaults(fn=cmd_refresh)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point; returns the exit status."""
    return common.run(build_parser().parse_args(argv), lock=True)


if __name__ == "__main__":
    raise SystemExit(main())
