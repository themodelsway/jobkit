#!/usr/bin/env python3
"""Interview-prep sessions, kept in prep/sessions/. Standard library only.

  sessions new "AWS fundamentals" [--mode architecture|stories|jd|leadership|tutor] [--topic architecture|leadership|stories] [--order default|random] [--category C] [--jd jd.txt]
                                   [--track T] [--area A] [--tier N] [--kind service|pair|scenario] [--company C] [--count 10]
  sessions list
  sessions resume ID         # what was covered, last answers, and the next item to ask
  sessions log ID ITEM --question Q --answer A|- [--grade G] [--confidence 0|1|2] [--quiz]
                                                 # --answer - reads the full answer from stdin
  sessions close ID
  sessions reopen ID          # continue a closed session

A session is one file with a queue of items (architecture cards or STAR stories) and an append-only log that
keeps your FULL answers. Re-drilling a topic in a later session adds a log entry there and never edits an old
session. Confidence per card is shared across sessions (prep/arch/progress.json).
"""
from __future__ import annotations

import argparse
import random
import re
import sys
from collections.abc import Sequence
from datetime import date
from typing import Any, Final, NotRequired, TypedDict, cast

from jobkit import common
from jobkit.common import ToolError
from jobkit.interview import arch
from jobkit.interview import lead
from jobkit.interview import prep, tables
from jobkit.resumes import query_resume as qr

ID_RE: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
MODE_KINDS: Final[dict[str, str]] = {"architecture": "architecture", "stories": "stories", "leadership": "leadership"}
SLUG_CHARS: Final[int] = 40
RESUME_PREVIEW: Final[int] = 300
now = common.now


class QueueItem(TypedDict):
    """One thing to ask: a card, a leadership question or a story."""

    id: str
    kind: str


class LogEntry(TypedDict):
    """One answered item, with the user's full answer."""

    at: str
    item: str
    kind: str
    question: str
    answer: str
    grade: NotRequired[str | None]
    confidence_after: NotRequired[int | None]
    tutor: NotRequired[bool]
    quiz: NotRequired[bool]


class Session(TypedDict):
    """prep/sessions/<id>.json."""

    id: str
    title: str
    mode: str
    topic: NotRequired[str]
    status: str
    created: str
    updated: str
    jd: NotRequired[str | None]
    queue: list[QueueItem]
    log: list[LogEntry]


# ---------------------------------------------------------------- storage

def get_session(sid: str) -> Session:
    """The session with this id."""
    session = tables.load_session(sid) if ID_RE.match(sid) else None
    if session is None:
        raise ToolError(f"No session {sid}. Run `sessions list`.")
    return cast(Session, session)


def put_session(session: Session) -> None:
    """Save the session (its log can only grow)."""
    session["updated"] = now()
    tables.save_session(session)


def known_kind(item: str) -> str | None:
    """card / leader / story for an id that exists in the data, else None (tolerates missing data files)."""
    if any(c["id"] == item for c in (tables.load_catalog() or {"cards": []})["cards"]):
        return "card"
    if tables.has_questions() and any(q["id"] == item for q in lead.cards()):
        return "leader"
    if tables.has_stories() and any(s["id"] == item for s in prep.stories()):
        return "story"
    return None


# ---------------------------------------------------------------- queues

def card_queue(args: argparse.Namespace, cards: list[arch.Card] | None = None) -> list[QueueItem]:
    """Cards not yet solid, lowest tier and weakest first (or random)."""
    cat, prog = arch.catalog(), arch.progress()["cards"]
    position = {c["id"]: i for i, c in enumerate(cat["cards"])}
    pool = cards if cards is not None else arch.flt(cat["cards"], args)
    pool = [c for c in pool if arch.progress_of(prog, c["id"])["confidence"] < 2]
    if getattr(args, "order", "default") == "random":
        random.shuffle(pool)
    else:
        pool.sort(key=lambda c: (c["tier"], arch.progress_of(prog, c["id"])["confidence"],
                                 arch.progress_of(prog, c["id"])["last_drilled"] or "", position[c["id"]]))
    return [{"id": c["id"], "kind": "card"} for c in pool]


def story_queue(args: argparse.Namespace, text: str | None = None) -> list[QueueItem]:
    """Stories not yet done (those with material first); with a JD, only relevant ones, best first."""
    stories = [s for s in prep.stories() if s["status"] != "done" and (not args.company or args.company == s["company"])]
    stories.sort(key=lambda s: (s["status"] == "empty", not s["engagement"]))   # material first: workable now
    if text is not None:
        analysis = qr.analyze(text)
        ranked = prep.ranked_scores(analysis)
        stories = [s for s in stories if prep.story_relevance(s, ranked, analysis.themes)]
        stories.sort(key=lambda s: -prep.story_relevance(s, ranked, analysis.themes))
    return [{"id": s["id"], "kind": "story"} for s in stories]


def build_queue(args: argparse.Namespace) -> tuple[list[QueueItem], str | None]:
    """(queue, jd path) for the new session's mode."""
    kind = args.topic if args.mode == "tutor" else MODE_KINDS.get(args.mode)
    if kind == "architecture":
        return card_queue(args), None
    if kind == "stories":
        return story_queue(args), None
    if kind == "leadership":
        return [{"id": q["id"], "kind": "leader"} for q in lead.ordered(args)], None
    if not args.jd:
        raise ToolError("--jd is required for mode jd")
    text = common.read_text_arg(args.jd)
    return card_queue(args, arch.matches(text, arch.catalog())) + story_queue(args, text), args.jd


def unique_session_id(title: str) -> str:
    """Date plus slug of the title, with -2, -3 ... when the id is taken."""
    base = f"{date.today().isoformat()}-{arch.slug(title)[:SLUG_CHARS]}"
    sid, n = base, 2
    while tables.session_exists(sid):
        sid, n = f"{base}-{n}", n + 1
    return sid


# ---------------------------------------------------------------- commands

def show_next(session: Session) -> None:
    """Print the first queued item that has no logged answer yet."""
    done = {e["item"] for e in session["log"]}
    for item in session["queue"]:
        if item["id"] in done:
            continue
        print(f"\nNext item ({item['kind']}):")
        if item["kind"] == "leader":
            lead.show(lead.find(item["id"]))
        elif item["kind"] == "card":
            arch.show(arch.find(arch.catalog(), item["id"]), arch.progress_of(arch.progress()["cards"], item["id"]))
        else:
            story = next((s for s in prep.stories() if s["id"] == item["id"]), None)
            if story:
                prep.show(story, prep.eng_of(story, prep.engagements()))
            else:
                print(f"  {item['id']}")
        return
    print("\nEvery queued item has been asked. Close the session or add more with `log`.")


def cmd_new(args: argparse.Namespace) -> None:
    """Start a session with a queue for the chosen mode and filters."""
    queue, jd = build_queue(args)
    queue = queue[:args.count]
    if not queue:
        raise ToolError("Nothing to ask for those filters (every item may already be solid, or no card matches "
                        "the JD). No session created.")
    sid = unique_session_id(args.title)
    session: Session = {"id": sid, "title": args.title, "mode": args.mode, "status": "open", "created": now(),
                        "updated": now(), "jd": jd, "queue": queue, "log": []}
    if args.mode == "tutor":
        session["topic"] = args.topic
    put_session(session)
    print(f"Started session {sid} with {len(queue)} items.")
    show_next(session)


def cmd_list(args: argparse.Namespace) -> None:
    """List sessions, newest first."""
    rows = tables.session_rows()
    if not rows:
        print("No sessions yet.")
        return
    for row in rows:
        print(f"  {row['id']:<50} {row['status']:<7} {row['mode']:<12} {row['logged']}/{row['total']} items  "
              f"(last: {row['updated'][:16]})")


def cmd_resume(args: argparse.Namespace) -> None:
    """Show what a session covered, its last answers, and the next item."""
    session = get_session(args.id)
    asked = len({e["item"] for e in session["log"]})
    print(f"Session {session['id']} | {session['title']} | {session['mode']} | {session['status']} | "
          f"JD: {session.get('jd') or '-'}")
    print(f"Started {session['created'][:16]}, updated {session['updated'][:16]}; "
          f"{asked} of {len(session['queue'])} items asked.")
    for entry in session["log"][-3:]:
        cut = "..." if len(entry["answer"]) > RESUME_PREVIEW else ""
        print(f"\n  [{entry['at'][:16]}] {entry['item']} (confidence after: {entry.get('confidence_after', '-')})"
              f"\n  Q: {entry['question']}\n  A: {entry['answer'][:RESUME_PREVIEW]}{cut}")
    if session["status"] == "open":
        show_next(session)


def resolve_item(session: Session, item: str) -> QueueItem | None:
    """The queue entry for `item`, or None if it is not queued; fails for an id that exists nowhere."""
    queued = next((x for x in session["queue"] if x["id"] == item), None)
    if queued is None and not known_kind(item):
        raise ToolError(f"Unknown item {item}. Use an id from arch list, lead list or prep status.")
    return queued


def check_log_flags(session: Session, args: argparse.Namespace, kind: str) -> None:
    """Reject confidence on stories and --quiz outside tutor sessions."""
    if args.confidence is not None and kind == "story":
        raise ToolError("Stories have no confidence: omit --confidence (use prep set for story status).")
    if args.quiz and (session["mode"] != "tutor" or not args.grade or args.confidence != 2):
        raise ToolError("--quiz is for tutor sessions only, and needs --grade (what the answer got right) "
                        "and --confidence 2.")


def record_confidence(kind: str, item: str, confidence: int, tutor: bool) -> None:
    """Save the confidence for a card or question; a lesson never lowers what a real drill earned."""
    if kind == "card":
        cards: dict[str, Any] = dict(arch.progress()["cards"])
        entry: dict[str, Any] = cards.setdefault(item, arch.blank_progress())
    else:
        cards = lead.prog()["questions"]
        entry = cards.setdefault(item, lead.blank())
    if not tutor or confidence > entry["confidence"]:
        entry["confidence"] = confidence
    entry["last_drilled"] = date.today().isoformat()
    if kind == "card":
        tables.save_progress(cards)
    else:
        tables.save_lead_progress(cards)


def cmd_log(args: argparse.Namespace) -> None:
    """Append the user's full answer to the session and record confidence."""
    session = get_session(args.id)
    if session["status"] != "open":
        raise ToolError(f"Session {session['id']} is closed. Run `sessions reopen {session['id']}` to continue it.")
    answer = sys.stdin.read().strip() if args.answer == "-" else args.answer.strip()
    if not answer:
        raise ToolError("Empty answer: nothing logged. Pass the user's full answer.")
    queued = resolve_item(session, args.item)
    kind = queued["kind"] if queued else known_kind(args.item) or ""
    check_log_flags(session, args, kind)
    if queued is None:
        session["queue"].append({"id": args.item, "kind": kind})
    tutor = session["mode"] == "tutor"
    confidence = args.confidence
    if tutor and confidence is not None and not args.quiz:
        confidence = min(confidence, 1)    # teaching alone never makes an item solid; only a graded, passed quiz does
    session["log"].append({"at": now(), "item": args.item, "kind": kind, "question": args.question, "answer": answer,
                           "grade": args.grade, "confidence_after": confidence, "tutor": tutor,
                           "quiz": bool(args.quiz)})
    if confidence is not None:
        record_confidence(kind, args.item, confidence, tutor)
    put_session(session)
    print(f"Logged answer for {args.item} in {session['id']} ({len(session['log'])} entries)."
          + (f" Confidence recorded: {confidence}." if confidence is not None else ""))


def set_status(args: argparse.Namespace, status: str, verb: str) -> Session:
    """Change a session's status and say so."""
    session = get_session(args.id)
    session["status"] = status
    put_session(session)
    print(f"{verb} {session['id']}.")
    return session


def cmd_close(args: argparse.Namespace) -> None:
    """Close a session."""
    set_status(args, "closed", "Closed")


def cmd_reopen(args: argparse.Namespace) -> None:
    """Reopen a closed session and show the next item."""
    show_next(set_status(args, "open", "Reopened"))


# ---------------------------------------------------------------- entry point

def build_parser() -> argparse.ArgumentParser:
    """The command-line parser."""
    parser = common.make_parser(__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    new = sub.add_parser("new")
    new.add_argument("title")
    new.add_argument("--mode", choices=["architecture", "stories", "jd", "leadership", "tutor"], default="architecture")
    new.add_argument("--jd")
    new.add_argument("--track")
    new.add_argument("--area")
    new.add_argument("--tier", type=int)
    new.add_argument("--kind", choices=list(arch.KINDS))
    new.add_argument("--company")
    new.add_argument("--order", choices=["default", "random"], default="default")
    new.add_argument("--topic", choices=["architecture", "leadership", "stories"], default="architecture",
                     help="tutor mode: what to teach")
    new.add_argument("--category")
    new.add_argument("--count", type=int, default=10)
    new.set_defaults(fn=cmd_new)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    for name, fn in (("resume", cmd_resume), ("close", cmd_close), ("reopen", cmd_reopen)):
        one = sub.add_parser(name)
        one.add_argument("id")
        one.set_defaults(fn=fn)
    log = sub.add_parser("log")
    log.add_argument("id")
    log.add_argument("item")
    log.add_argument("--question", required=True)
    log.add_argument("--answer", required=True)
    log.add_argument("--grade")
    log.add_argument("--quiz", action="store_true",
                     help="tutor mode only: a quiz was answered correctly (needs --grade and --confidence 2)")
    log.add_argument("--confidence", type=int, choices=[0, 1, 2])
    log.set_defaults(fn=cmd_log)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point; returns the exit status."""
    return common.run(build_parser().parse_args(argv), lock=True)


if __name__ == "__main__":
    raise SystemExit(main())
