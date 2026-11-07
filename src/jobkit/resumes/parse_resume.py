#!/usr/bin/env python3
"""Parse the text of one resume (already extracted by extract.py from a pdf, docx, md or txt file) into structured pieces.

Handles the two layouts seen so far:
  * layout A: "WORK EXPERIENCE" heading, "Company" / "Title" / "MM/YYYY - Present", "•" bullets
  * layout B: "Work History" heading, "Company – Title" / ["Role:" / "Client:"] / dates, "●" bullets
Employer discovery also accepts "Company" / "Title" / dates on three lines, when the middle line holds a
job-title word and the line above it could be a company name.

Library module (no command line). Pure functions, no file or network access, except that the employer
registry is module state: `set_companies` installs {id: (name, header regex)} from
the stored employers, and `parse_work` / `parse_resume` use it unless you pass `company_res`.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from difflib import SequenceMatcher
from hashlib import sha1
from typing import Any, Final, Literal, TypedDict

from jobkit.resumes.extract import is_contact_line

BULLETS: Final[str] = "•●§▪◦"
ZERO_WIDTH: Final[dict[int, None]] = dict.fromkeys(map(ord, "\u200b‌‍﻿"))
SUB_MARK: Final[str] = "\x00SUB"          # prefix for 'o' sub-points, folded into the bullet above them
# A dash between employer and title: an en/em dash, or a hyphen with spaces around it (not Acme-Labs).
SEP: Final[str] = r"(?:\s*[–—]\s*|\s+-\s+)"
SIMILAR_THRESHOLD: Final[float] = 0.92   # used by the merge step: near-identical bullets become variants
MAX_COMPANY_WORDS: Final[int] = 7
MAX_HEADLINE_CHARS: Final[int] = 60
SKILL_SECTIONS: Final[tuple[str, ...]] = ("skills", "skills_leadership", "skills_technical")

# canonical company id -> (display name, header regex); filled by set_companies(). The regex must match the
# whole header line; group "t" captures a title written on the same line ("Company - Title").
COMPANIES: dict[str, tuple[str, str]] = {}
COMPANY_RES: dict[str, re.Pattern[str]] = {}

HEADINGS: Final[dict[str, str]] = {
    "professional summary": "summary",
    "summary": "summary",
    "profile": "profile",
    "skills": "skills",
    "leadership": "skills_leadership",
    "leadership skills": "skills_leadership",
    "technical": "skills_technical",
    "technical skills": "skills_technical",
    "certifications": "certifications",
    "education": "education",
    "work history": "work",
    "work experience": "work",
    "projects": "projects",
}

DATE_RE: Final = re.compile(
    r"^(?P<s>\d{2}/\d{4})\s*[–—-]\s*(?P<e>\d{2}/\d{4}|Present|Current)$", re.I)
TRAILING_DATE_RE: Final = re.compile(
    r"^(?P<l>.*?\S)\s{2,}(?P<d>\d{2}/\d{4}\s*[–—-]\s*(?:\d{2}/\d{4}|Present|Current))\s*$", re.I)
ROLE_PREFIX: Final = re.compile(r"role\s*:", re.I)
HEADER_PREFIX: Final = re.compile(r"(role|client)\s*:", re.I)

GROUPS: Final[dict[str, str]] = {
    "leadership skills": "Leadership",
    "software engineering": "Software Engineering",
    "sdlc": "Software Engineering",
    "placeholder": "Cloud",
    "cloud strategy": "Cloud",
    "ai/ml": "AI/ML",
    "gen ai": "AI/ML",
    "genai": "AI/ML",
    "web technologies": "Web",
    "observability solutions": "Observability",
    "observability": "Observability",
    "languages": "Languages",
    "storage": "Data",
    "analytics": "Data",
    "database systems": "Data",
    "bigdata": "Data",
    "big data": "Data",
}
STOP_SKILLS: Final[frozenset[str]] = frozenset({"solutions", "solution", "strategy", "cloud strategy", "other"})

METRIC_RE: Final = re.compile(
    r"\$\s?\d[\d.,]*\s?(?:[MBK]\b|million|billion|thousand)?\+?|\d+(?:\.\d+)?\s?%|\d+\+?\s?(?:percent|million|years|x)\b",
    re.I)


class WorkEntry(TypedDict):
    """One job (company header, dates, bullets) found in the work history."""

    company_id: str
    title: str
    subtitle: str
    client: str
    start: str | None
    end: str | None
    dated: bool
    bullets: list[str]


class SkillItem(TypedDict):
    """A skill with its alternative spellings."""

    name: str
    aliases: list[str]


class Resume(TypedDict):
    """Result of parse_resume for a text with a work-history heading."""

    is_resume: Literal[True]
    work: list[WorkEntry]
    skills: dict[str, list[SkillItem]]
    summary: str
    headline: str
    profile_points: list[str]
    certifications: list[str]
    education: list[str]
    projects: list[str]
    problems: list[str]


class NotResume(TypedDict):
    """Result of parse_resume for a text without a work-history heading."""

    is_resume: Literal[False]
    problems: list[str]


ParsedResume = Resume | NotResume


def set_companies(registry: Mapping[str, tuple[str, str]]) -> None:
    """Install {id: (name, regex)} in place, so modules that imported COMPANIES see it."""
    COMPANIES.clear()
    COMPANIES.update(registry)
    COMPANY_RES.clear()
    COMPANY_RES.update({cid: re.compile(rx + r"$") for cid, (_, rx) in COMPANIES.items()})


def clean(text: str) -> str:
    """Fix PDF extraction noise inside a piece of text."""
    text = text.translate(ZERO_WIDTH).replace("\xa0", " ")
    text = re.sub(r"(\w)- (\w)", r"\1-\2", text)        # "Cross- functional"
    text = re.sub(r"\(\s+", "(", text)                    # "( AWS"
    text = re.sub(r"\s+\)", ")", text)                    # "placeholder"
    text = re.sub(r"Next\.\s+js", "Next.js", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def join_lines(lines: Iterable[str]) -> str:
    """Join wrapped lines into one cleaned string, re-joining words hyphenated at a line break."""
    out = ""
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if out.endswith("-") and line[:1].islower():
            out += line
        else:
            out += (" " if out else "") + line
    return clean(out)


def norm_date(text: str) -> str | None:
    """'MM/YYYY' -> 'YYYY-MM'; Present/Current -> None."""
    if text.lower() in ("present", "current"):
        return None
    month, year = text.split("/")
    return f"{year}-{month}"


def split_sections(lines: Iterable[str]) -> dict[str, list[str]]:
    """Return {section_key: [lines]} using HEADINGS; text before the first heading is 'header'."""
    sections: dict[str, list[str]] = {"header": []}
    current = "header"
    for line in lines:
        key = HEADINGS.get(line.strip().lower())
        if key:
            current = key
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line)
    return sections


def layout_work_lines(lines: Iterable[str]) -> list[str]:
    """Prepare `pdftotext -layout` lines for parse_work: a right-aligned date after the company name goes on
    its own line, and 'o' sub-points are marked so they are folded into the bullet above them."""
    out: list[str] = []
    for raw in lines:
        match = TRAILING_DATE_RE.match(raw.rstrip())
        if match and match["l"].lstrip()[:1] not in BULLETS:
            out += [match["l"].strip(), match["d"].strip()]
        elif re.match(r"^\s{4,}o\s+\S", raw):
            out.append(SUB_MARK + raw.strip()[1:].strip())
        else:
            out.append(raw)
    return out


TITLE_WORDS: Final = re.compile(
    r"\b(?:engineer|developer|manager|director|architect|consultant|analyst|lead|head|officer|president"
    r"|administrator|specialist|programmer|scientist|designer|owner|supervisor|vp)\b", re.I)


def _is_title_line(line: str) -> bool:
    """True for a line that reads as a job title on its own: a title word and no employer-title dash."""
    return bool(TITLE_WORDS.search(line)) and not re.search(SEP, line)


def _can_be_company_line(line: str) -> bool:
    """True when a line could be an employer name sitting above a title line."""
    return (line[0] not in BULLETS and not line.startswith(SUB_MARK) and not DATE_RE.match(line)
            and not HEADER_PREFIX.match(line) and not line.endswith(".")
            and _plausible_company(clean(line).strip(" ,")))


def _header_line_index(lines: list[str], date_index: int) -> int | None:
    """Index of the company header above a date line, skipping Role:/Client: lines; None if there is none.
    When the line above the dates is a job title and the line above that could be a company name
    ("Company" / "Title" / dates), the header is that company line."""
    j = date_index - 1
    while j >= 0 and HEADER_PREFIX.match(lines[j]):
        j -= 1
    if j < 0 or lines[j][0] in BULLETS or lines[j].startswith(SUB_MARK) or DATE_RE.match(lines[j]):
        return None
    if j == date_index - 1 and j > 0 and _is_title_line(lines[j]) and _can_be_company_line(lines[j - 1]):
        return j - 1
    return j


def _plausible_company(name: str) -> bool:
    return (1 < len(name) < MAX_HEADLINE_CHARS and name[0].isalnum() and (name[0].isupper() or name[0].isdigit())
            and len(name.split()) <= MAX_COMPANY_WORDS)


def discover_companies(layout_text: str) -> dict[str, str]:
    """Employer names in one resume's work history, found without any registry: {slug: name}.
    The header is the line just above a date range (skipping Role:/Client: lines), or the line that ends with
    the date range. Review the result: a company written two ways ("X" and "X, Parent") shows up as two."""
    section = split_sections(layout_text.splitlines()).get("work")
    if not section:
        return {}
    lines = [line.strip() for line in layout_work_lines(section) if line.strip()]
    found: dict[str, str] = {}
    for i, line in enumerate(lines):
        if not DATE_RE.match(line):
            continue
        header = _header_line_index(lines, i)
        if header is None:
            continue
        name = clean(re.split(SEP, lines[header])[0]).strip(" ,")
        if _plausible_company(name):
            found.setdefault(re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-"), name)
    return found


class _WorkParser:
    """Line-by-line state machine behind parse_work: company header, lines before the dates, the dates, then
    bullets with their wrapped continuation lines."""

    def __init__(self, company_res: Mapping[str, re.Pattern[str]]) -> None:
        self.company_res = company_res
        self.entries: list[WorkEntry] = []
        self.problems: list[str] = []
        self.cur: WorkEntry | None = None
        self.bullet: list[str] | None = None
        self.pre: list[str] = []          # non-bullet lines between the header and the dates

    def feed(self, raw: str) -> None:
        """Consume one line."""
        line = raw.strip()
        if not line or re.fullmatch(r"[\s()]*", line):
            return
        header = self._match_company(line)
        if header:
            self._start_entry(*header)
        elif self.cur is not None:
            self._feed_entry(self.cur, line)

    def finish(self) -> tuple[list[WorkEntry], list[str]]:
        """Close the last bullet, report entries without dates or bullets, and return (entries, problems)."""
        self._flush_bullet()
        for entry in self.entries:
            label = f"{entry['company_id']} {entry['start']}"
            if not entry["dated"]:
                self.problems.append(f"{label}: no dates found")
            if not entry["bullets"]:
                self.problems.append(f"{label}: no bullets found")
        return self.entries, self.problems

    def _match_company(self, line: str) -> tuple[str, str] | None:
        if line[0] in BULLETS:
            return None
        for cid, regex in self.company_res.items():
            match = regex.match(line)
            if match:
                return cid, (match.groupdict().get("t") or "").strip()
        return None

    def _start_entry(self, company_id: str, title: str) -> None:
        self._flush_bullet()
        self.cur = {"company_id": company_id, "title": title, "subtitle": "", "client": "",
                    "start": None, "end": None, "dated": False, "bullets": []}
        self.entries.append(self.cur)
        self.pre = []

    def _flush_bullet(self) -> None:
        if self.cur is not None and self.bullet is not None:
            text = join_lines(self.bullet)
            if text:
                self.cur["bullets"].append(text)
        self.bullet = None

    def _feed_entry(self, cur: WorkEntry, line: str) -> None:
        if cur["dated"]:
            self._after_dates(cur, line)
            return
        match = DATE_RE.match(line)
        if not match:
            self._before_dates(cur, line)
            return
        cur["start"], cur["end"], cur["dated"] = norm_date(match["s"]), norm_date(match["e"]), True
        if not cur["title"] and self.pre:
            cur["title"] = self.pre[0]

    def _before_dates(self, cur: WorkEntry, line: str) -> None:
        if line.startswith(SUB_MARK):
            return
        lowered = line.lower()
        if lowered.startswith("role:"):
            cur["subtitle"] = line.split(":", 1)[1].strip()
        elif lowered.startswith("client:"):
            cur["client"] = line.split(":", 1)[1].strip()
        elif line[0] not in BULLETS:
            self.pre.append(clean(line))

    def _after_dates(self, cur: WorkEntry, line: str) -> None:
        if line.startswith(SUB_MARK):
            if self.bullet is not None:
                self.bullet.append(line[len(SUB_MARK):])
            return
        is_role = line.lower().startswith("role:")
        if not cur["title"] and self.bullet is None and line[0] not in BULLETS and not is_role:
            cur["title"] = clean(line)        # layout A: "Company   dates" then the title on the next line
        elif is_role:
            cur["subtitle"] = line.split(":", 1)[1].strip()
        elif line[0] in BULLETS:
            self._flush_bullet()
            self.bullet = [line.lstrip(BULLETS + " ")]
        elif self.bullet is not None:
            self.bullet.append(line)
        else:
            self.problems.append(f"stray line in {cur['company_id']}: {line[:60]}")


def parse_work(lines: Iterable[str], company_res: Mapping[str, re.Pattern[str]] | None = None
               ) -> tuple[list[WorkEntry], list[str]]:
    """Return (entries, problems) for the work-history lines, matching employers with `company_res`
    (default: the registry installed by set_companies)."""
    parser = _WorkParser(COMPANY_RES if company_res is None else company_res)
    for raw in lines:
        parser.feed(raw)
    return parser.finish()


def split_items(text: str) -> list[str]:
    """Split a skills string on , ; and 'and' at paren depth 0; drop 'Label –' prefixes."""
    items: list[str] = []
    buf, depth, i = "", 0, 0
    while i < len(text):
        char = text[i]
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        if depth == 0 and char in ",;":
            items.append(buf)
            buf = ""
        elif depth == 0 and text[i:i + 5] == " and " and buf.strip():
            items.append(buf)
            buf = ""
            i += 4
        else:
            buf += char
        i += 1
    items.append(buf)
    cleaned = (re.sub(r"^[A-Za-z ]+\s[–—-]\s", "", clean(item)).strip(" .") for item in items)   # "NoSQL – DynamoDB"
    return [item for item in cleaned if item]


def _split_bullets(lines: Iterable[str]) -> tuple[list[str], list[list[str]]]:
    """(lines before the first bullet marker, one list of lines per bullet with its marker removed)."""
    leading: list[str] = []
    bullets: list[list[str]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line[0] in BULLETS:
            bullets.append([line.lstrip(BULLETS + " ")])
        elif bullets:
            bullets[-1].append(line)
        else:
            leading.append(line)
    return leading, bullets


def bullet_items(lines: Iterable[str]) -> list[str]:
    """Items of a bulleted section: loose lines before the first bullet, then one string per bullet."""
    leading, bullets = _split_bullets(lines)
    return [text for text in [clean(line) for line in leading] + [join_lines(b) for b in bullets] if text]


def _split_label(text: str, labels: list[str]) -> tuple[str, str] | None:
    """Split 'Label: a, b' (or, in some resumes, 'Label, a, b') into (label, rest)."""
    match = re.match(r"^(?P<l>[^:]+?)\s*:\s*(?P<r>.*)$", text)
    if not match:
        low = text.lower()
        label = next((x for x in labels if low.startswith(x) and low[len(x):].lstrip()[:1] == ","), None)
        match = re.match(rf"^(?P<l>.{{{len(label)}}})\s*,\s*(?P<r>.*)$", text) if label else None
    return (match["l"].strip(), match["r"]) if match else None


def _add_skills(groups: dict[str, dict[str, set[str]]], group: str, items: Iterable[str]) -> None:
    """Add 'Name (alias)' items to a group, skipping stop words."""
    for item in items:
        match = re.match(r"^(.*?)\s*\(([^)]+)\)$", item)
        name, alias = (clean(match[1]), [clean(match[2])]) if match else (item, [])
        if name and name.lower() not in STOP_SKILLS:
            groups.setdefault(group, {}).setdefault(name, set()).update(alias)


def parse_skills(sections: Mapping[str, list[str]]) -> tuple[dict[str, list[SkillItem]], list[str]]:
    """Return {group: [{'name', 'aliases'}]} and a list of problems (unknown group labels)."""
    groups: dict[str, dict[str, set[str]]] = {}
    problems: list[str] = []
    labels = sorted(GROUPS, key=len, reverse=True)
    for key in SKILL_SECTIONS:
        for text in (join_lines(b) for b in _split_bullets(sections.get(key, []))[1]):
            if key == "skills_leadership":
                _add_skills(groups, "Leadership", split_items(text))
                continue
            labelled = _split_label(text, labels)
            if labelled is None:     # unlabeled list, e.g. "Agile methodologies, CI/CD": sorted by your skill curation
                _add_skills(groups, "Unsorted", split_items(text))
                continue
            label, rest = labelled
            group = GROUPS.get(label.lower())
            if group is None:
                problems.append(f"unknown skill group label: {label}")
                group = "Unsorted"
            _add_skills(groups, group, split_items(rest))
    skills = {g: [SkillItem(name=n, aliases=sorted(a)) for n, a in items.items()] for g, items in groups.items()}
    return skills, problems


def _work_lines(sections: Mapping[str, list[str]], layout_text: str) -> list[str]:
    """Lines of the work history: from the layout text when it has them (it keeps each bullet next to its marker)."""
    lines = sections["work"]
    if layout_text:
        layout_work = split_sections(layout_text.splitlines()).get("work")
        if layout_work:
            lines = layout_work_lines(layout_work)
    return [line for line in lines if not is_contact_line(line)]    # PDFs are not cleaned on extraction


def _summary_and_headline(sections: Mapping[str, list[str]]) -> tuple[str, str]:
    """(summary text, headline). Layout A has no summary heading: skip the name and contact lines, and treat a
    short first line without a full stop as a headline."""
    header = [line for line in sections.get("header", []) if line.strip()]
    summary_lines = [line for line in sections.get("summary") or header[2:] if not is_contact_line(line)]
    headline = ""
    if not sections.get("summary") and summary_lines:
        first = summary_lines[0].strip()
        if len(first) < MAX_HEADLINE_CHARS and not first.endswith("."):
            headline, summary_lines = clean(first), summary_lines[1:]
    return join_lines(summary_lines), headline


def parse_resume(text: str, layout_text: str = "",
                 company_res: Mapping[str, re.Pattern[str]] | None = None) -> ParsedResume:
    """Parse one resume. `text` is normal reading-order text (summary, skills, certifications ...);
    `layout_text` is the same PDF from `pdftotext -layout`, used for the work history because it keeps every
    bullet's text next to its marker (reading-order text can detach bullets across columns/pages)."""
    sections = split_sections(text.splitlines())
    if "work" not in sections:
        return {"is_resume": False, "problems": ["no work-experience heading found"]}
    work, work_problems = parse_work(_work_lines(sections, layout_text), company_res)
    if not work:
        work_problems.append("work-experience section found, but no known employer in it")
    skills, skill_problems = parse_skills(sections)
    summary, headline = _summary_and_headline(sections)
    return {
        "is_resume": True,
        "work": work,
        "skills": skills,
        "summary": summary,
        "headline": headline,
        "profile_points": [p for p in bullet_items(sections.get("profile", [])) if p not in BULLETS],
        "certifications": bullet_items(sections.get("certifications", [])),
        "education": [e for e in [join_lines(sections.get("education", []))] if e],
        "projects": [e for e in [join_lines(sections.get("projects", []))] if e],
        "problems": work_problems + skill_problems,
    }


# ---- helpers used when merging into the resume data --------------------------------------------

def bullet_key(text: str) -> str:
    """Text reduced to lower-case letters and digits, for comparing bullets."""
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def bullet_id(company_id: str, text: str) -> str:
    """Stable short id of a bullet: company prefix plus a hash of its normalized text."""
    return f"{company_id[:4]}-{sha1(bullet_key(text).encode()).hexdigest()[:6]}"


def similar(a: str, b: str) -> float:
    """Similarity (0-1) of two bullets after normalization."""
    return SequenceMatcher(None, bullet_key(a), bullet_key(b)).ratio()


def find_metrics(text: str) -> list[str]:
    """Numbers worth checking in a bullet ($ amounts, percentages, 'N million', 'N years'), first seen order."""
    seen: set[str] = set()
    out: list[str] = []
    for match in METRIC_RE.finditer(text):
        value = match.group(0).strip()
        if value.lower() not in seen:
            seen.add(value.lower())
            out.append(value)
    return out


def skill_terms(skills_by_group: Mapping[str, Iterable[Mapping[str, Any]]]) -> dict[str, str]:
    """Flat {term: canonical_name} from the skills vocabulary (every name and alias, including one- and
    two-letter ones such as R and Go)."""
    terms: dict[str, str] = {}
    for items in skills_by_group.values():
        for item in items:
            name = str(item["name"])
            aliases: Iterable[str] = item.get("aliases") or []
            for term in [name, *aliases]:
                if term.strip():
                    terms[term] = name
    return terms


AMBIGUOUS: Final[frozenset[str]] = frozenset({"go", "make", "rust", "ruby", "dart", "ant", "pig", "chef", "swift",
                                              "spring", "puppet", "julia"})   # skill names that are also ordinary words
SENTENCE_START: Final[re.Pattern[str]] = re.compile(r"(?:^|[.!?]\s+|\n)[ \t]*[-*\u2022]?[ \t]*$")
LIST_ITEM_END: Final[re.Pattern[str]] = re.compile(r"[ \t]*(?:[,;/)]|$|\n)")


def is_ambiguous(term: str) -> bool:
    """True for a skill name that is also an ordinary word (Go, Make, Rust ...)."""
    return term.lower() in AMBIGUOUS


def term_pattern(term: str) -> re.Pattern[str]:
    """The pattern that finds a skill name as a whole word. One- and two-character names (R, Go, HR) and names that
    are also ordinary words (Make, Rust) must match capitalisation exactly and may not touch a letter, digit, hyphen
    or ampersand ("Go-to-market", "R&D"); other names ignore capitalisation."""
    if len(term) <= 2 or is_ambiguous(term):
        return re.compile(rf"(?<![\w\-&]){re.escape(term)}(?![\w\-&])")
    return re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", re.I)


def _matches(term: str, text: str) -> list[re.Match[str]]:
    """Where the skill name occurs as itself. An ordinary-word name at the start of a sentence ("Go to market")
    counts only when it stands alone, as a list item does; otherwise it is only a possible match."""
    found = term_pattern(term).finditer(text)
    if not is_ambiguous(term):
        return list(found)
    return [m for m in found if not SENTENCE_START.search(text[:m.start()])
            or LIST_ITEM_END.match(text, m.end())]


def term_found(term: str, text: str) -> bool:
    """True when the skill name occurs in the text as the skill (see `term_pattern` and `_matches`)."""
    return bool(_matches(term, text))


def term_count(term: str, text: str) -> int:
    """How many times the skill name occurs in the text as the skill."""
    return len(_matches(term, text))


def possible_matches(text: str, terms: Mapping[str, str]) -> list[tuple[str, str]]:
    """(skill, sentence) for ordinary-word skill names the text uses with the right capitalisation but only at the
    start of a sentence, where it cannot be told from the plain word ("Go to market"). A skill that is found
    properly elsewhere in the text is not listed. The caller shows these for a person to confirm."""
    sure = {name for term, name in terms.items() if term_found(term, text)}
    out: list[tuple[str, str]] = []
    for term, name in terms.items():
        if not is_ambiguous(term) or name in sure or any(n == name for n, _ in out):
            continue
        pattern = re.compile(rf"(?<![\w\-&]){re.escape(term)}(?![\w\-&])")
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
            if pattern.search(sentence):
                out.append((name, sentence.strip()[:160]))
                break
    return out


def tag_skills(text: str, terms: Mapping[str, str]) -> list[str]:
    """Canonical names of the skills mentioned in the text, sorted."""
    found: list[str] = []
    for term, name in terms.items():
        if name not in found and term_found(term, text):
            found.append(name)
    return sorted(found)
