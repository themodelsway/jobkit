#!/usr/bin/env python3
"""Readiness report across architecture cards, leadership questions and STAR stories. Read-only, stdlib only.

  readiness                 # summary per area / category / company, plus gaps to work on
  readiness --jd jd.txt     # same, limited to what that job description touches (architecture + stories)
  readiness --days 30       # a "solid" answer older than this many days counts as aging (default: the stored
                            # retest window, 30 when none is set; `profile set reassess_days N` changes it)
  readiness --due           # list the items due for a retest (the aging ones) instead of the report [--json] [-o FILE]
  readiness --target NAME   # add evidence per value of a researched company (`target`); with --jd, only what both
                            # select; with --due, only the due items that match a value of that company

This is evidence, not a score. Each item gets one label from your own logged drills:
  untested        never drilled
  some gaps       drilled, graded 1
  solid-unlogged  set to 2 by hand, with no logged answer behind it
  solid-once      graded 2 in logged answers on a single day (could be luck)
  solid-repeated  graded 2 in logged answers on at least two different days
  aging           graded 2 but last drilled more than --days ago, or every graded 2 older than --days
Only logged entries with a non-empty answer count. Entries from tutor lessons count only when the quiz was passed.
For stories: empty / draft / done / done-rehearsed (done, answer logged within --days) / done-aging (older).
For leadership: the question label plus how many examples with content are filled (target: up to 3 employers).
There is deliberately no single percentage: it would hide thin evidence and the grades come from practice, not from a real interviewer.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Final, TypedDict, cast

from jk import common
from jk.common import ToolError
from jk.interview import arch
from jk.interview import lead
from jk.interview import prep
from jk.interview import tables, targets
from jk.interview.story_model import Engagement, Story
from jk.resumes import query_resume as qr
from jk.user import profile as up

ORDER: Final[tuple[str, ...]] = ("untested", "some gaps", "solid-unlogged", "solid-once", "aging", "solid-repeated")
STORY_LABELS: Final[tuple[str, ...]] = ("empty", "draft", "done", "done-rehearsed", "done-aging")
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
    solid = evidence["graded2"] if evidence else set()
    days = {d for d in solid if (date.today() - date.fromisoformat(d)).days <= max_age}
    if solid and not days:
        return "aging"                    # solid answers exist, but none recent: a lesson since then does not refresh them
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

def lead_section(jd_text: str | None, hist: Mapping[str, Evidence], days: int) -> list[tuple[int, str, str, str]]:
    """Print the leadership summary; returns the gaps (sort key, question id, label, examples text)."""
    if jd_text is not None:
        print("\nLEADERSHIP: not filtered by a JD; run without --jd for the full view.")
        return []
    if not tables.has_questions():
        print("\nLEADERSHIP: not set up (run lead init).")
        return []
    questions, progress = lead.cards(), lead.prog()["questions"]
    target = lead.example_target()
    by_category: dict[str, list[str]] = defaultdict(list)
    gaps: list[tuple[int, str, str, str]] = []
    for question in questions:
        p = progress.get(question["id"], lead.blank())
        lab = label(p["confidence"], p["last_drilled"], hist.get(question["id"]), days)
        by_category[question["category"]].append(lab)
        text = lead.examples_text(p)
        if lab in WEAK_LABELS or lead.example_gap(p):
            gaps.append((ORDER.index(lab), question["id"], lab, text))
    print("\nLEADERSHIP")
    for category, labels in sorted(by_category.items()):
        print(line(category, labels))
    filled = sum(lead.filled_examples(progress.get(q["id"], lead.blank())) for q in questions)
    na = sum(lead.skipped_examples(progress.get(q["id"], lead.blank())) for q in questions)
    print(f"  STAR examples filled: {filled} of {len(questions) * target} (question x up to {lead.TOP_N} employers)"
          + (f"; {na} marked not applicable" if na else ""))
    companies = tables.load_company_facts()
    recorded = [c for c, facts in companies.items() if not lead.missing_scope(facts)]
    print(f"  Scope facts (team size, budget) complete for {len(recorded)} of {len(companies)} companies")
    return sorted(gaps)[:MAX_GAPS]


# ---------------------------------------------------------------- stories

def story_label(story: Story, hist: Mapping[str, Evidence], max_age: int = 30) -> str:
    """empty / draft / done; done-rehearsed when a session logged an answer within `max_age` days, done-aging
    when the only logged answers are older. (A story has no grade: this says attempted, not performed well.)"""
    evidence = hist.get(story["id"])
    if story["status"] == "done" and evidence and evidence["answered"]:
        newest = max(evidence["answered"])
        return "done-rehearsed" if (date.today() - date.fromisoformat(newest)).days <= max_age else "done-aging"
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


def story_section(jd_text: str | None, hist: Mapping[str, Evidence], days: int = 30) -> list[tuple[str, str, str]]:
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
        lab = story_label(story, hist, days)
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


# ---------------------------------------------------------------- due for a retest

class Due(TypedDict):
    """One item whose good answer is older than the window."""

    id: str
    name: str
    last: str
    age_days: int


def _due_row(item: str, name: str, last: str | None, days: set[str] | None) -> Due | None:
    """A `Due` row, dated by the newest good answer (or the last drill when none is logged)."""
    day = max(days) if days else last
    if not day:
        return None
    return Due(id=item, name=name, last=day, age_days=(date.today() - date.fromisoformat(day)).days)


def due_items(hist: Mapping[str, Evidence], days: int) -> list[Due]:
    """Items the report labels aging (cards, leadership questions) or done-aging (stories), oldest first."""
    rows: list[Due | None] = []
    if tables.has_catalog():
        prog = arch.progress()["cards"]
        rows += [_due_row(c["id"], c["name"], arch.progress_of(prog, c["id"])["last_drilled"],
                          hist.get(c["id"], {}).get("graded2"))
                 for c in arch.catalog()["cards"] if card_label(c, prog, hist, days) == "aging"]
    if tables.has_questions():
        progress = lead.prog()["questions"]
        rows += [_due_row(q["id"], q["question"], progress.get(q["id"], lead.blank())["last_drilled"],
                          hist.get(q["id"], {}).get("graded2"))
                 for q in lead.cards()
                 if label(progress.get(q["id"], lead.blank())["confidence"],
                          progress.get(q["id"], lead.blank())["last_drilled"], hist.get(q["id"]), days) == "aging"]
    if tables.has_stories():
        rows += [_due_row(s["id"], f"{s['company_name']}: {s['theme']}", None, hist.get(s["id"], {}).get("answered"))
                 for s in prep.stories() if story_label(s, hist, days) == "done-aging"]
    return sorted((r for r in rows if r), key=lambda r: (-r["age_days"], r["id"]))


def target_items(jd_text: str | None) -> dict[str, targets.Item]:
    """id -> item for the stories and leadership questions a company report covers: with a JD, only the stories in
    the JD's themes (leadership questions are not selected by a JD)."""
    stories = prep.stories() if tables.has_stories() else []
    if jd_text is not None:
        themes = qr.analyze(jd_text).themes
        stories = [s for s in stories if s["theme"] in themes]
    items = {s["id"]: targets.story_item(s) for s in stories}
    if tables.has_questions() and jd_text is None:
        progress = lead.prog()["questions"]
        items.update({q["id"]: targets.question_item(q, progress.get(q["id"])) for q in lead.cards()})
    return items


def item_label(item: targets.Item, hist: Mapping[str, Evidence], days: int) -> str:
    """The existing evidence label of a story or leadership question."""
    if item.kind == "story":
        return story_label(next(s for s in prep.stories() if s["id"] == item.id), hist, days)
    p = lead.prog()["questions"].get(item.id, lead.blank())
    return label(p["confidence"], p["last_drilled"], hist.get(item.id), days)


def target_section(company: Mapping[str, object], jd_text: str | None, hist: Mapping[str, Evidence], days: int) -> None:
    """Evidence per value of a company: its state and the items that match it, each with its label. No score."""
    items = target_items(jd_text)
    print(f"\nCOMPANY: {company['name']}" + (" (items the JD also selects)" if jd_text is not None else "")
          + " - evidence per value, no overall score")
    for value in targets.values(company):
        print(f"  {value['name']}: {targets.value_state(value, items.values())}  {targets.fact_source(value)}")
        for item in items.values():
            how = targets.how(value, item)
            if how:
                print(f"    {item.id} [{item_label(item, hist, days)}]" + (" matched by word" if how == "word" else ""))


def due_for_target(rows: list[Due], name: str) -> list[Due]:
    """The due rows whose item matches a value of the company by theme or by word (cards never match)."""
    company, items = targets.find(name), target_items(None)
    return [r for r in rows if r["id"] in items and targets.matches(company, items[r["id"]])]


def cmd_due(args: argparse.Namespace, days: int) -> None:
    """Print the items due for a retest, as text or `--json`; with --target only those matching the company."""
    if args.jd:
        raise ToolError("--due lists what is due for a retest across everything; it cannot be combined with --jd.")
    rows = due_items(attempts(), days)
    if args.target:
        matching = due_for_target(rows, args.target)
        if rows and not matching and not args.json:
            common.emit(f"{len(rows)} item(s) due for a retest in all; none match {args.target}.\n", args.output)
            return
        rows = matching
    if args.json:
        common.emit(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", args.output)
        return
    text = "".join(f"  {r['id']:<40} {r['name'][:50]:<50} last good {r['last']} ({r['age_days']} days ago)\n"
                   for r in rows)
    text += (f"{len(rows)} item(s) due for a retest (older than {days} days)\n" if rows
             else f"none due (nothing older than {days} days)\n")
    common.emit(text, args.output)


# ---------------------------------------------------------------- entry point

def print_next(weak: Sequence[tuple[int, str, str]], gaps: Sequence[tuple[int, str, str, str]],
               todo: Sequence[tuple[str, str, str]]) -> None:
    """The 'WORK ON NEXT' list."""
    print("\nWORK ON NEXT")
    for _, name, lab in weak:
        print(f"  architecture: {name} ({lab})")
    for _, qid, lab, text in gaps[:SHOWN_NEXT]:
        print(f"  leadership: {qid} ({lab}, {text})")
    for company, theme, lab in todo[:SHOWN_NEXT]:
        print(f"  story: {company} / {theme} ({lab})")


def cmd_report(args: argparse.Namespace) -> None:
    """Print the readiness report."""
    days = args.days if args.days is not None else up.reassess_days()
    if args.due:
        cmd_due(args, days)
        return
    company = targets.find(args.target) if args.target else None
    jd_text = common.read_text_arg(args.jd) if args.jd else None
    hist = attempts()
    if not tables.has_catalog():
        raise ToolError("No architecture catalog yet: run arch init.")
    weak = arch_section(jd_text, hist, days)
    gaps = lead_section(jd_text, hist, days)
    todo = story_section(jd_text, hist, days)
    print_next(weak, gaps, todo)
    if company is not None:
        target_section(company, jd_text, hist, days)
    print("\n" + NOTE)


def build_parser() -> argparse.ArgumentParser:
    """The command-line parser."""
    parser = common.make_parser(__doc__)
    parser.add_argument("--jd", help="job description file, or - for stdin")
    parser.add_argument("--days", type=int, default=None,
                        help="a solid answer older than this counts as aging (default: the stored retest window, else 30)")
    parser.add_argument("--due", action="store_true", help="list the items due for a retest instead of the report")
    parser.add_argument("--target", help="a researched company: add evidence per value of that company")
    parser.add_argument("--json", action="store_true", help="with --due: print the list as JSON")
    parser.add_argument("-o", "--output", help="with --due: write the list to this file")
    parser.set_defaults(fn=cmd_report)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point; returns the exit status."""
    return common.run(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
