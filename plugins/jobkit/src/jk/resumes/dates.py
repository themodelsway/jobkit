"""Find and read date ranges in resume lines ("09/2021 - Present", "Sep 2021 – Aug 2023", "2012 – 2017").

Library module with no file access. Dates are stored as `YYYY-MM`, or `YYYY` when a resume gives only a year; an
open end (Present, Current, Now ...) is None.

  find_date_range("Acme Corp | Engineer | Sep 2021 – Present")  ->  ("Acme Corp | Engineer |", "Sep 2021", "Present", "")
  parse_date("Sep 2021")  ->  "2021-09"
"""
from __future__ import annotations

import re
from datetime import date
from typing import Final, NamedTuple

MONTH_NAMES: Final[tuple[str, ...]] = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
OPEN_ENDS: Final[frozenset[str]] = frozenset({"present", "current", "now", "today", "ongoing", "date"})

_MONTH = r"(?:0?[1-9]|1[0-2])"
_YEAR = r"(?:19|20)\d{2}"
_NAME = (r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?"
         r"|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?")
_TOKEN = (rf"(?:{_MONTH}[/.-]{_YEAR}(?!\d)|{_YEAR}[-/.]{_MONTH}(?![\d])|{_MONTH}/\d{{2}}(?!\d)"
          rf"|{_NAME}[ ]*,?[ ]*(?:{_YEAR}|'\d{{2}})(?!\d)|{_YEAR}(?!\d))")
_OPEN = r"(?:present|current|now|today|ongoing|(?:(?:to|till|until)[ ]+)?date)"
_SEP = r"(?:[ ]*[–—-][ ]*|[ ]+(?:to|until|till)[ ]+)"
RANGE_RE: Final = re.compile(rf"(?<![\w/.-])(?P<s>{_TOKEN}){_SEP}(?P<e>{_TOKEN}|{_OPEN})(?![\w/])", re.I)
EDGE_PUNCT: Final[str] = " \t|·,;:–—-()[]"


class DateRange(NamedTuple):
    """Where a date range sits in a line: the text before it, the two ends as written, the text after it."""

    before: str
    start: str
    end: str
    after: str


def find_date_range(line: str) -> DateRange | None:
    """The first date range in the line, with the text around it (edge punctuation and spaces removed)."""
    match = RANGE_RE.search(line)
    if not match:
        return None
    return DateRange(line[:match.start()].strip(EDGE_PUNCT), match["s"], match["e"], line[match.end():].strip(EDGE_PUNCT))


def is_date_line(line: str) -> bool:
    """True for a line that holds a date range and nothing else."""
    found = find_date_range(line)
    return bool(found and not found.before and not found.after)


def _two_digit_year(text: str) -> int:
    """20YY when YY is not in the future, else 19YY."""
    short = int(text)
    return 2000 + short if short <= date.today().year % 100 else 1900 + short


def parse_date(text: str) -> str | None:
    """One end of a range as 'YYYY-MM' ('YYYY' when only a year is given); None for Present, Current and the like."""
    text = re.sub(r"^(?:to|till|until)\s+", "", text.strip().lower())
    if text in OPEN_ENDS:
        return None
    named = re.fullmatch(rf"({_NAME})[ ]*,?[ ]*({_YEAR}|'\d{{2}})", text)
    if named:
        year = named[2] if len(named[2]) == 4 else str(_two_digit_year(named[2][1:]))
        return f"{year}-{MONTH_NAMES.index(named[1][:3]) + 1:02d}"
    year_first = re.fullmatch(rf"({_YEAR})[-/.]({_MONTH})", text)
    if year_first:
        return f"{year_first[1]}-{int(year_first[2]):02d}"
    month_first = re.fullmatch(rf"({_MONTH})[/.-]({_YEAR}|\d{{2}})", text)
    if month_first:
        year = month_first[2] if len(month_first[2]) == 4 else str(_two_digit_year(month_first[2]))
        return f"{year}-{int(month_first[1]):02d}"
    return text if re.fullmatch(_YEAR, text) else None


def month_index(value: str | None) -> int | None:
    """Months since year 0 for 'YYYY-MM' (June for a bare 'YYYY'), else None."""
    found = re.fullmatch(r"(\d{4})(?:-(\d{2}))?", value or "")
    if not found:
        return None
    return int(found[1]) * 12 + (int(found[2]) - 1 if found[2] else 5)
