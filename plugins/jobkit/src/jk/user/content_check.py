"""Compare text with the contributor's own stored data: shared phrases, near-copies, distinctive values, figures and
term fingerprints (for contributors who commit; `profile terms check` runs it next to the personal terms).

The index is built in memory on every run from the database and the extracted resume text in the output folder,
used, and discarded: nothing is written to disk, so it is never out of date and personal text is never copied.
jobkit's own seeded text (the card catalog, built-in questions, themes and role families) is left out of the index.

Import it as `from jk.user import content_check`; it does no work at import time.
"""
from __future__ import annotations

import dataclasses
import re
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Final

from jk import base, records
from jk.interview import lead, prep, tracks
from jk.resumes import query_resume
from jk.resumes import resume_data
from jk.user import tables

SHINGLE: Final[int] = 5                 # words in a shared phrase
CONTENT_WORDS: Final[int] = 3           # a shared phrase needs this many words that are not stop words
NEAR_RATIO: Final[float] = 0.75         # a line this similar to a stored line is a near-copy
NEAR_MIN: Final[int] = 25               # characters a line needs before it is compared for a near-copy
NEAR_SHARED: Final[int] = 3             # a stored line is compared only when it shares this many content words
FIGURES_MIN: Final[int] = 2             # distinct stored figures in one line
FINGERPRINT_MIN: Final[int] = 3         # distinct distinctive terms in one line
VALUE_MIN_WORDS: Final[int] = 2         # a title, certification or degree is matched exactly when it has 2+ words
STOP: Final[frozenset[str]] = query_resume.STOP | frozenset({"s", "t", "via", "per", "using", "across", "within"})
NOUN_STOP: Final[frozenset[str]] = STOP - {"years", "year", "months"}
WORD: Final[re.Pattern[str]] = re.compile(r"[a-z0-9]+")
NUMBER: Final[re.Pattern[str]] = re.compile(r"(?<![\d.,])\d+(?:[.,]\d+)*")
YEAR: Final[re.Pattern[str]] = re.compile(r"(19|20)\d\d")
FIGURE: Final[re.Pattern[str]] = re.compile(
    r"(?<![\w.,])(?P<money>\$\s?)?(?P<number>\d+(?:[.,]\d+)*)\+?(?:\s?(?P<unit>%|percent|million|billion|thousand|[kmb](?![a-z])))?"
    r"\+?(?:\s(?P<noun>[a-z]{3,}))?")
FIGURE_MIN: Final[int] = 10             # smaller numbers are too common to point to anyone
SENTENCE: Final[re.Pattern[str]] = re.compile(r"(?<=[.!?;])\s+|\n")
# Data kinds holding the contributor's own text, and those holding only jobkit's seeded text.
OWN_KINDS: Final[tuple[str, ...]] = ("stories", "engagements", "cards-progress", "lead-progress", "lead-scope",
                                     "sessions", "resume-companies", "resume-profile", "curated", "curation-themes")
SEEDED_KINDS: Final[tuple[str, ...]] = ("cards-catalog", "cards-tracks", "lead-questions", "themes")
OWN_SETTINGS: Final[tuple[str, ...]] = ("preparing_for",)


@dataclass(frozen=True)
class Hit:
    """One line that matches stored data: its number, the kind of match and where the stored text comes from."""

    line: int
    kind: str              # phrase | near-copy | value | figures | fingerprint
    source: str            # for example "resume line ab-12" or "story s-3"; never the stored text itself


@dataclass
class Index:
    """What a line is compared with. Built in memory by `build`; never saved."""

    phrases: dict[tuple[str, ...], str] = field(default_factory=dict)
    lines: list[tuple[str, str]] = field(default_factory=list)
    by_word: dict[str, list[int]] = field(default_factory=dict)
    values: dict[str, str] = field(default_factory=dict)
    figures: dict[str, str] = field(default_factory=dict)
    marks: dict[str, str] = field(default_factory=dict)
    ignored: tuple[str, ...] = ()
    patterns: dict[str, re.Pattern[str] | None] = field(default_factory=dict)

    def check(self, text: str) -> list[Hit]:
        """Every line of a text that matches stored data."""
        return check_text(self, text)

    def empty(self) -> bool:
        """True when there is nothing stored to compare with."""
        return not (self.phrases or self.lines or self.values or self.figures or self.marks)


def words(text: str) -> list[str]:
    """The lower-case words of a text."""
    return WORD.findall(text.lower())


def shingles(text: str) -> Iterator[tuple[str, ...]]:
    """Every run of SHINGLE words that holds at least CONTENT_WORDS words that are not stop words."""
    seen = words(text)
    for start in range(len(seen) - SHINGLE + 1):
        run = tuple(seen[start:start + SHINGLE])
        if sum(w not in STOP for w in run) >= CONTENT_WORDS:
            yield run


def strings(data: Any, kind: str, label: str = "") -> Iterator[tuple[str, str]]:
    """Every (source, text) string inside nested data; the source is the kind plus the nearest record id."""
    label = label or kind
    if isinstance(data, str):
        yield label, data
    elif isinstance(data, Mapping):
        here = f"{kind} {data['id']}" if isinstance(data.get("id"), str) else label
        for value in data.values():
            yield from strings(value, kind, here)
    elif dataclasses.is_dataclass(data) and not isinstance(data, type):
        yield from strings(dataclasses.asdict(data), kind, label)
    elif isinstance(data, Iterable) and not isinstance(data, bytes):
        for value in data:
            yield from strings(value, kind, label)


def seeded_text() -> Iterator[str]:
    """jobkit's own seeded text, which is never the contributor's: stored seeds and the built-in sources."""
    for kind in SEEDED_KINDS:
        yield from (text for _, text in strings(records.kind(kind).export(), kind))
    for data in (tracks.builtin_seed(), tracks.families(), lead.SEED, prep.QUESTIONS, query_resume.THEME_HINTS,
                 resume_data.BUILTIN_THEMES):
        yield from (text for _, text in strings(data, "seed"))


def own_text() -> Iterator[tuple[str, str]]:
    """Every (source, text) of the contributor's own data: the stored kinds, a few settings and the extracted text."""
    for kind in OWN_KINDS:
        name = "resume line" if kind == "resume-companies" else kind.rstrip("s").replace("-", " ")
        yield from strings(records.kind(kind).export(), name)
    for role in records.kind("role-questions").export()["roles"]:
        for question in role["questions"]:
            if question["source"] == "personal":
                yield from strings(question, "role question")
    settings = tables.load_settings()
    for key in OWN_SETTINGS:
        yield from strings(settings.get(key), "setting")
    folder = base.output_dir()
    for path in sorted(folder.glob("*.txt")) if folder.is_dir() else []:
        yield "extracted resume text", path.read_text(encoding="utf-8", errors="ignore")


def add_text(index: Index, source: str, text: str, seeded: set[tuple[str, ...]]) -> None:
    """Index one stored text: its phrases (less the seeded ones) and each sentence long enough to compare."""
    for run in shingles(text):
        if run not in seeded:
            index.phrases.setdefault(run, source)
    for part in SENTENCE.split(text):
        part = part.strip().lower()
        if len(part) >= NEAR_MIN and not any(run in seeded for run in shingles(part)):
            for word in {w for w in words(part) if w not in STOP}:
                index.by_word.setdefault(word, []).append(len(index.lines))
            index.lines.append((part, source))


def wordings(bullet: Mapping[str, Any]) -> list[str]:
    """Every stored wording of a resume line: its text, its variants and the wording each file uses."""
    per_file = [w for found in (bullet.get("wordings") or {}).values() for w in found]
    return [bullet.get("text", ""), *bullet.get("variants", []), *per_file]


def distinctive(companies: Mapping[str, Any], profile: Mapping[str, Any], settings: Mapping[str, Any],
                curation: Mapping[str, Any], skills: Mapping[str, Any]) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """(values, figures, marks): exact values (titles, certifications, degrees, headlines), the figures of resume
    lines, and the terms whose combination points to one career (titles, certifications, own vocabulary, skills of
    two or more words that jobkit does not ship itself). Each maps the lower-case text to its source."""
    roles = [r for c in companies.values() for r in c.get("roles", [])]
    titles = {t for r in roles for t in [*r.get("titles", []), *r.get("subtitles", [])]}
    certs = {c["name"] if isinstance(c, Mapping) else str(c) for c in profile.get("certifications", [])}
    values = {**{t.lower(): "title" for t in titles}, **{c.lower(): "certification" for c in certs},
              **{e.lower(): "education" for e in profile.get("education", [])},
              **{h.lower(): "headline" for h in profile.get("headlines", [])}}
    values = {k.strip(" .,;:-•●"): v for k, v in values.items() if len(words(k)) >= VALUE_MIN_WORDS}
    figures = {n: "resume line figure" for c in companies.values() for b in c.get("bullets", [])
               for text in wordings(b) for n in numbers(text)}
    if isinstance(settings.get("years_experience"), int):
        figures[f"{settings['years_experience']} years"] = "years of experience"
    vocabulary = [w for key in ("theme_words", "positioning_words") for k, hints in (curation.get(key) or {}).items()
                  for w in [k, *hints]]
    skill_names = [s["name"] for group in (skills.get("groups") or {}).values() for s in group if len(words(s["name"])) >= 2]
    marks = {**{w.lower(): "own vocabulary" for w in vocabulary}, **{s.lower(): "skill" for s in skill_names},
             **{k: v for k, v in values.items() if v in ("title", "certification")}}
    return values, figures, marks


def build(ignored: Iterable[str] = ()) -> Index:
    """The index of the contributor's stored data, built now and kept only in memory."""
    shipped = " \n ".join(seeded_text()).lower()
    seeded = set(shingles(shipped))
    index = Index(ignored=tuple(sorted({i.lower() for i in ignored if i.strip()}, key=len, reverse=True)))
    for source, text in own_text():
        add_text(index, source, text, seeded)
    settings = tables.load_settings()
    index.values, index.figures, index.marks = distinctive(
        records.kind("resume-companies").export() or {}, records.kind("resume-profile").export() or {}, settings,
        records.kind("curation-themes").export() or {}, records.kind("resume-skills").export() or {})
    index.marks = {k: v for k, v in index.marks.items() if len(words(k)) >= VALUE_MIN_WORDS and k not in shipped}
    return index


def phrase_pattern(text: str) -> re.Pattern[str] | None:
    """A whole-word, case-insensitive pattern for a stored value; a hyphen also matches a space."""
    body = r"[- ]".join(re.escape(part) for part in text.split("-"))
    return re.compile(rf"(?<![a-z0-9]){body}(?![a-z0-9])") if text.strip() else None


def found(index: Index, table: Mapping[str, str], line: str) -> dict[str, str]:
    """The entries of `table` that appear in the (lower-case) line, as {text: source}."""
    hits: dict[str, str] = {}
    for text, source in table.items():
        if text not in index.patterns:
            index.patterns[text] = phrase_pattern(text)
        rx = index.patterns[text]
        if rx is not None and text in line and rx.search(line):
            hits[text] = source
    return hits


def numbers(text: str) -> set[str]:
    """The figures in a text written so that they can point to one career, in one spelling: percentages ("41%",
    "41 percent"), amounts ("$7M", "$7 million") and counts of something ("17 sites", "3,500 members"; 10 or more,
    not a year). A bare number is too common to count."""
    figures: set[str] = set()
    for match in FIGURE.finditer(text.lower()):
        money, number, unit, noun = match.group("money"), match.group("number").replace(",", ""), match.group("unit"), match.group("noun")
        if unit in ("%", "percent"):
            figures.add(number + "%")
        elif money:
            figures.add("$" + number + (unit or "")[:1])
        elif (noun and noun not in NOUN_STOP and number.replace(".", "", 1).isdigit() and not YEAR.fullmatch(number)
              and float(number) >= FIGURE_MIN):
            figures.add(f"{number}{(unit or '')[:1]} {noun}")
    return figures


def figure_keys(index: Index, line: str) -> dict[str, str]:
    """The distinct stored figures in a line, as {figure: source}."""
    return {n: index.figures[n] for n in numbers(line) if n in index.figures}


def near_copy(index: Index, line: str) -> str | None:
    """The source of a stored sentence this line nearly copies, or None."""
    if len(line) < NEAR_MIN:
        return None
    shared = Counter(i for w in {w for w in words(line) if w not in STOP} for i in index.by_word.get(w, ()))
    for i, count in shared.most_common(20):
        if count < NEAR_SHARED:
            break
        stored, source = index.lines[i]
        matcher = SequenceMatcher(None, line, stored, autojunk=False)
        if matcher.quick_ratio() >= NEAR_RATIO and matcher.ratio() >= NEAR_RATIO:
            return source
    return None


def check_line(index: Index, number: int, raw: str) -> Hit | None:
    """The strongest match of one line, or None: a shared phrase, an exact value, a near-copy, figures or a
    fingerprint of distinctive terms. Text the contributor marked as ignored is removed first."""
    line = raw.lower()
    for text in index.ignored:
        line = line.replace(text, " ")
    phrase = next((index.phrases[run] for run in shingles(line) if run in index.phrases), None)
    if phrase:
        return Hit(number, "phrase", phrase)
    if value := found(index, index.values, line):
        return Hit(number, "value", next(iter(value.values())))
    if source := near_copy(index, line):
        return Hit(number, "near-copy", source)
    if len(figures := figure_keys(index, line)) >= FIGURES_MIN:
        return Hit(number, "figures", next(iter(figures.values())))
    if len(marks := found(index, index.marks, line)) >= FINGERPRINT_MIN:
        return Hit(number, "fingerprint", ", ".join(sorted(set(marks.values()))))
    return None


def check_text(index: Index, text: str) -> list[Hit]:
    """Every line of a text that matches stored data."""
    if index.empty():
        return []
    return [hit for n, raw in enumerate(text.splitlines(), 1) if (hit := check_line(index, n, raw))]
