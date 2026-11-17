"""Answer styles: STAR, SOAR and CARL as labeled views of one stored story. Standard library only.

A story is stored once, in the STAR fields plus `lessons`. A style never changes what is stored; it only names
the parts, groups the stored text, prompts for what is missing and says when a story is complete:

  star   Situation, Task, Action, Result
  soar   Situation, Obstacle (the task field), Action, Result
  carl   Challenge (the situation followed by the task), Action, Result, Learning (the lessons field)

The style in force for a command is, in order: the style given on the command, the session's current style,
the profile default, then star (`in_force`).
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from jk.common import ToolError
from jk.user import profile

DEFAULT_STYLE: Final[str] = "star"
JOIN: Final[str] = " "                    # between the pieces of a part that reads several fields


@dataclass(frozen=True)
class Part:
    """One part of a style: what the user calls it, the stored fields it reads, and where a save goes."""

    name: str
    label: str
    fields: tuple[str, ...]
    prompt: str
    folds: str | None = None              # a field a merged save empties (the challenge swallows the task)

    @property
    def write_to(self) -> str:
        """The stored field a save writes to."""
        return self.fields[0]


@dataclass(frozen=True)
class Style:
    """A named order of parts and a one-line use."""

    name: str
    use: str
    parts: tuple[Part, ...]


SITUATION = Part("situation", "Situation", ("situation",), "What was the situation?")
TASK = Part("task", "Task", ("task",), "What were you responsible for?")
OBSTACLE = Part("obstacle", "Obstacle", ("task",), "What stood in the way?")
CHALLENGE = Part("challenge", "Challenge", ("situation", "task"), "What was the challenge you faced?",
                 folds="task")
ACTION = Part("action", "Action", ("action",), "What did you personally do?")
RESULT = Part("result", "Result", ("result",), "What was the result, in numbers if you can?")
LEARNING = Part("learning", "Learning", ("lessons",), "What did you learn, and what would you do differently?")

STYLES: Final[dict[str, Style]] = {
    "star": Style("star", "a clear sequence for most behavioral questions",
                  (SITUATION, TASK, ACTION, RESULT)),
    "soar": Style("soar", "when overcoming something is the point of the story",
                  (SITUATION, OBSTACLE, ACTION, RESULT)),
    "carl": Style("carl", "when what was learned matters as much as what happened",
                  (CHALLENGE, ACTION, RESULT, LEARNING)),
}


def names() -> tuple[str, ...]:
    """The style names in listing order."""
    return tuple(STYLES)


def get(name: str) -> Style:
    """The style called `name`; `ToolError` naming the valid styles otherwise."""
    if name not in STYLES:
        raise ToolError(f"Unknown style {name!r}: use {', '.join(STYLES)}.")
    return STYLES[name]


def in_force(option: str | None = None, session: str | None = None) -> str:
    """The style for a command: its option, then the session's style, then the profile default, then star."""
    return get(option or session or profile.answer_style() or DEFAULT_STYLE).name


def listing() -> list[str]:
    """One line per style: its name, its parts in order and its use."""
    return [f"{style.name:<5} {', '.join(p.label for p in style.parts)}: {style.use}"
            for style in STYLES.values()]


def part_for(style: str, name: str) -> Part:
    """The part of `style` called `name`; `ToolError` listing the parts of the style otherwise."""
    for part in get(style).parts:
        if part.name == name:
            return part
    raise ToolError(f"{name!r} is not a part of {style}. Its parts are: "
                    + ", ".join(p.name for p in get(style).parts) + ".")


def stored_fields(style: str) -> frozenset[str]:
    """The stored fields the parts of `style` read."""
    return frozenset(field for part in get(style).parts for field in part.fields)


def part_text(part: Part, story: Mapping[str, Any]) -> str:
    """The text a part shows: the stored fields it reads, in order, with nothing repeated or invented."""
    pieces = (str(story.get(field) or "").strip() for field in part.fields)
    return JOIN.join(piece for piece in pieces if piece)


def missing_parts(style: str, story: Mapping[str, Any]) -> list[Part]:
    """The parts of `style` that have no text in the story."""
    return [part for part in get(style).parts if not part_text(part, story)]


def complete_styles(story: Mapping[str, Any]) -> list[str]:
    """The styles in which every part of the story has text."""
    return [name for name in STYLES if not missing_parts(name, story)]


def next_prompt(style: str, story: Mapping[str, Any]) -> str | None:
    """The prompt for the first missing part of the style, or None when the story is complete in it."""
    missing = missing_parts(style, story)
    return missing[0].prompt if missing else None


def save_part(story: dict[str, Any], style: str, name: str, value: str, merge: bool = False) -> str:
    """Store `value` as the part `name` of `style`; return what was written, for the user.

    A save never repeats text. The challenge is stored as the situation; when the task already has text the
    save is refused unless `merge` is true, and a merge empties the task.

    Raises:
        ToolError: the part is not in the style, or a challenge would leave the task's text beside the new one.
    """
    part = part_for(style, name)
    if part.folds and str(story.get(part.folds) or "").strip():
        if not merge:
            raise ToolError(
                f"The {part.folds} already has text, so saving a {part.name} would repeat it. Either set the "
                f"{part.write_to} and the {part.folds} separately (in star or soar), or save again with "
                f"--merge to put the new text in the {part.write_to} and fold the {part.folds} into it.")
        story[part.folds] = None
        story[part.write_to] = value
        return f"{part.label} saved as the {part.write_to}; the {part.folds} was folded into it and is now empty."
    story[part.write_to] = value
    return f"{part.label} saved as the {part.write_to}."
