#!/usr/bin/env python3
"""Readiness report across architecture cards, leadership questions and STAR stories. Read-only, stdlib only.

  readiness                 # summary per area / category / company, plus gaps to work on
  readiness --jd jd.txt     # same, limited to what that job description touches (architecture + stories)
  readiness --days 30       # a "solid" answer older than this many days counts as aging (default 30)

This is evidence, not a score. Each item gets one label from your own logged drills:
  untested        never drilled
  some gaps       drilled, graded 1
  solid-unlogged  set to 2 by hand, with no logged answer behind it
  solid-once      graded 2 in logged answers on a single day (could be luck)
  solid-repeated  graded 2 in logged answers on at least two different days
  aging           graded 2 but last drilled more than --days ago
Only logged entries with a non-empty answer count. Entries from tutor lessons count only when the quiz was passed.
For stories: empty / draft / done / done-rehearsed (done and logged in a session at least once).
For leadership: the question label plus how many of the top-3 company examples are filled.
There is deliberately no single percentage: it would hide thin evidence and the grades come from practice, not from a real interviewer.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Final, TypedDict, cast

from jobkit import common
from jobkit.common import ToolError
from jobkit.interview import arch
from jobkit.interview import lead
from jobkit.interview import prep
from jobkit.interview import tables
from jobkit.interview.story_model import Engagement, Story
from jobkit.resumes import query_resume as qr

ORDER: Final[tuple[str, ...]] = ("untested", "some gaps", "solid-unlogged", "solid-once", "aging", "solid-repeated")
STORY_LABELS: Final[tuple[str, ...]] = ("empty", "draft", "done", "done-rehearsed")
WEAK_LABELS: Final[tuple[str, ...]] = ("untested", "some gaps", "aging")
MAX_GAPS: Final[int] = 8
SHOWN_NEXT: Final[int] = 5
NOTE: Final[str] = (
    "Note: labels come from your own practice answers as graded in sessions. They show coverage and how "
    "well-tested an answer is, not how an interviewer will score you. One 'solid' attempt is weak evidence; "
    "repeat it on another day.")


class Evidence(TypedDict):
    """Dates (YYYY-MM-DD) on which an item was answered / graded solid in logged practice."""

    graded2: set[str]
    answered: set[str]


def attempts() -> dict[str, Evidence]:
    """item id -> evidence, from the answers logged in sessions that count as practice."""
    return cast(dict[str, Evidence], tables.evidence())


def label(conf: int, last: str | None, evidence: Evidence | None, max_age: int) -> str:
    """The evidence label of one item (see the module docstring)."""
    if conf == 0 or not last:
        return "untested"
    if conf == 1:
        return "some gaps"
    if (date.today() - date.fromisoformat(last)).days > max_age:
        return "aging"
    days = evidence["graded2"] if evidence else set()
    return "solid-repeated" if len(days) >= 2 else "solid-once" if days else "solid-unlogged"


def line(name: str, labels: Sequence[str], width: int = 30) -> str:
    """One report row: the name, the item count and how many items carry each label."""
    counts = Counter(labels)
    parts = "  ".join(f"{k} {counts[k]}" for k in ORDER if counts[k])
    return f"  {name:<{width}} {len(labels):>3} items | {parts}"


# ---------------------------------------------------------------- architecture

def jd_cards(jd_text: str, cat: arch.Catalog) -> list[arch.Card]:
    """Service cards the JD mentions, plus the decision pairs that compare any of them."""
    services = arch.matches(jd_text, cat)
    names = {n.lower() for c in services for n in [c["name"], *c["aliases"]]}
    pairs = [c for c in cat["cards"] if c["kind"] == "pair" and any(m.lower() in names for m in c["members"])]
    return services + pairs


def card_label(card: arch.Card, prog: Mapping[str, arch.Progress], hist: Mapping[str, Evidence], days: int) -> str:
    """The evidence label of a card."""
    p = arch.progress_of(dict(prog), card["id"])
    return label(p["confidence"], p["last_drilled"], hist.get(card["id"]), days)


def arch_section(jd_text: str | None, hist: Mapping[str, Evidence], days: int) -> list[tuple[int, str, str]]:
    """Print the architecture summary; returns the weak tier-1 cards (sort key, name, label)."""
    cat = arch.catalog()
    cards = jd_cards(jd_text, cat) if jd_text is not None else cat["cards"]
    prog = arch.progress()["cards"]
    several = len({arch.track_of(c) for c in cat["cards"]}) > 1
    by_area: dict[str, list[str]] = defaultdict(list)
    weak: list[tuple[int, str, str]] = []
    for card in cards:
        lab = card_label(card, prog, hist, days)
        by_area[arch.area_label(card, several)].append(lab)
        if card["tier"] == 1 and lab in WEAK_LABELS:
            weak.append((ORDER.index(lab), card["name"], lab))
    print("ARCHITECTURE" + (" (cards matching the JD)" if jd_text is not None else ""))
    for area, labels in sorted(by_area.items()):
        print(line(area, labels))
    print(line("Tier 1 services (your list)",
               [card_label(c, prog, hist, days) for c in cards if c["tier"] == 1 and c["kind"] == "service"]))
    services = [c for c in cards if c["kind"] == "service"]
    unchecked = sum(1 for c in services if c.get("verified_on") is None)
    print(f"  Lifecycle facts not yet checked against the vendor docs: {unchecked} of {len(services)} services "
          "(checked on first drill)")
    if jd_text is not None:
        print("  (design scenarios are not matched to a JD; run without --jd to see them)")
    return sorted(weak)[:MAX_GAPS]


# ---------------------------------------------------------------- leadership

def lead_section(jd_text: str | None, hist: Mapping[str, Evidence], days: int) -> list[tuple[int, str, str, int]]:
    """Print the leadership summary; returns the gaps (sort key, question id, label, examples filled)."""
    if jd_text is not None:
        print("\nLEADERSHIP: not filtered by a JD; run without --jd for the full view.")
        return []
    if not tables.has_questions():
        print("\nLEADERSHIP: not set up (run lead init).")
        return []
    questions, progress = lead.cards(), lead.prog()["questions"]
    by_category: dict[str, list[str]] = defaultdict(list)
    gaps: list[tuple[int, str, str, int]] = []
    for question in questions:
        p = progress.get(question["id"], lead.blank())
        lab = label(p["confidence"], p["last_drilled"], hist.get(question["id"]), days)
        by_category[question["category"]].append(lab)
        have = len(p["examples"])
        if lab in WEAK_LABELS or have < lead.TOP_N:
            gaps.append((ORDER.index(lab), question["id"], lab, have))
    print("\nLEADERSHIP")
    for category, labels in sorted(by_category.items()):
        print(line(category, labels))
    filled = sum(len(progress.get(q["id"], lead.blank())["examples"]) for q in questions)
    print(f"  STAR examples filled: {filled} of {len(questions) * lead.TOP_N} (question x top-{lead.TOP_N} company)")
    companies = tables.load_company_facts()
    recorded = [c for c, facts in companies.items() if any(facts.values())]
    print(f"  Scope facts (team size, budget...) recorded for {len(recorded)} of {len(companies)} companies")
    return sorted(gaps)[:MAX_GAPS]


# ---------------------------------------------------------------- stories

def story_label(story: Story, hist: Mapping[str, Evidence]) -> str:
    """empty / draft / done, or done-rehearsed when a session logged an answer for it."""
    evidence = hist.get(story["id"])
    if story["status"] == "done" and evidence and evidence["answered"]:
        return "done-rehearsed"
    return str(story["status"])


def story_notes(story: Story, engagements: Sequence[Engagement]) -> list[str]:
    """Quality remarks from prep.health for a story that has been started."""
    health = prep.health(story, engagements)
    notes = []
    if health["errors"]:
        notes.append(f"{len(health['errors'])} rule error(s)")
    if health["weak_facts"]:
        notes.append(f"{health['weak_facts']} unsure/proposed fact(s) in use")
    if health["open_followups"]:
        notes.append(f"{health['open_followups']} open follow-up(s)")
    if not health["spoken"] and story["status"] == "done":
        notes.append("no spoken version")
    if not health["linked"]:
        notes.append("no engagement linked")
    return notes


def story_section(jd_text: str | None, hist: Mapping[str, Evidence]) -> list[tuple[str, str, str]]:
    """Print the story summary; returns the stories still to write (company, theme, label)."""
    stories = prep.stories() if tables.has_stories() else []
    if not stories:
        print("\nSTAR STORIES: none yet (run prep init).")
        return []
    if jd_text is not None:
        themes = qr.analyze(jd_text).themes
        stories = [s for s in stories if s["theme"] in themes]
    by_company: dict[str, list[str]] = defaultdict(list)
    todo: list[tuple[str, str, str]] = []
    quality: list[tuple[str, str, list[str]]] = []
    engagements = prep.engagements()
    for story in stories:
        lab = story_label(story, hist)
        notes = story_notes(story, engagements) if story["status"] != "empty" else []
        if notes:
            quality.append((story["id"], lab, notes))
        by_company[story["company_name"]].append(lab)
        if lab in ("empty", "draft"):
            todo.append((story["company_name"], story["theme"], lab))
    print("\nSTAR STORIES" + (" (themes in the JD)" if jd_text is not None else ""))
    for company, labels in by_company.items():
        counts = Counter(labels)
        print(f"  {company:<30} {len(labels):>3} stories | "
              + "  ".join(f"{k} {counts[k]}" for k in STORY_LABELS if counts[k]))
    if quality:
        print("  Story quality (from prep validate; not a grade of your answers):")
        for sid, lab, notes in quality:
            print(f"    {sid} [{lab}]: " + "; ".join(notes))
    return todo[:MAX_GAPS]


# ---------------------------------------------------------------- entry point

def print_next(weak: Sequence[tuple[int, str, str]], gaps: Sequence[tuple[int, str, str, int]],
               todo: Sequence[tuple[str, str, str]]) -> None:
    """The 'WORK ON NEXT' list."""
    print("\nWORK ON NEXT")
    for _, name, lab in weak:
        print(f"  architecture: {name} ({lab})")
    for _, qid, lab, have in gaps[:SHOWN_NEXT]:
        print(f"  leadership: {qid} ({lab}, {have}/{lead.TOP_N} examples)")
    for company, theme, lab in todo[:SHOWN_NEXT]:
        print(f"  story: {company} / {theme} ({lab})")


def cmd_report(args: argparse.Namespace) -> None:
    """Print the readiness report."""
    jd_text = common.read_text_arg(args.jd) if args.jd else None
    hist = attempts()
    if not tables.has_catalog():
        raise ToolError("No architecture catalog yet: run arch init.")
    weak = arch_section(jd_text, hist, args.days)
    gaps = lead_section(jd_text, hist, args.days)
    todo = story_section(jd_text, hist)
    print_next(weak, gaps, todo)
    print("\n" + NOTE)


def build_parser() -> argparse.ArgumentParser:
    """The command-line parser."""
    parser = common.make_parser(__doc__)
    parser.add_argument("--jd", help="job description file, or - for stdin")
    parser.add_argument("--days", type=int, default=30, help="a solid answer older than this counts as aging")
    parser.set_defaults(fn=cmd_report)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point; returns the exit status."""
    return common.run(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
