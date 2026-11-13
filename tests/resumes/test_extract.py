"""Tests for resumes/extract.py: one synthetic resume rendered as txt, md and docx must parse the same way.
The docx files are built here with zipfile (no binary fixtures). Run: uv run python -m unittest discover -s tests -t ."""
import contextlib
import io
import tempfile
import unittest
import zipfile
from pathlib import Path, PureWindowsPath
from unittest import mock
from xml.sax.saxutils import escape

from jk import common
from jk.common import ToolError
from jk.resumes import extract, parse_resume as pr, process_resumes as proc

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



def tiny_pdf(lines):
    """A one-page PDF with the given (x, y, text) lines, built by hand so no PDF tool is needed."""
    stream = "".join(f"BT /F1 11 Tf {x} {y} Td ({text}) Tj ET\n" for x, y, text in lines).encode()
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
            b"/Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"endstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offsets = b"%PDF-1.4\n", []
    for number, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1) + b"".join(b"%010d 00000 n \n" % o for o in offsets)
    return out + b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)


class ExtractCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        saved = (dict(pr.COMPANIES), dict(pr.COMPANY_RES))
        pr.set_companies(REGISTRY)
        self.addCleanup(lambda: pr.set_companies(saved[0]))

    def parse_file(self, path: Path) -> dict:
        doc = extract.extract(path)
        return pr.parse_resume(doc.text, doc.layout_text)

    def write(self, name: str, text: str) -> Path:
        path = self.tmp / name
        path.write_text(text, encoding="utf-8")
        return path


class FormatEquivalenceTests(ExtractCase):
    def test_txt_md_docx_parse_to_the_same_work_history(self):
        files = {"txt": self.write("r.txt", as_txt()), "md": self.write("r.md", as_md()),
                 "docx": write_docx(self.tmp / "r.docx", as_docx_body())}
        results = {fmt: self.parse_file(path) for fmt, path in files.items()}
        for fmt, parsed in results.items():
            with self.subTest(fmt=fmt):
                self.assertTrue(parsed["is_resume"], parsed["problems"])
                self.assertEqual(parsed["problems"], [])
                self.assertEqual([e["company_id"] for e in parsed["work"]], ["acme-corp", "globex"])
                self.assertEqual([(e["start"], e["end"]) for e in parsed["work"]], [("2021-03", None), ("2015-01", "2021-02")])
                self.assertEqual([e["title"] for e in parsed["work"]], ["Lead Engineer", "Senior Engineer"])
                self.assertEqual([e["bullets"] for e in parsed["work"]], [JOBS[0][3], JOBS[1][3]])
        self.assertEqual(results["txt"]["work"], results["md"]["work"])
        self.assertEqual(results["txt"]["work"], results["docx"]["work"])
        self.assertEqual(results["txt"]["skills"], results["docx"]["skills"])

    def test_format_is_reported(self):
        self.assertEqual(extract.extract(self.write("r.txt", as_txt())).format, "txt")
        self.assertEqual(extract.extract(self.write("r.markdown", as_md())).format, "md")
        self.assertEqual(extract.extract(write_docx(self.tmp / "r.docx", as_docx_body())).format, "docx")


class RegistryTests(ExtractCase):
    def test_supported_suffixes(self):
        self.assertEqual(extract.supported_suffixes(), (".docx", ".markdown", ".md", ".pdf", ".txt"))

    def test_unsupported_suffix_names_the_supported_ones(self):
        with self.assertRaises(common.ToolError) as ctx:
            extract.extract(self.tmp / "old.doc")
        self.assertIn("Unsupported resume format '.doc'", str(ctx.exception))
        self.assertIn(".docx", str(ctx.exception))

    def test_suffix_match_ignores_case(self):
        self.assertEqual(extract.extract(self.write("R.TXT", as_txt())).format, "txt")

    def test_lock_and_hidden_files_are_not_resumes(self):
        self.assertTrue(extract.is_resume_file(Path("a/Resume.docx")))
        self.assertFalse(extract.is_resume_file(Path("a/~$Resume.docx")))
        self.assertFalse(extract.is_resume_file(Path("a/.hidden.txt")))
        self.assertFalse(extract.is_resume_file(Path("a/notes.xlsx")))

    def test_new_format_needs_only_a_registered_class(self):
        with mock.patch.dict(extract.EXTRACTORS):
            class RtfLike:
                suffixes = (".rtf",)

                def extract(self, _path):
                    return extract.ExtractedDocument("hello", "", "rtf")

            extract.register(RtfLike)
            self.assertEqual(extract.extract(self.tmp / "x.rtf").format, "rtf")
            self.assertIn(".rtf", extract.supported_suffixes())
        self.assertNotIn(".rtf", extract.supported_suffixes())


class TextTests(ExtractCase):
    def test_normalize_unifies_bullets_and_tabs(self):
        out = extract.normalize("- one\n* two\n1. three\n● four\n\u200bAcme\tPresent\r\n")
        self.assertEqual(out.splitlines(), ["• one", "• two", "• three", "• four", "Acme   Present"])

    def test_date_after_single_space_gets_a_gap_but_bullets_do_not(self):
        out = extract.normalize("Acme Corp 03/2021 - Present\n• Shipped 01/2020 - 02/2021")
        self.assertEqual(out.splitlines(), ["Acme Corp   03/2021 - Present", "• Shipped 01/2020 - 02/2021"])

    def test_contact_lines_are_dropped_but_prose_is_kept(self):
        out = extract.normalize("\n".join([*CONTACT, "Atlanta, GA 30024", "Saved costs, to 50000", "Emailed jane@example.com daily"]))
        self.assertEqual(out.splitlines(), ["Saved costs, to 50000", "Emailed jane@example.com daily"])

    def test_cp1252_fallback(self):
        path = self.tmp / "old.txt"
        path.write_bytes("Café – résumé".encode("cp1252"))
        self.assertEqual(extract.read_text_file(path), "Café – résumé")

    def test_utf8_bom_is_removed(self):
        path = self.tmp / "bom.txt"
        path.write_bytes(b"\xef\xbb\xbfHello")
        self.assertEqual(extract.read_text_file(path), "Hello")


class MarkdownTests(ExtractCase):
    def md(self, text: str) -> list[str]:
        return extract.extract(self.write("t.md", text)).text.splitlines()

    def test_syntax_is_stripped(self):
        out = self.md("## Heading\n\n**bold** and *it* and _it2_ with [link](http://x.y) and `code`\n\n---\n\n1. numbered\n")
        self.assertEqual(out, ["Heading", "", "bold and it and it2 with link and code", "", "• numbered"])

    def test_pandoc_artifacts(self):
        text = ("> **Acme -- Architect\\\n> Client: Bank**\n\nsaved \\$50M \\- done\n\n<!-- -->\n\n"
                "![](media/i.png){width=\"1in\"}\n\n[[jane@example.com]{.underline}](mailto:jane@example.com)\n\n"
                "<jane@example.com>\n\nA---B and C -- D\n")
        out = [line for line in self.md(text) if line.strip()]
        self.assertEqual(out, ["Acme – Architect", "Client: Bank", "saved $50M - done", "A—B and C – D"])

    def test_pipe_table_row_becomes_one_line_and_separator_is_dropped(self):
        out = self.md("| Acme Corp | 03/2021 - Present |\n|---|---|\n| jane@example.com | 12345, Exampleville, GA |\n")
        self.assertEqual([line for line in out if line.strip()], ["Acme Corp   03/2021 - Present"])

    def test_grid_table_keeps_multi_line_cells_separate(self):
        grid = ("+------------+------------+\n| Skills     | Tools      |\n+============+============+\n"
                "| - Python   | - Docker   |\n|            |            |\n| - Go       | - Make     |\n+------------+------------+\n")
        out = [line for line in self.md(grid) if line.strip()]
        self.assertEqual(out, ["Skills   Tools", "• Python", "• Go", "• Docker", "• Make"])


class DocxTests(ExtractCase):
    def docx(self, body: str) -> list[str]:
        return extract.extract(write_docx(self.tmp / "t.docx", body)).text.splitlines()

    def test_tab_becomes_gap_and_list_paragraph_gets_bullet(self):
        self.assertEqual(self.docx(para("Acme\t03/2021 - Present") + para("did a thing", bullet=True)),
                         ["Acme   03/2021 - Present", "• did a thing"])

    def test_single_line_cells_join_and_multi_paragraph_cells_stay_separate(self):
        body = table([[["Acme"], ["03/2021 - Present"]], [["first", "second"], ["third"]]])
        self.assertEqual(self.docx(body), ["Acme   03/2021 - Present", "first", "second", "third"])

    def test_nested_table_is_read_once(self):
        inner = table([[["inner A"], ["inner B"]]])
        outer = f"<w:tbl><w:tr><w:tc>{para('before')}{inner}{para('after')}</w:tc></w:tr></w:tbl>"
        self.assertEqual(self.docx(outer), ["before", "inner A   inner B", "after"])

    def test_contact_block_row_is_dropped_with_its_address(self):
        body = para("kept") + table([[[], ["jane@example.com"]], [[], ["12345, Exampleville, GA USA"]]]) + para("also kept")
        self.assertEqual(self.docx(body), ["kept", "also kept"])

    def test_not_a_docx_is_a_tool_error(self):
        path = self.write("broken.docx", "this is not a zip")
        with self.assertRaises(common.ToolError) as ctx:
            extract.extract(path)
        self.assertIn("broken.docx is not a readable .docx", str(ctx.exception))


class PipelineTests(ExtractCase):
    data: dict = {}

    def run_process(self, path: Path, ledger: dict, unparsed: dict) -> str:
        data = {"companies": {}, "skills": {"groups": {}}, "profile": proc.rd.empty_profile()}
        text_dir = self.tmp / "text"
        text_dir.mkdir(exist_ok=True)
        with mock.patch.object(proc, "TEXT_DIR", text_dir), contextlib.redirect_stdout(io.StringIO()):
            outcome = proc.process_file(path, self.tmp, ledger, unparsed, data)
        self.data = data
        return outcome

    def test_docx_is_processed_and_raw_text_name_keeps_the_suffix(self):
        path = write_docx(self.tmp / "me.docx", as_docx_body())
        ledger, unparsed = {}, {}
        self.assertEqual(self.run_process(path, ledger, unparsed), "parsed")
        self.assertEqual(ledger["me.docx"]["kind"], "resume")
        self.assertEqual(sorted(self.data["companies"]), ["acme-corp", "globex"])
        self.assertTrue((self.tmp / "text" / "me.docx.txt").is_file())
        self.assertEqual(self.run_process(path, ledger, unparsed), "unchanged")

    def test_text_name(self):
        self.assertEqual(proc.text_name("a/b c.pdf"), "a__b_c.txt")
        self.assertEqual(proc.text_name("a/b c.docx"), "a__b_c.docx.txt")

    def test_keys_use_forward_slashes_and_raw_text_names_have_no_separator(self):
        root = Path("/resumes")
        self.assertEqual(proc.rel(root / "2026" / "me.pdf", root), "2026/me.pdf")
        for key in ("2026/me.pdf", "2026\\me.pdf", "C:\\x\\me.pdf"):
            name = proc.text_name(key)
            self.assertFalse({"/", "\\", ":"} & set(name), name)
        self.assertEqual(proc.text_name("2026\\me.pdf"), proc.text_name("2026/me.pdf"))

    def test_windows_style_relative_path_gives_the_same_key(self):
        self.assertEqual(PureWindowsPath("C:/r/2026/me.pdf").relative_to(PureWindowsPath("C:/r")).as_posix(),
                         "2026/me.pdf")

    def test_unreadable_file_is_recorded_and_does_not_stop_the_run(self):
        path = self.write("broken.docx", "not a zip")
        ledger, unparsed = {}, {}
        self.assertEqual(self.run_process(path, ledger, unparsed), "other")
        self.assertEqual(ledger["broken.docx"]["kind"], "other")
        self.assertIn("not a readable .docx", unparsed["broken.docx"][0])

    def test_list_resumes_finds_every_format_and_skips_lock_files(self):
        for name in ("a.pdf", "b.docx", "c.md", "d.txt", "~$b.docx", "e.xlsx", ".f.txt"):
            (self.tmp / name).write_bytes(b"x")
        found = sorted(p.name for p in proc.list_resumes([self.tmp]))
        self.assertEqual(found, ["a.pdf", "b.docx", "c.md", "d.txt"])




class CorruptPdfTests(unittest.TestCase):
    def test_damaged_pdf_is_a_tool_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "broken.pdf"
            bad.write_text("not a PDF", encoding="utf-8")
            with self.assertRaises(ToolError):
                extract.extract(bad)
            with mock.patch("shutil.which", return_value=None), self.assertRaises(ToolError):
                extract.extract(bad)


if __name__ == "__main__":
    unittest.main()


class PdfWithoutPopplerTests(unittest.TestCase):
    def test_layout_text_is_not_empty_and_keeps_the_date_apart(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "me.pdf"
            path.write_bytes(tiny_pdf([(50, 700, "Acme Corp"), (420, 700, "01/2020 - Present"),
                                       (50, 680, "Senior Engineer")]))
            with mock.patch("jk.resumes.extract.shutil.which", return_value=None):
                doc = extract.extract(path)
        self.assertIn("Senior Engineer", doc.text)
        self.assertRegex(doc.layout_text, r"Acme Corp {2,}01/2020 - Present")
