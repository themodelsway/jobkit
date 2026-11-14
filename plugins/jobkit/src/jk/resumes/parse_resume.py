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

from jk.resumes import dates
from jk.resumes.extract import is_contact_line
from jk.resumes.headings import COMBINED, LOOKUP, heading_key, inline_heading, is_unknown_heading
from jk.resumes.work_layout import (BULLETS, HEADER_PREFIX, MAX_HEADLINE_CHARS, SEP, SUB_MARK, can_be_company_line,
                                    employer_by_context, is_location, is_title_line, plausible_company, structure_work_lines)

ZERO_WIDTH: Final[dict[int, None]] = dict.fromkeys(map(ord, "\u200b‌‍﻿"))
PARSER_VERSION: Final[int] = 3           # raise it when reading or parsing changes what a resume file yields: the next
                                         # `process-resumes` run then backs up the data and rebuilds it from the files
SIMILAR_THRESHOLD: Final[float] = 0.92   # used by the merge step: near-identical bullets become variants
SKILL_SECTIONS: Final[tuple[str, ...]] = ("skills", "skills_leadership", "skills_technical")

# canonical company id -> (display name, header regex); filled by set_companies(). The regex must match the
# whole header line; group "t" captures a title written on the same line ("Company - Title").
COMPANIES: dict[str, tuple[str, str]] = {}
COMPANY_RES: dict[str, re.Pattern[str]] = {}


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
    "programming languages": "Languages",
    "cloud": "Cloud",
    "cloud platforms": "Cloud",
    "databases": "Data",
    "database": "Data",
    "storage": "Data",
    "analytics": "Data",
    "database systems": "Data",
    "bigdata": "Data",
    "big data": "Data",
}
MAX_LABEL_CHARS: Final[int] = 40
MAX_LABEL_WORDS: Final[int] = 5
WIDE_GAP_RE: Final = re.compile(r"\s{3,}")   # the gap between cells of a table row or columns of a list
GAP_RE: Final = re.compile(r"\s{2,}")        # a narrower gap counts too in a line that has no other separator
MAX_SKILL_CHARS: Final[int] = 60          # a longer "skill" is a sentence that wandered into the skills section
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
    """One end of a date range as 'YYYY-MM' ('YYYY' when only a year is given); Present, Current and the like -> None."""
    return dates.parse_date(text)


def _is_company_header(line: str) -> bool:
    """True when the line matches a known employer (the registry installed by set_companies)."""
    return any(regex.match(line.strip()) for regex in COMPANY_RES.values())


def _starts_unknown_section(lines: list[str], index: int) -> bool:
    """True when an ALL-CAPS short line inside the work history is a section heading we do not know (and not an
    employer: an employer line has a date range within the next lines)."""
    if not is_unknown_heading(lines[index]) or _is_company_header(lines[index]) or is_title_line(lines[index]):
        return False                       # a job title in capitals (below its dated employer) is not a heading
    following = [line for line in lines[index + 1:index + 8] if line.strip()][:3]
    return not any(dates.find_date_range(line) for line in following)


def split_sections(lines: Iterable[str]) -> dict[str, list[str]]:
    """Return {section_key: [lines]}; text before the first heading is 'header'. A known heading whose content is
    not stored starts the section 'other'; an unknown ALL-CAPS heading inside the work history does too and is
    named in the '_unknown' entry. 'Skills: Python, Java' starts the skills section with its content."""
    rows = list(lines)
    sections: dict[str, list[str]] = {"header": []}
    current = "header"
    for index, line in enumerate(rows):
        key = heading_key(line)
        inline = None if key else inline_heading(line, in_work=current == "work")
        if key:
            current = key
            sections.setdefault(current, [])
        elif inline:
            current = inline[0]
            sections.setdefault(current, []).append(inline[1])
        elif current == "work" and _starts_unknown_section(rows, index):
            sections.setdefault("_unknown", []).append(line.strip())
            current = "other"
            sections.setdefault(current, [])
        else:
            sections.setdefault(current, []).append(line)
    return sections


CERT_RE: Final = re.compile(r"certif|licen[cs]e|\b(?:AWS|Azure|GCP|CCNA|CISSP|PMP|CKA|CKAD|TOGAF|Scrum)\b", re.I)


def route_combined(sections: dict[str, list[str]]) -> dict[str, list[str]]:
    """A combined 'Education and Certifications' block: lines that name a certification go to certifications, the
    others to education."""
    for line in sections.pop(COMBINED, []):
        sections.setdefault("certifications" if CERT_RE.search(line) else "education", []).append(line)
    return sections


def layout_work_lines(lines: Iterable[str]) -> list[str]:
    """Prepare work-history lines for parse_work (every format): dates on their own line below a header written in
    any common shape, titles and employers in the order employer, title, places dropped (see work_layout)."""
    return structure_work_lines(lines)


def _header_line_index(lines: list[str], date_index: int) -> int | None:
    """Index of the company header above a date line, skipping Role:/Client: lines; None if there is none.
    When the line above the dates is a job title and the line above that could be a company name
    ("Company" / "Title" / dates), the header is that company line."""
    j = date_index - 1
    while j >= 0 and HEADER_PREFIX.match(lines[j]):
        j -= 1
    if j < 0 or lines[j][0] in BULLETS or lines[j].startswith(SUB_MARK) or dates.is_date_line(lines[j]):
        return None
    if j == date_index - 1 and j > 0 and is_title_line(lines[j]) and can_be_company_line(lines[j - 1]):
        return j - 1
    return j


def _employer_by_header(lines: list[str], header: int, date_index: int, name: str) -> bool:
    """True when `name`, which holds a title word, is the employer of the header block: a clearer title stands in the
    header itself ('Principal Labs – Senior Engineer'), between the header and the dates, or just after the dates."""
    title_part = re.split(SEP, lines[header], maxsplit=1)[1:]
    between = lines[header + 1:date_index]
    after = lines[date_index + 1:date_index + 2]
    return any(employer_by_context(name, other) for other in [*title_part, *between, *after]
               if other and other[0] not in BULLETS)


def discover_companies(layout_text: str) -> dict[str, str]:
    """Employer names in one resume's work history, found without any registry: {slug: name}.
    The header is the line just above a date range (skipping Role:/Client: lines), or the line that ends with
    the date range. A job title or a place is never taken for an employer. Review the result: a company written
    two ways ("X" and "X, Parent") shows up as two."""
    section = split_sections(layout_text.splitlines()).get("work")
    if not section:
        return {}
    lines = layout_work_lines(section)
    found: dict[str, str] = {}
    for i, line in enumerate(lines):
        if not dates.is_date_line(line):
            continue
        header = _header_line_index(lines, i)
        if header is None:
            continue
        name = clean(re.split(SEP, lines[header])[0]).strip(" ,")
        if plausible_company(name) and (not is_title_line(name) or _employer_by_header(lines, header, i, name)) \
                and not is_location(name):
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
        self.marked = False               # the current entry has a bullet with a marker
        self.inferred = False             # the current entry has bullets found only by their line breaks

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
        self.marked = self.inferred = False

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
        found = dates.find_date_range(line)
        if not found or found.before or found.after:
            self._before_dates(cur, line)
            return
        cur["start"], cur["end"], cur["dated"] = norm_date(found.start), norm_date(found.end), True
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
        if dates.is_date_line(line) or heading_key(line):          # structure is never part of a bullet
            self._flush_bullet()
            self.problems.append(f"unexpected line in {cur['company_id']}: {line[:60]}")
            return
        is_role = line.lower().startswith("role:")
        if not cur["title"] and self.bullet is None and line[0] not in BULLETS and not is_role:
            cur["title"] = clean(line)        # layout A: "Company   dates" then the title on the next line
        elif is_role:
            cur["subtitle"] = line.split(":", 1)[1].strip()
        elif line[0] in BULLETS:
            self._flush_bullet()
            self.bullet = [line.lstrip(BULLETS + " ")]
            self.marked = True
        else:
            self._continue_bullet(cur, line)

    def _continue_bullet(self, cur: WorkEntry, line: str) -> None:
        """A line with no marker: the wrapped end of the current bullet or, in an entry that has no markers at all
        (bullets drawn as shapes, or plain paragraphs), the start of a new bullet found by its line break."""
        if self.bullet is not None and (self.marked or not self._ends_sentence(self.bullet[-1]) or not line[:1].isupper()):
            self.bullet.append(line)
            return
        self._flush_bullet()
        self.bullet = [line]
        if not self.inferred:
            self.inferred = True
            self.problems.append(f"{cur['company_id']} {cur['start']}: bullets inferred from line breaks (no bullet marks)")

    @staticmethod
    def _ends_sentence(text: str) -> bool:
        return text.rstrip().endswith((".", ";", "%"))


def parse_work(lines: Iterable[str], company_res: Mapping[str, re.Pattern[str]] | None = None
               ) -> tuple[list[WorkEntry], list[str]]:
    """Return (entries, problems) for the work-history lines, matching employers with `company_res`
    (default: the registry installed by set_companies)."""
    parser = _WorkParser(COMPANY_RES if company_res is None else company_res)
    for raw in lines:
        parser.feed(raw)
    return parser.finish()


def split_items(text: str) -> list[str]:
    """Split a skills string on , ; | · • and 'and' at paren depth 0; drop 'Label –' prefixes."""
    items: list[str] = []
    buf, depth, i = "", 0, 0
    while i < len(text):
        char = text[i]
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        if depth == 0 and char in ",;|·•":
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
    if match and (len(match["l"]) > MAX_LABEL_CHARS or len(match["l"].split()) > MAX_LABEL_WORDS):
        return None                                   # a sentence with a colon, not "Label: items"
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


def _cells_to_list(text: str) -> str:
    """'Python   Java' -> 'Python, Java': gaps between table cells become commas. Three spaces always do; two do only
    in a line with no comma, semicolon or bar of its own (text from a poor conversion has double spaces inside names)."""
    return (GAP_RE if not re.search(r"[,;|·•]", text) else WIDE_GAP_RE).sub(", ", text)


def _skill_entries(lines: Iterable[str]) -> list[str]:
    """One string per skills entry: each bullet, and each unmarked line before the first bullet (a wrapped line that
    continues a list joins the line above, shown by the line above: a trailing comma, semicolon, 'and' or open
    bracket; a lowercase name such as 'nginx' is a skill of its own). Cells of one table row, 2 or more spaces
    apart, become a list, in marked entries too."""
    leading, bullets = _split_bullets(lines)
    entries: list[str] = []
    for line in leading:
        text = clean(_cells_to_list(line.strip()))
        previous = entries[-1] if entries else ""
        if previous and (previous.endswith((",", ";", "/", "&")) or previous.lower().endswith((" and", " or"))
                         or previous.count("(") > previous.count(")")):
            entries[-1] = f"{previous} {text}"
        else:
            entries.append(text)
    marked = [join_lines(_cells_to_list(line) for line in b) for b in bullets]
    return [entry for entry in entries + marked if entry]


def parse_skills(sections: Mapping[str, list[str]]) -> tuple[dict[str, list[SkillItem]], list[str]]:
    """Return {group: [{'name', 'aliases'}]} and a list of problems (unknown group labels, sentences in skills)."""
    groups: dict[str, dict[str, set[str]]] = {}
    problems: list[str] = []
    labels = sorted(GROUPS, key=len, reverse=True)
    for key in SKILL_SECTIONS:
        for text in _skill_entries(sections.get(key, [])):
            group, rest = "Leadership", text
            labelled = None if key == "skills_leadership" else _split_label(text, labels)
            if labelled is not None:
                group = GROUPS.get(labelled[0].lower(), "")
                rest = labelled[1]
                if not group:
                    problems.append(f"unknown skill group label: {labelled[0]}")
            elif key != "skills_leadership":
                group = "Unsorted"    # unlabeled list, e.g. "Agile methodologies, CI/CD": sorted by your skill curation
            items = split_items(rest)
            long = [item for item in items if len(item) > MAX_SKILL_CHARS]
            if long:
                problems.append(f"skills item looks like a sentence, not a skill: {long[0][:60]}")
            _add_skills(groups, group or "Unsorted", [item for item in items if item not in long])
    skills = {g: [SkillItem(name=n, aliases=sorted(a)) for n, a in items.items()] for g, items in groups.items()}
    return skills, problems


def _work_lines(sections: Mapping[str, list[str]], layout_text: str) -> list[str]:
    """Lines of the work history: from the layout text when it has them (it keeps each bullet next to its marker)."""
    lines = layout_work_lines(sections["work"])
    if layout_text:
        layout_work = split_sections(layout_text.splitlines()).get("work")
        if layout_work:
            lines = layout_work_lines(layout_work)
    return [line for line in lines if not is_contact_line(line)]    # PDFs are not cleaned on extraction


HAS_CONTACT_RE: Final = re.compile(r"[\w.+-]+@[\w-]+\.|\d{3}[ .)-]+\d{3}[ .-]\d{4}|linkedin\.com", re.I)


def _header_skip(header: list[str]) -> int:
    """How many lines at the top of a file without a summary heading are the name and what goes with it: two (the
    name and a contact or title line), but one when the second line is already running text (a long line or one that
    ends with a full stop), so a name followed directly by the summary keeps its summary."""
    if len(header) < 2:
        return len(header)
    second = header[1].strip()
    prose = ((len(second) >= MAX_HEADLINE_CHARS or second.endswith(".")) and not HAS_CONTACT_RE.search(second)
             and not is_location(second))
    return 1 if prose else 2


def _summary_and_headline(sections: Mapping[str, list[str]]) -> tuple[str, str]:
    """(summary text, headline). Layout A has no summary heading: skip the name and contact lines, drop contact and
    place lines, and treat a short first line without a full stop as a headline."""
    header = [line for line in sections.get("header", []) if line.strip()]
    summary_lines = [line for line in sections.get("summary") or header[_header_skip(header):]
                     if not is_contact_line(line) and not is_location(line.strip())]
    headline = ""
    if not sections.get("summary") and summary_lines:
        first = summary_lines[0].strip()
        if len(first) < MAX_HEADLINE_CHARS and not first.endswith("."):
            headline, summary_lines = clean(first), summary_lines[1:]
    return join_lines(summary_lines), headline


DEGREE_RE: Final = re.compile(
    r"\b(?:bachelor|master|mba|ph\.?d|doctor|diploma|associate|b\.?s\.?c?|m\.?s\.?c?|b\.?tech|m\.?tech|b\.?e|m\.?e)\b",
    re.I)


def list_items(lines: Iterable[str], split_degrees: bool = False) -> list[str]:
    """Items of a section that is a list (education, projects): each bullet, then the unmarked lines before the first
    bullet as one item. With `split_degrees`, an unmarked line that starts with a degree name when the item already
    holds one starts a new item, so two degrees written one under the other are two items. Blank lines mean nothing:
    PDF text has them between pieces of one line."""
    leading, bullets = _split_bullets(lines)
    items: list[str] = []
    current: list[str] = []
    for line in leading:
        if split_degrees and current and DEGREE_RE.match(line.strip()) and DEGREE_RE.search(" ".join(current)):
            items.append(join_lines(current))
            current = []
        current.append(line)
    items.append(join_lines(current))
    return [item for item in items + [join_lines(b) for b in bullets] if item]


def _glued_heading(text: str) -> str | None:
    """A section heading written in capitals inside a line of text ('... quality gates. AWARDS'), else None."""
    return next((name for name in LOOKUP if len(name) >= 6 and name.upper() in text), None)


def _diagnostics(sections: Mapping[str, list[str]], work: Iterable[WorkEntry], points: list[str]) -> list[str]:
    """Problems that point at a parse gone wrong: an unknown heading that ended the work history, a heading glued into a
    bullet, a section that has a heading but no content, profile points that read like a skills list."""
    found = [f'unknown heading "{name}" ended the work history' for name in sections.get("_unknown", [])]
    for entry in work:
        glued = next((g for b in entry["bullets"] if (g := _glued_heading(b))), None)
        if glued:
            found.append(f'{entry["company_id"]} {entry["start"]}: a bullet contains the heading "{glued}"')
    empty = [key for key in ("certifications", "education", "projects") if key in sections
             and not any(line.strip() for line in sections[key])]
    if any(key in sections for key in SKILL_SECTIONS) and not any(line.strip() for key in SKILL_SECTIONS
                                                                 for line in sections.get(key, [])):
        empty.append("skills")
    found += [f"section {key} has a heading but no content" for key in empty]
    if len(points) >= 3 and sum(len(point.split()) <= 4 for point in points) * 2 >= len(points):
        found.append("profile points look like a skills list (most are 1-4 words)")
    return found


def parse_resume(text: str, layout_text: str = "",
                 company_res: Mapping[str, re.Pattern[str]] | None = None) -> ParsedResume:
    """Parse one resume. `text` is normal reading-order text (summary, skills, certifications ...);
    `layout_text` is the same PDF from `pdftotext -layout`, used for the work history because it keeps every
    bullet's text next to its marker (reading-order text can detach bullets across columns/pages)."""
    sections = route_combined(split_sections(text.splitlines()))
    if "work" not in sections:
        return {"is_resume": False, "problems": ["no work-experience heading found"]}
    work, work_problems = parse_work(_work_lines(sections, layout_text), company_res)
    if not work and layout_text:             # the layout text gave no job: try the reading-order text of the section
        plain, plain_problems = parse_work(_work_lines(sections, ""), company_res)
        if plain:
            work, work_problems = plain, [*plain_problems, "work history read from the reading-order text"]
    if not work and not any(dates.find_date_range(line) for line in sections["work"]):
        return {"is_resume": False, "problems": ["work-experience heading found, but no dated entries under it"]}   # a form
    if not work:
        work_problems.append("work-experience section found, but no known employer in it")
    skills, skill_problems = parse_skills(sections)
    summary, headline = _summary_and_headline(sections)
    points = [p for p in bullet_items(sections.get("profile", [])) if p not in BULLETS]
    return {
        "is_resume": True,
        "work": work,
        "skills": skills,
        "summary": summary,
        "headline": headline,
        "profile_points": points,
        "certifications": bullet_items(sections.get("certifications", [])),
        "education": list_items(sections.get("education", []), split_degrees=True),
        "projects": list_items(sections.get("projects", [])),
        "problems": work_problems + skill_problems + _diagnostics(sections, work, points),
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
