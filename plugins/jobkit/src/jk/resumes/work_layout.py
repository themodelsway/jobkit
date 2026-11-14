"""Put the lines of a work-history section into one shape the work parser reads: header line, then date line.

Resumes write a job many ways. This module turns each of them into "Company" or "Company – Title", followed by a
line that holds only the dates:

  Company     09/2021 - Present            Company | Title | Sep 2021 – Present      Title    2019 - 2022
  Title                                    Title, Company (2019–2022)                Company
                                           Title at Company   2019 - 2022            Seattle, WA

A title written before the employer is swapped, a location line is dropped, and a title with its own dates inside
an employer (a promotion) becomes "Employer – Title" with its own date line. The employer registry is not needed.
Library module with no file access.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Final, NamedTuple

from jk.resumes.dates import RANGE_RE, find_date_range, is_date_line

BULLETS: Final[str] = "•●§▪◦"
SUB_MARK: Final[str] = "\x00SUB"          # prefix for 'o' sub-points, folded into the bullet above them
# A dash between employer and title: an en/em dash, or a hyphen with spaces around it (not Acme-Labs).
SEP: Final[str] = r"(?:\s*[–—]\s*|\s+-\s+)"
MAX_COMPANY_WORDS: Final[int] = 7
MAX_HEADLINE_CHARS: Final[int] = 60
MAX_HEADER_WORDS: Final[int] = 10
HEADER_PREFIX: Final = re.compile(r"(role|client)\s*:", re.I)
TITLE_WORDS: Final = re.compile(
    r"\b(?:engineer|developer|manager|director|architect|consultant|analyst|lead|head|officer|president"
    r"|administrator|specialist|programmer|scientist|designer|owner|supervisor|vp|principal|staff|associate"
    r"|intern|founder|co-founder|partner|advisor|strategist|coordinator|executive|researcher|cto|cio|ceo|ciso"
    r"|sde|sdet|evangelist|technologist|instructor|professor|trainer)\b", re.I)
TITLE_FILLER: Final = re.compile(r"^(?:senior|sr\.?|junior|jr\.?|chief|deputy|assistant|global|regional|of|and|&|the|for|to)$", re.I)
STATES: Final[frozenset[str]] = frozenset(
    "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR "
    "PA RI SC SD TN TX UT VT VA WA WV WI WY ON QC BC AB".split())
LOCATION_RE: Final = re.compile(r"^(?:(?P<city>[A-Z][A-Za-z .'-]{1,30}),\s*(?P<st>[A-Z]{2})(?:,\s*(?:USA|US))?"
                                r"|(?i:remote|hybrid|on-?site)(?:\s*[(,-].{0,20})?)$")
TRAILING_LOCATION_RE: Final = re.compile(r",\s*[A-Z][A-Za-z .'-]{1,30},\s*(?P<st>[A-Z]{2})$")


class HeaderParts(NamedTuple):
    """A job header taken apart; any part may be empty."""

    company: str
    title: str
    location: str


def tidy(text: str) -> str:
    """Whitespace squeezed to single spaces and edge commas removed."""
    return " ".join(text.split()).strip(" ,")


def is_location(line: str) -> bool:
    """True for a line that is only a place: 'Seattle, WA', 'Remote', 'Hybrid (Atlanta)'."""
    found = LOCATION_RE.match(line.strip())
    return bool(found) and (found["st"] is None or found["st"] in STATES)


def is_title_line(line: str) -> bool:
    """True for a line that reads as a job title on its own: a title word and no employer-title dash."""
    return bool(TITLE_WORDS.search(line)) and not re.search(SEP, line)


def title_score(line: str) -> float:
    """Share of the words of a line that read as part of a job title (title words, 'Senior', 'of' ...). 'Senior
    Engineer' is 1.0 and 'Principal Labs' 0.5, so of two lines that both hold a title word the higher is the title."""
    words = re.findall(r"[\w&.]+", line)
    return sum(1 for word in words if TITLE_WORDS.fullmatch(word) or TITLE_FILLER.match(word)) / len(words) if words else 0.0


def employer_by_context(name: str, other: str | None) -> bool:
    """True when `name` holds a title word but is the employer, because `other` (the line on the other side of the
    dates) is a clearer job title: 'Principal Labs' beside 'Senior Engineer'."""
    return bool(other) and is_title_line(name) and is_title_line(other or "") and title_score(other or "") > title_score(name)


def plausible_company(name: str) -> bool:
    """True when the text could be an employer name: short, starts with a capital or digit."""
    return (1 < len(name) < MAX_HEADLINE_CHARS and name[0].isalnum() and (name[0].isupper() or name[0].isdigit())
            and len(name.split()) <= MAX_COMPANY_WORDS)


def can_be_company_line(line: str) -> bool:
    """True when a line could be an employer name sitting above a title line."""
    return (line[0] not in BULLETS and not line.startswith(SUB_MARK) and not is_date_line(line)
            and not HEADER_PREFIX.match(line) and not line.endswith(".") and not is_location(line)
            and plausible_company(tidy(line)))


def _classify(parts: list[str]) -> HeaderParts:
    """Sort the pieces of a `|`-separated header into employer, title and place."""
    company = title = location = ""
    titles = [p for p in (q.strip() for q in parts) if p and not is_location(p) and is_title_line(p)]
    best = max(titles, key=title_score, default="")             # two title-like parts: the clearer one is the title
    for part in (p.strip() for p in parts if p.strip()):
        if is_location(part):
            location = location or part
        elif part == best and not title:
            title = part
        elif not company:
            company = part
    return HeaderParts(company, title, location)


def split_header(line: str) -> HeaderParts:
    """Employer, title and place of a header line written in one of the common shapes (see the module text)."""
    if re.search(r"[|·]", line):
        return _classify(re.split(r"\s*[|·]\s*", line))
    swapped = re.fullmatch(r"(?P<t>.+?)\s+(?:at|@)\s+(?P<c>.+)", line)
    if swapped and is_title_line(swapped["t"]) and plausible_company(swapped["c"]):
        return HeaderParts(swapped["c"], swapped["t"], "")
    first, comma, rest = line.partition(", ")
    if comma and is_title_line(first) and plausible_company(rest) and not is_title_line(rest) and not is_location(rest):
        return HeaderParts(rest, first, "")
    place = TRAILING_LOCATION_RE.search(line)
    if place and place["st"] in STATES:
        return HeaderParts(line[:place.start()], "", place[0].lstrip(", "))
    return HeaderParts("", "", "")


def canonical_header(line: str) -> str:
    """'Company – Title' (or 'Company') for a header in any shape; a line that is already one is returned as is."""
    parts = split_header(line)
    if not parts.company:
        return line
    return f"{parts.company} – {parts.title}" if parts.title else parts.company


def _looks_like_header(text: str, gapped: bool) -> bool:
    """True when the text beside a date range can be a job header and not a sentence that ends in dates. A gap of
    two or more spaces before the dates (a right-aligned date, a tab) is taken as proof; otherwise the text must be
    short and may not end with a full stop."""
    if not text or not (text[0].isupper() or text[0].isdigit()):
        return False
    return gapped or ((len(text.split()) <= MAX_HEADER_WORDS or "|" in text) and not text.endswith("."))


def _has_gap(raw: str, text_first: bool) -> bool:
    """True when two or more spaces separate the date range from the header text beside it."""
    match = RANGE_RE.search(raw)
    if match is None:
        return False
    side = raw[:match.start()] if text_first else raw[match.end():]
    return bool(re.search(r"\s{2,}$" if text_first else r"^\s{2,}\S", side))


def _split_dates(raw: str) -> list[str]:
    """One line as header and date lines when it has a date range and a header-like rest; else the line."""
    found = find_date_range(raw.strip())
    if found is None or raw.strip()[0] in BULLETS:
        return [raw]
    rest = found.before or found.after
    if found.before and found.after and not is_location(found.after):
        return [raw]                                     # dates inside a sentence
    dates = f"{found.start} - {found.end}"
    if not rest or is_location(rest):
        return [dates]
    gapped = _has_gap(raw, bool(found.before))
    return [canonical_header(rest), dates] if _looks_like_header(rest, gapped) else [raw]


def split_date_lines(lines: Iterable[str]) -> list[str]:
    """Pass 1: a date range after, or before, a header goes on its own line; 'o' sub-points get SUB_MARK."""
    out: list[str] = []
    for raw in lines:
        if re.match(r"^\s{4,}o\s+\S", raw):
            out.append(SUB_MARK + raw.strip()[1:].strip())
        else:
            out += _split_dates(raw)
    return [line.strip() for line in out if line.strip()]


def _header_index(out: list[str]) -> int | None:
    """Index in `out` of the header above a date line, skipping Role:/Client: lines."""
    j = len(out) - 1
    while j >= 0 and HEADER_PREFIX.match(out[j]):
        j -= 1
    return j if j >= 0 else None


def _is_bullet(line: str) -> bool:
    return line[0] in BULLETS or line.startswith(SUB_MARK)


def _company_of(header: str) -> str:
    return tidy(re.split(SEP, header)[0])


def _next_text(lines: list[str], i: int) -> int | None:
    """Index of the first line after `i` that is not a place."""
    j = i + 1
    while j < len(lines) and is_location(lines[j]):
        j += 1
    return j if j < len(lines) else None


class _Structurer:
    """State of pass 2: output so far, the employer in force, and which lines were consumed as title-first employers."""

    def __init__(self, lines: list[str]) -> None:
        self.lines = lines
        self.out: list[str] = []
        self.company = ""
        self.in_bullet = False
        self.skip: set[int] = set()

    def run(self) -> list[str]:
        """Walk the lines once and return the structured list."""
        for i, line in enumerate(self.lines):
            if i in self.skip:
                continue
            if is_date_line(line):
                self._date(i, line)
            elif is_location(line) and not self.in_bullet:
                continue
            else:
                self.in_bullet = self.in_bullet or _is_bullet(line)
                self.out.append(line)
        return self.out

    def _date(self, i: int, line: str) -> None:
        self.in_bullet = False
        header = _header_index(self.out)
        if header is not None:
            self._header(i, header)
        self.out.append(line)

    def _header(self, i: int, h: int) -> None:
        """Take the line at `h`, the one above a date line, as an employer header or as a job title."""
        line = self.out[h]
        if _is_bullet(line):
            return
        parts = split_header(line) if not re.search(SEP, line) else HeaderParts("", "", "")   # 'A – B' is already canonical
        nxt = _next_text(self.lines, i)
        after = self.lines[nxt] if nxt is not None and not _is_bullet(self.lines[nxt]) else None
        if parts.company:
            self.out[h] = canonical_header(line)                          # 'Company | Title' with its dates on the next line
            self.company = parts.company
        elif employer_by_context(line, after):
            self.company = _company_of(line)                              # 'Principal Labs' above 'Senior Engineer'
        elif is_title_line(line):
            self._title_header(i, h)
        else:
            self.company = _company_of(line)

    def _title_first(self, following: int, prev: str | None, title: str) -> bool:
        """True when the line at `following` is the employer of a title written first (see `_title_header`)."""
        nxt = self.lines[following]
        return ((not is_title_line(nxt) or employer_by_context(nxt, title)) and can_be_company_line(nxt)
                and (prev is None or not can_be_company_line(prev) or is_date_line(prev)))

    def _title_header(self, i: int, h: int) -> None:
        """The line above a date is a job title: decide title-first, promotion or the 'Company / Title / dates' shape."""
        title = self.out[h]
        prev = self.out[h - 1] if h > 0 else None
        following = _next_text(self.lines, i)
        if following is not None and self._title_first(following, prev, title):
            self.company = self.lines[following]                       # title first, employer on the next line
            self.out[h] = f"{self.company} – {title}"
            self.skip.add(following)
        elif prev is not None and is_date_line(prev) and h >= 2 and not _is_bullet(self.out[h - 2]):
            company = _company_of(self.out[h - 2])                     # employer dates, then a role with its own dates
            self.out[h - 2:h + 1] = [f"{company} – {title}"]
            self.company = company
        elif self.company and prev is not None and not can_be_company_line(prev):
            self.out[h] = f"{self.company} – {title}"                  # a promotion inside the current employer
        elif prev is not None and can_be_company_line(prev):
            self.company = _company_of(prev)                           # "Company / Title / dates": remember the employer


def structure_work_lines(lines: Iterable[str]) -> list[str]:
    """The lines of a work section in the shape described in the module text (blank lines removed)."""
    return _Structurer(split_date_lines(lines)).run()
