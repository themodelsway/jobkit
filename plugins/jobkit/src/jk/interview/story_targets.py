"""`prep for-target`: the user's stories ranked for a researched company, with every company value and its state.

Read-only: no story text is written. See `targets.py` for the matching and the four value states. Library module;
`prep` registers the subcommand with `add_parser`.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from jk.interview import styles, targets
from jk.interview.story_model import Engagement, Story


def _target_story_line(company: Mapping[str, Any], story: Story) -> str:
    """One ranked story: how it matches the company's values and whether it is complete in the suggested style."""
    found = targets.matches(company, targets.story_item(story))
    how = "; ".join(f"{value['name']} by {kind}" for value, kind in found) or "matches no value"
    line = f"{story['id']}  ({story['company_name']}, {story['status']})  {how}"
    if company.get("style"):
        missing = styles.missing_parts(company["style"], story)
        line += f" | complete in {company['style']}: " + ("yes" if not missing else
                                                          "no, missing " + ", ".join(p.name for p in missing))
    return line


def _gap_hint(value: Mapping[str, Any], engagements: Sequence[Engagement]) -> str:
    """Where a story for an uncovered value could come from: engagements whose text holds a hint word."""
    found = [e["id"] for e in engagements
             if targets.mentions(value.get("hints", []), " ".join(str(e.get(k) or "") for k in ("title", "summary", "notes")))]
    return ("build one from engagement " + ", ".join(found)) if found else "no engagement mentions it yet"


def report(name: str | None, stories: Sequence[Story], engagements: Sequence[Engagement]) -> None:
    """Rank stories for a researched company and show every value with its state. Read-only."""
    company = targets.find(name, use_default=True)
    if not name:
        print(f"(the default company, {company['name']})")
    print(f"Stories for {company['name']}: {targets.suggestion_text(company) or 'no suggested style'}")
    ranked = sorted(stories, key=lambda s: (s["status"] == "empty", targets.group(company, targets.story_item(s))))
    for story in ranked:
        print(f"  {_target_story_line(company, story)}")
    items = [targets.story_item(s) for s in stories]
    print("\nValues")
    for value in targets.values(company):
        value_state = targets.value_state(value, items)
        extra = f" ({_gap_hint(value, engagements)})" if value_state == "no story" else ""
        print(f"  {value['id']}  {value['name']}: {value_state}{extra}  {targets.fact_source(value)}")
        for question in targets.questions_for(company, value["id"]):
            print(f"      Q: {question['wording']} {targets.fact_source(question)}")
    print("\nNo story text is written here; suggested wording is for the user to decide.")


def add_parser(sub: Any, stories: Callable[[], Sequence[Story]], engagements: Callable[[], Sequence[Engagement]]) -> None:
    """Register `for-target [COMPANY]` on prep's subparsers; `stories` and `engagements` load the user's data."""
    parser = sub.add_parser("for-target")
    parser.add_argument("company", nargs="?", help="a researched company (default: the profile's target_company)")
    parser.set_defaults(fn=lambda args: report(args.company, stories(), engagements()))
