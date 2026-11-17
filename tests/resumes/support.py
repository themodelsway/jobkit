"""Shared helpers for the resume tests: a small fictional resume in several formats, a rebuildable resume folder,
a pipeline built once from the sample files in `data/`, and stored-record builders. All data is fictional."""
import contextlib
import io
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import Any
from unittest import mock
from xml.sax.saxutils import escape

from jk.resumes import extract
from jk.resumes import parse_resume as pr
from jk.resumes import process_resumes as proc
from jk.resumes import resume_data as rd
from tests.support import HomeCase, HomeClassCase, call

DATA_DIR = Path(__file__).resolve().parent / "data"

# The employers of the fictional resume below, as the parser's registry holds them.
REGISTRY = {
    "acme-corp": ("Acme Corp", r"Acme Corp(?:" + pr.SEP + r"(?P<t>.+))?"),
    "acme-2": ("Acme 2", r"Acme 2"),
}
# The employers of the sample files in `data/`.
DATA_REGISTRY = {**REGISTRY, "acme-3": ("Acme 3", r"Acme 3(?:" + pr.SEP + r"(?P<t>.+))?")}

JOBS = [
    ("Acme Corp", "03/2021 - Present", "Lead Designer",
     ["Cut checkout drop-off by 18% across 7 product flows using usability testing.", "Built a design system with shared prototypes."]),
    ("Acme 2", "01/2015 - 02/2021", "Senior Strategist", ["Moved 40 screens to a shared component library."]),
]
HEAD = ["Jane Example", "Senior Product Designer"]
SKILLS = "Languages: English, Spanish and French"
EXTRA_BULLET = "Reduced build times by 40% with a shared cache."
JD = "Senior Product Designer: prototyping, English, usability testing, design systems, mentor designers, component libraries."


def as_txt() -> str:
    """The fictional resume as plain text."""
    lines = [*HEAD, "SKILLS", f"• {SKILLS}", "WORK EXPERIENCE"]
    for company, dates, title, bullets in JOBS:
        lines += [f"{company}      {dates}", title, *[f"• {b}" for b in bullets]]
    return "\n".join(lines) + "\n"


def para(text: str, listed: bool = False) -> str:
    """A Word paragraph, as a list item when `listed`; a tab in the text becomes a Word tab."""
    runs = "<w:tab/>".join(f"<w:r><w:t>{escape(part)}</w:t></w:r>" for part in text.split("\t"))
    return f"<w:p>{'<w:pPr><w:numPr/></w:pPr>' if listed else ''}{runs}</w:p>"


def table(rows: list[list[list[str]]]) -> str:
    """A Word table from rows of cells of paragraph texts."""
    body = "".join("<w:tr>" + "".join("<w:tc>" + "".join(para(t) for t in cell) + "</w:tc>" for cell in row) + "</w:tr>"
                   for row in rows)
    return f"<w:tbl>{body}</w:tbl>"


def write_docx(path: Path, body: str) -> Path:
    """A minimal .docx holding the given document body, built with zipfile (no binary fixtures)."""
    xml = ('<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/'
           f'wordprocessingml/2006/main"><w:body>{body}</w:body></w:document>')
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", xml)
    return path


def bullet(text: str, metrics: list[str], **extra) -> dict:
    """A minimal stored bullet with its figures."""
    return {"id": text[:8], "text": text, "metrics": metrics, "skills": [], "sources": ["a"], **extra}


def line(text: str, role_start: str | None = None, **extra: Any) -> dict[str, Any]:
    """A stored bullet."""
    return {"id": text[:8], "text": text, "role_start": role_start, "skills": [], "themes": [], "metrics": [],
            "sources": ["a"], **extra}


def role(start: str, end: str | None, title: str) -> dict[str, Any]:
    """A stored role."""
    return {"start": start, "end": end, "titles": [title], "subtitles": [], "clients": [], "sources": ["a"]}


def jd_from_bullets(data: dict) -> str:
    """A job description made of the bullets' own words, so every bullet scores as relevant."""
    return " ".join(b["text"] for c in data["companies"].values() for b in c["bullets"])


class EmployersCase(unittest.TestCase):
    """Parses with the fictional resume's employers registered (and the previous registry restored); no home folder."""

    def setUp(self) -> None:
        super().setUp()
        saved = dict(pr.COMPANIES)
        pr.set_companies(REGISTRY)
        self.addCleanup(pr.set_companies, saved)


class RebuildCase(HomeCase):
    """A temporary resume folder and home; `rebuild()` runs the real build."""

    def setUp(self):
        super().setUp()
        tmp = self.home
        self.resumes, self.text_dir = tmp / "resumes", tmp / "output"
        self.resumes.mkdir()
        saved = dict(pr.COMPANIES)
        pr.set_companies({**REGISTRY, "acme-3": ("Acme 3", r"Acme 3")})
        self.addCleanup(lambda: pr.set_companies(saved))
        self.tmp = tmp
        for patch in (mock.patch.object(proc, "TEXT_DIR", self.text_dir), mock.patch.object(rd, "TEXT_DIR", self.text_dir)):
            patch.start()
            self.addCleanup(patch.stop)

    def write(self, name: str, text: str) -> Path:
        """Write a resume file into the resume folder."""
        path = self.resumes / name
        path.write_text(text, encoding="utf-8")
        return path

    def rebuild(self) -> str:
        """Rebuild the stored resume data from the folder; what the build printed."""
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            proc.build(proc.list_resumes([self.resumes]), self.resumes, force=False)
        return out.getvalue()

    def bullets(self) -> dict[str, list[str]]:
        """{bullet text: sources} over all companies."""
        companies = rd.load_companies()
        return {b["text"]: b["sources"] for c in companies.values() for b in c["bullets"]}


class PipelineCase(HomeClassCase):
    """Resume data merged, curated and written once per class from the two sample files in `data/`."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tmp = cls.home
        saved = dict(pr.COMPANIES)
        pr.set_companies(DATA_REGISTRY)
        data = {"companies": {}, "skills": {"groups": {}}, "profile": rd.empty_profile()}
        text_a = (DATA_DIR / "layout_a.txt").read_text(encoding="utf-8")
        lay_a = (DATA_DIR / "layout_a.layout.txt").read_text(encoding="utf-8")
        text_b = (DATA_DIR / "layout_b.txt").read_text(encoding="utf-8")
        proc.merge_resume(data, "a.pdf", pr.parse_resume(text_a, lay_a))
        proc.merge_resume(data, "b.pdf", pr.parse_resume(text_b, text_b))
        proc.curate_skills(data)
        proc.retag(data)
        proc.apply_curated(data)
        ledger = {"a.pdf": {"mtime": 100.0, "size": 1, "kind": "resume"}, "b.pdf": {"mtime": 200.0, "size": 1, "kind": "resume"},
                  "c.pdf": {"mtime": 50.0, "size": 1, "kind": "other"}}
        proc.write_data(data, ledger, {})
        cls.data = data
        cls._saved = saved

    @classmethod
    def tearDownClass(cls):
        pr.set_companies(cls._saved)
        super().tearDownClass()

    def cli(self, main, *argv):
        """Run a command's `main`; (status, stdout, stderr)."""
        return call(main, *argv)


def as_md() -> str:
    lines = [f"**{HEAD[0]}**", "", HEAD[1], "", "## SKILLS", "", f"- {SKILLS}", "", "## WORK EXPERIENCE", ""]
    for company, dates, title, bullets in JOBS:
        lines += [f"**{company} {dates}**", "", f"# {title}", "", *[f"- {b}" for b in bullets], ""]
    return "\n".join(lines)


def as_docx_body() -> str:
    parts = [para(h) for h in HEAD] + [para("SKILLS"), para(SKILLS, listed=True), para("WORK EXPERIENCE")]
    for company, dates, title, bullets in JOBS:
        parts += [para(f"{company}\t{dates}"), para(title), *[para(b, listed=True) for b in bullets]]
    return "".join(parts)


class ExtractCase(EmployersCase):
    """`EmployersCase` with a scratch folder (`self.tmp`) for resume files."""

    def setUp(self):
        super().setUp()
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def parse_file(self, path: Path) -> dict:
        doc = extract.extract(path)
        return pr.parse_resume(doc.text, doc.layout_text)

    def write(self, name: str, text: str) -> Path:
        path = self.tmp / name
        path.write_text(text, encoding="utf-8")
        return path


def second_resume() -> str:
    """A tailored resume with its own headline, education, certification, project and a different Acme 2 title."""
    text = as_txt().replace("Senior Product Designer\n", "Senior Product Designer\nAccessibility specialist\n")
    return text.replace("Senior Strategist", "People Director") + EXTRAS


EXTRAS = ("\nEDUCATION\nBSc Physics, Example University\nCERTIFICATIONS\n• Example Certified Practitioner\n"
          "PROJECTS\nBuilt a hobby compiler in Rust\n")


def parse_sample(name, layout=None):
    text = (DATA_DIR / f"{name}.txt").read_text(encoding="utf-8")
    lay = (DATA_DIR / f"{layout}.txt").read_text(encoding="utf-8") if layout else text
    return pr.parse_resume(text, lay)
