#!/usr/bin/env python3
"""Resume line length: find the stored lines over the limit and check a shorter wording before it is saved.

A shorter wording is the user's own: the agent proposes it only when asked, the user accepts it, and it is saved with
`process-resumes curate add short-wording ID TEXT`. A stored line is never changed. A wording is accepted only when it
is within the limit and keeps every figure of the original; named terms it drops are warnings for the user to judge.

Commands:
  resume-lines list [--all]        stored lines over the limit (every line with --all), with their length
  resume-lines show ID             one line: its length, other stored wordings, and any approved wording
  resume-lines validate ID TEXT    check a proposed wording; exit status 1 when it is not acceptable

Standard library only. Run it as the `resume-lines` command.
"""
from __future__ import annotations

import argparse
import re
from collections.abc import Sequence
from typing import Final

from jk import common
from jk.common import ToolError
from jk.resumes import resume_data as rd
from jk.resumes.resume_data import LINE_LIMIT, LINE_WARN, Bullet, Company

FIGURE: Final[re.Pattern[str]] = re.compile(
    r"(?P<sign>(?<![A-Za-z0-9)%])[-\u2212\u2013](?=\$?\d))?(?<![A-Za-z0-9])\$?\d[\d,]*(?:\.\d+)?"
    r"\s*(?:%|percent\b|million\b|billion\b|thousand\b|[kmb]\b)?", re.I)   # a minus counts only in front of a number, not in "5-10"
WORD_SHORTHAND: Final[dict[str, str]] = {"percent": "%", "million": "m", "billion": "b", "thousand": "k"}
NAMED: Final[re.Pattern[str]] = re.compile(r"[A-Za-z][A-Za-z0-9+#./-]*")


def figures(text: str) -> set[str]:
    """The figures in a line in one spelling ("70 percent" and "70%" are the same)."""
    found = set()
    for match in FIGURE.finditer(text):
        value = re.sub(r"[\s,]", "", match.group(0).lower())
        value = re.sub(r"^[\u2212\u2013]", "-", value)         # every minus sign is one spelling
        found.add(re.sub("|".join(WORD_SHORTHAND), lambda m: WORD_SHORTHAND[m.group(0)], value))
    return found


def named_terms(text: str) -> set[str]:
    """Product, company and acronym names: words with a capital after the first letter or a digit, and capitalised
    words that do not start the line."""
    terms = set()
    for match in NAMED.finditer(text):
        word = match.group(0).strip(".-/")
        interior = any(c.isupper() or c.isdigit() for c in word[1:])
        if len(word) > 1 and (interior or (word[0].isupper() and match.start() > 0)):
            terms.add(word.lower())
    return terms


def problems(original: str, wording: str) -> tuple[list[str], list[str]]:
    """(errors, warnings) for a proposed wording of a line. Errors: empty, over the limit, a figure dropped or added.
    Warnings: named terms the wording no longer contains."""
    errors: list[str] = []
    if not wording.strip():
        return ["the wording is empty"], []
    if len(wording) > LINE_LIMIT:
        errors.append(f"{len(wording)} characters; the limit is {LINE_LIMIT}")
    before, after = figures(original), figures(wording)
    if before - after:
        errors.append("figures dropped: " + ", ".join(sorted(before - after)))
    if after - before:
        errors.append("figures added: " + ", ".join(sorted(after - before)))
    dropped = sorted(named_terms(original) - {w.lower().strip(".-/") for w in NAMED.findall(wording)})
    return errors, ([f"terms no longer present: {', '.join(dropped)}"] if dropped else [])


def find_bullet(bullet_id: str) -> tuple[Company, Bullet]:
    """The stored company and line with this id."""
    for company in rd.load_companies().values():
        for bullet in company["bullets"]:
            if bullet["id"] == bullet_id:
                return company, bullet
    raise ToolError(f"No stored line {bullet_id}. `resume-lines list` shows the ids.")


def require_acceptable(bullet_id: str, wording: str) -> None:
    """Raise ToolError unless the wording is an acceptable shorter version of the stored line."""
    errors, _ = problems(find_bullet(bullet_id)[1]["text"], wording)
    if errors:
        raise ToolError(f"That wording is not accepted for {bullet_id}: " + "; ".join(errors))


def cmd_list(args: argparse.Namespace) -> None:
    """Print the stored lines over the limit (or every line), longest first."""
    approved = rd.load_curated().get("short_wording", {})
    rows = [(len(b["text"]), b["id"], c["name"], b["text"]) for c in rd.load_companies().values()
            for b in c["bullets"] if not b.get("ignored") and (args.all or len(b["text"]) > LINE_LIMIT)]
    for length, bullet_id, company, text in sorted(rows, reverse=True):
        note = ("  [FAR OVER the limit]" if length > LINE_WARN else "") + ("  [approved wording saved]" if bullet_id in approved else "")
        print(f"{bullet_id}  {length}  {company}{note}\n    {text}")
    print(f"{len(rows)} line(s)" + ("" if args.all else f" over {LINE_LIMIT} characters") + ".")


def cmd_show(args: argparse.Namespace) -> None:
    """Print one line with its length, its other stored wordings and any approved wording."""
    company, bullet = find_bullet(args.id)
    print(f"{bullet['id']}  {len(bullet['text'])} characters  {company['name']}\n    {bullet['text']}")
    for wording in sorted(set(rd.wordings_of(bullet)) - {bullet["text"]}):
        print(f"  other stored wording ({len(wording)} characters): {wording}")
    approved = rd.load_curated().get("short_wording", {}).get(bullet["id"])
    print(f"  approved wording ({len(approved)} characters): {approved}" if approved else "  no approved wording")


def cmd_validate(args: argparse.Namespace) -> int:
    """Check a proposed wording; status 1 when it is not acceptable."""
    errors, warnings = problems(find_bullet(args.id)[1]["text"], args.text)
    print(f"{len(args.text)} characters (limit {LINE_LIMIT})")
    for message in errors:
        print(f"  not acceptable: {message}")
    for message in warnings:
        print(f"  check: {message}")
    print("  acceptable" if not errors else "  not acceptable")
    return 1 if errors else 0


def build_parser() -> argparse.ArgumentParser:
    """The command-line parser."""
    parser = common.make_parser(__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    listing = sub.add_parser("list", help="stored lines over the limit")
    listing.add_argument("--all", action="store_true", help="every line, not only those over the limit")
    listing.set_defaults(fn=cmd_list)
    show = sub.add_parser("show", help="one line, its other wordings and any approved wording")
    show.add_argument("id")
    show.set_defaults(fn=cmd_show)
    validate = sub.add_parser("validate", help="check a proposed shorter wording")
    validate.add_argument("id")
    validate.add_argument("text")
    validate.set_defaults(fn=cmd_validate)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point; returns the exit status."""
    return common.run(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
