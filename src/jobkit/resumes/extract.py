"""Turn a resume file (pdf, docx, md, txt) into text the parser understands.

One extractor per file format, found by suffix (strategy + registry). The rest of the pipeline calls only
`extract(path)` and gets an `ExtractedDocument` back; it never learns which format the file was.

  from jobkit.resumes import extract
  doc = extract.extract(Path("resume.docx"))
  parse_resume(doc.text, doc.layout_text)

To support a new format, write a class with `suffixes` and `extract()` and decorate it with `@register`.
Standard library only; PDF uses poppler's `pdftotext` when it is installed and `pypdf` otherwise.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, Final, Protocol
from xml.etree import ElementTree

from jobkit import common

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
MAX_CONTACT_BLOCK: Final[int] = 6
TRAILING_DATE_RE: Final = re.compile(r"(?<=\S)[ ]+(\d{2}/\d{4}\s*[–—-]\s*(?:\d{2}/\d{4}|Present|Current))\s*$", re.I)
W: Final[str] = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
DOCX_BODY: Final[str] = "word/document.xml"
DOCX_SIDE_PART_RE: Final = re.compile(r"word/(?:header|footer)\d*\.xml")
MIN_PDF_CHARS: Final[int] = 20             # fewer letters than this in a whole PDF means there is no text layer


@dataclass(frozen=True)
class ExtractedDocument:
    """What an extractor hands to the parser."""

    text: str            # reading-order text
    layout_text: str     # text keeping the original positions; the same text for formats without a layout
    format: str          # "pdf", "docx", "md" or "txt"


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
        raise common.ToolError(f"{path.name} has no text layer: it looks like a scanned image, and OCR is not supported. "
                               "Export a text PDF or use docx/txt/md.")
    if letters == 0:
        raise common.ToolError(f"{path.name} has no text.")
    return doc


# ---------------------------------------------------------------- shared text clean-up

def normalize(text: str) -> str:
    """Common clean-up for non-PDF text: newlines, zero-width characters, non-breaking spaces, bullet glyphs.

    Every list marker (`-`, `*`, `1.`, `●` ...) becomes `•` so the parser sees one bullet style. Lines that hold
    only an email address, phone number, LinkedIn address or postal address are dropped: documents often carry a floating contact
    block, and it would otherwise be glued onto the bullet above it and end up in the resume data.
    """
    text = text.translate(ZERO_WIDTH).replace("\xa0", " ").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]*\t[ \t]*", GAP, text)
    text = "\n".join(line for line in text.split("\n") if not CONTACT_LINE_RE.match(line))
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


def row_lines(cells: list[list[str]]) -> list[str]:
    """Lines for one table row, each cell given as its list of non-blank lines. A row of single-line cells (a title
    beside its dates) becomes one line joined by GAP; a row with a multi-line cell (a page laid out as a table)
    keeps every line, cell after cell. A row with a contact block (a short cell holding an email or phone line)
    loses all its short cells, so the address beside the email goes too."""
    if any(_is_contact_block(cell) for cell in cells):
        cells = [cell for cell in cells if len(cell) > MAX_CONTACT_BLOCK]
    if all(len(cell) <= 1 for cell in cells):
        line = GAP.join(line.strip() for cell in cells for line in cell)
        return [line] if line else []
    return [line for cell in cells for line in cell]


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
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    return list(PdfReader(path).pages)


@register
class PdfExtractor:
    """PDF via poppler: `pdftotext` for reading order, `pdftotext -layout` for positions; pypdf (reading order and
    its own layout mode) when poppler is missing, as on most Windows computers."""

    suffixes: ClassVar[tuple[str, ...]] = (".pdf",)

    def extract(self, path: Path) -> ExtractedDocument:
        """Reading-order text plus layout text (from pypdf's layout mode without poppler)."""
        return ExtractedDocument(self._reading_order(path), self._layout(path), "pdf")

    @staticmethod
    def _reading_order(path: Path) -> str:
        if shutil.which("pdftotext"):
            return subprocess.run(["pdftotext", str(path), "-"], capture_output=True, text=True, check=True).stdout
        return "\n\n".join(page.extract_text() or "" for page in _pypdf_pages(path))

    @staticmethod
    def _layout(path: Path) -> str:
        if not shutil.which("pdftotext"):
            return "\n\n".join(page.extract_text(extraction_mode="layout") or "" for page in _pypdf_pages(path))
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


def _pipe_row(line: str) -> str | None:
    """A pipe-table row as cells joined by GAP; None for a row with a contact cell; other lines unchanged."""
    match = MD_TABLE_ROW_RE.match(line)
    if not match:
        return line
    cells = [cell.strip() for cell in match[1].split("|") if cell.strip()]
    if any(CONTACT_LINE_RE.match(cell) for cell in cells):
        return None
    return GAP.join(cells)


def _is_pipe_rule(line: str) -> bool:
    """True for the |---|---| separator row of a pipe table."""
    match = MD_TABLE_ROW_RE.match(line)
    return bool(match and MD_TABLE_RULE_RE.match(match[1]))


def _grid_cuts(rule: str) -> list[int]:
    """Column boundaries of a grid table: the positions of '+' in a `+----+----+` rule."""
    return [i for i, char in enumerate(rule.rstrip()) if char == "+"]


def _grid_row(lines: list[str], cuts: list[int]) -> list[str]:
    """One grid-table row (its physical lines between two rules) as lines, via `row_lines`."""
    cells: list[list[str]] = [[] for _ in range(len(cuts) - 1)]
    for line in lines:
        for column, (start, end) in enumerate(zip(cuts, cuts[1:], strict=False)):
            part = line[start + 1:end].strip()
            if part:
                cells[column].append(part)
    return row_lines(cells)


def _grid_tables(lines: list[str]) -> list[str]:
    """Replace each pandoc grid table (`+---+` rules with `|` rows) by the lines of its rows."""
    out: list[str] = []
    i = 0
    while i < len(lines):
        if not MD_GRID_RULE_RE.match(lines[i]):
            out.append(lines[i])
            i += 1
            continue
        cuts = _grid_cuts(lines[i])
        row: list[str] = []
        i += 1
        while i < len(lines) and lines[i][:1] in ("+", "|"):
            if MD_GRID_RULE_RE.match(lines[i]):
                out += _grid_row(row, cuts)
                row = []
            else:
                row.append(lines[i])
            i += 1
        out += _grid_row(row, cuts) if row else []
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
        rows = (_pipe_row(line) for line in text.splitlines())
        text = normalize("\n".join(row for row in rows if row is not None))
        return ExtractedDocument(text, text, "md")


# ---------------------------------------------------------------- docx

def _paragraph_text(paragraph: ElementTree.Element) -> str:
    """Text of one w:p in document order: tabs become GAP, line breaks newlines; list paragraphs get a bullet."""
    parts: list[str] = []
    for node in paragraph.iter():
        if node.tag == f"{W}t":
            parts.append(node.text or "")
        elif node.tag == f"{W}tab":
            parts.append(GAP)
        elif node.tag in (f"{W}br", f"{W}cr"):
            parts.append("\n")
    text = "".join(parts)
    in_list = paragraph.find(f"{W}pPr/{W}numPr") is not None
    return f"{BULLET} {text.lstrip()}" if in_list and text.strip() and not text.lstrip().startswith(BULLET) else text


def _table_lines(table: ElementTree.Element) -> Iterator[str]:
    """Lines of a table, row by row (see `row_lines`); nested tables are read recursively."""
    for row in table.findall(f"{W}tr"):
        yield from row_lines([[line for line in docx_lines(cell) if line.strip()] for cell in row.findall(f"{W}tc")])


def docx_lines(body: ElementTree.Element) -> Iterator[str]:
    """Lines of a body, table cell or content control: paragraphs and tables in order, nested tables included."""
    for child in body:
        if child.tag == f"{W}p":
            yield from _paragraph_text(child).split("\n")
        elif child.tag == f"{W}tbl":
            yield from _table_lines(child)
        elif child.tag == f"{W}sdt":                       # content control wrapping paragraphs
            content = child.find(f"{W}sdtContent")
            if content is not None:
                yield from docx_lines(content)


def _side_text(path: Path) -> bool:
    """True when a docx header or footer part holds any text."""
    with zipfile.ZipFile(path) as archive:
        parts = [n for n in archive.namelist() if DOCX_SIDE_PART_RE.fullmatch(n)]
        return any(node.text and node.text.strip() for n in parts
                   for node in ElementTree.fromstring(archive.read(n)).iter(f"{W}t"))


@register
class DocxExtractor:
    """Word .docx, read straight from the zip (no third-party package). Headers and footers are ignored."""

    suffixes: ClassVar[tuple[str, ...]] = (".docx",)

    def extract(self, path: Path) -> ExtractedDocument:
        """Body paragraphs and tables as text; the same text serves as layout text (tabs keep dates apart)."""
        try:
            with zipfile.ZipFile(path) as archive:
                root = ElementTree.fromstring(archive.read(DOCX_BODY))
        except (zipfile.BadZipFile, KeyError, ElementTree.ParseError) as error:
            raise common.ToolError(f"{path.name} is not a readable .docx file ({error}).") from error
        body = root.find(f"{W}body")
        text = normalize("\n".join(docx_lines(body if body is not None else root)))
        if not text.strip() and _side_text(path):
            raise common.ToolError(f"{path.name} has no body text; its text is in a header or footer, which is not read.")
        return ExtractedDocument(text, text, "docx")
