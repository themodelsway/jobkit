"""Researched target companies: the facts a save must carry, a company's state, and matching values to stories.

Nothing about a company is shipped. The `interview-prep` skill tells the agent to read pages about a company's
hiring process, vet each fact and save it; this module checks what it can see (link, quote length, label, date of
pull, the agent's vetting confirmation, links on known user-content sites), stores, dates and ages the facts, and
matches each company value to the user's stories and leadership questions by theme or by whole word. It never
fetches a page, so it cannot check that a quote is on its page. Library module with no command line.
"""
from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Final
from urllib.parse import urlparse

from jk.common import ToolError
from jk.interview import styles
from jk.interview import target_tables as tt
from jk.user import profile

Record = dict[str, Any]
KINDS: Final[tuple[str, ...]] = ("value", "round", "grading", "question", "questioning")
LABELS: Final[tuple[str, ...]] = ("company-references", "othersite-references")
BASES: Final[tuple[str, ...]] = ("stated", "inferred")
MAX_QUOTE_WORDS: Final[int] = 40
FOUND: Final[str] = "found"
NONE_FOUND: Final[str] = "none found"
VALUE_STATES: Final[tuple[str, ...]] = ("covered", "possible", "no story", "needs your judgment")
# Sites whose content is written by individual users, and the user-written pages of job sites. A fixed list: the
# skill tells the agent to leave out any other user-written page, which this code cannot recognise.
USER_HOSTS: Final[tuple[str, ...]] = (
    "reddit.com", "quora.com", "stackexchange.com", "stackoverflow.com", "news.ycombinator.com", "teamblind.com",
    "fishbowlapp.com", "levels.fyi", "medium.com", "substack.com", "twitter.com", "x.com", "facebook.com",
    "youtube.com", "tiktok.com", "discord.com", "ambitionbox.com", "comparably.com", "kununu.com")
JOB_SITES: Final[tuple[str, ...]] = ("glassdoor", "indeed", "linkedin", "ziprecruiter", "monster", "simplyhired",
                                     "careerbliss", "jobcase", "naukri", "seek")
USER_PAGES: Final[re.Pattern[str]] = re.compile(
    r"/(?:cmp/[^/]+/)?(?:reviews?|interviews?|interview-questions|salar(?:y|ies)|benefits|faq|questions?|answers?|"
    r"comments?|forums?|community|posts?|pulse|feed)(?:[/_.-]|$)|/Working-at-",
    re.IGNORECASE)


# ---------------------------------------------------------------- facts and saves

def site(link: str) -> str:
    """The name of the site a link is on: its host without `www.`."""
    host = urlparse(link).hostname or ""
    return host.removeprefix("www.")


def user_content(link: str) -> bool:
    """True when a link is on a known user-content site, or on a job site's reviews, interview reports, salaries,
    questions and answers or member posts. Other pages of a job site (its own articles) are accepted."""
    host = site(link)
    if any(host == h or host.endswith("." + h) for h in USER_HOSTS):
        return True
    job_site = any(part in JOB_SITES for part in host.split("."))
    return job_site and bool(USER_PAGES.search(urlparse(link).path))


def _day(value: Any) -> date | None:
    """A YYYY-MM-DD date from text, or None when it is not one."""
    try:
        return date.fromisoformat(value) if isinstance(value, str) and len(value) == 10 else None
    except ValueError:
        return None


def _link_problem(link: Any) -> str | None:
    """Why a reference link is refused, or None."""
    if not isinstance(link, str) or not link.strip():
        return "has no reference link (every fact needs a link to the page it came from)"
    try:
        parts = urlparse(link)
        valid = parts.scheme in ("http", "https") and bool(parts.hostname)
    except ValueError:
        valid = False
    if not valid:
        return f"has a link that is not an http or https address: {link!r}"
    if user_content(link):
        return f"links to user-written content ({site(link)}), which is not accepted"
    return None


def fact_problems(fact: Any, today: date) -> list[str]:
    """Everything wrong with one fact of a save (empty when it can be stored)."""
    if not isinstance(fact, dict):
        return ["is not an object"]
    problems = [p for p in [_link_problem(fact.get("link"))] if p]
    quote = fact.get("quote")
    if not isinstance(quote, str) or not quote.strip():
        problems.append("has no quote (copy a short passage word for word from the page)")
    elif len(quote.split()) > MAX_QUOTE_WORDS:
        problems.append(f"has a quote of {len(quote.split())} words; at most {MAX_QUOTE_WORDS} are allowed")
    if fact.get("kind") not in KINDS:
        problems.append(f"has kind {fact.get('kind')!r}; use {', '.join(KINDS)}")
    if fact.get("label") not in LABELS:
        problems.append(f"has label {fact.get('label')!r}; use {' or '.join(LABELS)}")
    pulled = _day(fact.get("pulled"))
    if pulled is None or pulled > today:
        problems.append(f"has date of pull {fact.get('pulled')!r}; give the date the page was read (YYYY-MM-DD, "
                        "not in the future)")
    if fact.get("vetted") is not True:
        problems.append("is not vetted: the save must confirm the page was read, the quote is on it and it is not "
                        "written by individual users (\"vetted\": true)")
    if not isinstance(fact.get("wording"), str) or not fact["wording"].strip():
        problems.append("has no wording (a short statement of what the quote says)")
    return problems + _value_problems(fact)


def _text(value: Any) -> bool:
    """True for a string that is not blank."""
    return isinstance(value, str) and bool(value.strip())


def _value_problems(fact: Mapping[str, Any]) -> list[str]:
    """Problems with the value-only fields: a value needs a name; themes and hints are lists of words."""
    problems = []
    if fact.get("kind") == "value" and not _text(fact.get("name")):
        problems.append("is a value with no name (a 'name' in words)")
    if fact.get("value") is not None and not _text(fact.get("value")):
        problems.append("has a 'value' that is not the id of a value")
    for field in ("themes", "hints"):
        value = fact.get(field, [])
        if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
            problems.append(f"has {field} that are not a list of words")
    return problems


def read_save(raw: str) -> Record:
    """A save from JSON text: {"name": ..., "facts": [...], "suggested_style": {...}}; ToolError for a mistake."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ToolError(f"The save is not valid JSON ({error}).") from error
    if not isinstance(data, dict) or not isinstance(data.get("facts", []), list):
        raise ToolError("The save must be a JSON object with a 'facts' list (see `target --help`).")
    if data.get("name") is not None and not _text(data["name"]):
        raise ToolError("Nothing was saved: the save's 'name' must be the company name in words.")
    return data


def _clean(fact: Mapping[str, Any]) -> Record:
    """The stored form of a checked fact: the known fields only, text trimmed."""
    keep = ("id", "kind", "name", "wording", "quote", "link", "label", "pulled", "vetted", "themes", "hints", "value")
    out = {k: fact[k] for k in keep if fact.get(k) is not None}
    out.update({k: out[k].strip() for k in ("name", "wording", "quote", "link") if isinstance(out.get(k), str)})
    if out.get("kind") == "value":
        out.setdefault("themes", [])
        out.setdefault("hints", [])
    return out


def _merge_facts(old: Sequence[Record], new: Sequence[Mapping[str, Any]], today: date) -> list[Record]:
    """The old facts with the new ones added or replacing by id; ToolError naming every refused fact."""
    problems, seen = [], set()
    for number, fact in enumerate(new, 1):
        fid = fact.get("id") if isinstance(fact, dict) else None
        name = f"fact {fid!r}" if isinstance(fid, str) and fid.strip() else f"fact #{number}"
        if not isinstance(fid, str) or not fid.strip():
            problems.append(f"{name}: has no id (an id in words)")
        elif fid in seen:
            problems.append(f"{name}: the id is used twice in this save")
        else:
            seen.add(fid)
        problems += [f"{name}: {p}" for p in fact_problems(fact, today)]
    if problems:
        raise ToolError("Nothing was saved:\n  " + "\n  ".join(problems))
    merged = {f["id"]: f for f in old}
    for fact in new:
        merged[fact["id"]] = _clean(fact)
    return list(merged.values())


def _check_links(facts: Sequence[Mapping[str, Any]]) -> None:
    """A question's `value` must name a value of the same company."""
    value_ids = {f["id"] for f in facts if f["kind"] == "value"}
    wrong = [f["id"] for f in facts if f["kind"] == "question" and f.get("value") and f["value"] not in value_ids]
    if wrong:
        raise ToolError("Nothing was saved: question(s) " + ", ".join(wrong) + " name a value this company does not have.")


def _suggestion(spec: Any, facts: Sequence[Mapping[str, Any]]) -> tuple[str | None, str | None, list[str]]:
    """(style, basis, fact ids) of a suggested answer style; ToolError for a wrong one."""
    if spec is None:
        return None, None, []
    if not isinstance(spec, dict) or spec.get("style") not in styles.names() or spec.get("basis") not in BASES:
        raise ToolError("Nothing was saved: 'suggested_style' needs a 'style' (" + ", ".join(styles.names())
                        + ") and a 'basis' (" + " or ".join(BASES) + ").")
    ids = spec.get("facts", [])
    known = {f["id"] for f in facts}
    if not isinstance(ids, list) or not ids or any(not _text(i) or i not in known for i in ids):
        raise ToolError("Nothing was saved: 'suggested_style' must list the ids of the stored facts it rests on.")
    return spec["style"], spec["basis"], list(ids)


def merge_save(existing: Mapping[str, Any] | None, data: Mapping[str, Any], today: date) -> Record:
    """The company after a save: facts added or replaced by id, the others kept, the suggestion replaced when the
    save gives one. Raises ToolError, and nothing is stored, when any part is refused."""
    name = str(data.get("name") or (existing or {}).get("name") or "").strip()
    if not name:
        raise ToolError("Nothing was saved: the save has no company 'name'.")
    facts = _merge_facts((existing or {}).get("facts", []), data.get("facts", []), today)
    if not facts:
        raise ToolError("Nothing was saved: a save needs at least one fact (use `target none-found` when no page "
                        "qualified).")
    _check_links(facts)
    company: Record = {"key": tt.key_of(name), "name": (existing or {}).get("name") or name, "outcome": FOUND,
                       "researched": today.isoformat(), "facts": facts, "style": None, "style_basis": None,
                       "style_facts": []}
    if existing and "suggested_style" not in data and all(i in {f["id"] for f in facts} for i in existing.get("style_facts", [])):
        company.update(style=existing.get("style"), style_basis=existing.get("style_basis"),
                       style_facts=existing.get("style_facts", []))
    if "suggested_style" in data:
        company["style"], company["style_basis"], company["style_facts"] = _suggestion(data["suggested_style"], facts)
    return company


# ---------------------------------------------------------------- state

def research_days() -> int:
    """The research window in days (the profile setting, 30 when not set)."""
    return profile.research_days()


def stale_facts(company: Mapping[str, Any], window: int, today: date) -> list[str]:
    """Ids of the facts read more than `window` days ago."""
    return [f["id"] for f in company["facts"] if (today - date.fromisoformat(f["pulled"])).days > window]


def state(company: Mapping[str, Any] | None, window: int, today: date) -> str:
    """`fresh`, `stale`, `none found` or `not researched` (see the target-companies spec)."""
    if company is None:
        return "not researched"
    if company["outcome"] == NONE_FOUND:
        return "stale" if (today - date.fromisoformat(company["researched"])).days > window else NONE_FOUND
    return "stale" if not company["facts"] or stale_facts(company, window, today) else "fresh"


def find(name: str | None, use_default: bool = False, none_found: bool = False) -> Record:
    """The company called `name` (any letter case); with `use_default` and no name, the profile's default company.
    A company recorded as none found is returned only with `none_found`, whether named or the default.

    Raises:
        ToolError: no name and no default, no profile by that name (the message lists the ones that exist), or a
            company recorded as none found when `none_found` is not set.
    """
    names = ", ".join(tt.company_names()) or "none yet"
    default = not name and use_default
    if default:
        name = profile.target_company()
        if not name:
            raise ToolError(f"No company given and no default company is set. Researched companies: {names}.")
    found = tt.load_company(name or "")
    if found is None:
        raise ToolError(f"The default company {name!r} no longer exists. Researched companies: {names}." if default
                        else f"No researched profile for {name!r}. Researched companies: {names}.")
    if found["outcome"] != FOUND and not none_found:
        raise ToolError(f"Research found no qualifying page for {found['name']} ({found['researched']}), so there is "
                        "nothing to prepare against for it. Practise without the company.")
    return found


# ---------------------------------------------------------------- matching

@dataclass(frozen=True)
class Item:
    """A story or leadership question, as the matching sees it."""

    id: str
    kind: str                # "story" or "leader"
    themes: frozenset[str]
    text: str
    has_content: bool


def story_item(story: Mapping[str, Any]) -> Item:
    """A story: its theme and extra themes, its text, and whether it has content (it is not empty)."""
    text = " ".join(str(story.get(f) or "") for f in ("headline", "situation", "task", "action", "result", "lessons"))
    return Item(story["id"], "story", frozenset([story["theme"], *story.get("also_themes", [])]), text,
                story.get("status") != "empty")


def question_item(question: Mapping[str, Any], progress: Mapping[str, Any] | None) -> Item:
    """A leadership question: its themes, its text, and whether the user has written a principle or an example."""
    entry = progress or {}
    filled = bool(str(entry.get("principle") or "").strip()) or any(
        any(str(v or "").strip() for k, v in fields.items() if k != "skipped")
        for fields in (entry.get("examples") or {}).values())
    return Item(question["id"], "leader", frozenset(question.get("themes", [])), question.get("question", ""), filled)


def values(company: Mapping[str, Any]) -> list[Record]:
    """The company's values, in stored order."""
    return [f for f in company["facts"] if f["kind"] == "value"]


def mentions(words: Iterable[str], text: str) -> bool:
    """True when any of the words appears in the text as a whole word, in any letter case."""
    return any(re.search(rf"\b{re.escape(word)}\b", text, re.IGNORECASE) for word in words)


def how(value: Mapping[str, Any], item: Item) -> str | None:
    """`theme` when the item has a theme the value lists, `word` when a hint word is in its text, else None."""
    if item.themes & set(value.get("themes", [])):
        return "theme"
    return "word" if mentions(value.get("hints", []), item.text) else None


def matches(company: Mapping[str, Any], item: Item) -> list[tuple[Record, str]]:
    """(value, how) for every value of the company the item matches."""
    return [(value, found) for value in values(company) if (found := how(value, item))]


def value_state(value: Mapping[str, Any], items: Iterable[Item]) -> str:
    """One of the four states of a value, from the items it could match (see the target-companies spec)."""
    if not value.get("themes") and not value.get("hints"):
        return "needs your judgment"
    found = [(item, how(value, item)) for item in items]
    if any(h == "theme" and item.has_content for item, h in found):
        return "covered"
    if any(h == "word" for _, h in found):
        return "possible"
    return "no story"


def group(company: Mapping[str, Any], item: Item) -> tuple[int, int]:
    """Sort key of an item for a company: theme matches first, then word matches, then the rest; inside a group,
    more matching values first."""
    found = matches(company, item)
    kinds = {h for _, h in found}
    return (0 if "theme" in kinds else 1 if kinds else 2, -len(found))


def questions_for(company: Mapping[str, Any], value_id: str) -> list[Record]:
    """The stored typical questions of one value."""
    return [f for f in company["facts"] if f["kind"] == "question" and f.get("value") == value_id]


def unknown_themes(company: Mapping[str, Any], items: Iterable[Item]) -> list[str]:
    """Themes the company's values list that none of the user's stories or questions use."""
    have = {theme for item in items for theme in item.themes}
    return sorted({t for value in values(company) for t in value.get("themes", []) if t not in have})


# ---------------------------------------------------------------- text

def fact_source(fact: Mapping[str, Any]) -> str:
    """Where a fact came from, for the user: its label, the site, the date of pull and the vetting."""
    vetted = "vetted" if fact.get("vetted") else "not vetted"
    return f"[{fact['label']}, {site(fact['link'])}, read {fact['pulled']}, {vetted}]"


def fact_text(fact: Mapping[str, Any]) -> str:
    """One fact as a line: the value name (for a value), the wording and where it came from."""
    head = f"{fact['name']}: " if fact.get("name") else ""
    return f"{fact['id']}  {head}{fact['wording']} {fact_source(fact)}"


def suggestion_text(company: Mapping[str, Any]) -> str | None:
    """The suggested answer style: `stated` with its facts, or `inferred` shown as our suggestion; None without."""
    if not company.get("style"):
        return None
    ids = ", ".join(company.get("style_facts", []))
    if company.get("style_basis") == "stated":
        return f"suggested style: {company['style']} (stated by the company, see {ids})"
    return f"suggested style: {company['style']} (our suggestion, not the company's word; based on {ids})"


def grading(company: Mapping[str, Any]) -> list[Record]:
    """What the company's graders look for: its grading notes."""
    return [f for f in company["facts"] if f["kind"] == "grading"]
