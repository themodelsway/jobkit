"""Tests for plugins/jobkit/src/jk/resumes/visual.py: the parser asks before a visual reading, a transcript is used only
once it is confirmed for the PDF as it is, and the `process-resumes visual` commands. All data is fictional."""
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from jk import common
from jk.resumes import extract, visual
from jk.resumes import parse_resume as pr
from jk.resumes import process_resumes as proc
from jk.resumes import visual_render as vr
from tests.resumes.visual.support import READING, TEXT

TRANSCRIPT = ("Alex Example\n\nWORK EXPERIENCE\nAcme 4   09/2021 - Present\nSenior Strategist\n"
              "• Led migration of 40 services to Kubernetes, cutting hosting cost by 30%.\n")


class VisualTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.pdf = self.tmp / "scan.pdf"
        self.pdf.write_bytes(b"%PDF-1.4")
        self.transcript = self.tmp / "visual" / "scan.txt"
        patcher = mock.patch.multiple(extract.PdfExtractor, _reading_order=mock.Mock(return_value=""),
                                      _layout=mock.Mock(return_value=""))
        patcher.start()
        self.addCleanup(patcher.stop)

    def save(self, text: str = TRANSCRIPT) -> None:
        self.transcript.parent.mkdir(exist_ok=True)
        self.transcript.write_text(text, encoding="utf-8")

    def replace_pdf(self, content: bytes) -> None:
        self.pdf.write_bytes(content)
        later = self.transcript.stat().st_mtime + 10 if self.transcript.exists() else 0
        os.utime(self.pdf, (later, later))                       # the new PDF is newer than any transcript

    def test_list_shows_the_home_folder_as_a_tilde(self):
        home = Path.home()
        item = {"key": "scan.pdf", "state": next(iter(visual.STATE_TEXT)), "reason": f"cannot read {home}/r/scan.pdf",
                "pdf": f"{home}/r/scan.pdf", "transcript": f"{home}/.jobkit/output/visual/scan.txt"}
        out = io.StringIO()
        with mock.patch.object(visual, "VISUAL_DIR", self.tmp / "visual"), contextlib.redirect_stdout(out):
            visual.cmd_list([item])
        self.assertNotIn(str(home), out.getvalue())
        self.assertIn("~/r/scan.pdf", out.getvalue())

    def test_without_a_transcript_the_error_is_raised(self):
        with self.assertRaises(extract.NeedsVisualRead):
            visual.read_document(self.pdf, self.transcript)

    def test_an_empty_transcript_does_not_count(self):
        self.save("  \n")
        self.assertEqual(visual.state(self.pdf, self.transcript), "none")

    def test_an_unconfirmed_transcript_is_not_used(self):
        self.save()
        self.assertEqual(visual.state(self.pdf, self.transcript), "unconfirmed")
        with self.assertRaises(extract.NeedsVisualRead) as ctx:
            visual.read_document(self.pdf, self.transcript)
        self.assertIn("not been confirmed", str(ctx.exception))

    def test_a_confirmed_transcript_is_used_in_place_of_the_pdf_text(self):
        self.save()
        visual.confirm(self.pdf, self.transcript)
        doc = visual.read_document(self.pdf, self.transcript)
        self.assertEqual((doc.text, doc.format), (TRANSCRIPT, "visual"))

    def test_confirm_needs_a_transcript(self):
        with self.assertRaises(common.ToolError):
            visual.confirm(self.pdf, self.transcript)

    def test_an_edit_made_before_the_pdf_was_replaced_is_not_accepted_for_the_new_pdf(self):
        self.save()
        visual.confirm(self.pdf, self.transcript)
        self.save(TRANSCRIPT + "• Correction to the old scan.\n")            # edited, for the old scan
        self.replace_pdf(b"%PDF-1.4 another scan")
        self.assertEqual(visual.state(self.pdf, self.transcript), "stale")
        with self.assertRaises(extract.NeedsVisualRead) as ctx:
            visual.read_document(self.pdf, self.transcript)
        self.assertIn("earlier version", str(ctx.exception))

    def test_confirming_again_makes_the_transcript_fresh_for_the_new_pdf(self):
        self.save()
        visual.confirm(self.pdf, self.transcript)
        self.replace_pdf(b"%PDF-1.4 another scan")
        visual.confirm(self.pdf, self.transcript)
        self.assertEqual(visual.state(self.pdf, self.transcript), "fresh")

    def test_pending_lists_the_pdf_with_its_key_and_transcript_path(self):
        found = visual.pending([self.pdf], {self.pdf: ("2026/scan.pdf", "scan.txt")})
        self.assertEqual([(item["key"], item["state"]) for item in found], [("2026/scan.pdf", "none")])
        self.assertTrue(found[0]["transcript"].endswith("scan.txt"))

    def test_a_pdf_that_reads_fine_is_not_pending(self):
        with mock.patch.object(extract, "extract", return_value=extract.ExtractedDocument("t", "t", "pdf")):
            self.assertEqual(visual.pending([self.pdf], {self.pdf: ("scan.pdf", "scan.txt")}), [])

    def test_confirm_command_picks_one_pdf_by_key_or_name(self):
        self.save()
        files = {self.pdf: ("2026/scan.pdf", "scan.txt")}
        with mock.patch.object(visual, "VISUAL_DIR", self.transcript.parent):
            visual.cmd_confirm(files, "scan.pdf")
            self.assertEqual(visual.state(self.pdf, self.transcript), "fresh")
            for name in ("other.pdf", "scan"):
                with self.assertRaises(common.ToolError):
                    visual.cmd_confirm(files, name)

    def test_different_paths_get_different_transcript_names(self):
        keys = ["a/b.pdf", "a__b.pdf", "a b.pdf", "a_b.pdf"]
        self.assertEqual(len({proc.transcript_name(key) for key in keys}), 4)

    def test_process_file_follows_the_whole_approval_flow(self):
        ledger, unparsed = {}, {}

        def run() -> str:
            return proc.process_file(self.pdf, self.tmp, ledger, unparsed, mock.MagicMock())
        with mock.patch.object(proc, "transcript_for", return_value=self.transcript), \
                mock.patch.object(proc, "TEXT_DIR", self.tmp), mock.patch.object(proc, "merge_resume"):
            self.assertEqual(run(), "other")                                  # asks first
            self.assertIn("read visually", unparsed["scan.pdf"][0])
            self.assertEqual(run(), "unchanged")
            self.save()
            self.assertEqual(run(), "other")                                  # saved, not confirmed: still not used
            visual.confirm(self.pdf, self.transcript)
            self.assertEqual(run(), "parsed")
            self.assertEqual(run(), "unchanged")
            self.replace_pdf(b"%PDF-1.4 another scan")                        # another scan of the same resume
            self.assertEqual(run(), "other")
            self.assertIn("earlier version", unparsed["scan.pdf"][0])
            self.save()                                                       # same words, saved again
            visual.confirm(self.pdf, self.transcript)
            self.assertEqual(run(), "parsed")                                 # approved again: read, though text is equal
            self.assertEqual(run(), "unchanged")
            self.assertNotIn("earlier version", str(unparsed))                # the rejection is gone from the report


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
        self.assertIn("Acme 4", out.getvalue())

    def test_compare_says_where_to_save_agreed_corrections(self):
        out = self.run_compare({**READING, "skills": ["Python", "Terraform"]})
        self.assertIn("save the full corrected text as", out)
        self.assertIn("visual confirm r.pdf", out)

    def test_a_correction_that_loses_work_bullets_is_not_confirmed(self):
        scrambled = TEXT.replace("Acme 4   09/2021 - Present\nSenior Strategist\n", "").replace(
            "Skills:", "Acme 4   09/2021 - Present\nSenior Strategist\nSkills:")
        self.transcript.write_text(scrambled, encoding="utf-8")
        with self.assertRaises(common.ToolError) as caught:
            visual.cmd_confirm(self.files, "r.pdf")
        self.assertIn("--layout", str(caught.exception))
        self.assertEqual(visual.state(self.pdf, self.transcript), "unconfirmed")
        self.transcript.write_text(TEXT.replace("Python, Kubernetes", "Python, Terraform"), encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            visual.cmd_confirm(self.files, "r.pdf")
        self.assertEqual(visual.state(self.pdf, self.transcript), "fresh")

    def use_pdf_text(self, text: str) -> None:
        for name in ("_reading_order", "_layout"):
            patcher = mock.patch.object(extract.PdfExtractor, name, mock.Mock(return_value=text))
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_an_agreed_removal_of_a_duplicate_bullet_is_confirmed_and_recorded(self):
        bullet = READING["employers"][0]["bullets"][0]
        self.use_pdf_text(TEXT.replace("Skills:", f"• {bullet}\nSkills:"))
        self.transcript.write_text(TEXT, encoding="utf-8")
        with self.assertRaises(common.ToolError) as caught:
            visual.cmd_confirm(self.files, "r.pdf")
        self.assertIn(bullet, str(caught.exception))
        self.assertIn("--remove", str(caught.exception))
        with self.assertRaises(common.ToolError):
            visual.cmd_confirm(self.files, "r.pdf", ["A bullet nobody wrote."])
        self.assertEqual(visual.state(self.pdf, self.transcript), "unconfirmed")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            visual.cmd_confirm(self.files, "r.pdf", [bullet])
        self.assertEqual(visual.state(self.pdf, self.transcript), "fresh")
        self.assertIn("1 agreed removal", out.getvalue())
        self.assertEqual(self.tmp.joinpath("t.txt.removed").read_text(encoding="utf-8"), bullet + "\n")

    def test_a_bullet_moved_to_another_employer_is_a_loss_though_totals_agree(self):
        two_jobs = TEXT.replace("Skills:", "Acme 5   01/2018 - 08/2021\nEngineer\n• Built a queue for billing.\nSkills:")
        self.use_pdf_text(two_jobs)
        moved = two_jobs.replace("• Built a queue for billing.\n", "").replace(
            "• Led migration", "• Wrote an onboarding guide for new staff.\n• Led migration")
        self.transcript.write_text(moved, encoding="utf-8")
        with self.assertRaises(common.ToolError) as caught:
            visual.cmd_confirm(self.files, "r.pdf")
        self.assertIn("Built a queue for billing.", str(caught.exception))

    def test_a_reworded_bullet_and_an_agreed_role_removal(self):
        two_jobs = TEXT.replace("Skills:", "Acme 5   01/2018 - 08/2021\nEngineer\n• Built a queue for billing.\nSkills:")
        self.use_pdf_text(two_jobs)
        self.transcript.write_text(TEXT.replace("40 services", "41 services"), encoding="utf-8")
        with self.assertRaises(common.ToolError) as caught:
            visual.cmd_confirm(self.files, "r.pdf")
        self.assertIn("Acme 5 2018-01", str(caught.exception))
        self.assertNotIn("41 services", str(caught.exception))
        with contextlib.redirect_stdout(io.StringIO()):
            visual.cmd_confirm(self.files, "r.pdf", ["Acme 5 2018-01"])
        self.assertEqual(visual.state(self.pdf, self.transcript), "fresh")

    def test_layout_text_can_be_printed(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            visual.cmd_text(self.files, "r.pdf", layout=True)
        self.assertIn("Acme 4", out.getvalue())

    def test_cli_schema_prints_the_shape(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            proc.cmd_visual(proc.build_parser().parse_args(["visual", "schema"]))
        self.assertIn('"employers"', out.getvalue())


class ConfirmClearsImagesTests(unittest.TestCase):
    def test_confirming_the_transcript_removes_its_page_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = root / "scan.pdf"
            pdf.write_bytes(b"%PDF-1.4")
            transcript = root / "visual" / "scan.txt"
            transcript.parent.mkdir()
            transcript.write_text("Alex Example\n", encoding="utf-8")
            pages = root / "pages"
            (pages / "scan").mkdir(parents=True)
            (pages / "scan" / "page-1.png").write_bytes(b"png")
            with (mock.patch.object(vr, "PAGES_DIR", pages), mock.patch.object(visual, "VISUAL_DIR", transcript.parent)):
                visual.cmd_confirm({pdf: ("scan.pdf", "scan.txt")}, "scan.pdf")
            self.assertFalse((pages / "scan").exists())
