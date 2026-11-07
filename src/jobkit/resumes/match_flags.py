"""Flags: what a close call is worth, and the fixed fallback each one takes.

A flag names two readings of one requirement. The engine computes how far the lower score moves between them
(the swing). In step one every flag takes its fallback (the lower level; the category of the posting section,
else a fixed order; the lower priority); the other reading is kept so the upper score can credit it. Standard
library only, no database.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from jobkit.resumes import match_engine as me
from jobkit.resumes.match_request import Flag, Item, Request

THRESHOLD: Final[Decimal] = Decimal(2)       # points; a swing below this is a small close call
MAX_REVIEWERS: Final[int] = 3                # step two: flags that may go to a reviewer; above it the posting is vague
SECTION_HINTS: Final[tuple[tuple[tuple[str, ...], str], ...]] = (
    (("qualification", "education", "degree", "certification"), "education"),
    (("leadership", "people", "management"), "people_leadership"),
    (("strategy", "strategic", "budget"), "strategy"),
    (("domain", "industry", "sector"), "domain"),
    (("responsibilit", "what you", "impact", "outcome", "achievement"), "impact"),
    (("skill", "technolog", "tools", "tech stack", "technical"), "core_skills"),
)


@dataclass(frozen=True)
class FlagInfo:
    """A flag after its fallback was chosen."""

    id: str
    kind: str
    quote: str
    took: str
    other: str
    swing: Decimal
    gain: Decimal
    above: bool


def category_for_section(section: str) -> str | None:
    """The category a posting heading points at, or None."""
    low = section.lower()
    for words, category in SECTION_HINTS:
        if any(word in low for word in words):
            return category
    return None


def fallback(item: Item, flag: Flag) -> tuple[str, str]:
    """(the reading taken, the other reading) for a flag, by the fixed rules."""
    first, second = flag.readings
    if flag.kind == "level":
        rank = {level: i for i, level in enumerate(me.LEVELS)}
        took = max(flag.readings, key=rank.__getitem__)             # later in LEVELS = lower credit
    elif flag.kind == "priority":
        took = max(flag.readings, key=me.PRIORITIES.index)          # later = lower priority
    else:
        hinted = category_for_section(item.section)
        took = hinted if hinted in flag.readings else min(flag.readings, key=me.CATEGORIES.index)
    return took, (second if took == first else first)


def _reading(item: Item, kind: str | None = None, value: str | None = None) -> me.Reading:
    """The reading of an item, with one part replaced."""
    category, priority, level = item.category, item.priority, item.level
    if kind == "level" and value:
        level = value
    elif kind == "category" and value:
        category = value
    elif kind == "priority" and value:
        priority = value
    return me.Reading(category, priority, level)


def build_requirements(request: Request) -> list[me.Requirement]:
    """Engine requirements: a flagged item takes its fallback and keeps the other reading as `alt`."""
    out = []
    for item in request.items:
        if item.flag is None:
            out.append(me.Requirement(item.id, _reading(item), item.importance))
            continue
        took, other = fallback(item, item.flag)
        out.append(me.Requirement(item.id, _reading(item, item.flag.kind, took), item.importance,
                                  _reading(item, item.flag.kind, other)))
    return out


def flag_infos(request: Request, requirements: Sequence[me.Requirement], weights: Mapping[str, Decimal]
               ) -> list[FlagInfo]:
    """Every flag with its fallback and swing, biggest swing first, then input order."""
    infos = []
    for item in request.items:
        if item.flag is None:
            continue
        took, other = fallback(item, item.flag)
        moved = me.shift(requirements, weights, item.id)
        infos.append(FlagInfo(item.id, item.flag.kind, item.quote, took, other, abs(moved), max(moved, Decimal(0)),
                              abs(moved) >= THRESHOLD))
    return sorted(infos, key=lambda f: -f.swing)        # sorted() is stable: ties keep input order


def is_vague(infos: Sequence[FlagInfo]) -> bool:
    """True when more flags than the reviewer cap are worth settling."""
    return sum(1 for f in infos if f.above) > MAX_REVIEWERS


def label(kind: str, value: str) -> str:
    """A reading in everyday words."""
    if kind == "category":
        return me.CATEGORY_LABELS.get(value, value)
    if kind == "level":
        return me.LEVEL_WORDS.get(value, value)
    return value.replace("_", " ")


def assumption(info: FlagInfo, points: int) -> str:
    """The plain-words line for a flag: what the posting says, what was assumed, what it could be worth."""
    text = (f'The posting says "{info.quote.strip().rstrip(".")}". I counted it as {label(info.kind, info.took)}; '
            f"if it is {label(info.kind, info.other)}, ")
    if points > 0:
        return text + f"the score could be up to {points} points higher."
    return text + "the score would hardly change."
