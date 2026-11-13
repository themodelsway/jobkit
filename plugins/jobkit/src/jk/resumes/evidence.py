"""What counts as usable evidence for a skill, shared by ranking, building and the match-score code pass.

A stored line is usable when it is neither ignored nor flagged for review. For one skill it is then `ok`,
`confirm_use` (reads like training only: counts, but never above partial) or `not_demonstrated` (a clause about
that skill explicitly denies professional use: no credit). The phrase lists are short and fixed on purpose: a
reviewer can contest a level that it gets wrong (see `match_codepass.apply_code`).
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Final

from jk.resumes.resume_data import Bullet

OK: Final[str] = "ok"
CONFIRM_USE: Final[str] = "confirm_use"
NOT_DEMONSTRATED: Final[str] = "not_demonstrated"

DENIAL: Final[re.Pattern[str]] = re.compile(
    r"\b(?:no|not|never|without)\s+(?:any\s+)?(?:production|professional|commercial|real[- ]world|hands[- ]on|work)"
    r"\s+(?:use|usage|experience|exposure)\b"
    r"|(?:\bnot|\bnever|n't)\s+(?:use|used|using)\b|\bno\s+experience\b", re.I)
TRAINING: Final[re.Pattern[str]] = re.compile(
    r"\b(?:completed|finished|took|attended)\s+(?:an?\s+|the\s+)?(?:\w+\s+){0,2}"
    r"(?:introduction|intro|tutorial|course|bootcamp)\b"
    r"|\bbeginner[- ]level\b|\bintroductory\s+(?:course|class|training|level|knowledge)\b|\bcoursework only\b", re.I)
CLAUSE_BREAK: Final[re.Pattern[str]] = re.compile(r"[;,]|\bbut\b", re.I)


def admissible(bullet: Bullet) -> bool:
    """False for a line that is ignored or flagged needs_review."""
    return not bullet.get("ignored") and not bullet.get("needs_review")


def _names(clause: str, skill: str, terms: Mapping[str, str] | None = None) -> bool:
    """True when the clause names the skill, or one of its aliases in `terms` ({term: canonical name}), as a
    whole word (case-insensitive)."""
    spellings = [skill, *(t for t, canon in (terms or {}).items() if canon == skill)]
    return any(re.search(rf"(?<![\w]){re.escape(t)}(?![\w])", clause, re.I) for t in spellings)


def _applies(clause: str, skill: str, tagged: Sequence[str], terms: Mapping[str, str] | None = None) -> bool:
    """Whether a clause says something about this skill: it names it (or an alias), or it names no other tagged
    skill and the line is about this skill alone."""
    if _names(clause, skill, terms):
        return True
    others = [s for s in tagged if s != skill]
    return not others and not any(_names(clause, s, terms) for s in tagged)


def use_state(text: str, skill: str, tagged: Sequence[str] = (), terms: Mapping[str, str] | None = None) -> str:
    """How a line stands for one skill: `not_demonstrated` when a clause about it explicitly denies professional
    use, `confirm_use` when one reads like training only, else `ok`. A denial about another skill in the same
    line does not count against this one; a denial wins over training wording."""
    state = OK
    for clause in CLAUSE_BREAK.split(text):
        if not _applies(clause, skill, tagged, terms):
            continue
        if DENIAL.search(clause):
            return NOT_DEMONSTRATED
        if TRAINING.search(clause):
            state = CONFIRM_USE
    return state


def line_state(bullet: Bullet, skill: str, terms: Mapping[str, str] | None = None) -> str | None:
    """`use_state` of a stored line for a skill, or None when the line is ignored or flagged (set aside)."""
    if not admissible(bullet):
        return None
    return use_state(bullet["text"], skill, [*bullet.get("skills", []), *bullet.get("skills_manual", [])], terms)


def lead_lines(bullets: Iterable[Bullet], skill: str, terms: Mapping[str, str] | None = None) -> list[Bullet]:
    """The lines that may be offered as a lead for a skill: not ignored, not flagged, not denying its use."""
    return [b for b in bullets if line_state(b, skill, terms) in (OK, CONFIRM_USE)]


def weight(bullet: Bullet) -> int:
    """How many plain mentions the line is worth: 2 when it states a measured result, else 1."""
    return 2 if bullet.get("metrics") else 1
