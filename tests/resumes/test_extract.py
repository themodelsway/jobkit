"""Sample resume helpers shared by the resume tests: one synthetic resume as plain text or as a docx body.
The docx files are built here with zipfile (no binary fixtures)."""
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from jobkit.resumes import parse_resume as pr

REGISTRY = {
    "acme-corp": ("Acme Corp", r"Acme Corp(?:" + pr.SEP + r"(?P<t>.+))?"),
    "globex": ("Globex Inc", r"Globex Inc"),
}
JOBS = [
    ("Acme Corp", "03/2021 - Present", "Lead Engineer",
     ["Cut page load time by 30% across 12 services using caching.", "Built a search service on PostgreSQL."]),
    ("Globex Inc", "01/2015 - 02/2021", "Senior Engineer", ["Moved 40 services to a shared build system."]),
]
HEAD = ["Jane Example", "Senior Software Engineer"]
SKILLS = "Languages: Python, TypeScript and Go"
CONTACT = ["jane@example.com", "555.010.0100", "12345, Exampleville, GA USA"]


def as_txt() -> str:
    lines = [*HEAD, "SKILLS", f"• {SKILLS}", "WORK EXPERIENCE"]
    for company, dates, title, bullets in JOBS:
        lines += [f"{company}      {dates}", title, *[f"• {b}" for b in bullets]]
    return "\n".join(lines) + "\n"


def as_md() -> str:
    lines = [f"**{HEAD[0]}**", "", HEAD[1], "", "## SKILLS", "", f"- {SKILLS}", "", "## WORK EXPERIENCE", ""]
    for company, dates, title, bullets in JOBS:
        lines += [f"**{company} {dates}**", "", f"# {title}", "", *[f"- {b}" for b in bullets], ""]
    return "\n".join(lines)


def para(text: str, bullet: bool = False) -> str:
    runs = "<w:tab/>".join(f"<w:r><w:t>{escape(part)}</w:t></w:r>" for part in text.split("\t"))
    return f"<w:p>{'<w:pPr><w:numPr/></w:pPr>' if bullet else ''}{runs}</w:p>"


def table(rows: list[list[list[str]]]) -> str:
    """Rows of cells of paragraph texts."""
    body = "".join("<w:tr>" + "".join("<w:tc>" + "".join(para(t) for t in cell) + "</w:tc>" for cell in row) + "</w:tr>"
                   for row in rows)
    return f"<w:tbl>{body}</w:tbl>"


def write_docx(path: Path, body: str) -> Path:
    xml = ('<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/'
           f'wordprocessingml/2006/main"><w:body>{body}</w:body></w:document>')
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", xml)
    return path


def as_docx_body() -> str:
    parts = [para(h) for h in HEAD] + [para("SKILLS"), para(SKILLS, bullet=True), para("WORK EXPERIENCE")]
    for company, dates, title, bullets in JOBS:
        parts += [para(f"{company}\t{dates}"), para(title), *[para(b, bullet=True) for b in bullets]]
    return "".join(parts)
