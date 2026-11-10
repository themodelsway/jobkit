"""The code pass: requirements that stored facts can rate without a model.

Named skills (from the stored vocabulary and aliases), the level of a degree, certifications, and total years
of experience. Each result has an id starting `code:`; pass 1 copies that id into its request and `check`
replaces whatever level the agent gave it with the code's. "Or related field" wording, years tied to one skill
and certifications the user does not hold are left to pass 1. The thresholds are placeholders to tune.
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Any, Final, NotRequired, TypedDict

from jobkit import common
from jobkit.resumes import evidence
from jobkit.resumes import match_facts as mf
from jobkit.resumes import query_resume as qr
from jobkit.resumes.match_request import Request

YEARS_FULL: Final[Decimal] = Decimal("1.00")           # share of the asked years that earns each level
YEARS_SUBSTANTIAL: Final[Decimal] = Decimal("0.75")
YEARS_PARTIAL: Final[Decimal] = Decimal("0.40")
SKILL_FULL_LINES: Final[int] = 2                       # lines that show a skill for full credit (one is substantial)
MAX_EVIDENCE: Final[int] = 3
DEGREE_RANKS: Final[tuple[tuple[int, re.Pattern[str]], ...]] = (
    (3, re.compile(r"(?<![a-z])(ph\.?d|doctorate|doctoral)(?![a-z])", re.I)),
    (2, re.compile(r"(?<![a-z])(master(?:['\u2019]?s)?|mba|m\.s\.|msc|m\.?tech|m\.?eng)(?![a-z])", re.I)),
    (1, re.compile(r"(?<![a-z])(bachelor(?:['\u2019]?s)?|b\.s\.|bsc|b\.?tech|b\.?eng|b\.a\.|"
                   r"undergraduate degree)(?![a-z])", re.I)),
)
CERT_LEVELS: Final[dict[str, int]] = {"foundational": 1, "practitioner": 1, "fundamentals": 1, "associate": 2,
                                      "professional": 3, "specialty": 3, "expert": 3}
TOTAL_YEARS: Final[re.Pattern[str]] = re.compile(
    r"(\d{1,2})\s*\+?\s*(?:or more\s+)?(?:years?|yrs?)\s+(?:of\s+)?"
    r"(?:(?:relevant|professional|industry|related|work|hands-on|total|overall|progressive)\s+)*experience\b"
    r"(?!\s+(?:with|in|using|of|on|building|designing|developing|leading|managing|working|across|within|as)\b)",
    re.I)
OPEN_ENDED: Final[re.Pattern[str]] = re.compile(r"\b(related|equivalent|similar)\b", re.I)


class CodeItem(TypedDict):
    """A requirement rated by code."""

    id: str
    kind: str
    label: str
    quote: str
    section: str
    level: str
    evidence: list[str]
    reason: str
    set_aside: NotRequired[list[str]]     # lines set aside or capped, in plain words (skills only)


def sentences(text: str) -> list[tuple[str, str]]:
    """(sentence, the posting heading it sat under) for every sentence or list line of the posting."""
    out: list[tuple[str, str]] = []
    section = ""
    for raw in text.replace("\r\n", "\n").split("\n"):
        line = raw.strip().lstrip("-*• ").strip()
        if not line:
            continue
        if _is_heading(raw.strip()):
            section = line.rstrip(":")
            continue
        out += [(s.strip(), section) for s in re.split(r"(?<=[.!?])\s+", line) if s.strip()]
    return out


def _is_heading(line: str) -> bool:
    """True for a short line that names a section ("Qualifications:", "WHAT YOU WILL DO")."""
    if not line or line[0] in "-*•" or len(line) > 60 or line.endswith((".", ";", ",")):
        return False
    return line.endswith(":") or line.isupper() or (len(line.split()) <= 4 and line.istitle())


def _sentence_with(parts: list[tuple[str, str]], pattern: str) -> tuple[str, str]:
    """The first sentence matching the pattern (case-insensitive) and its heading, or ("", "")."""
    for sentence, section in parts:
        if re.search(pattern, sentence, re.I):
            return sentence[:240], section
    return "", ""


def code_pass(posting: str, facts: mf.ResumeFacts, today: date | None = None) -> list[CodeItem]:
    """Every requirement the stored facts can rate, in a fixed order: skills, degrees, certifications, years."""
    parts = sentences(posting)
    items = _skills(posting, parts, facts) + _degrees(parts, facts) + _certifications(posting, parts, facts)
    years = _years(parts, facts, today or date.today())
    return items + ([years] if years else [])


def _slug(text: str) -> str:
    """Id-safe form of a name."""
    return common.slug(text) or "item"


def _skills(posting: str, parts: list[tuple[str, str]], facts: mf.ResumeFacts) -> list[CodeItem]:
    """Skills the posting names that the stored vocabulary knows, rated by how many lines show them."""
    skills: Any = facts.skills
    terms = qr.vocabulary(skills)
    counts = qr.jd_skills(posting, terms)
    out: list[CodeItem] = []
    for name in sorted(counts):
        tagged = [(cid, b) for cid, c in facts.companies.items() for b in c["bullets"]
                  if name in (*b.get("skills", []), *b.get("skills_manual", []))]
        states = [(cid, b, evidence.line_state(b, name, terms)) for cid, b in tagged]
        lines = [(cid, b["id"]) for cid, b, s in states if s == evidence.OK]
        training = [(cid, b["id"]) for cid, b, s in states if s == evidence.CONFIRM_USE]
        mentions = sum(evidence.weight(b) for _, b, s in states if s == evidence.OK)
        level = "full" if mentions >= SKILL_FULL_LINES else "substantial" if lines else "partial"
        if name in skills.get("tag_only", []) and not (lines or training):
            continue            # a quality word with no usable line is not resume evidence
        cited = (lines or training)[:MAX_EVIDENCE]
        refs = [mf.bullet_ref(facts, cid, bid) for cid, bid in cited] + [f"skill:{name}"]
        quote, section = _sentence_with(parts, re.escape(name))
        out.append({"id": f"code:skill:{_slug(name)}", "kind": "skill", "label": name, "quote": quote,
                    "section": section, "level": level, "evidence": refs,
                    "reason": _skill_reason(name, lines, training, bool(tagged)),
                    "set_aside": _set_aside(name, states)})
    return out


def _skill_reason(name: str, lines: list[tuple[str, str]], training: list[tuple[str, str]], tagged: bool) -> str:
    """Why a skill got its level, in plain words."""
    if lines:
        return f"{name} is shown in {len(lines)} stored line(s)"
    if training:
        return f"{name} appears only in lines that read like training, so it counts for at most partial"
    return f"{name} is only in the skills list: " + (
        "the lines that mention it are flagged, ignored, or not demonstrated in your profile"
        if tagged else "no line shows it")


def _set_aside(name: str, states: list[tuple[str, Any, str | None]]) -> list[str]:
    """One plain sentence for each line that is not demonstrated or reads like training, quoted so it can be found."""
    notes = []
    for _, bullet, state in states:
        quote = bullet["text"][:100]
        if state == evidence.NOT_DEMONSTRATED:
            notes.append(f"{name}: not demonstrated in your profile, because a line says it was not used at work: "
                         f"\u201c{quote}\u201d")
        elif state == evidence.CONFIRM_USE:
            notes.append(f"{name}: a line reads like training, so it counts for at most partial; worth confirming "
                         f"whether you also used it at work: \u201c{quote}\u201d")
    return notes


def degree_rank(text: str) -> int:
    """0 when the text names no degree, else 1 bachelor, 2 master, 3 doctorate."""
    return next((rank for rank, pattern in DEGREE_RANKS if pattern.search(text)), 0)


FIELD_SKIP: Final[frozenset[str]] = frozenset({"degree", "field", "related", "and", "the", "any", "with", "from"})
RELATED_FIELDS: Final[tuple[frozenset[str], ...]] = tuple(frozenset(group) for group in (
    ("computer science", "software engineering", "computer engineering", "information technology",
     "information systems", "informatics"),
    ("electrical engineering", "electronics", "electronic engineering", "computer engineering"),
    ("finance", "accounting", "economics"), ("statistics", "mathematics", "data science", "applied mathematics"),
    ("business administration", "management", "business"), ("physics", "applied physics")))


def _field_phrase(sentence: str) -> str:
    """The field a degree sentence names ("in Computer Science") as normalised lower-case words, or ""."""
    found = re.search(r"\bin\s+([A-Za-z][A-Za-z ,/&-]{2,60})", sentence)
    if not found:
        return ""
    phrase = re.split(r"[,.;]|\bor\b|\band\b|\bfrom\b", found.group(1))[0]
    return " ".join(w for w in re.findall(r"[a-z]{3,}", phrase.lower()) if w not in FIELD_SKIP)


def _field_level(phrase: str, line: str) -> str:
    """full when the stored degree names the whole field, substantial when it names a related field from the
    table, else partial. One shared word ("Science") is not a match."""
    text = _norm(line)
    if re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", text):
        return "full"
    for group in RELATED_FIELDS:
        if phrase in group and any(re.search(rf"(?<![a-z0-9]){re.escape(name)}(?![a-z0-9])", text)
                                   for name in group - {phrase}):
            return "substantial"
    return "partial"


def _degrees(parts: list[tuple[str, str]], facts: mf.ResumeFacts) -> list[CodeItem]:
    """Degree requirements, one per level and field, rated by level and, when the posting names a field, by that
    field. The first requirement of a level has the id `code:degree:N`; another field at the same level adds
    `:field`."""
    out: list[CodeItem] = []
    seen: set[tuple[int, str]] = set()
    for sentence, section in parts:
        asked = degree_rank(sentence)
        field = _field_phrase(sentence) if asked else ""
        if not asked or (asked, field) in seen or OPEN_ENDED.search(sentence):
            continue
        plain = not any(rank == asked for rank, _ in seen)
        seen.add((asked, field))
        level, refs, reason = _rate_degree(asked, field, facts)
        rid = f"code:degree:{asked}" if plain else f"code:degree:{asked}:{_slug(field or 'any')}"
        out.append({"id": rid, "kind": "degree", "label": ("bachelor", "master", "doctorate")[
            asked - 1] + " degree" + (f" in {field}" if field else ""), "quote": sentence[:240], "section": section,
                    "level": level, "evidence": refs, "reason": reason})
    return out


def _rate_degree(asked: int, field: str, facts: mf.ResumeFacts) -> tuple[str, list[str], str]:
    """(level, evidence, reason) for a degree of at least this rank, with an optional whole-field check."""
    held = [(i, line) for i, line in enumerate(facts.education, 1) if degree_rank(line) >= asked]
    if not held:
        return "profile_miss", [], "no stored education shows a degree at this level"
    if not field:
        return "full", [f"education:{held[0][0]}"], "a stored degree meets the level asked"
    rank = {"full": 0, "substantial": 1, "partial": 2}
    number, line = min(held, key=lambda pair: rank[_field_level(field, pair[1])])
    level = _field_level(field, line)
    reasons = {"full": "a stored degree meets the level and names the field",
               "substantial": "a stored degree meets the level and names a related field",
               "partial": "a stored degree meets the level but not the field named"}
    return level, [f"education:{number}"], reasons[level]


def _norm(text: str) -> str:
    """Lowercase letters and digits with single spaces."""
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _cert_parts(name: str) -> tuple[str, int]:
    """(name without its level word, its level: 3 when no level word is given)."""
    words = _norm(name).split()
    level = max((CERT_LEVELS[w] for w in words if w in CERT_LEVELS), default=3)
    return " ".join(w for w in words if w not in CERT_LEVELS), level


def _asked_cert_level(text: str, base: str) -> int | None:
    """The level word right after the certification's name in the posting, or None."""
    found = re.search(rf"(?<![a-z0-9]){re.escape(base)}(?![a-z0-9])(.{{0,30}})", text)
    if not found:
        return None
    return max((CERT_LEVELS[w] for w in _norm(found.group(1)).split() if w in CERT_LEVELS), default=None)


def _certifications(posting: str, parts: list[tuple[str, str]], facts: mf.ResumeFacts) -> list[CodeItem]:
    """Stored certifications the posting names: full at the level asked or above, partial at a lower level."""
    text = _norm(posting)
    out: list[CodeItem] = []
    for name in facts.certifications:
        base, held = _cert_parts(name)
        if len(base) < 3 or not re.search(rf"(?<![a-z0-9]){re.escape(base)}(?![a-z0-9])", text):
            continue
        asked = _asked_cert_level(text, base)
        level = "full" if asked is None or held >= asked else "partial"
        quote, section = _sentence_with(parts, re.escape(base).replace(r"\ ", r"[\s\-]+"))
        out.append({"id": f"code:cert:{_slug(base)}", "kind": "certification", "label": name, "quote": quote,
                    "section": section, "level": level, "evidence": [f"certification:{name}"],
                    "reason": "a stored certification matches" if level == "full"
                    else "a stored certification is the same one at a lower level"})
    return out


def months_covered(facts: mf.ResumeFacts, today: date) -> tuple[int, list[str]]:
    """(months covered by dated roles with overlaps counted once, company ids that contribute, newest first)."""
    spans: list[tuple[int, int]] = []
    owners: dict[str, int] = {}
    for cid, company in facts.companies.items():
        for role in company["roles"]:
            start = _month(role.get("start"))
            if start is None:
                continue
            end = _month(role.get("end")) if role.get("end") else today.year * 12 + today.month - 1
            if end is not None and end >= start:
                spans.append((start, end))
                owners[cid] = max(owners.get(cid, 0), end)
    spans.sort()
    total, edge = 0, -1
    for start, end in spans:
        total += max(0, end - max(start, edge + 1) + 1)
        edge = max(edge, end)
    return total, sorted(owners, key=lambda c: -owners[c])


def _month(value: Any) -> int | None:
    """Months since year 0 for a 'YYYY-MM' date, else None."""
    found = re.fullmatch(r"(\d{4})-(\d{2})", str(value or ""))
    return int(found.group(1)) * 12 + int(found.group(2)) - 1 if found else None


def years_level(held: Decimal, asked: Decimal) -> str:
    """The level for years held against years asked, by the share thresholds."""
    share = held / asked
    if share >= YEARS_FULL:
        return "full"
    if share >= YEARS_SUBSTANTIAL:
        return "substantial"
    return "partial" if share >= YEARS_PARTIAL else "profile_miss"


def _years(parts: list[tuple[str, str]], facts: mf.ResumeFacts, today: date) -> CodeItem | None:
    """Total years of experience asked (when the posting names it without tying it to a skill), rated by dated roles."""
    asked = [(int(m.group(1)), s, sec) for s, sec in parts if (m := TOTAL_YEARS.search(s))]
    if not asked or max(a[0] for a in asked) == 0:
        return None
    wanted, sentence, section = max(asked, key=lambda a: a[0])
    months, owners = months_covered(facts, today)
    held = Decimal(months) / 12
    level = years_level(held, Decimal(wanted))
    return {"id": "code:years", "kind": "years", "label": f"{wanted}+ years of experience",
            "quote": sentence[:240], "section": section, "level": level,
            "evidence": [f"role:{c}" for c in owners[:5]] if level != "profile_miss" else [],
            "reason": f"dated roles cover about {held:.1f} years against {wanted} asked"}


def apply_code(request: Request, items: list[CodeItem]) -> list[str]:
    """Give each code-rated requirement the code's level and evidence (source: code); return notes of disagreements."""
    by_id = {item["id"]: item for item in items}
    notes: list[str] = []
    for entry in request.items:
        code = by_id.get(entry.id)
        if code is None:
            continue
        if entry.level != code["level"]:
            notes.append(f"{entry.id}: the code pass says {code['level']}; pass 1 said {entry.level}")
        entry.level, entry.evidence, entry.reason = code["level"], list(code["evidence"]), code["reason"]
        entry.source, entry.flag = "code", None
        if entry.contest and entry.contest[0] != code["level"]:
            level, why = entry.contest
            notes.append(f"{entry.id}: contested by the reviewer, {code['level']} to {level} ({why})")
            entry.code_level, entry.level, entry.source = code["level"], level, "code, contested"
            entry.reason = f"code said {code['level']} ({code['reason']}); reviewer says {level}: {why}"
    return notes
