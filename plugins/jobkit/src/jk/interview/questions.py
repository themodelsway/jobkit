"""Save and practice interview questions for a role.

  questions list [ROLE]                       # saved questions and research status
  questions show ID                           # wording, source, evidence and confidence
  questions save ROLE --seed FILE|-           # JSON object with a questions list, add or replace by id
  questions none-found ROLE                   # date a search that found no qualifying source
  questions stale [ROLE]                      # citations or unsuccessful searches due for review
  questions remove ID                         # remove a question and its current progress
  questions personal ROLE [--jd FILE|-] [--requirement NAME] [--count N]
  questions set ID --confidence 0|1|2

Each saved question has a question and source. Sources are general, research, company and personal.
Research and company sources require a link, quote, pulled (YYYY-MM-DD) and vetted: true. General
and personal questions carry no citation. A personal question names a bullet or posting requirement.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any, Final

from jk import common
from jk.base import ToolError
from jk.interview import question_tables as qt
from jk.interview import targets
from jk.resumes import evidence
from jk.resumes import query_resume as qr
from jk.resumes import resume_data as rd

ID_PATTERN: Final = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
LABELS: Final = {"general": "general-knowledge", "research": "othersite-references",
                 "company": "company-references", "personal": "personal"}
EVIDENCE_FIELDS: Final = ("link", "quote", "pulled", "vetted")
PERSONAL_FIELDS: Final = ("bullet", "requirement")
OWNERSHIP: Final = re.compile(r"\b(?:led|owned|managed|directed|oversaw|supervised)\b", re.IGNORECASE)


def digest(value: str) -> str:
    """Create a stable fingerprint for a role or question."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def question_id(role: str, row: Mapping[str, Any]) -> str:
    """Namespace an optional local ID, or derive one from the question and its provenance."""
    prefix = f"{qt.ID_PREFIX}{digest(qt.key_of(role))}:"
    ident = row.get("id")
    if ident is None:
        basis = [row.get(field) for field in ("source", "question", "link", *PERSONAL_FIELDS)]
        return prefix + digest(json.dumps(basis, ensure_ascii=False))
    if isinstance(ident, str) and ID_PATTERN.fullmatch(ident.removeprefix(prefix)):
        return prefix + ident.removeprefix(prefix)
    raise ToolError("Use a lowercase question id with letters, numbers, hyphens or underscores (up to 64 characters).")


def read_role(value: str) -> str:
    """Normalize a nonempty role name."""
    role = " ".join(value.split())
    if not role:
        raise ToolError("Give a role name.")
    return role


def local_problems(row: Mapping[str, Any]) -> list[str]:
    """Check local provenance and reject reference metadata on local prompts."""
    if any(row.get(field) is not None for field in EVIDENCE_FIELDS):
        return ["local questions cannot have citation fields"]
    provided = [field for field in PERSONAL_FIELDS if row.get(field) is not None]
    if row["source"] == "general" and provided:
        return ["general-knowledge questions cannot name a personal reference"]
    if row["source"] == "personal" and (len(provided) != 1 or not text_value(row[provided[0]])):
        return ["a personal question must name one resume bullet or posting requirement"]
    return []


def text_value(value: Any) -> bool:
    """Check for text with at least one nonspace character."""
    return isinstance(value, str) and bool(value.strip())


def clean_question(role: str, raw: object, today: date) -> qt.Question:
    """Validate a question and normalize the fields that will be stored."""
    if not isinstance(raw, dict):
        raise ToolError("each question must be a JSON object")
    source = raw.get("source")
    if not isinstance(source, str) or source not in LABELS:
        raise ToolError(f"use a source of {', '.join(LABELS)}")
    if not text_value(raw.get("question")):
        raise ToolError("give the question wording")
    label = LABELS[source]
    problems = targets.reference_problems(raw, today) if source in qt.CITED_SOURCES else local_problems(raw)
    if source in qt.CITED_SOURCES and any(raw.get(field) is not None for field in PERSONAL_FIELDS):
        problems.append("cited questions cannot name a personal reference")
    if raw.get("label", label) != label:
        problems.append(f"use the label {label}")
    if problems:
        raise ToolError(". ".join(problems))
    row = qt.Question(id=question_id(role, raw), source=source, label=label, question=raw["question"].strip(),
                      link=raw.get("link"), pulled=raw.get("pulled"))
    if source in qt.CITED_SOURCES:
        row.update(quote=raw["quote"].strip(), vetted=True)
    if raw.get("bullet") is not None:
        row["bullet"] = raw["bullet"].strip()
    if raw.get("requirement") is not None:
        row["requirement"] = raw["requirement"].strip()
    return row


def read_batch(role: str, raw: str, today: date) -> list[qt.Question]:
    """Read and validate every row before writing any question."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ToolError(f"The save is not valid JSON ({exc}).") from exc
    if not isinstance(data, dict):
        raise ToolError("The save must be a JSON object with a questions list.")
    if "role" in data and (not text_value(data["role"]) or qt.key_of(data["role"]) != qt.key_of(role)):
        raise ToolError("Nothing was saved: the role in the seed does not match the requested role.")
    rows = data.get("questions")
    if not isinstance(rows, list) or not rows:
        raise ToolError("Nothing was saved: give a nonempty questions list.")
    checked: dict[str, qt.Question] = {}
    for position, row in enumerate(rows, 1):
        try:
            question = clean_question(role, row, today)
            if question["id"] in checked:
                raise ToolError("duplicate question id")
        except ToolError as exc:
            raise ToolError(f"Nothing was saved. Question {position}: {exc}.") from exc
        checked[question["id"]] = question
    bullets = {q["bullet"] for q in checked.values() if "bullet" in q}
    if bullets:
        known = {b["id"] for company in rd.load_companies().values() for b in company["bullets"] if evidence.admissible(b)}
        if missing := bullets - known:
            raise ToolError("Nothing was saved: unavailable resume bullet(s): " + ", ".join(sorted(missing)))
    return list(checked.values())


def stale_ids(role: qt.RoleResearch, window: int, today: date) -> list[str]:
    """List stale citations in their saved order."""
    return targets.stale_facts({"facts": [q for q in role["questions"] if q["pulled"]]}, window, today)


def research_state(role: qt.RoleResearch, window: int, today: date) -> str:
    """Describe a role's research status without treating local questions as research."""
    if role["outcome"] == qt.NOT_RESEARCHED:
        return qt.NOT_RESEARCHED
    return targets.state({"outcome": role["outcome"], "researched": role["researched"],
                          "facts": [q for q in role["questions"] if q["pulled"]]}, window, today)


def show(question: qt.Question, progress: qt.Progress | None = None) -> None:
    """Display the question, provenance and confidence."""
    print(f"  {question['id']} [{question['label']}]: {question['question']}")
    if question["link"]:
        print(f"    {question['link']} (read {question['pulled']})")
        print(f"    Quote: {question.get('quote', '')}")
    if "bullet" in question:
        print(f"    Resume line: {question['bullet']}")
    if "requirement" in question:
        print(f"    Posting requirement: {question['requirement']}")
    print(f"    Confidence: {progress['confidence'] if progress else 0}")


def cmd_list(args: argparse.Namespace) -> None:
    """List roles, research state and saved questions."""
    roles = qt.load_roles(args.role)
    if not roles:
        print("No role questions or research saved.")
    window, today = targets.research_days(), date.today()
    for role in roles:
        print(f"{role['role']} (research: {research_state(role, window, today)})")
        for question in role["questions"]:
            print(f"  {question['id']} [{question['label']}]: {question['question']}")


def show_saved(item: str) -> None:
    """Show one saved question by ID."""
    question = qt.find(item)
    if question is None:
        raise ToolError(f"Unknown role question {item}. Use questions list.")
    show(question, qt.load_progress().get(item))


def cmd_show(args: argparse.Namespace) -> None:
    """Show the requested question."""
    show_saved(args.id)


def cmd_save(args: argparse.Namespace) -> None:
    """Save an entire question batch or refuse it with no changes."""
    role = read_role(args.role)
    questions = read_batch(role, common.read_text_arg(args.seed), date.today())
    qt.save_questions(role, questions)
    print(f"Saved {len(questions)} question(s) for {role}.")


def cmd_none_found(args: argparse.Namespace) -> None:
    """Record that a search found no qualifying questions."""
    role = read_role(args.role)
    today = date.today()
    qt.record_none_found(role, today)
    print(f"Recorded no qualifying sources for {role} on {today.isoformat()}.")


def cmd_stale(args: argparse.Namespace) -> None:
    """List stale question citations or expired unsuccessful searches."""
    window, today = targets.research_days(), date.today()
    stale = [role for role in qt.load_roles(args.role) if research_state(role, window, today) == "stale"]
    for role in stale:
        ids = stale_ids(role, window, today)
        detail = ", ".join(ids) if ids else f"no qualifying sources on {role['researched']}"
        print(f"  {role['role']}: {detail}")
    if not stale:
        print(f"No stale role research (window: {window} days).")


def cmd_remove(args: argparse.Namespace) -> None:
    """Remove a stored question and its progress."""
    qt.remove_question(args.id)
    print(f"Removed {args.id}.")


def claim_prompts(companies: Mapping[str, rd.Company]) -> list[tuple[int, dict[str, str]]]:
    """Use the stored wording and dates to ask about figures, ownership and role transitions."""
    prompts: list[tuple[int, dict[str, str]]] = []
    for company in rd.newest_first(companies.values()):
        starts = sorted({role["start"] for role in company["roles"] if role["start"]})
        transitions: set[str] = set(starts[1:])
        for bullet in company["bullets"]:
            if not evidence.admissible(bullet):
                continue
            text, start = bullet["text"], bullet["role_start"]
            ref = {"source": "personal", "bullet": bullet["id"]}
            if bullet["metrics"]:
                prompts.append((0, {**ref, "question": f"How did you measure the result in this claim? {text}"}))
            if OWNERSHIP.search(text):
                prompts.append((1, {**ref, "question": f"What did you own, and what did others contribute? {text}"}))
            if start and start in transitions:
                prompt = f"How did your responsibilities change in the role where you did this? {text}"
                prompts.append((2, {**ref, "question": prompt}))
                transitions.remove(start)
    return prompts


def cmd_personal(args: argparse.Namespace) -> None:
    """Generate local practice questions from stored claims and posting gaps."""
    role = read_role(args.role)
    if args.requirement and not args.jd:
        raise ToolError("--requirement needs --jd.")
    gaps: list[dict[str, str]] = []
    if args.jd:
        analysis = qr.analyze(common.read_text_arg(args.jd), requirements=args.requirement)
        gaps = [{"source": "personal", "requirement": name,
                 "question": f"What relevant experience, if any, could you discuss for this requirement: {name}?"}
                for name in analysis.need if name not in analysis.covered]
    claims = [row for _, row in sorted(claim_prompts(rd.load_companies()), key=lambda item: item[0])]
    rows = list({row["question"]: row for row in gaps + claims}.values())[:args.count]
    if not rows:
        print("No resume claims or posting gaps matched.")
        return
    qt.save_questions(role, [clean_question(role, row, date.today()) for row in rows])
    print(f"Saved {len(rows)} personal question(s) for {role}.")


def cmd_set(args: argparse.Namespace) -> None:
    """Record the confidence from practicing a saved question."""
    qt.set_progress(args.id, qt.Progress(confidence=args.confidence, last_drilled=date.today().isoformat()))
    print(f"Recorded confidence {args.confidence} for {args.id}.")


def build_parser() -> argparse.ArgumentParser:
    """Build the questions command-line parser."""
    parser = common.make_parser(__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name, handler in (("list", cmd_list), ("stale", cmd_stale), ("none-found", cmd_none_found),
                          ("save", cmd_save), ("personal", cmd_personal)):
        command = sub.add_parser(name)
        command.add_argument("role", nargs="?" if name in ("list", "stale") else None)
        command.set_defaults(fn=handler)
        if name == "save":
            command.add_argument("--seed", required=True, help="a JSON file or - for standard input")
        if name == "personal":
            command.add_argument("--jd", help="a job posting file or - for standard input")
            command.add_argument("--requirement", action="append", default=[], help="a requirement from the posting")
            command.add_argument("--count", type=common.positive_int, default=10)
    for name, handler in (("show", cmd_show), ("remove", cmd_remove), ("set", cmd_set)):
        command = sub.add_parser(name)
        command.add_argument("id")
        command.set_defaults(fn=handler)
        if name == "set":
            command.add_argument("--confidence", type=int, choices=[0, 1, 2], required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the questions command inside one transaction."""
    return common.run_writer(build_parser().parse_args(argv), {cmd_list, cmd_show, cmd_stale})


if __name__ == "__main__":
    raise SystemExit(main())
