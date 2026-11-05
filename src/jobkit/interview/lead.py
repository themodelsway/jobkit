#!/usr/bin/env python3
"""Leadership interview questionnaire, kept in prep/leadership/. Standard library only.

  python src/interview/lead.py init                      # create/extend questions + progress (never overwrites answers)
  python src/interview/lead.py status                    # per category: confidence counts; profile gaps
  python src/interview/lead.py next [--category C] [--order default|random]
  python src/interview/lead.py show ID                   # question, profile facts, candidate stories for the top 3 companies, saved answers
  python src/interview/lead.py list [--category C]
  python src/interview/lead.py set ID principle|notes|confidence VALUE      # principle = "how I handle this" in your own words
  python src/interview/lead.py example ID COMPANY FIELD VALUE               # FIELD: situation task action result metric
  python src/interview/lead.py profile show
  python src/interview/lead.py profile set COMPANY FIELD VALUE              # factual scope: team sizes, reports, budget, cadence...

Every question can hold a principle plus one STAR example per company (the most recent three: see TOP_N).
Candidate stories come from prep.py (resume-based stories whose themes match); a finished story there can be reused.
"""
from __future__ import annotations

import argparse
import random
from collections import defaultdict
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any, Final, NamedTuple, TypedDict

from jobkit import common
from jobkit.common import ToolError
from jobkit.interview import arch
from jobkit.interview import prep
from jobkit.interview.story_model import Story
from jobkit.resumes import query_resume as qr
from jobkit.resumes.resume_data import Company

DIR: Path = arch.ROOT / "prep" / "leadership"
QUESTIONS: Path = DIR / "questions.json"
PROGRESS: Path = DIR / "progress.json"
PROFILE: Path = DIR / "profile.json"
TOP_N: Final[int] = 3
STAR: Final[tuple[str, ...]] = ("situation", "task", "action", "result", "metric")
PROFILE_FIELDS: Final[tuple[str, ...]] = ("title", "direct_reports", "indirect_team", "team_composition", "budget",
                                          "stakeholders", "reporting_to", "cadence", "notes")
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


# `init` keeps only the themes that appear in the user's own scanned resume data (resume-data/json/index.json),
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


def cards() -> list[Question]:
    """All questions; fails when `init` has not run."""
    if not QUESTIONS.exists():
        raise ToolError("No prep/leadership/questions.json yet: run `lead.py init` first.")
    return arch.load(QUESTIONS, {})["questions"]


def prog() -> dict[str, Any]:
    """prep/leadership/progress.json: {"questions": {id: QuestionProgress}}."""
    return arch.load(PROGRESS, {"questions": {}})


def find(qid: str) -> Question:
    """The question with this id."""
    for question in cards():
        if question["id"] == qid:
            return question
    raise ToolError(f"No question {qid}")


def user_themes() -> set[str] | None:
    """Themes found in the user's resume data, or None when there is no resume data yet."""
    try:
        return set(common.load_json(qr.DATA / "index.json", {})["themes"])
    except (OSError, KeyError, ValueError):
        return None


def require_top_company(company: str) -> None:
    """Fail unless the company is one of the top companies."""
    ids = top_company_ids()
    if company not in ids:
        raise ToolError("COMPANY must be one of " + ", ".join(ids))


# ---------------------------------------------------------------- commands

def cmd_init(args: argparse.Namespace) -> None:
    """Create or extend the questions, progress and company profiles."""
    mine = user_themes()
    old = {q["id"]: q for q in arch.load(QUESTIONS, {"questions": []})["questions"]}
    out: list[Question] = []
    added = 0
    for seed in SEED:
        added += seed.id not in old
        old.pop(seed.id, None)
        out.append({"id": seed.id, "category": seed.category, "question": seed.question,
                    "themes": [t for t in seed.themes if mine is None or t in mine]})
    out += list(old.values())
    arch.save(QUESTIONS, {"questions": out})
    progress = prog()
    for question in out:
        progress["questions"].setdefault(question["id"], blank())
    arch.save(PROGRESS, progress)
    profile = arch.load(PROFILE, {"companies": {}})
    ids = top_company_ids()
    for cid in ids:
        profile["companies"].setdefault(cid, blank_profile())
    arch.save(PROFILE, profile)
    print(f"{len(out)} questions ({added} new) in {QUESTIONS.relative_to(arch.ROOT)}; profile for {', '.join(ids)}")


def show_profile(only: Sequence[str] | None = None) -> None:
    """Print the factual scope (team sizes, budget ...) saved per company."""
    for cid, facts in arch.load(PROFILE, {"companies": {}})["companies"].items():
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


def cmd_show(args: argparse.Namespace) -> None:
    """Show one question."""
    show(find(args.id))


def in_category(question: Question, category: str | None) -> bool:
    """Whether the question belongs to the (partially typed) category filter."""
    return not category or category.lower() in question["category"].lower()


def cmd_list(args: argparse.Namespace) -> None:
    """List questions with confidence and example counts."""
    progress = prog()["questions"]
    for question in cards():
        if in_category(question, args.category):
            p = progress.get(question["id"], blank())
            print(f"  {question['id']:<24} {question['category']:<28} {arch.CONF[p['confidence']]:<12} "
                  f"{len(p['examples'])}/{TOP_N} examples")


def ordered(args: argparse.Namespace) -> list[Question]:
    """Questions not yet solid: weakest and least recently drilled first (or random)."""
    progress = prog()["questions"]
    todo = [q for q in cards() if in_category(q, args.category) and progress.get(q["id"], blank())["confidence"] < 2]
    if getattr(args, "order", "default") == "random":
        random.shuffle(todo)
    else:
        todo.sort(key=lambda q: (progress.get(q["id"], blank())["confidence"],
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
    profile = arch.load(PROFILE, {"companies": {}})["companies"]
    gaps = [cid for cid, facts in profile.items() if not any(facts.values())]
    print("\nProfile facts missing for: " + (", ".join(gaps) or "none"))


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
    arch.save(PROGRESS, progress)
    print(f"Updated {args.id}.{args.field}")


def cmd_example(args: argparse.Namespace) -> None:
    """Save one STAR field of the user's example for a question and company."""
    find(args.id)
    require_top_company(args.company)
    if args.field not in STAR:
        raise ToolError("FIELD must be one of " + ", ".join(STAR))
    progress = prog()
    entry = progress["questions"].setdefault(args.id, blank())
    entry["examples"].setdefault(args.company, {})[args.field] = args.value
    arch.save(PROGRESS, progress)
    print(f"Updated {args.id} example for {args.company}.{args.field}")


def cmd_profile(args: argparse.Namespace) -> None:
    """Show the company profiles, or set one fact (team size, budget ...)."""
    if args.action == "show":
        show_profile()
        return
    if args.company is None or args.field not in PROFILE_FIELDS:
        raise ToolError("usage: profile set COMPANY FIELD VALUE; FIELD in " + ", ".join(PROFILE_FIELDS))
    require_top_company(args.company)
    profile = arch.load(PROFILE, {"companies": {}})
    profile["companies"].setdefault(args.company, blank_profile())[args.field] = args.value
    arch.save(PROFILE, profile)
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
    listing.set_defaults(fn=cmd_list)
    shower = sub.add_parser("show")
    shower.add_argument("id")
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
