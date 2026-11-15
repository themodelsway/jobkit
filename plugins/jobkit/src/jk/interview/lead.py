#!/usr/bin/env python3
"""Leadership interview questionnaire, kept in the database. Standard library only.

  lead init                      # create/extend questions + progress (never overwrites answers)
  lead status                    # per category: confidence counts; profile gaps
  lead next [--category C] [--order default|random]
  lead show ID [--target COMPANY]   # question, profile facts, candidate stories for the 3 newest companies, saved
                                    # answers; with --target, the company values it matches and their typical questions
  lead list [--category C] [--target COMPANY]   # with --target, each question's matching values; read-only
  lead set ID principle|notes|confidence VALUE      # principle = "how I handle this" in your own words
  lead example ID COMPANY FIELD VALUE               # FIELD: situation task action result metric
  lead skip ID COMPANY [REASON]                     # no real example there (never had that role, say): not a gap
  lead unskip ID COMPANY
  lead profile show
  lead profile set COMPANY FIELD VALUE              # factual scope: team sizes, reports, budget, cadence...

Every question can hold a principle plus a STAR example for any employer in the resume data. The coverage target
is up to three examples (see TOP_N), or fewer when there are fewer employers; blank examples do not count.
An employer marked with `skip` (a reason, in your words) counts as covered but is shown as not applicable.
Candidate stories come from prep.py (resume-based stories whose themes match); a finished story there can be reused.
"""
from __future__ import annotations

import argparse
import random
from collections import defaultdict
from collections.abc import Sequence
from datetime import date
from typing import Any, Final, NamedTuple, TypedDict, cast

from jk import common
from jk.common import ToolError
from jk.interview import arch
from jk.interview import prep, tables, targets
from jk.interview.story_model import Story
from jk.resumes import query_resume as qr
from jk.resumes import tables as rd_tables
from jk.resumes.resume_data import Company

TOP_N: Final[int] = 3
STAR: Final[tuple[str, ...]] = ("situation", "task", "action", "result", "metric")
PROFILE_FIELDS: Final[tuple[str, ...]] = ("title", "direct_reports", "indirect_team", "team_composition", "budget",
                                          "stakeholders", "reporting_to", "cadence", "notes")
SCOPE_FIELDS: Final[tuple[str, ...]] = ("direct_reports", "indirect_team", "budget")
SETTABLE: Final[tuple[str, ...]] = ("principle", "notes", "confidence")


class SeedQuestion(NamedTuple):
    """A question every user gets: id, category, text and generic theme names."""

    id: str
    category: str
    question: str
    themes: list[str]


class Question(TypedDict):
    """One stored question."""

    id: str
    category: str
    question: str
    themes: list[str]


class QuestionProgress(TypedDict):
    """The user's state for one question."""

    confidence: int
    principle: str
    notes: str
    last_drilled: str | None
    examples: dict[str, dict[str, str]]


# `init` keeps only the themes that appear in the user's own scanned resume data (the stored resume index),
# so nothing here depends on any one person's resume.
SEED: Final[tuple[SeedQuestion, ...]] = tuple(SeedQuestion(*row) for row in (
    ("team-scope", "Scope and facts", "How many people have you led, directly and indirectly, in each role?", ["team-leadership"]),
    ("budget-scope", "Scope and facts", "What budget, P&L or spend have you owned or influenced?", ["topic-06", "topic-09"]),
    ("principles", "Scope and facts", "Describe your leadership style in one minute, with an example.", ["team-leadership"]),
    ("roadmap-build", "Roadmapping and strategy", "Walk me through how you build a technology roadmap.", ["strategy-roadmap"]),
    ("roadmap-buyin", "Roadmapping and strategy", "How do you get executives who disagree to buy into a roadmap?", ["stakeholder-alignment", "executive-advisory", "strategy-roadmap"]),
    ("roadmap-change", "Roadmapping and strategy", "Tell me about a time you changed a roadmap midway. Why, and how did you communicate it?", ["strategy-roadmap", "topic-17"]),
    ("metrics-success", "Roadmapping and strategy", "How do you measure the success of an architecture or a team?", ["strategy-roadmap", "delivery-leadership"]),
    ("prioritize-framework", "Prioritization", "How do you prioritize when everything is urgent?", ["delivery-leadership", "strategy-roadmap"]),
    ("prioritize-no", "Prioritization", "Tell me about a time you said no to a stakeholder.", ["stakeholder-alignment", "executive-advisory"]),
    ("tech-debt", "Prioritization", "How do you balance technical debt against new features?", ["topic-17"]),
    ("mentoring-approach", "Mentoring and people", "How do you mentor and grow architects and engineers?", ["mentoring"]),
    ("mentoring-example", "Mentoring and people", "Tell me about someone you developed who grew significantly.", ["mentoring", "team-leadership"]),
    ("underperformer", "Mentoring and people", "How do you handle an underperformer?", ["team-leadership", "mentoring"]),
    ("hiring", "Mentoring and people", "How do you hire, and what do you look for in an architect?", ["team-leadership"]),
    ("delegation", "Mentoring and people", "How do you delegate while staying accountable?", ["team-leadership", "delivery-leadership"]),
    ("conflict-team", "Conflict", "Tell me about a conflict between two people on your team and how you resolved it.", ["team-leadership"]),
    ("conflict-peer", "Conflict", "Tell me about a disagreement with a peer or another architect.", ["stakeholder-alignment"]),
    ("conflict-exec", "Conflict", "Tell me about disagreeing with a senior executive or client.", ["executive-advisory", "stakeholder-alignment"]),
    ("conflict-vendor", "Conflict", "A vendor or partner is underperforming. What do you do?", ["vendor-management"]),
    ("delivery-risk", "Execution", "Tell me about a delivery that was at risk and how you recovered it.", ["delivery-leadership"]),
    ("failure", "Execution", "Tell me about your biggest professional failure or mistake.", ["delivery-leadership"]),
    ("ambiguity", "Execution", "Tell me about leading through ambiguity.", ["strategy-roadmap", "topic-01", "topic-17"]),
    ("change-resisted", "Execution", "Tell me about driving a change people resisted.", ["topic-17", "workshops", "stakeholder-alignment"]),
    ("influence-no-authority", "Influence and communication", "How do you influence without authority?", ["stakeholder-alignment", "workshops"]),
    ("exec-tradeoff", "Influence and communication", "How do you explain a technical trade-off to a non-technical executive?", ["executive-advisory", "workshops"]),
    ("decide-incomplete", "Influence and communication", "Tell me about a decision you made with incomplete data, or one you disagreed with and committed to.", ["delivery-leadership", "governance-compliance"]),
    ("multi-engagement", "Influence and communication", "How do you manage several clients or engagements at once?", ["topic-18", "delivery-leadership"]),
    ("team-culture", "Culture", "How do you build team culture, including on remote or mixed teams?", ["team-leadership", "mentoring"]),
))


# ---------------------------------------------------------------- storage

def blank() -> QuestionProgress:
    """Progress of a question nobody has answered yet."""
    return {"confidence": 0, "principle": "", "notes": "", "last_drilled": None, "examples": {}}


def blank_profile() -> dict[str, str | None]:
    """A company profile with every field empty."""
    return {field: None for field in PROFILE_FIELDS}


def top_companies() -> list[Company]:
    """The most recent TOP_N companies of the resume data."""
    return qr.newest_first(qr.load()[0])[:TOP_N]


def top_company_ids() -> list[str]:
    """Ids of the top companies."""
    return [c["id"] for c in top_companies()]


def example_target() -> int:
    """How many examples a question should have: TOP_N, or the number of employers when that is fewer."""
    try:
        return max(1, min(TOP_N, len(qr.load()[0])))
    except ToolError:
        return TOP_N


def has_content(fields: dict[str, str]) -> bool:
    """Whether an example has some real STAR content (blank or whitespace-only fields and the skip mark do not count)."""
    return any(str(v).strip() for k, v in fields.items() if k in STAR)


def filled_examples(entry: QuestionProgress) -> int:
    """How many companies have an example with some real content."""
    return sum(1 for fields in entry["examples"].values() if has_content(fields))


def skipped_examples(entry: QuestionProgress) -> int:
    """How many companies are marked not applicable (and have no example of their own)."""
    return sum(1 for fields in entry["examples"].values() if fields.get("skipped") and not has_content(fields))


def examples_text(entry: QuestionProgress) -> str:
    """`2/3 examples` or `2/3 examples, 1 not applicable`."""
    skipped = skipped_examples(entry)
    return f"{filled_examples(entry)}/{example_target()} examples" + (f", {skipped} not applicable" if skipped else "")


def example_gap(entry: QuestionProgress) -> bool:
    """Whether the question still lacks examples: not applicable employers count as covered."""
    return filled_examples(entry) + skipped_examples(entry) < example_target()


def missing_scope(facts: dict[str, Any] | None) -> list[str]:
    """The scope facts (team size, budget) still unset for a company; an entered 0 counts as set."""
    return [f for f in SCOPE_FIELDS if not str((facts or {}).get(f) or "").strip()]


def cards() -> list[Question]:
    """All questions; fails when `init` has not run."""
    if not tables.has_questions():
        raise ToolError("No leadership questions yet: run `lead init` first.")
    return cast(list[Question], tables.load_questions())


def prog() -> dict[str, Any]:
    """{"questions": {id: QuestionProgress}} for every question the user has touched."""
    return {"questions": tables.load_lead_progress()}


def find(qid: str) -> Question:
    """The question with this id."""
    for question in cards():
        if question["id"] == qid:
            return question
    raise ToolError(f"No question {qid}")


def user_themes() -> set[str] | None:
    """Themes found in the user's resume data, or None when there is no resume data yet."""
    try:
        return set((rd_tables.load_index() or {})["themes"])
    except (OSError, KeyError, ValueError):
        return None


def require_company(company: str) -> None:
    """Fail unless the company is an employer in the resume data."""
    ids = [c["id"] for c in qr.newest_first(qr.load()[0])]
    if company not in ids:
        raise ToolError("COMPANY must be one of " + ", ".join(ids))


# ---------------------------------------------------------------- commands

def cmd_init(args: argparse.Namespace) -> None:
    """Create or extend the questions, progress and company profiles."""
    mine = user_themes()
    old: dict[str, Question] = {q["id"]: cast(Question, q) for q in tables.load_questions()}
    out: list[Question] = []
    added = 0
    for seed in SEED:
        added += seed.id not in old
        old.pop(seed.id, None)
        out.append({"id": seed.id, "category": seed.category, "question": seed.question,
                    "themes": [t for t in seed.themes if mine is None or t in mine]})
    out += list(old.values())
    tables.replace_questions(out)
    progress = prog()
    for question in out:
        progress["questions"].setdefault(question["id"], blank())
    tables.replace_lead_progress(progress["questions"])
    profile = {"companies": tables.load_company_facts()}
    ids = top_company_ids()
    for cid in ids:
        profile["companies"].setdefault(cid, blank_profile())
    tables.replace_company_facts(profile["companies"])
    print(f"{len(out)} questions ({added} new); profile for {', '.join(ids)}")


def show_profile(only: Sequence[str] | None = None) -> None:
    """Print the factual scope (team sizes, budget ...) saved per company."""
    for cid, facts in tables.load_company_facts().items():
        if only and cid not in only:
            continue
        filled = {k: v for k, v in facts.items() if v}
        print(f"  {cid}: " + ("; ".join(f"{k}={v}" for k, v in filled.items()) or "(no facts yet)"))


def load_stories() -> list[Story]:
    """The prep stories, or none when prep has no stories file yet."""
    try:
        return prep.stories()
    except ToolError:
        return []


def story_line(story: Story) -> str:
    """One line for a candidate story: id, status, headline and anything still weak about it."""
    health = prep.health(story)
    notes = [("spoken " + "/".join(health["spoken"])) if health["spoken"] else "",
             f"{health['weak_facts']} unsure fact(s)" if health["weak_facts"] else "",
             f"{health['open_followups']} open follow-up(s)" if health["open_followups"] else ""]
    extra = ", ".join(n for n in notes if n)
    return f"    {story['id']} [{story['status']}] {story['headline'][:110]}" + (f" ({extra})" if extra else "")


def print_candidates(question: Question, progress: QuestionProgress, companies: Sequence[str]) -> None:
    """Candidate stories and any saved example, per top company."""
    stories = load_stories()
    print("  candidate stories (resume-based, from prep.py):")
    for cid in companies:
        candidates = [s for s in stories if s["company"] == cid
                      and ({s["theme"], *s["also_themes"]} & set(question["themes"]))]
        for story in candidates:
            print(story_line(story))
        if not candidates:
            print(f"    {cid}: no matching story theme; ask the user for a real example")
        example = progress["examples"].get(cid)
        if example:
            print(f"    saved example for {cid}: " + "; ".join(f"{k}={v}" for k, v in example.items() if v))


def show(question: Question) -> None:
    """Print a question with its progress, profile facts and candidate stories."""
    progress = prog()["questions"].get(question["id"], blank())
    print(f"[{question['id']}] {question['category']}\n  Q: {question['question']}")
    print(f"  confidence: {arch.CONF[progress['confidence']]} | last drilled: {progress['last_drilled'] or '-'}")
    print(f"  my principle: {progress['principle'] or '-'}")
    top = top_company_ids()
    print("  profile facts:")
    show_profile(top)
    print_candidates(question, progress, top)
    if progress["notes"]:
        print(f"  notes: {progress['notes']}")


def target_item(question: Question) -> targets.Item:
    """A question as the company matching sees it."""
    return targets.question_item(question, prog()["questions"].get(question["id"]))


def matches_text(company: dict[str, Any], question: Question) -> str:
    """The company values a question matches and how: "Ownership (theme), Pace (word)"; "" for none."""
    return ", ".join(f"{value['name']} ({how})" for value, how in targets.matches(company, target_item(question)))


def print_target_values(company: dict[str, Any], question: Question) -> None:
    """The values of the company the question matches, each with how and its stored typical questions."""
    found = targets.matches(company, target_item(question))
    print(f"  {company['name']} values: " + ("" if found else "none match this question"))
    for value, how in found:
        print(f"    {value['name']} (by {how}) {targets.fact_source(value)}")
        for typical in targets.questions_for(company, value["id"]):
            print(f"      Q: {typical['wording']} {targets.fact_source(typical)}")


def cmd_show(args: argparse.Namespace) -> None:
    """Show one question; with --target, the company values it matches. Read-only."""
    question = find(args.id)
    show(question)
    if args.target:
        print_target_values(targets.find(args.target), question)


def in_category(question: Question, category: str | None) -> bool:
    """Whether the question belongs to the (partially typed) category filter."""
    return not category or category.lower() in question["category"].lower()


def question_row(question: Question, progress: dict[str, Any]) -> str:
    """One listing row: id, category, confidence and example counts."""
    p = progress.get(question["id"], blank())
    return f"  {question['id']:<24} {question['category']:<28} {arch.CONF[p['confidence']]:<12} {examples_text(p)}"


def cmd_list(args: argparse.Namespace) -> None:
    """List questions with confidence and example counts; with --target, the company values each matches."""
    progress = prog()["questions"]
    chosen = [q for q in cards() if in_category(q, args.category)]
    if not args.target:
        for question in chosen:
            print(question_row(question, progress))
        return
    company = targets.find(args.target)
    matched = [q for q in chosen if matches_text(company, q)]
    print(f"Leadership questions for {company['name']}:")
    for question in matched:
        print(f"{question_row(question, progress)} | {matches_text(company, question)}")
    print(f"\nQuestions that match no value of {company['name']}:")
    for question in (q for q in chosen if q not in matched):
        print(question_row(question, progress))
    judgment = [v for v in targets.values(company) if not v.get("themes") and not v.get("hints")]
    if judgment:
        print("\nValues that need your judgment (no themes or hint words to match):")
        for value in judgment:
            print(f"  {value['name']} {targets.fact_source(value)}")
            for typical in targets.questions_for(company, value["id"]):
                print(f"    Q: {typical['wording']}")


def ordered(args: argparse.Namespace, include_solid: bool = False) -> list[Question]:
    """Questions not yet solid: weakest and least recently drilled first (or random). With `include_solid`, solid
    questions follow, the least recently drilled first."""
    progress = prog()["questions"]
    todo = [q for q in cards() if in_category(q, args.category)
            and (include_solid or progress.get(q["id"], blank())["confidence"] < 2)]
    if getattr(args, "order", "default") == "random":
        random.shuffle(todo)
        todo.sort(key=lambda q: progress.get(q["id"], blank())["confidence"] >= 2)
    else:
        todo.sort(key=lambda q: (progress.get(q["id"], blank())["confidence"] >= 2,
                                 progress.get(q["id"], blank())["confidence"],
                                 progress.get(q["id"], blank())["last_drilled"] or ""))
    return todo


def cmd_next(args: argparse.Namespace) -> None:
    """Show the next question to work on."""
    todo = ordered(args)
    if todo:
        show(todo[0])
    else:
        print("Nothing left in that selection.")


def cmd_status(args: argparse.Namespace) -> None:
    """Per category: how many questions are solid, have gaps, or are not drilled; profile gaps."""
    progress = prog()["questions"]
    by_category: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    for question in cards():
        by_category[question["category"]][progress.get(question["id"], blank())["confidence"]] += 1
    for category, n in by_category.items():
        print(f"  {category:<30} {n[2]} solid, {n[1]} some gaps, {n[0]} not drilled")
    profile = tables.load_company_facts()
    gaps = [f"{cid} ({', '.join(m)})" for cid in (profile or {}) if (m := missing_scope(profile[cid]))]
    print("\nScope facts missing for: " + (", ".join(gaps) or "none"))


def cmd_set(args: argparse.Namespace) -> None:
    """Set a question's principle, notes or confidence."""
    find(args.id)
    progress = prog()
    entry = progress["questions"].setdefault(args.id, blank())
    if args.field == "confidence":
        if args.value not in ("0", "1", "2"):
            raise ToolError("confidence must be 0, 1 or 2")
        entry["confidence"], entry["last_drilled"] = int(args.value), date.today().isoformat()
    else:
        entry[args.field] = args.value
    tables.set_lead_progress(args.id, entry)
    print(f"Updated {args.id}.{args.field}")


def cmd_example(args: argparse.Namespace) -> None:
    """Save one STAR field of the user's example for a question and company."""
    find(args.id)
    require_company(args.company)
    if args.field not in STAR:
        raise ToolError("FIELD must be one of " + ", ".join(STAR))
    progress = prog()
    entry = progress["questions"].setdefault(args.id, blank())
    fields = entry["examples"].setdefault(args.company, {})
    fields[args.field] = args.value
    fields.pop("skipped", None)                      # a real example replaces a not-applicable mark
    tables.set_lead_progress(args.id, entry)
    print(f"Updated {args.id} example for {args.company}.{args.field}")


def cmd_skip(args: argparse.Namespace) -> None:
    """Mark an employer as not applicable for a question (or clear the mark with `unskip`)."""
    find(args.id)
    require_company(args.company)
    progress = prog()
    entry = progress["questions"].setdefault(args.id, blank())
    fields = entry["examples"].setdefault(args.company, {})
    if args.cmd == "unskip":
        fields.pop("skipped", None)
    elif has_content(fields):
        raise ToolError(f"{args.id} already has an example for {args.company}; it is not 'not applicable'.")
    else:
        fields["skipped"] = (args.reason or "").strip() or "not applicable"
    tables.set_lead_progress(args.id, entry)
    print(f"{'Cleared' if args.cmd == 'unskip' else 'Marked not applicable:'} {args.id} for {args.company}.")


def cmd_profile(args: argparse.Namespace) -> None:
    """Show the company profiles, or set one fact (team size, budget ...)."""
    if args.action == "show":
        show_profile()
        return
    if args.company is None or args.field not in PROFILE_FIELDS:
        raise ToolError("usage: profile set COMPANY FIELD VALUE; FIELD in " + ", ".join(PROFILE_FIELDS))
    require_company(args.company)
    facts = tables.load_company_facts()
    facts.setdefault(args.company, blank_profile())[args.field] = args.value
    tables.replace_company_facts(facts)
    print(f"Updated profile {args.company}.{args.field}")


# ---------------------------------------------------------------- entry point

def build_parser() -> argparse.ArgumentParser:
    """The command-line parser."""
    parser = common.make_parser(__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init").set_defaults(fn=cmd_init)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    nxt = sub.add_parser("next")
    nxt.add_argument("--category")
    nxt.add_argument("--order", choices=["default", "random"], default="default")
    nxt.set_defaults(fn=cmd_next)
    listing = sub.add_parser("list")
    listing.add_argument("--category")
    listing.add_argument("--target", help="a researched company: mark each question with the values it matches")
    listing.set_defaults(fn=cmd_list)
    shower = sub.add_parser("show")
    shower.add_argument("id")
    shower.add_argument("--target", help="a researched company: list the values this question matches")
    shower.set_defaults(fn=cmd_show)
    setter = sub.add_parser("set")
    setter.add_argument("id")
    setter.add_argument("field", choices=SETTABLE)
    setter.add_argument("value")
    setter.set_defaults(fn=cmd_set)
    example = sub.add_parser("example")
    for name in ("id", "company", "field", "value"):
        example.add_argument(name)
    example.set_defaults(fn=cmd_example)
    for name in ("skip", "unskip"):
        skip = sub.add_parser(name)
        skip.add_argument("id")
        skip.add_argument("company")
        if name == "skip":
            skip.add_argument("reason", nargs="?")
        skip.set_defaults(fn=cmd_skip)
    profile = sub.add_parser("profile")
    profile.add_argument("action", choices=["show", "set"])
    for name in ("company", "field", "value"):
        profile.add_argument(name, nargs="?")
    profile.set_defaults(fn=cmd_profile)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point; returns the exit status."""
    return common.run(build_parser().parse_args(argv), lock=True)


if __name__ == "__main__":
    raise SystemExit(main())
