"""Story and engagement model for interview prep: defaults, validation, rendering, search.

Pure functions, no file I/O (prep.py does the reading and writing). Standard library only.

Two record types, both stored through prep.py:

  engagement  one real project, written once: facts (each with a basis), decisions, people.
  story       one STAR narrative about an engagement (or standalone, as before): STAR text, metrics with a basis,
              spoken versions, likely questions, never_say list, follow-ups.

Every fact says how we know it (FACT_BASES). Only USABLE_BASES may appear in interview text; "unsure" and
"proposed" (a design suggested by the assistant, never claimed by the user) are kept but cannot back a story.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any, Final, NotRequired, TypedDict, cast

from jk import common
from jk.interview import styles

SCHEMA_VERSION: Final[int] = 2
FACT_BASES: Final[tuple[str, ...]] = ("stated", "estimate", "unsure", "verified-doc", "proposed")
USABLE_BASES: Final[tuple[str, ...]] = ("stated", "estimate", "verified-doc")
METRIC_BASES: Final[tuple[str, ...]] = ("measured", "estimated", "stated", "unknown")
OWNERSHIP: Final[tuple[str, ...]] = ("mine", "team", "client", "shared", "unsure")
STATUSES: Final[tuple[str, ...]] = ("empty", "draft", "done")
STAR: Final[tuple[str, ...]] = ("situation", "task", "action", "result")
TEXT_FIELDS: Final[tuple[str, ...]] = ("situation", "task", "action", "result", "metric", "lessons", "notes")
LIST_FIELDS: Final[tuple[str, ...]] = ("follow_ups", "likely_questions", "never_say", "also_themes")
SPOKEN_LIMITS: Final[dict[str, int]] = {"60s": 160, "2min": 330}      # words, at roughly 150 words per minute
ENG_TEXT_FIELDS: Final[tuple[str, ...]] = ("title", "my_role", "period", "summary", "notes")
HEDGED_METRIC_BASES: Final[tuple[str, ...]] = ("estimated", "unknown")
OWNED_DECISIONS: Final[tuple[str, ...]] = ("mine", "shared")
SNIPPET_BEFORE: Final[int] = 40
SNIPPET_AFTER: Final[int] = 60

_NUM = re.compile(r"\d[\d,.]*\s?%|\$\s?\d[\d,.]*\s?[MKB]?\b", re.I)
_HEDGE = re.compile(r"estimat|approx|about|around|roughly|projected", re.I)
_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")
_I_WORD = re.compile(r"\bI\b")
_WE_WORD = re.compile(r"\b(we|our|us)\b", re.I)

now = common.now


class Fact(TypedDict):
    """One thing known about an engagement, with how we know it."""

    id: str
    text: str
    basis: str
    source: NotRequired[str]
    note: NotRequired[str]
    added: NotRequired[str]


class Decision(TypedDict):
    """A choice made on the engagement, and who owned it."""

    id: str
    what: str
    why: NotRequired[str]
    alternatives: NotRequired[list[str]]
    tradeoffs: NotRequired[str]
    ownership: NotRequired[str]


class Metric(TypedDict):
    """A number a story quotes, with how it was obtained."""

    name: str
    value: str
    basis: str
    note: NotRequired[str]


class Engagement(TypedDict):
    """One real project, written once."""

    id: str
    company: str | None
    title: str | None
    my_role: str | None
    period: str | None
    summary: str | None
    notes: str | None
    facts: list[Fact]
    decisions: list[Decision]
    people: list[dict[str, Any]]
    counters: dict[str, int]
    updated: str | None


class Story(TypedDict):
    """One STAR narrative."""

    id: str
    company: str
    company_name: str
    theme: str
    headline: str
    status: str
    situation: str | None
    task: str | None
    action: str | None
    result: str | None
    metric: str | None
    lessons: str | None
    notes: str | None
    follow_ups: list[str]
    likely_questions: list[str]
    never_say: list[str]
    also_themes: list[str]
    engagement: str | None
    uses_facts: list[str]
    metrics: list[Metric]
    resolved: list[dict[str, str]]
    spoken: dict[str, str | None]
    metrics_on_resume: list[str]
    anchor_bullets: list[str]
    updated: str | None


Issue = tuple[str, str]               # (level, message); level 'error' blocks status done, 'warn' is advice
Hit = tuple[str, str, str, str]       # (kind, id, field, snippet)


def normalize_story(raw_story: Story | dict[str, Any]) -> Story:
    """Fill every v2 field with a default, in place. Never removes or rewrites existing content.
    Takes the raw dict (older files lack newer fields) and returns it as a complete Story."""
    story = cast(dict[str, Any], raw_story)
    for name in TEXT_FIELDS:
        story.setdefault(name, None)
    for name in LIST_FIELDS:
        story.setdefault(name, [])
    story.setdefault("status", "empty")
    story.setdefault("engagement", None)
    story.setdefault("uses_facts", [])
    story.setdefault("metrics", [])
    story.setdefault("resolved", [])
    spoken = story.setdefault("spoken", {})
    for key in SPOKEN_LIMITS:
        spoken.setdefault(key, None)
    story.setdefault("metrics_on_resume", [])
    story.setdefault("anchor_bullets", [])
    story.setdefault("updated", None)
    return cast(Story, story)


def normalize_engagement(raw_eng: Engagement | dict[str, Any]) -> Engagement:
    """Fill every engagement field with a default, in place; takes the raw dict, returns a complete Engagement."""
    eng = cast(dict[str, Any], raw_eng)
    eng.setdefault("company", None)
    for name in ENG_TEXT_FIELDS:
        eng.setdefault(name, None)
    eng.setdefault("facts", [])
    eng.setdefault("decisions", [])
    eng.setdefault("people", [])
    eng.setdefault("counters", {})
    eng.setdefault("updated", None)
    return cast(Engagement, eng)


def next_id(container: Mapping[str, Any], key: str, prefix: str) -> str:
    """f1, f2, ... for container[key]. A stored counter means the id of a removed item is never handed out again."""
    counters: dict[str, int] = container.setdefault("counters", {})    # type: ignore[attr-defined]
    top = counters.get(prefix, 0)
    for item in container[key]:
        match = re.fullmatch(prefix + r"(\d+)", item["id"])
        if match:
            top = max(top, int(match.group(1)))
    counters[prefix] = top + 1
    return f"{prefix}{top + 1}"


def fact_map(eng: Engagement | None) -> dict[str, Fact]:
    """{fact id: fact} for an engagement (empty when there is none)."""
    return {f["id"]: f for f in eng["facts"]} if eng else {}


def words(text: str | None) -> int:
    """Number of words in the text."""
    return len((text or "").split())


def story_text(story: Story, style: str = styles.DEFAULT_STYLE, sep: str = " ") -> str:
    """All the text a listener could hear: the parts of the style, then the spoken versions, joined by `sep`."""
    parts = [styles.part_text(part, story) for part in styles.get(style).parts]
    parts += [story["spoken"].get(key) for key in SPOKEN_LIMITS]
    return sep.join(str(part) for part in parts if part)


def check_fact(fact: Fact) -> list[str]:
    """Problems with one fact, as messages."""
    problems = []
    if not (fact.get("text") or "").strip():
        problems.append("fact has no text")
    if fact.get("basis") not in FACT_BASES:
        problems.append(f"basis must be one of {', '.join(FACT_BASES)}")
    if fact.get("basis") == "verified-doc" and not str(fact.get("source") or "").startswith(("http://", "https://")):
        problems.append("a verified-doc fact needs a source URL")
    return problems


def validate_engagement(eng: Engagement) -> list[Issue]:
    """Errors in an engagement's facts and decisions."""
    out: list[Issue] = []
    seen: set[str] = set()
    for fact in eng["facts"]:
        if fact["id"] in seen:
            out.append(("error", f"{eng['id']}: duplicate fact id {fact['id']}"))
        seen.add(fact["id"])
        out += [("error", f"{eng['id']}.{fact['id']}: {msg}") for msg in check_fact(fact)]
    for dec in eng["decisions"]:
        if dec.get("ownership") not in OWNERSHIP:
            out.append(("error", f"{eng['id']}.{dec['id']}: ownership must be one of {', '.join(OWNERSHIP)}"))
        if not (dec.get("what") or "").strip():
            out.append(("error", f"{eng['id']}.{dec['id']}: decision has no 'what'"))
    return out


def _check_links(story: Story, eng: Engagement | None, facts: Mapping[str, Fact]) -> list[Issue]:
    out: list[Issue] = []
    if story["status"] not in STATUSES:
        out.append(("error", f"status must be one of {', '.join(STATUSES)}"))
    if story["engagement"] and not eng:
        out.append(("error", f"linked engagement {story['engagement']} does not exist"))
    if story["uses_facts"] and not story["engagement"]:
        out.append(("error", "uses_facts needs a linked engagement"))
    for fid in story["uses_facts"]:
        fact = facts.get(fid)
        if fact is None:
            out.append(("error", f"uses fact {fid}, which is not in the engagement"))
        elif fact["basis"] not in USABLE_BASES:
            out.append(("error", f"fact {fid} is '{fact['basis']}' and cannot back a story: "
                                 "confirm it (fact set --basis stated) or unlink it"))
    return out


def _check_metrics(story: Story) -> list[Issue]:
    out: list[Issue] = []
    for metric in story["metrics"]:
        if metric.get("basis") not in METRIC_BASES:
            out.append(("error", f"metric '{metric.get('name')}' basis must be one of {', '.join(METRIC_BASES)}"))
        if not str(metric.get("name") or "").strip() or not str(metric.get("value") or "").strip():
            out.append(("error", "every metric needs a name and a value"))
    return out


def _check_done(story: Story, style: str, marking: bool) -> list[Issue]:
    """The done rule. Marking a story done needs every part of the style in force. A story already stored as
    done stays valid while it is complete in any style; a gap in the style in force is then only a warning."""
    if story["status"] != "done":
        return []
    missing = styles.missing_parts(style, story)
    if not missing:
        return []
    if marking or not styles.complete_styles(story):
        return [("error", "cannot be done, still empty: " + ", ".join(part.name for part in missing))]
    return [("warn", f"{part.label} is empty in {style}") for part in missing]


def _check_text_rules(story: Story, text: str, style: str, marking: bool) -> list[Issue]:
    out: list[Issue] = []
    lowered = text.lower()
    for term in story["never_say"]:
        if term.lower() in lowered:
            out.append(("error", f"text contains a never_say term: '{term}'"))
    out += _check_done(story, style, marking)
    if not story["engagement"] and story["status"] != "empty":
        out.append(("warn", "no engagement linked (facts and decisions are not tracked for this story)"))
    return out


def _squash(text: str) -> str:
    return re.sub(r"\s", "", text)


def _numbers(text: str) -> set[str]:
    """The percentages and money amounts in the text, without spaces or a closing full stop or comma."""
    return {_squash(x).rstrip(".,") for x in _NUM.findall(text)}


def _unhedged_numbers(text: str) -> set[str]:
    """The numbers quoted in a sentence that has no hedge word ('about', 'estimated', ...)."""
    return set().union(*(_numbers(s) for s in _SENTENCE.split(text) if not _HEDGE.search(s)))


def _check_numbers(story: Story, text: str, facts: Mapping[str, Fact]) -> list[Issue]:
    """Warn about a number with no metric or fact giving that exact number, and an estimate quoted without a hedge."""
    out: list[Issue] = []
    backing = [str(m.get("value", "")) for m in story["metrics"]] + [facts[i]["text"] for i in story["uses_facts"]
                                                                     if i in facts]
    known = _numbers(" ".join(backing))
    hedged = _numbers(" ".join(str(m["value"]) for m in story["metrics"] if m.get("basis") in HEDGED_METRIC_BASES))
    unhedged = _unhedged_numbers(text)
    for number in sorted(_numbers(text)):
        if number not in known:
            out.append(("warn", f"number {number} in the text has no metric or fact behind it"))
        elif number in hedged and number in unhedged:
            out.append(("warn", f"number {number} is an estimate: say 'estimated' or 'about' when you quote it"))
    return out


def _check_voice(story: Story) -> list[Issue]:
    out: list[Issue] = []
    for key, cap in SPOKEN_LIMITS.items():
        count = words(story["spoken"].get(key))
        if count > cap:
            out.append(("warn", f"spoken {key} is {count} words; aim for {cap} or fewer"))
    action = story.get("action") or ""
    i_count, we_count = len(_I_WORD.findall(action)), len(_WE_WORD.findall(action))
    if action and we_count > i_count:
        out.append(("warn", f"action says 'we/our' {we_count} times and 'I' {i_count} times: make your own part clear"))
    if story["status"] == "done" and story["follow_ups"]:
        out.append(("warn", f"{len(story['follow_ups'])} follow-up(s) still open"))
    return out


def validate_story(story: Story, eng: Engagement | None = None, style: str = styles.DEFAULT_STYLE,
                   marking: bool = False) -> list[Issue]:
    """Return [(level, message)], level 'error' blocks status done, 'warn' is advice.

    `style` is the style in force; `marking` is true while the story is being marked done (see `_check_done`).
    """
    facts = fact_map(eng)
    text = story_text(story, style)
    found = (_check_links(story, eng, facts) + _check_metrics(story) + _check_text_rules(story, text, style, marking)
             + _check_numbers(story, story_text(story, style, "\n"), facts) + _check_voice(story))
    return [(level, f"{story['id']}: {message}") for level, message in found]


def _metric_line(metric: Metric) -> str:
    note = f" - {metric['note']}" if "note" in metric else ""
    return f"- {metric['name']}: {metric['value']} ({metric['basis']}){note}"


def _decision_line(dec: Decision) -> str:
    alternatives = ", ".join(dec.get("alternatives") or [])
    return (f"- {dec['what']} - why: {dec.get('why') or '-'}" + (f"; alternatives: {alternatives}" if alternatives else "")
            + (f"; trade-offs: {dec['tradeoffs']}" if "tradeoffs" in dec else ""))


def _engagement_sections(eng: Engagement) -> list[str]:
    lines: list[str] = []
    unsure = [f for f in eng["facts"] if f["basis"] == "unsure"]
    if unsure:
        lines += ["", "## Unsure (say 'I believe' or leave out)"] + [f"- {f['text']}" for f in unsure]
    mine = [d for d in eng["decisions"] if d.get("ownership") in OWNED_DECISIONS]
    if mine:
        lines += ["", "## My decisions and trade-offs"] + [_decision_line(d) for d in mine]
    return lines


def render_story_md(story: Story, eng: Engagement | None = None, style: str = styles.DEFAULT_STYLE) -> str:
    """One-page markdown cheat sheet for a story, headed with the parts of the style.

    Spoken versions are printed as stored, with a note, in every style.
    """
    lines = [f"# {story['id']}: {story['headline'] or story['theme']}", "",
             f"{story.get('company_name', '')} | theme: {story['theme']} | status: {story['status']}"]
    if eng:
        lines.append(f"Engagement: {eng['id']} - {eng.get('title') or ''} (role: {eng.get('my_role') or '-'})")
    chosen = styles.get(style)
    for part in chosen.parts:
        lines += ["", f"## {part.label}", styles.part_text(part, story) or "-"]
    if story["metrics"]:
        lines += ["", "## Numbers (say them with their label)"] + [_metric_line(m) for m in story["metrics"]]
    spoken = [key for key in SPOKEN_LIMITS if story["spoken"].get(key)]
    for key in spoken:
        lines += ["", f"## Spoken ({key}, {words(story['spoken'][key])} words)", story["spoken"][key] or ""]
    if spoken:
        lines += ["", f"*Spoken versions are shown as written; they are not rearranged to {chosen.name}.*"]
    if story.get("lessons") and "lessons" not in styles.stored_fields(style):
        lines += ["", "## Lessons", story["lessons"] or ""]
    if story["likely_questions"]:
        lines += ["", "## Likely questions"] + [f"- {q}" for q in story["likely_questions"]]
    if story["never_say"]:
        lines += ["", "## Never say"] + [f"- {t}" for t in story["never_say"]]
    if eng:
        lines += _engagement_sections(eng)
    if story["follow_ups"]:
        lines += ["", "## Open follow-ups"] + [f"- {q}" for q in story["follow_ups"]]
    return "\n".join(lines) + "\n"


def _snippet(text: str, needle: str) -> str:
    """The text around the first match of needle, on one line."""
    start = text.lower().index(needle)
    lead = "..." if start > SNIPPET_BEFORE else ""
    return lead + text[max(0, start - SNIPPET_BEFORE): start + len(needle) + SNIPPET_AFTER].replace("\n", " ")


def _story_candidates(story: Story) -> Iterable[tuple[str, Any]]:
    for name in (*TEXT_FIELDS, "headline"):
        yield name, story.get(name)
    for key, value in story["spoken"].items():
        yield f"spoken.{key}", value
    for name in LIST_FIELDS:
        for item in story[name]:
            yield name, item


def _engagement_candidates(eng: Engagement) -> Iterable[tuple[str, Any]]:
    for name in ENG_TEXT_FIELDS:
        yield name, eng.get(name)
    for fact in eng["facts"]:
        yield f"fact {fact['id']} ({fact['basis']})", fact["text"]
    for dec in eng["decisions"]:
        for key in ("what", "why", "tradeoffs"):
            yield f"decision {dec['id']}.{key}", dec.get(key)


def search(stories: Iterable[Story], engagements: Iterable[Engagement], needle: str) -> list[Hit]:
    """Case-insensitive substring search over story text and engagement facts/decisions."""
    wanted = needle.lower()
    hits: list[Hit] = []
    for story in stories:
        hits += [("story", story["id"], field, _snippet(str(text), wanted))
                 for field, text in _story_candidates(story) if text and wanted in str(text).lower()]
    for eng in engagements:
        hits += [("engagement", eng["id"], field, _snippet(str(text), wanted))
                 for field, text in _engagement_candidates(eng) if text and wanted in str(text).lower()]
    return hits
