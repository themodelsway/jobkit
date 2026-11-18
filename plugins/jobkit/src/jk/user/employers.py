"""Employer names written more than one way across the resumes.

A resume scan finds every spelling of an employer as it is written. Spellings that differ only in letter case,
accents, punctuation, spacing, "&" for "and", a leading "The" or a legal ending (Inc, LLC, Ltd, Corp, GmbH ...)
name one employer: `plan` merges them without asking. Names that only look alike (one is the start of the other,
one is the initials of the other, or they differ by a letter or two) may still be different employers:
`look_alikes` lists them so the user can confirm, and `profile companies merge` joins them.

Standard library only; nothing here reads or writes the database.
"""
from __future__ import annotations

import copy
import itertools
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Final

SEP: Final[str] = r"\s*[–—-]\s*"
TITLE_SUFFIX: Final[str] = rf"(?:{SEP}(?P<t>.+))?"
LEGAL_WORDS: Final[frozenset[str]] = frozenset({
    "inc", "incorporated", "llc", "llp", "lp", "ltd", "limited", "corp", "corporation", "co", "company", "plc",
    "gmbh", "ag", "sa", "nv", "bv", "pty", "pvt", "pte", "private"})
SMALL_WORDS: Final[frozenset[str]] = frozenset({"and", "of", "the", "for"})
TYPO_RATIO: Final[float] = 0.85     # two names this similar, letter by letter, may be one name mistyped
TYPO_MIN_CHARS: Final[int] = 5      # shorter names differ by too few letters to tell a typo from another name

Record = dict[str, Any]


@dataclass
class Scan:
    """The stored employers with a scan's spellings applied, and what changed."""

    employers: dict[str, Record]
    new: list[str] = field(default_factory=list)                     # ids of employers added
    merged: dict[str, list[str]] = field(default_factory=dict)       # id -> other spellings merged into it
    skipped: list[str] = field(default_factory=list)                 # spellings whose id an edited employer holds


def employer_id(name: str) -> str:
    """The id of an employer name: lowercase letters, digits and dashes."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def key_words(name: str) -> list[str]:
    """The words that identify an employer: accents, case, punctuation, a leading "The" and legal endings removed."""
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii").lower()
    words = re.findall(r"[a-z0-9]+", plain.replace("&", " and ").replace("+", " and "))
    if len(words) > 1 and words[0] == "the":
        words = words[1:]
    while len(words) > 1 and words[-1] in LEGAL_WORDS:
        words.pop()
    return words


def name_key(name: str) -> str:
    """One spelling for every way of writing the same employer name (spaces dropped, so "A.B.C." equals "ABC")."""
    return "".join(key_words(name)) or name.lower()


def _initials(words: Sequence[str]) -> set[str]:
    """The initials of a name, with and without its small words ("Bank of Acme": "boa" and "ba")."""
    return {"".join(w[0] for w in words), "".join(w[0] for w in words if w not in SMALL_WORDS)}


def look_alike(first: str, second: str) -> bool:
    """True when two different employer names may still be one employer: one is the start of the other, one is
    the initials of the other, or they differ by a letter or two."""
    a, b = key_words(first), key_words(second)
    if not a or not b or a == b:
        return bool(a) and a == b
    short, long_ = sorted((a, b), key=len)
    if long_[:len(short)] == short:
        return True
    if len(short) == 1 and len(long_) > 1 and len(short[0]) > 1 and short[0] in _initials(long_):
        return True
    ka, kb = "".join(a), "".join(b)
    return min(len(ka), len(kb)) >= TYPO_MIN_CHARS and SequenceMatcher(None, ka, kb).ratio() >= TYPO_RATIO


def names_of(entry: Mapping[str, Any]) -> list[str]:
    """The display name of a stored employer and its other spellings."""
    return [entry["name"], *entry.get("aliases", [])]


def look_alikes(employers: Mapping[str, Mapping[str, Any]]) -> list[tuple[str, str]]:
    """Pairs of employer ids whose names look alike, in stored order."""
    return [(a, b) for a, b in itertools.combinations(employers, 2)
            if any(look_alike(x, y) for x in names_of(employers[a]) for y in names_of(employers[b]))]


def header_regex(names: Sequence[str]) -> str:
    """The standard pattern for an employer header line: any of the names, then an optional " - title"."""
    heads = [re.escape(n) for n in names]
    return (heads[0] if len(heads) == 1 else f"(?:{'|'.join(heads)})") + TITLE_SUFFIX


def widen(entry: Record, names: Sequence[str]) -> bool:
    """Let a stored employer also match these spellings; False (and unchanged) when its pattern is custom."""
    if not entry["regex"].endswith(TITLE_SUFFIX):
        return False
    head = entry["regex"][:-len(TITLE_SUFFIX)]
    entry["regex"] = f"(?:{'|'.join([head, *map(re.escape, names)])}){TITLE_SUFFIX}"
    entry["aliases"] = sorted({*entry.get("aliases", []), *names} - {entry["name"]})
    return True


def registry(employers: Mapping[str, Mapping[str, Any]]) -> dict[str, tuple[str, str]]:
    """{id: (display name, header regex)} for parse_resume.set_companies."""
    return {cid: (entry["name"], entry["regex"]) for cid, entry in employers.items()}


def _shouting(name: str) -> bool:
    """True when most letters of a name are capitals ("ACME CORP, Inc.")."""
    return sum(c.isupper() for c in name) > sum(c.islower() for c in name)


def _pick(names: Sequence[str], counts: Mapping[str, int]) -> str:
    """The display name among spellings of one employer: the one in most resumes, then not mostly capitals, then
    the first found."""
    return min(names, key=lambda n: (-counts.get(n, 0), _shouting(n), names.index(n)))


def _stored_keys(employers: Mapping[str, Record]) -> dict[str, str]:
    """{name key: id} for the stored employers whose pattern can take more spellings."""
    keys: dict[str, str] = {}
    for cid, entry in employers.items():
        if entry["regex"].endswith(TITLE_SUFFIX):
            for name in names_of(entry):
                keys.setdefault(name_key(name), cid)
    return keys


def _unknown(employers: Mapping[str, Record], spellings: Sequence[str]) -> list[str]:
    """The spellings no stored employer's pattern matches yet."""
    patterns = [re.compile(entry["regex"] + "$") for entry in employers.values()]
    return [s for s in spellings if not any(p.match(s) for p in patterns)]


def plan(stored: Mapping[str, Record], spellings: Mapping[str, int]) -> Scan:
    """Apply the spellings found by a scan ({spelling: number of resumes}) to a copy of the stored employers.

    A spelling of a stored employer is added to it; the other spellings are grouped by name key, and each group
    becomes one new employer. A stored employer is never renamed or removed, and one with a custom pattern is
    never changed: a group whose id such an employer already holds is listed in `skipped` instead.
    """
    scan = Scan(copy.deepcopy(dict(stored)))
    keys = _stored_keys(scan.employers)
    groups: dict[str, list[str]] = {}
    for spelling in _unknown(scan.employers, list(spellings)):
        groups.setdefault(name_key(spelling), []).append(spelling)
    for key, names in groups.items():
        if key in keys and widen(scan.employers[keys[key]], names):
            scan.merged.setdefault(keys[key], []).extend(names)
            continue
        chosen = _pick(names, spellings)
        cid = employer_id(chosen)
        if not cid or cid in scan.employers:
            scan.skipped.extend(names)
            continue
        others = [n for n in names if n != chosen]
        scan.employers[cid] = {"name": chosen, "regex": header_regex([chosen, *others])}
        scan.new.append(cid)
        if others:
            scan.employers[cid]["aliases"] = sorted(others)
            scan.merged[cid] = others
    return scan
