#!/usr/bin/env python3
"""Researched target companies: how a company hires, each fact with its reference link. Standard library only.

  target list                         # every researched company with its state
  target show [NAME]                  # values, rounds, grading notes, typical questions, suggested style, state
                                      # (no NAME: the profile's default company, `profile set target_company`)
  target save NAME --seed FILE|-      # add facts or replace them by id; all or nothing
  target none-found NAME              # research found no qualifying page (dated; not repeated while fresh)
  target stale                        # companies whose facts are older than the research window, with the fact ids
  target recheck NAME FACT [--remove] # the page still says it (date of pull set to today), or, after the user
                                      # responds with yes, --remove a fact the page no longer says
  target remove NAME                  # remove a company and its facts (says how many sessions name it)

Nothing is shipped: the interview-prep skill tells the agent to research a company and save what it vetted. The
command never reads a page; it refuses what it can see is wrong. A save is JSON:

  {"name": "Company X",
   "facts": [{"id": "v1", "kind": "value", "name": "Ownership", "wording": "What the quote says, briefly.",
              "quote": "A short passage copied word for word from the page.", "link": "https://...",
              "label": "company-references", "pulled": "YYYY-MM-DD", "vetted": true,
              "themes": ["team-leadership"], "hints": ["deadline"]},
             {"id": "q1", "kind": "question", "value": "v1", "wording": "...", "quote": "...", ...}],
   "suggested_style": {"style": "star", "basis": "stated", "facts": ["g1"]}}

  kind      value, round, grading, question (optional "value": the id of its value), questioning
  label     company-references (a site the company publishes) or othersite-references (any other site)
  vetted    true: the agent read the page, the quote is on it, and it is not written by individual users
  quote     at most 40 words; links on known user-content sites (forums, reviews, salary pages) are refused
  themes, hints   a value's mapping to the user's stories (theme names, whole words); not claims about the company
"""
from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import date
from typing import Any

from jk import common
from jk.common import ToolError
from jk.interview import lead, prep, tables, targets
from jk.interview import target_tables as tt
from jk.user import profile

KIND_TITLES = (("value", "Values"), ("round", "Rounds"), ("grading", "What graders look for"),
               ("questioning", "Questioning style"))


def user_items() -> list[targets.Item]:
    """The user's stories and leadership questions, as the matching sees them."""
    items = [targets.story_item(s) for s in prep.stories()] if tables.has_stories() else []
    if tables.has_questions():
        progress = lead.prog()["questions"]
        items += [targets.question_item(q, progress.get(q["id"])) for q in lead.cards()]
    return items


def sessions_naming(name: str) -> int:
    """How many sessions name this company."""
    return sum(1 for s in tables.all_sessions() if tt.key_of(str(s.get("target") or "")) == tt.key_of(name))


def cmd_list(args: argparse.Namespace) -> None:
    """Every researched company with its state."""
    companies = tt.load_companies()
    if not companies:
        print("No researched companies yet.")
        return
    window, today = targets.research_days(), date.today()
    for company in companies:
        style = f", suggested style {company['style']}" if company.get("style") else ""
        print(f"  {company['name']:<30} {targets.state(company, window, today):<14} {len(company['facts'])} facts, "
              f"researched {company['researched']}{style}")


def _print_kind(company: dict[str, Any], kind: str, title: str) -> None:
    """One group of facts, with each fact's link; a value also shows its mapping and its typical questions."""
    facts = [f for f in company["facts"] if f["kind"] == kind]
    if not facts:
        return
    print(f"\n{title}")
    for fact in facts:
        print(f"  {targets.fact_text(fact)}\n      {fact['link']}")
        if kind == "value":
            mapping = ", ".join(fact.get("themes", [])) or "-", ", ".join(fact.get("hints", [])) or "-"
            print(f"      themes: {mapping[0]} | hint words: {mapping[1]}")
            for question in targets.questions_for(company, fact["id"]):
                print(f"      Q: {targets.fact_text(question)}")


def cmd_show(args: argparse.Namespace) -> None:
    """One company's profile: its facts by kind, the suggested style and its state."""
    company = targets.find(args.name, use_default=True, none_found=True)
    if company["outcome"] == targets.NONE_FOUND:
        print(f"{company['name']}: {targets.state(company, targets.research_days(), date.today())} "
              f"(no qualifying page was found on {company['researched']})")
        return
    if not args.name:
        print(f"(the default company, {company['name']})")
    window = targets.research_days()
    status = targets.state(company, window, date.today())
    stale = targets.stale_facts(company, window, date.today())
    print(f"{company['name']}: {status}" + (f" (stale facts: {', '.join(stale)})" if stale else ""))
    print(targets.suggestion_text(company) or "suggested style: none")
    for kind, title in KIND_TITLES:
        _print_kind(company, kind, title)
    loose = [f for f in company["facts"] if f["kind"] == "question" and not f.get("value")]
    if loose:
        print("\nTypical questions")
        for fact in loose:
            print(f"  {targets.fact_text(fact)}\n      {fact['link']}")


def cmd_save(args: argparse.Namespace) -> None:
    """Add facts to a company, or replace them by id; nothing is stored when any part is refused."""
    data = targets.read_save(common.read_text_arg(args.seed))
    if data.get("name") and tt.key_of(str(data["name"])) != tt.key_of(args.name):
        raise ToolError(f"Nothing was saved: the save is for {data['name']!r}, not {args.name!r}.")
    existing = tt.load_company(args.name)
    company = targets.merge_save(existing, {**data, "name": args.name}, date.today())
    tt.save_company(company)
    if existing and existing["name"] != args.name:
        print(f"Saved to the existing profile {existing['name']} (names are compared without regard to case).")
    print(f"Saved {len(data.get('facts', []))} fact(s) for {company['name']}; it now has {len(company['facts'])}.")
    unknown = targets.unknown_themes(company, user_items())
    if unknown:
        print("Warning: these themes match none of your stories or questions yet: " + ", ".join(unknown))


def cmd_none_found(args: argparse.Namespace) -> None:
    """Record that research found no qualifying page, dated today."""
    existing = tt.load_company(args.name)
    if existing and existing["facts"]:
        raise ToolError(f"{existing['name']} has {len(existing['facts'])} stored facts; re-check them with "
                        "`target recheck` instead of recording none found.")
    name = existing["name"] if existing else args.name.strip()
    tt.save_company({"key": tt.key_of(name), "name": name, "outcome": targets.NONE_FOUND,
                     "researched": date.today().isoformat(), "style": None, "style_basis": None,
                     "style_facts": [], "facts": []})
    print(f"Recorded that no qualifying page was found for {name} ({date.today().isoformat()}). It is not researched "
          f"again for {targets.research_days()} days.")


def cmd_stale(args: argparse.Namespace) -> None:
    """Companies that are stale, with the facts to read again."""
    window, today = targets.research_days(), date.today()
    stale = [c for c in tt.load_companies() if targets.state(c, window, today) == "stale"]
    for company in stale:
        ids = targets.stale_facts(company, window, today)
        print(f"  {company['name']}: " + (f"facts {', '.join(ids)}" if ids else
                                         f"none found on {company['researched']}, research again"))
    if not stale:
        print(f"No stale companies (window: {window} days).")


def cmd_recheck(args: argparse.Namespace) -> None:
    """The page still says the fact (date of pull set to today), or remove a fact the page no longer says."""
    company = targets.find(args.name)
    fact = next((f for f in company["facts"] if f["id"] == args.fact), None)
    if fact is None:
        raise ToolError(f"{company['name']} has no fact {args.fact!r}. Its facts: "
                        + ", ".join(f["id"] for f in company["facts"]))
    if args.remove:
        kept_facts = [f for f in company["facts"]
                      if f["id"] != args.fact and not (f["kind"] == "question" and f.get("value") == args.fact)]
        if not kept_facts:
            raise ToolError(f"Removing {args.fact} would leave {company['name']} with no facts, so nothing was "
                            f"removed. To drop its research, use `target remove {company['name']}`.")
        company["facts"] = kept_facts
        kept = [i for i in company.get("style_facts", []) if i in {f["id"] for f in company["facts"]}]
        if company.get("style") and not kept:
            company.update(style=None, style_basis=None)
            print("The suggested style rested only on removed facts, so it was removed too.")
        company["style_facts"] = kept
        verb = "Removed"
    else:
        fact["pulled"] = date.today().isoformat()
        verb = "Re-checked"
    tt.save_company(company)
    print(f"{verb} {args.fact} of {company['name']}.")


def cmd_remove(args: argparse.Namespace) -> None:
    """Remove a company and its facts; sessions that name it keep working."""
    found = tt.load_company(args.name)
    if found is None:
        raise ToolError(f"No researched company {args.name!r}. Researched companies: "
                        + (", ".join(tt.company_names()) or "none yet"))
    tt.remove_company(args.name)
    used = sessions_naming(found["name"])
    default = " It is the default company in the profile, which now names a company that does not exist." \
        if tt.key_of(profile.target_company() or "") == found["key"] else ""
    print(f"Removed {found['name']}. {used} session(s) name it; they keep working without its profile.{default}")


def build_parser() -> argparse.ArgumentParser:
    """The command-line parser."""
    parser = common.make_parser(__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    show = sub.add_parser("show")
    show.add_argument("name", nargs="?")
    show.set_defaults(fn=cmd_show)
    save = sub.add_parser("save")
    save.add_argument("name")
    save.add_argument("--seed", required=True, help="the save as JSON: a file, or - for standard input")
    save.set_defaults(fn=cmd_save)
    for name, fn in (("none-found", cmd_none_found), ("remove", cmd_remove)):
        one = sub.add_parser(name)
        one.add_argument("name")
        one.set_defaults(fn=fn)
    sub.add_parser("stale").set_defaults(fn=cmd_stale)
    recheck = sub.add_parser("recheck")
    recheck.add_argument("name")
    recheck.add_argument("fact")
    recheck.add_argument("--remove", action="store_true", help="the page no longer says it and the user agreed")
    recheck.set_defaults(fn=cmd_recheck)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point; returns the exit status."""
    readers = {cmd_list, cmd_show, cmd_stale}   # these change nothing
    return common.run_writer(build_parser().parse_args(argv), readers)


if __name__ == "__main__":
    raise SystemExit(main())
