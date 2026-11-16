"""Tests for plugins/jobkit/src/jk/resumes/extract.py: one fictional resume as txt, md and docx reads the same way;
PDF clean-up, Markdown tables and empty extractions. The docx files are built with zipfile (no binary fixtures)."""
import contextlib
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from jk import common
from jk.common import ToolError
from jk.resumes import extract
from jk.resumes import parse_resume as pr
from jk.resumes import process_resumes as proc
from jk.resumes import resume_data as rd
from tests.resumes.support import JOBS, REGISTRY, ExtractCase, as_docx_body, as_md, as_txt, para, table, write_docx

CONTACT = ["jane@example.com", "555.010.0100", "12345, Exampleville, GA USA"]


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

    def test_grid_table_with_headings_is_read_column_by_column(self):
        grid = ("+------------+------------+\n| Skills     | Tools      |\n+============+============+\n"
                "| - Python   | - Docker   |\n|            |            |\n| - Go       | - Make     |\n+------------+------------+\n")
        out = [line for line in self.md(grid) if line.strip()]
        self.assertEqual(out, ["Skills", "• Python", "• Go", "Tools", "• Docker", "• Make"])


class DocxTests(ExtractCase):
    def docx(self, body: str) -> list[str]:
        return extract.extract(write_docx(self.tmp / "t.docx", body)).text.splitlines()

    def test_tab_becomes_gap_and_list_paragraph_gets_bullet(self):
        self.assertEqual(self.docx(para("Acme\t03/2021 - Present") + para("did a thing", listed=True)),
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


class CorruptPdfTests(unittest.TestCase):
    def test_damaged_pdf_is_a_tool_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "broken.pdf"
            bad.write_text("not a PDF", encoding="utf-8")
            with self.assertRaises(ToolError):
                extract.extract(bad)
            with mock.patch("shutil.which", return_value=None), self.assertRaises(ToolError):
                extract.extract(bad)


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


class EmptyExtractionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def message(self, path: Path) -> str:
        with self.assertRaises(common.ToolError) as ctx:
            extract.extract(path)
        return str(ctx.exception)

    def test_scanned_pdf_says_so(self):
        path = self.tmp / "scan.pdf"
        path.write_bytes(b"%PDF-1.4")
        with mock.patch.object(extract.PdfExtractor, "_reading_order", return_value="  \n"), \
                mock.patch.object(extract.PdfExtractor, "_layout", return_value=""):
            message = self.message(path)
        self.assertIn("scanned image", message)
        self.assertIn("OCR is not supported", message)
        self.assertIn("read visually if the user agrees", message)

    def test_scanned_pdf_asks_for_a_visual_reading(self):
        path = self.tmp / "scan.pdf"
        path.write_bytes(b"%PDF-1.4")
        with mock.patch.object(extract.PdfExtractor, "_reading_order", return_value=""), \
                mock.patch.object(extract.PdfExtractor, "_layout", return_value=""):
            with self.assertRaises(extract.NeedsVisualRead):
                extract.extract(path)

    def test_unreadable_docx_does_not_ask_for_a_visual_reading(self):
        path = self.tmp / "bad.docx"
        path.write_bytes(b"not a zip")
        with self.assertRaises(common.ToolError) as ctx:
            extract.extract(path)
        self.assertNotIsInstance(ctx.exception, extract.NeedsVisualRead)

    def test_docx_with_text_only_in_a_header_says_so(self):
        path = write_docx(self.tmp / "h.docx", "")
        with zipfile.ZipFile(path, "a") as archive:
            archive.writestr("word/header1.xml", '<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                                                 "<w:p><w:r><w:t>Jane Example</w:t></w:r></w:p></w:hdr>")
        self.assertIn("header or footer", self.message(path))

    def test_text_box_in_the_body_is_still_read(self):
        box = ('<w:p><w:r><mc:AlternateContent xmlns:mc="x"><mc:Choice><w:pict><w:txbxContent><w:p><w:r>'
               "<w:t>Boxed text here</w:t></w:r></w:p></w:txbxContent></w:pict></mc:Choice></mc:AlternateContent></w:r></w:p>")
        self.assertEqual(extract.extract(write_docx(self.tmp / "b.docx", box)).text.strip(), "Boxed text here")

    def test_empty_text_file_says_no_text(self):
        path = self.tmp / "e.txt"
        path.write_text("\n  \n", encoding="utf-8")
        self.assertIn("has no text", self.message(path))

    def test_bad_file_is_recorded_and_good_file_still_processed(self):
        resumes = self.tmp / "r"
        resumes.mkdir()
        (resumes / "empty.txt").write_text("", encoding="utf-8")
        (resumes / "good.txt").write_text(as_txt(), encoding="utf-8")
        saved = dict(pr.COMPANIES)
        pr.set_companies(REGISTRY)
        self.addCleanup(lambda: pr.set_companies(saved))
        data = {"companies": {}, "skills": {"groups": {}}, "profile": rd.empty_profile()}
        ledger, unparsed = {}, {}
        text_dir = self.tmp / "out"
        text_dir.mkdir()
        with mock.patch.object(proc, "TEXT_DIR", text_dir), contextlib.redirect_stdout(io.StringIO()):
            bad = proc.process_file(resumes / "empty.txt", resumes, ledger, unparsed, data)
            good = proc.process_file(resumes / "good.txt", resumes, ledger, unparsed, data)
        self.assertEqual((bad, good), ("other", "parsed"))
        self.assertIn("has no text", unparsed["empty.txt"][0])


class PdfCleanTests(unittest.TestCase):
    def test_other_bullet_glyphs_become_one_bullet_and_ligatures_unfold(self):
        pages = extract.clean_pdf_pages("➢ first\n- second\n third\n● kept\n§ kept\nthe ﬁnal ﬂow\n")
        self.assertEqual(pages, ["• first\n• second\n• third\n● kept\n§ kept\nthe final flow\n"])

    def test_repeated_footer_page_number_and_repeated_header_are_removed(self):
        page1 = "Jane Example\nbody one\nConfidential\n"
        page2 = "Jane Example\nbody two\nConfidential\nPage 2 of 2"
        pages = extract.clean_pdf_pages(f"{page1}\f{page2}")
        self.assertEqual(pages[0].split("\n")[0], "Jane Example")
        self.assertNotIn("Jane Example", pages[1])
        self.assertNotIn("Confidential", "".join(pages))
        self.assertNotIn("Page 2", "".join(pages))

    def test_a_one_page_document_keeps_its_last_line(self):
        self.assertEqual(extract.clean_pdf_pages("one\ntwo\n3"), ["one\ntwo\n3"])


class MarkdownTableTests(unittest.TestCase):
    def md(self, text: str) -> list[str]:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.md"
            path.write_text(text, encoding="utf-8")
            return [line for line in extract.extract(path).text.splitlines() if line.strip()]

    def test_grid_layout_table_is_read_column_by_column(self):
        grid = ("+-----------------+-----------------+\n| **Leadership**  | **Technical**   |\n"
                "+=================+=================+\n| - Mentoring     | - Python        |\n"
                "| - Hiring        | - Kubernetes    |\n+-----------------+-----------------+\n")
        self.assertEqual(self.md(grid), ["Leadership", "• Mentoring", "• Hiring", "Technical", "• Python", "• Kubernetes"])

    def test_grid_timeline_row_puts_the_date_after_the_employer(self):
        rule = "+" + "-" * 19 + "+" + "-" * 21 + "+\n"
        grid = rule + "| Northwind Traders | 09/2021 - Present   |\n|" + " " * 19 + "|" + " " * 21 + "|\n" + rule
        self.assertEqual(self.md(grid), ["Northwind Traders   09/2021 - Present"])

    def test_pipe_layout_table_is_read_column_by_column(self):
        table_md = "| Skills | Certifications |\n|---|---|\n| Python | Example Certification |\n"
        self.assertEqual(self.md(table_md), ["Skills", "Python", "Certifications", "Example Certification"])


class SurveyColumnsTests(unittest.TestCase):
    def test_extracted_document_lists_the_pages_read_as_columns(self):
        doc = extract.ExtractedDocument("t", "t", "pdf", (2,))
        self.assertEqual(doc.column_pages, (2,))
        self.assertEqual(extract.ExtractedDocument("t", "t", "md").column_pages, ())
