"""A practice session for a researched company: ordering the queue by the company and showing its emphasis.

A company orders a session's queue and never empties it: stories and leadership questions that match a value by
theme come first, then those that match by word, then the rest; inside a group an item matching more values comes
first and ties keep the usual order. Role-knowledge cards keep their places. Library module with no command line.
"""
from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from typing import Any

from jk.interview import lead, prep, tables, targets


def items_by_id() -> dict[str, targets.Item]:
    """id -> item for every stored story and leadership question."""
    items = {s["id"]: targets.story_item(s) for s in prep.stories()} if tables.has_stories() else {}
    if tables.has_questions():
        progress = lead.prog()["questions"]
        items.update({q["id"]: targets.question_item(q, progress.get(q["id"])) for q in lead.cards()})
    return items


def order[Entry: Mapping[str, Any]](queue: Sequence[Entry], company: Mapping[str, Any],
                                   shuffle: bool) -> tuple[list[Entry], str | None]:
    """The queue ordered by the company (cards keep their places), and a note when the company changed nothing.

    With `shuffle` the items are shuffled inside each group (theme, word, rest) instead of keeping their order.
    """
    items = items_by_id()
    slots = [i for i, q in enumerate(queue) if q["kind"] != "card"]
    keyed = [(targets.group(company, items[queue[i]["id"]]) if queue[i]["id"] in items else (2, 0), n, queue[i])
             for n, i in enumerate(slots)]
    if shuffle:
        random.shuffle(keyed)
        keyed.sort(key=lambda row: row[0][0])
    else:
        keyed.sort(key=lambda row: (row[0], row[1]))
    out = list(queue)
    for slot, (_, _, item) in zip(slots, keyed, strict=True):
        out[slot] = item
    if not slots:
        return out, "A company does not change the order of role-knowledge cards."
    if all(key[0] == 2 for key, _, _ in keyed):
        return out, f"No story or leadership question in this queue matches {company['name']} yet."
    return out, None


def marks(queue: Sequence[Mapping[str, Any]], company: Mapping[str, Any]) -> list[str]:
    """One line per queued story or question that matches the company: its id and the values it matches, and how."""
    items = items_by_id()
    lines = []
    for entry in queue:
        found = targets.matches(company, items[entry["id"]]) if entry["id"] in items else []
        if found:
            lines.append(f"  {entry['id']}: " + ", ".join(f"{v['name']} ({how})" for v, how in found))
    return lines


def emphasis(company: Mapping[str, Any], item_id: str) -> list[str]:
    """What the company's graders look for, and the values the next item matches, each fact with its source."""
    lines = [f"  {company['name']} graders look for:"]
    lines += [f"    {fact['wording']} {targets.fact_source(fact)}" for fact in targets.grading(company)] or \
        ["    (no grading notes were found)"]
    item = items_by_id().get(item_id)
    found = targets.matches(company, item) if item else []
    if found:
        lines.append("  This item matches: " + ", ".join(f"{v['name']} (by {how})" for v, how in found))
    return lines


def to_cover(company: Mapping[str, Any]) -> list[str]:
    """The values that are `no story` or `needs your judgment`, with their stored typical questions."""
    items = list(items_by_id().values())
    lines = []
    for value in targets.values(company):
        state = targets.value_state(value, items)
        if state in ("no story", "needs your judgment"):
            lines.append(f"  {value['name']} ({state}) {targets.fact_source(value)}")
            lines += [f"    Q: {q['wording']}" for q in targets.questions_for(company, value["id"])]
    return (["Values still to cover:"] + lines) if lines else []
