"""Turn a resume file (pdf, docx, md, txt) into text the parser understands.

One extractor per file format, found by suffix (strategy + registry). The rest of the pipeline calls only
`extract(path)` and gets an `ExtractedDocument` back; it never learns which format the file was.

  from jk.resumes import extract
  doc = extract.extract(Path("resume.docx"))
  parse_resume(doc.text, doc.layout_text)

To support a new format, write a class with `suffixes` and `extract()` and decorate it with `@register`.
Standard library only; PDF uses poppler's `pdftotext` when it is installed and `pypdf` otherwise.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import unicodedata
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, Final, Protocol
from xml.etree import ElementTree

from jk import common
from jk.resumes.columns import split_columns
from jk.resumes.dates import is_date_line
from jk.resumes.headings import heading_key

BULLET: Final[str] = "•"
GAP: Final[str] = "   "                    # stands in for a tab or table cell edge; the parser splits dates on 2+ spaces
ZERO_WIDTH: Final[dict[int, None]] = dict.fromkeys(map(ord, "\u200b\u200c\u200d\ufeff"))
LIST_MARKER_RE: Final = re.compile(r"^(\s*)(?:[-*+•●▪◦‣–¥]|\d+[.)])\s+")
CONTACT_LINE_RE: Final = re.compile(
    r"^\s*(?:[\w.+-]+@[\w-]+(?:\.[\w-]+)+"                                  # email
    r"|\(?\d{3}\)?[ .-]?\d{3}[ .-]\d{4}"                                      # phone
    r"|(?:https?://)?(?:www\.)?(?i:linkedin)\.com/\S*"                              # LinkedIn
    r"|\d{5}(?:-\d{4})?,\s*[A-Za-z .]+,\s*[A-Z]{2}\b.*"                      # "30024, City, ST ..."
    r"|.*,\s*[A-Z]{2}[ ,]+\d{5}(?:-\d{4})?)\s*$")                           # "... City, ST 30024"
CONTACT_SPLIT_RE: Final = re.compile(r"\s*[|·•]\s*")
MAX_CONTACT_BLOCK: Final[int] = 6
TRAILING_DATE_RE: Final = re.compile(r"(?<=\S)[ ]+(\d{2}/\d{4}\s*[–—-]\s*(?:\d{2}/\d{4}|Present|Current))\s*$", re.I)
W: Final[str] = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
DOCX_BODY: Final[str] = "word/document.xml"
DOCX_SIDE_PART_RE: Final = re.compile(r"word/(?:header|footer)\d*\.xml")
PDF_BULLET_RE: Final = re.compile(r"^([ \t]*)[-*+‣–—¥➢►▶■□◆◇❖✓✔→⁃\uf0b7\uf0a7\uf0d8\uf076\uf0fc]\s+")
PAGE_NUMBER_RE: Final = re.compile(r"^(?:page\s+)?\d+(?:\s*(?:of|/)\s*\d+)?$", re.I)
PAGE_BREAK: Final[str] = "\f"
VISUAL_HINT: Final[str] = ("The pages can be read visually if the user agrees; otherwise export a text PDF or use "
                           "docx/txt/md.")
MIN_PDF_CHARS: Final[int] = 20             # fewer letters than this in a whole PDF means there is no text layer


@dataclass(frozen=True)
class ExtractedDocument:
    """What an extractor hands to the parser."""

    text: str            # reading-order text
    layout_text: str     # text keeping the original positions; the same text for formats without a layout
    format: str          # "pdf", "docx", "md" or "txt"
    column_pages: tuple[int, ...] = ()   # 1-based numbers of the PDF pages read as columns (see columns.py)


class NeedsVisualRead(common.ToolError):
    """A PDF whose text cannot be read by the parser (no text layer, or not readable as a PDF). The agent may read
    its pages as images, but only after the user agrees (see visual.py)."""


class TextExtractor(Protocol):
    """A reader for one family of file suffixes."""

    suffixes: ClassVar[tuple[str, ...]]

    def extract(self, path: Path) -> ExtractedDocument:
        """Read the file and return its text."""
        ...


EXTRACTORS: dict[str, TextExtractor] = {}


def register[E: TextExtractor](cls: type[E]) -> type[E]:
    """Class decorator: make `cls` the extractor for each of its suffixes."""
    instance = cls()
    for suffix in cls.suffixes:
        EXTRACTORS[suffix] = instance
    return cls


def supported_suffixes() -> tuple[str, ...]:
    """Every file suffix with an extractor, sorted (lower case, with the dot)."""
    return tuple(sorted(EXTRACTORS))


def is_resume_file(path: Path) -> bool:
    """True for a readable-looking resume file: a supported suffix and not a Word `~$` lock file or hidden file."""
    return path.suffix.lower() in EXTRACTORS and not path.name.startswith(("~$", "."))


def extractor_for(path: Path) -> TextExtractor:
    """The extractor for this file's suffix; ToolError names the supported suffixes when there is none."""
    try:
        return EXTRACTORS[path.suffix.lower()]
    except KeyError:
        raise common.ToolError(f"Unsupported resume format '{path.suffix}' ({path.name}). "
                               f"Supported: {', '.join(supported_suffixes())}.") from None


def extract(path: Path) -> ExtractedDocument:
    """Read any supported resume file; a file with no usable text raises ToolError that names the likely cause."""
    doc = extractor_for(path).extract(path)
    letters = len(re.sub(r"\s", "", doc.text))
    if doc.format == "pdf" and letters < MIN_PDF_CHARS:
        raise NeedsVisualRead(f"{path.name} has no text layer: it looks like a scanned image, and OCR is not supported. "
                              f"{VISUAL_HINT}")
    if letters == 0:
        raise common.ToolError(f"{path.name} has no text.")
    return doc


# ---------------------------------------------------------------- shared text clean-up

def is_contact_line(line: str) -> bool:
    """True for a line that holds only contact details: an email, phone, LinkedIn or postal address, or several
    of them separated by `|`, `·` or `•`. A line with any other text is not one."""
    parts = [part for part in CONTACT_SPLIT_RE.split(line) if part.strip()]
    return bool(parts) and all(CONTACT_LINE_RE.match(part) for part in parts)


def normalize(text: str) -> str:
    """Common clean-up for non-PDF text: newlines, zero-width characters, non-breaking spaces, bullet glyphs.

    Every list marker (`-`, `*`, `1.`, `●` ...) becomes `•` so the parser sees one bullet style. Lines that hold
    only an email address, phone number, LinkedIn address or postal address are dropped: documents often carry a floating contact
    block, and it would otherwise be glued onto the bullet above it and end up in the resume data.
    """
    text = text.translate(ZERO_WIDTH).replace("\xa0", " ").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]*\t[ \t]*", GAP, text)
    text = "\n".join(line for line in text.split("\n") if not is_contact_line(line))
    lines = [_gap_before_date(LIST_MARKER_RE.sub(lambda m: f"{m[1]}{BULLET} ", line.rstrip()))
             for line in text.split("\n")]
    return "\n".join(lines).strip("\n") + "\n"


def _gap_before_date(line: str) -> str:
    """Put GAP before a date range that ends a line ("Acme  03/2021 - Present"): converters drop the tab that
    separated company and dates, and the parser tells a header from a sentence by that gap. Bullets are left alone."""
    if line.lstrip().startswith(BULLET):
        return line
    return TRAILING_DATE_RE.sub(lambda m: GAP + m[1], line)


def _is_contact_block(cell: list[str]) -> bool:
    """True for a short table cell (at most MAX_CONTACT_BLOCK lines) that has an email, phone or LinkedIn line."""
    return len(cell) <= MAX_CONTACT_BLOCK and any(CONTACT_LINE_RE.match(line) for line in cell)


def _drop_contact_cells(cells: list[list[str]]) -> list[list[str]]:
    """A row with a contact block (a short cell holding an email or phone line) loses all its short cells."""
    if any(_is_contact_block(cell) for cell in cells):
        return [cell for cell in cells if len(cell) > MAX_CONTACT_BLOCK]
    return cells


def _timeline_row(cells: list[list[str]]) -> list[str] | None:
    """A row of two cells, one of them only a date range (and perhaps a place), is a timeline entry: the other cell's
    first line goes in front of the date, as 'Company – Title    09/2021 - Present', and its other lines follow.
    None for any other row."""
    filled = [cell for cell in cells if cell]
    if len(filled) != 2:
        return None
    dated = [cell for cell in filled if len(cell) <= 2 and is_date_line(cell[0])]
    if len(dated) != 1:
        return None
    content = next(cell for cell in filled if cell is not dated[0])
    return [f"{content[0].strip()}{GAP}{dated[0][0].strip()}", *content[1:]]


def row_lines(cells: list[list[str]]) -> list[str]:
    """Lines for one table row, each cell given as its list of non-blank lines. A timeline row (see `_timeline_row`)
    puts the date after its entry. A row of single-line cells (a title beside its dates) becomes one line joined by
    GAP; a row with a multi-line cell keeps every line, cell after cell. A row with a contact block (a short cell
    holding an email or phone line) loses all its short cells, so the address beside the email goes too."""
    cells = _drop_contact_cells(cells)
    timeline = _timeline_row(cells)
    if timeline is not None:
        return timeline
    if all(len(cell) <= 1 for cell in cells):
        line = GAP.join(line.strip() for cell in cells for line in cell)
        return [line] if line else []
    return [line for cell in cells for line in cell]


def _is_layout_table(rows: list[list[list[str]]]) -> bool:
    """True for a table used to lay out the page: it has several columns and some cell starts with a section
    heading ('Leadership Skills | Technical Skills', a side bar beside the work history)."""
    return (any(len(row) > 1 for row in rows)
            and any(cell and heading_key(cell[0]) for row in rows for cell in row))


def _is_banner(row: list[list[str]]) -> bool:
    """True for a row that is only a section heading: one filled cell holding one line (a merged heading cell, or a
    heading cell beside empty ones)."""
    filled = [cell for cell in row if cell]
    return len(filled) == 1 and len(filled[0]) == 1 and heading_key(filled[0][0]) is not None


def _layout_lines(rows: list[list[list[str]]]) -> list[str]:
    """The rows of a layout table read column after column. A column that holds the work-history heading is the main
    flow and is read last, after the side columns, so work that continues below the table still follows its heading."""
    width = max(len(row) for row in rows)
    columns = [[line for row in rows if column < len(row) for line in row[column]] for column in range(width)]
    main = next((i for i, lines in enumerate(columns) if any(heading_key(line) == "work" for line in lines)), None)
    order = [i for i in range(width) if i != main] + ([] if main is None else [main])
    return [line for i in order for line in columns[i]]


def _body_lines(rows: list[list[list[str]]]) -> list[str]:
    """Rows without a banner: a layout table is read by column (see `_layout_lines`), any other row by row."""
    if not rows:
        return []
    if not _is_layout_table(rows):
        return [line for row in rows for line in row_lines(row)]
    return _layout_lines(rows)


def table_lines(rows: list[list[list[str]]]) -> list[str]:
    """Lines of a table given as rows of cells of non-blank lines. A banner row (a merged heading, or a lone heading cell
    above timeline rows) is kept in place and splits the table; each part is then a layout table, read column after column so a heading and its list stay
    together, or any other table, read row by row (see `row_lines`)."""
    out: list[str] = []
    body: list[list[list[str]]] = []
    kept = [_drop_contact_cells(r) for r in rows]
    for index, row in enumerate(kept):
        following = kept[index + 1] if index + 1 < len(kept) else None
        if _is_banner(row) and (len(row) == 1 or (following is not None and _timeline_row(following) is not None)):
            out += _body_lines(body) + [line for cell in row for line in cell]
            body = []
        else:
            body.append(row)
    return out + _body_lines(body)


def read_text_file(path: Path) -> str:
    """File contents as UTF-8 (BOM allowed); falls back to cp1252 for files saved by older Windows editors."""
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


# ---------------------------------------------------------------- pdf

def _pypdf_pages(path: Path) -> list[Any]:
    """The pages of a PDF read with pypdf, whose chatter about slightly damaged files is kept off the screen."""
    import logging  # pylint: disable=import-outside-toplevel
    from pypdf import PdfReader  # pylint: disable=import-outside-toplevel  # only needed without poppler
    from pypdf.errors import PyPdfError  # pylint: disable=import-outside-toplevel
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    try:
        return list(PdfReader(path).pages)
    except PyPdfError as exc:
        raise NeedsVisualRead(f"{path.name} could not be read as a PDF ({exc}). {VISUAL_HINT}") from exc


def _edge_lines(pages: list[list[str]]) -> list[tuple[int | None, int | None]]:
    """(index of the first, index of the last) non-blank line of each page."""
    edges: list[tuple[int | None, int | None]] = []
    for lines in pages:
        filled = [i for i, line in enumerate(lines) if line.strip()]
        edges.append((filled[0], filled[-1]) if filled else (None, None))
    return edges


def _drop_edges(pages: list[list[str]], page_numbers_only: bool) -> list[list[str]]:
    """One pass of `drop_page_furniture`: page numbers (all passes) and, when not `page_numbers_only`, headers and
    footers that repeat."""
    edges = _edge_lines(pages)
    first_text = pages[0][edges[0][0]].strip() if edges[0][0] is not None else ""
    heads = [pages[n][e[0]].strip() for n, e in enumerate(edges) if n and e[0] is not None]
    foots = [pages[n][e[1]].strip() for n, e in enumerate(edges) if e[1] is not None]
    drop: set[tuple[int, int]] = set()
    for n, (head, foot) in enumerate(edges):
        if not page_numbers_only and n and head is not None and (
                pages[n][head].strip() == first_text or heads.count(pages[n][head].strip()) > 1):
            drop.add((n, head))
        if foot is not None and (PAGE_NUMBER_RE.match(pages[n][foot].strip())
                                 or (not page_numbers_only and foots.count(pages[n][foot].strip()) > 1)):
            drop.add((n, foot))
    return [[line for i, line in enumerate(lines) if (n, i) not in drop] for n, lines in enumerate(pages)]


def drop_page_furniture(pages: list[list[str]]) -> list[list[str]]:
    """Remove what a page repeats: page numbers, a footer on two or more pages (also when a page number sits below
    it), and a header repeated from page 1 (the first copy stays). A document of one page is unchanged."""
    if len(pages) < 2:
        return pages
    return _drop_edges(_drop_edges(pages, True), False)


def canonical_pdf_bullets(line: str) -> str:
    """A line that starts with any other list glyph (dash, arrow, square, a symbol-font glyph) starts with `•`."""
    return PDF_BULLET_RE.sub(lambda m: f"{m[1]}{BULLET} ", line)


def clean_pdf_pages(text: str) -> list[str]:
    """The pages of PDF text: ligatures and look-alike characters unfolded, one bullet glyph, page headers and
    footers removed. Pages are separated by form feeds (pdftotext) in the input."""
    pages = [[canonical_pdf_bullets(line) for line in page.split("\n")]
             for page in unicodedata.normalize("NFKC", text).split(PAGE_BREAK)]
    return ["\n".join(lines) for lines in drop_page_furniture(pages)]


@register
class PdfExtractor:
    """PDF via poppler: `pdftotext` for reading order, `pdftotext -layout` for positions; pypdf (reading order and
    its own layout mode) when poppler is missing, as on most Windows computers. A page with columns is read one
    column after another (see columns.py), so a side bar never mixes into the main column."""

    suffixes: ClassVar[tuple[str, ...]] = (".pdf",)

    def extract(self, path: Path) -> ExtractedDocument:
        """Reading-order text (the column-by-column layout text when a page has columns) plus layout text."""
        try:
            reading, layout = self._reading_order(path), self._layout(path)
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or "").strip().splitlines()
            raise NeedsVisualRead(f"{path.name} could not be read as a PDF"
                                  f"{': ' + detail[0] if detail else ''}. {VISUAL_HINT}") from exc
        except (OSError, ValueError, KeyError) as exc:
            raise NeedsVisualRead(f"{path.name} could not be read as a PDF ({exc}). {VISUAL_HINT}") from exc
        pages = clean_pdf_pages(layout)
        split = [split_columns(page) for page in pages]
        marked = ["\n".join(canonical_pdf_bullets(line) for line in page.split("\n")) for page in split]
        layout_text = "\n".join(marked)
        text = layout_text if split != pages else "\n".join(clean_pdf_pages(reading))
        column_pages = tuple(n for n, (old, new) in enumerate(zip(pages, split, strict=True), 1) if old != new)
        split = marked
        return ExtractedDocument(text, layout_text, "pdf", column_pages)

    @staticmethod
    def _reading_order(path: Path) -> str:
        if shutil.which("pdftotext"):
            return subprocess.run(["pdftotext", str(path), "-"], capture_output=True, text=True, check=True).stdout
        return PAGE_BREAK.join(page.extract_text() or "" for page in _pypdf_pages(path))

    @staticmethod
    def _layout(path: Path) -> str:
        if not shutil.which("pdftotext"):
            return PAGE_BREAK.join(page.extract_text(extraction_mode="layout") or "" for page in _pypdf_pages(path))
        return subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True,
                              check=True).stdout


# ---------------------------------------------------------------- txt and md

@register
class TextFileExtractor:
    """Plain text."""

    suffixes: ClassVar[tuple[str, ...]] = (".txt",)

    def extract(self, path: Path) -> ExtractedDocument:
        """The file's text with bullets normalised; it also serves as layout text (lines keep their dates)."""
        text = normalize(read_text_file(path))
        return ExtractedDocument(text, text, "txt")


MD_RULES: Final[tuple[tuple[re.Pattern[str], str], ...]] = (
    (re.compile(r"<!--.*?-->", re.S), ""),                                  # HTML comment (pandoc list separator)
    (re.compile(r"^[ \t]*>[ \t]?", re.M), ""),                              # blockquote marker
    (re.compile(r"\\(?=[*_]*[ \t]*$)", re.M), ""),                         # trailing backslash = hard line break
    (re.compile(r"\{(?:width|height)=[^{}]*\}"), ""),                      # pandoc image size attributes
    (re.compile(r"^[ ]{0,3}#{1,6}[ \t]*(.*?)[ \t]*#*[ \t]*$", re.M), r"\1"),          # "## Heading" -> "Heading"
    (re.compile(r"<((?:mailto:|https?://)?[^<>\s]+)>"), r"\1"),                # <autolink> -> address
    (re.compile(r"\[([^\[\]]*)\]\{[^{}]*\}"), r"\1"),                       # pandoc span [text]{.underline} -> text
    (re.compile(r"!?\[([^\]]*)\]\([^)]*\)"), r"\1"),                        # [text](url) -> text
    (re.compile(r"(\*\*|__)(.+?)\1"), r"\2"),                               # bold
    (re.compile(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])"), r"\1"),      # *italic*
    (re.compile(r"(?<!\w)_(?!\s)(.+?)(?<!\s)_(?!\w)"), r"\1"),              # _italic_
    (re.compile(r"\*{2,}|_{3,}"), ""),                                     # emphasis left open by a line break
    (re.compile(r"`([^`]*)`"), r"\1"),                                      # inline code
    (re.compile(r"^\s*([-*_])(?:\s*\1){2,}\s*$", re.M), ""),                # horizontal rule
    (re.compile(r"(?<=\S)( ?)---( ?)(?=\S)"), r"\1—\2"),                     # pandoc "---" -> em dash
    (re.compile(r"(?<=\S)( ?)--( ?)(?=\S)"), r"\1–\2"),                      # "--" -> en dash
    (re.compile(r"\\([!-/:-@\[-`{-~])"), r"\1"),                             # backslash before punctuation
)
MD_TABLE_ROW_RE: Final = re.compile(r"^\s*\|(.*)\|\s*$")
MD_TABLE_RULE_RE: Final = re.compile(r"^[\s|:-]+$")
MD_GRID_RULE_RE: Final = re.compile(r"^\+[-=:+]+\+\s*$")


WRAPPED_EMPHASIS_RE: Final = re.compile(r"(\*\*|__|\*|_)(.+)\1")


def _unwrap(text: str) -> str:
    """'**Skills**' -> 'Skills', so a bold heading cell is recognised as a heading; other text unchanged."""
    found = WRAPPED_EMPHASIS_RE.fullmatch(text)
    return found[2].strip() if found else text


def _pipe_tables(lines: list[str]) -> list[str]:
    """Replace each run of pipe-table rows by the lines of the table (see `table_lines`); other lines unchanged."""
    out: list[str] = []
    rows: list[list[list[str]]] = []
    for line in [*lines, ""]:
        match = MD_TABLE_ROW_RE.match(line)
        if match:
            rows.append([[_unwrap(cell.strip())] if cell.strip() else [] for cell in match[1].split("|")])
            continue
        out += table_lines(rows) if rows else []
        rows = []
        out.append(line)
    return out[:-1]


def _is_pipe_rule(line: str) -> bool:
    """True for the |---|---| separator row of a pipe table."""
    match = MD_TABLE_ROW_RE.match(line)
    return bool(match and MD_TABLE_RULE_RE.match(match[1]))


def _grid_cuts(rule: str) -> list[int]:
    """Column boundaries of a grid table: the positions of '+' in a `+----+----+` rule."""
    return [i for i, char in enumerate(rule.rstrip()) if char == "+"]


def _grid_row(lines: list[str], cuts: list[int]) -> list[list[str]]:
    """One grid-table row (its physical lines between two rules) as cells, each a list of non-blank lines."""
    cells: list[list[str]] = [[] for _ in range(len(cuts) - 1)]
    for line in lines:
        for column, (start, end) in enumerate(zip(cuts, cuts[1:], strict=False)):
            part = line[start + 1:end].strip()
            if part:
                cells[column].append(_unwrap(part))
    return cells


def _grid_table(lines: list[str], i: int) -> tuple[list[str], int]:
    """The table whose first rule is at `lines[i]` as text lines (see `table_lines`), and the index after it."""
    cuts = _grid_cuts(lines[i])
    rows: list[list[list[str]]] = []
    row: list[str] = []
    i += 1
    while i < len(lines) and lines[i][:1] in ("+", "|"):
        if MD_GRID_RULE_RE.match(lines[i]):
            rows.append(_grid_row(row, cuts))
            row = []
        else:
            row.append(lines[i])
        i += 1
    if row:
        rows.append(_grid_row(row, cuts))
    return table_lines(rows), i


def _grid_tables(lines: list[str]) -> list[str]:
    """Replace each pandoc grid table (`+---+` rules with `|` rows) by the lines of its rows."""
    out: list[str] = []
    i = 0
    while i < len(lines):
        if MD_GRID_RULE_RE.match(lines[i]):
            text, i = _grid_table(lines, i)
            out += text
        else:
            out.append(lines[i])
            i += 1
    return out


@register
class MarkdownExtractor:
    """Markdown: syntax is stripped (headings, emphasis, links, tables) and list markers become bullets."""

    suffixes: ClassVar[tuple[str, ...]] = (".md", ".markdown")

    def extract(self, path: Path) -> ExtractedDocument:
        """Markdown rendered to the plain text the parser expects."""
        lines = [line for line in _grid_tables(read_text_file(path).splitlines()) if not _is_pipe_rule(line)]
        text = "\n".join(lines)
        for pattern, replacement in MD_RULES:
            text = pattern.sub(replacement, text)
        text = normalize("\n".join(_pipe_tables(text.splitlines())))
        return ExtractedDocument(text, text, "md")


# ---------------------------------------------------------------- docx

MC: Final[str] = "{http://schemas.openxmlformats.org/markup-compatibility/2006}"
DOCX_STYLES: Final[str] = "word/styles.xml"
SKIPPED_IN_TEXT: Final[frozenset[str]] = frozenset({f"{W}txbxContent", f"{W}pPr", f"{MC}Fallback"})


def _runs(node: ElementTree.Element) -> Iterator[str]:
    """The text pieces of a paragraph in order: text, tabs as GAP, line breaks as newlines. Text boxes (read apart),
    the Word 'fallback' copy of a drawing and paragraph properties (tab stop definitions) are not text."""
    for child in node:
        if child.tag in SKIPPED_IN_TEXT:
            continue
        if child.tag == f"{W}t":
            yield child.text or ""
        elif child.tag == f"{W}tab":
            yield GAP
        elif child.tag in (f"{W}br", f"{W}cr"):
            yield "\n"
        else:
            yield from _runs(child)


def _is_list_item(paragraph: ElementTree.Element, list_styles: frozenset[str]) -> bool:
    """True when the paragraph is a list item: it has its own list numbering (not number 0), or it has none of its own
    and its paragraph style carries numbering."""
    properties = paragraph.find(f"{W}pPr")
    if properties is None:
        return False
    numbering = properties.find(f"{W}numPr")
    number = numbering.find(f"{W}numId") if numbering is not None else None
    if number is not None:
        return number.get(f"{W}val") != "0"
    style = properties.find(f"{W}pStyle")
    return numbering is not None or (style is not None and style.get(f"{W}val") in list_styles)


def _paragraph_text(paragraph: ElementTree.Element, list_styles: frozenset[str] = frozenset()) -> str:
    """Text of one w:p in document order: tabs become GAP, line breaks newlines; list paragraphs get a bullet."""
    text = "".join(_runs(paragraph))
    in_list = _is_list_item(paragraph, list_styles)
    return f"{BULLET} {text.lstrip()}" if in_list and text.strip() and not text.lstrip().startswith(BULLET) else text


def _text_boxes(node: ElementTree.Element) -> Iterator[ElementTree.Element]:
    """The text boxes inside a paragraph. Word writes a drawing twice (`mc:Choice` and `mc:Fallback`): the first copy
    that has text is used and the other ignored."""
    for child in node:
        if child.tag == f"{W}txbxContent":
            yield child
        elif child.tag == f"{MC}AlternateContent":
            copies = [list(_text_boxes(branch)) for branch in child]
            yield from next((boxes for boxes in copies if boxes), [])
        else:
            yield from _text_boxes(child)


def _table_lines(table: ElementTree.Element, list_styles: frozenset[str]) -> Iterator[str]:
    """Lines of a table (see `table_lines`); nested tables are read recursively."""
    rows = [[[line for line in docx_lines(cell, list_styles) if line.strip()] for cell in row.findall(f"{W}tc")]
            for row in table.findall(f"{W}tr")]
    yield from table_lines(rows)


def docx_lines(body: ElementTree.Element, list_styles: frozenset[str] = frozenset()) -> Iterator[str]:
    """Lines of a body, table cell or content control: paragraphs and tables in order, nested tables included. A text
    box (a side column) is read as its own block, set off by blank lines, after the paragraph it is anchored in."""
    for child in body:
        if child.tag == f"{W}p":
            yield from _paragraph_text(child, list_styles).split("\n")
            for box in _text_boxes(child):
                yield ""
                yield from docx_lines(box, list_styles)
                yield ""
        elif child.tag == f"{W}tbl":
            yield from _table_lines(child, list_styles)
        elif child.tag == f"{W}sdt":                       # content control wrapping paragraphs
            content = child.find(f"{W}sdtContent")
            if content is not None:
                yield from docx_lines(content, list_styles)


def _numbered_styles(archive: zipfile.ZipFile) -> frozenset[str]:
    """Ids of the paragraph styles that carry list numbering, directly or through the style they are based on."""
    if DOCX_STYLES not in archive.namelist():
        return frozenset()
    try:
        root = ElementTree.fromstring(archive.read(DOCX_STYLES))
    except ElementTree.ParseError:
        return frozenset()
    own: dict[str, bool | None] = {}       # True: numbering on, False: switched off (numId 0), None: inherits
    parent: dict[str, str] = {}
    for style in root.findall(f"{W}style"):
        sid = style.get(f"{W}styleId", "")
        number = style.find(f"{W}pPr/{W}numPr/{W}numId")
        own[sid] = None if number is None else number.get(f"{W}val") != "0"
        based = style.find(f"{W}basedOn")
        if based is not None:
            parent[sid] = based.get(f"{W}val", "")

    def numbered(sid: str, seen: frozenset[str] = frozenset()) -> bool:
        if sid not in own or sid in seen:
            return False
        state = own[sid]
        return state if state is not None else numbered(parent.get(sid, ""), seen | {sid})
    return frozenset(sid for sid in own if numbered(sid))


def _side_text(path: Path) -> bool:
    """True when a docx header or footer part holds any text."""
    with zipfile.ZipFile(path) as archive:
        parts = [n for n in archive.namelist() if DOCX_SIDE_PART_RE.fullmatch(n)]
        return any(node.text and node.text.strip() for n in parts
                   for node in ElementTree.fromstring(archive.read(n)).iter(f"{W}t"))


@register
class DocxExtractor:
    """Word .docx, read straight from the zip (no third-party package). Headers and footers are ignored; text boxes,
    page-layout tables and bullets set by a paragraph style are read as the page shows them."""

    suffixes: ClassVar[tuple[str, ...]] = (".docx",)

    def extract(self, path: Path) -> ExtractedDocument:
        """Body paragraphs and tables as text; the same text serves as layout text (tabs keep dates apart)."""
        try:
            with zipfile.ZipFile(path) as archive:
                root = ElementTree.fromstring(archive.read(DOCX_BODY))
                list_styles = _numbered_styles(archive)
        except (zipfile.BadZipFile, KeyError, ElementTree.ParseError) as error:
            raise common.ToolError(f"{path.name} is not a readable .docx file ({error}).") from error
        body = root.find(f"{W}body")
        text = normalize("\n".join(docx_lines(body if body is not None else root, list_styles)))
        if not text.strip() and _side_text(path):
            raise common.ToolError(f"{path.name} has no body text; its text is in a header or footer, which is not read.")
        return ExtractedDocument(text, text, "docx")
