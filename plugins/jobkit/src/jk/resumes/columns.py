"""Split a page of fixed-width text (`pdftotext -layout`) into its columns.

A resume with a side column puts both columns on the same text lines:

  SKILLS                  SUMMARY
  Python                  Engineer with 15 years of experience.
  Java                    WORK EXPERIENCE

Read line by line, the work heading is buried and the side column is mixed into the main one. `split_columns`
finds the vertical gap shared by the lines of a column layout and returns the text one column after another, the
narrower column (usually the side bar) first so a main column that continues on a plain next page stays in order.
A page without a gutter is returned unchanged. Library module with no file access.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Final, NamedTuple

from jk.resumes.dates import is_date_line
from jk.resumes.headings import heading_key
from jk.resumes.work_layout import is_location

CHUNK_RE: Final = re.compile(r"\S+(?: {1,2}\S+)*")      # words separated by at most two spaces
MIN_LEFT_CHARS: Final[int] = 2
MIN_RIGHT_CHARS: Final[int] = 3
MIN_EVIDENCE: Final[int] = 6          # lines with text on both sides of the gutter
MIN_ALIGNED: Final[int] = 8           # lines whose right text starts at the same place
ALIGN_SHARE: Final[float] = 0.6
ALIGN_TOLERANCE: Final[int] = 4
MANY_ALIGNED: Final[int] = 12
PEAK_SHARE: Final[float] = 0.95
MAX_DEPTH: Final[int] = 2             # a column may itself hold two columns


class _Hit(NamedTuple):
    """A gap between two pieces of text on one line that could be a gutter: where it starts and ends."""

    start: int
    end: int


def _chunks(line: str) -> list[tuple[int, int]]:
    """(start, end) of each piece of text on a line; pieces are 3 or more spaces apart."""
    return [(m.start(), m.end()) for m in CHUNK_RE.finditer(line)]


def _hits(line: str) -> list[_Hit]:
    """The gaps on this line that could be a gutter. A gap before a date or a place (a right-aligned date) is not one."""
    chunks = _chunks(line)
    found = []
    for (start, end), (next_start, _) in zip(chunks, chunks[1:], strict=False):
        right = line[next_start:].strip()
        if end - start >= MIN_LEFT_CHARS and len(right) >= MIN_RIGHT_CHARS and not is_date_line(right) \
                and not is_location(right):
            found.append(_Hit(end, next_start))
    return found


def _best_gutter(lines: list[str]) -> int | None:
    """The last blank column shared by the lines that have a gap, just before the right-hand text starts; None when
    no gap repeats."""
    width = max((len(line) for line in lines), default=0)
    counts = [0] * (width + 1)
    for line in lines:
        for hit in _hits(line):
            for x in range(hit.start, hit.end):
                counts[x] += 1
    peak = max(counts, default=0)
    if peak < MIN_EVIDENCE:
        return None
    high = counts.index(peak)
    while high < width and counts[high + 1] >= peak * PEAK_SHARE:
        high += 1
    return high


def _covers(line: str, gutter: int) -> bool:
    """True when text on the line runs across the gutter column."""
    return any(start <= gutter < end for start, end in _chunks(line))


def _right_start(line: str, gutter: int) -> int | None:
    """Where the right-hand text of a line starts (None for a blank line, one that stops at the gutter, or one that
    crosses it)."""
    chunks = _chunks(line)
    right = [start for start, _ in chunks if start > gutter]
    if not right or _covers(line, gutter):
        return None
    return right[0]


def _is_column_layout(lines: list[str], gutter: int) -> bool:
    """True when the right-hand text of the lines starts at one place, as a column does, and not at scattered places
    as right-aligned titles or dates do."""
    starts = [s for line in lines if (s := _right_start(line, gutter)) is not None]
    evidence = sum(1 for line in lines if any(h.start <= gutter < h.end for h in _hits(line)))
    if len(starts) < MIN_ALIGNED or evidence < MIN_EVIDENCE:
        return False
    mode = Counter(starts).most_common(1)[0][0]
    aligned = [s for s in starts if abs(s - mode) <= ALIGN_TOLERANCE]
    only_right = sum(1 for line in lines if line.strip() and not line[:gutter + 1].strip() and _right_start(line, gutter))
    left_heads, right_heads = _headings(lines, gutter)
    own_sections = left_heads >= 1 and right_heads >= 1       # each side has section headings of its own: two columns
    return len(aligned) / len(starts) >= ALIGN_SHARE and (only_right >= 2 or evidence >= MANY_ALIGNED or own_sections)


def _headings(lines: list[str], gutter: int) -> tuple[int, int]:
    """How many lines have a section heading as their whole left text and as their whole right text."""
    left = sum(1 for line in lines if heading_key(line[:gutter + 1]))
    right = sum(1 for line in lines if heading_key(line[gutter + 1:]))
    return left, right


def _first_evidence(lines: list[str], gutter: int) -> int:
    """Index of the first line with text on both sides of the gutter."""
    return next(i for i, line in enumerate(lines) if any(h.start <= gutter < h.end for h in _hits(line)))


def _weight(lines: list[str]) -> int:
    """How much text a column holds: its characters other than spaces."""
    return sum(len(line.replace(" ", "")) for line in lines)


def _emit(left: list[str], right: list[str], depth: int) -> list[str]:
    """The two columns of one block, the one with less text first; each may split again."""
    columns = [right, left] if _weight(right) < _weight(left) else [left, right]
    out: list[str] = []
    for column in columns:
        out += _split(column, depth - 1) if depth > 0 else column
    return out


def _block_end(lines: list[str], start: int, gutter: int) -> int:
    """Index just after the last line of the column block that starts at `start`. The block runs to the first line
    that crosses the gutter (full-width text); when such a line follows, the lines after the last right-hand text
    that come after a blank line belong to that full-width text and not to a column."""
    cross = next((i for i in range(start, len(lines)) if _covers(lines[i], gutter)), len(lines))
    if cross == len(lines):
        return cross
    last_right = max((i for i in range(start, cross) if _right_start(lines[i], gutter) is not None), default=start)
    end = last_right + 1
    while end < cross and lines[end].strip():
        end += 1
    return end


def _columns(block: list[str], gutter: int, depth: int) -> list[str]:
    """The lines of one column block cut at the gutter and read column after column."""
    left = [line[:gutter + 1].rstrip() for line in block]
    right = [line[gutter + 1:].rstrip() for line in block]
    return _emit(left, right, depth)


def _split(lines: list[str], depth: int) -> list[str]:
    """Lines as columns (see the module text); the same list when there is no gutter. Full-width text ends a column
    block, and what follows it is looked at again, so a page can hold columns, then plain text, then columns."""
    gutter = _best_gutter(lines)
    if gutter is None or not _is_column_layout(lines, gutter):
        return lines
    start = _first_evidence(lines, gutter)
    end = _block_end(lines, start, gutter)
    return lines[:start] + _columns(lines[start:end], gutter, depth) + _split(lines[end:], depth)


def split_columns(page: str) -> str:
    """One page of layout text with its columns one after another; a page with no columns is returned unchanged."""
    lines = page.split("\n")
    result = _split(lines, MAX_DEPTH)
    return page if result is lines else "\n".join(result)
