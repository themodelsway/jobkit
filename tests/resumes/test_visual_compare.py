"""Comparing a visual reading of a PDF with what the parser read from it. All data is fictional.
Run: uv run python -m unittest discover -s tests -t ."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from jk import common
from jk.resumes import extract, parse_resume as pr, visual, visual_compare as vc

TEXT = ("Alex Example\n\nWork Experience\nNorthwind Traders   09/2021 - Present\nSenior Engineer\n"
        "• Led migration of 40 services to Kubernetes, cutting hosting cost by 30%.\n"
        "• Designed an event-driven order pipeline handling 2 million messages a day.\n"
        "Skills: Python, Kubernetes\nEducation: BS Computer Science\n")
READING = {"employers": [{"name": "Northwind Traders", "title": "Senior Engineer", "start": "2021-09", "end": None,
                          "bullets": ["Led migration of 40 services to Kubernetes, cutting hosting cost by 30%.",
                                      "Designed an event-driven order pipeline handling 2 million messages a day."]}],
           "skills": ["Python", "Kubernetes"], "certifications": [], "education": ["BS Computer Science"], "summary": ""}


def parsed(text: str = TEXT) -> pr.Resume:
    saved = dict(pr.COMPANIES)
    found = pr.discover_companies(text)
    pr.set_companies({k: (v, pr.re.escape(v) + rf"(?:{pr.SEP}(?P<t>.+))?") for k, v in found.items()})
    try:
        result = pr.parse_resume(text, text)
    finally:
        pr.set_companies(saved)
    assert result["is_resume"] is True
    return result


class CompareTests(unittest.TestCase):
    def setUp(self):
        saved = dict(pr.COMPANIES)
        found = pr.discover_companies(TEXT)
        pr.set_companies({k: (v, pr.re.escape(v)) for k, v in found.items()})
        self.addCleanup(pr.set_companies, saved)

    def differences(self, **change) -> list[vc.Difference]:
        reading = json.loads(json.dumps(READING))
        for key, value in change.items():
            reading[key] = value
        return vc.compare(parsed(), reading)

    def test_equal_readings_agree(self):
        self.assertEqual(self.differences(), [])

    def test_a_bullet_only_the_visual_reading_has_is_missing_from_the_parser(self):
        bullets = [*READING["employers"][0]["bullets"], "Cut build time from 40 to 12 minutes."]
        found = self.differences(employers=[{**READING["employers"][0], "bullets": bullets}])
        self.assertEqual([(d.kind, d.visual) for d in found], [("missing", "Cut build time from 40 to 12 minutes.")])

    def test_a_bullet_only_the_parser_has_is_extra(self):
        found = self.differences(employers=[{**READING["employers"][0], "bullets": READING["employers"][0]["bullets"][:1]}])
        self.assertEqual([d.kind for d in found], ["extra"])

    def test_a_reworded_bullet_is_different_and_both_are_shown(self):
        bullets = ["Led migration of 41 services to Kubernetes, cutting hosting cost by 30%.",
                   READING["employers"][0]["bullets"][1]]
        found = self.differences(employers=[{**READING["employers"][0], "bullets": bullets}])
        self.assertEqual([d.kind for d in found], ["different"])
        self.assertIn("40 services", found[0].parsed)
        self.assertIn("41 services", found[0].visual)

    def test_dates_and_titles_are_compared(self):
        found = self.differences(employers=[{**READING["employers"][0], "start": "2020-09", "title": "Staff Engineer"}])
        self.assertEqual({d.section.rsplit(" ", 1)[1] for d in found}, {"title", "start"})

    def test_an_employer_the_parser_missed_is_reported(self):
        extra = {"name": "Fabrikam Inc", "title": "Engineer", "start": "2018-01", "end": "2021-08", "bullets": ["Built a queue."]}
        found = self.differences(employers=[*READING["employers"], extra])
        self.assertEqual([(d.section, d.kind) for d in found], [("employers", "missing")])

    def test_skills_education_and_certifications(self):
        found = self.differences(skills=["Python", "Terraform"], certifications=["Example Certification"], education=[])
        self.assertEqual(sorted((d.section, d.kind) for d in found),
                         [("certifications", "missing"), ("education", "extra"), ("skills", "extra"), ("skills", "missing")])

    def test_report_names_both_sides(self):
        text = vc.format_report("a.pdf", [vc.Difference("skills", "missing", "", "Terraform")])
        self.assertIn("[missing] skills", text)
        self.assertIn("parser: (nothing)", text)
        self.assertIn("visual: Terraform", text)
        self.assertIn("agree", vc.format_report("a.pdf", []))

    def test_a_bad_reading_is_a_clear_error(self):
        for raw in ("not json", "[]", '{"employers": [{"name": 3}]}', '{"employers": [], "skills": [1]}'):
            with self.assertRaises(common.ToolError, msg=raw):
                vc.read_reading(raw)
        self.assertIn("employers", json.loads(vc.READING_SCHEMA))


class CommandTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.pdf = self.tmp / "r.pdf"
        self.pdf.write_bytes(b"%PDF-1.4")
        self.transcript = self.tmp / "t.txt"
        self.files = {self.pdf: ("2026/r.pdf", "t.txt")}
        saved = dict(pr.COMPANIES)
        self.addCleanup(pr.set_companies, saved)
        for patcher in (mock.patch.multiple(extract.PdfExtractor, _reading_order=mock.Mock(return_value=TEXT),
                                            _layout=mock.Mock(return_value=TEXT)),
                        mock.patch.object(visual, "VISUAL_DIR", self.tmp)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_compare(self, reading: dict) -> str:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            visual.cmd_compare(self.files, "r.pdf", json.dumps(reading))
        return out.getvalue()

    def test_compare_reads_the_pdf_and_reports(self):
        self.assertIn("agree", self.run_compare(READING))
        changed = {**READING, "skills": ["Python", "Terraform"]}
        self.assertIn("2 difference(s)", self.run_compare(changed))

    def test_an_unknown_pdf_is_an_error(self):
        with self.assertRaises(common.ToolError):
            visual.locate(self.files, "other.pdf")

    def test_a_confirmed_transcript_replaces_a_pdf_the_parser_could_read(self):
        corrected = TEXT.replace("Python, Kubernetes", "Python, Kubernetes, Terraform")
        self.transcript.write_text(corrected, encoding="utf-8")
        self.assertEqual(visual.read_document(self.pdf, self.transcript).text, TEXT)       # not confirmed: ignored
        visual.confirm(self.pdf, self.transcript)
        document = visual.read_document(self.pdf, self.transcript)
        self.assertEqual((document.text, document.format), (corrected, "visual"))
        self.assertIn("agree", self.run_compare({**READING, "skills": ["Python", "Kubernetes", "Terraform"]}))
        self.pdf.write_bytes(b"%PDF-1.4 changed")                                           # the PDF changed: back to the text
        self.assertEqual(visual.read_document(self.pdf, self.transcript).text, TEXT)

    def test_text_shows_what_the_parser_works_from(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            visual.cmd_text(self.files, "r.pdf")
        self.assertIn("Northwind Traders", out.getvalue())

    def test_compare_says_where_to_save_agreed_corrections(self):
        out = self.run_compare({**READING, "skills": ["Python", "Terraform"]})
        self.assertIn("save the full corrected text as", out)
        self.assertIn("visual confirm r.pdf", out)

    def test_cli_schema_prints_the_shape(self):
        from jk.resumes import process_resumes as proc  # pylint: disable=import-outside-toplevel
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            proc.cmd_visual(proc.build_parser().parse_args(["visual", "schema"]))
        self.assertIn('"employers"', out.getvalue())
