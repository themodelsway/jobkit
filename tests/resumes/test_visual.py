"""Visual reading of PDFs the parser cannot read: the parser asks first, and a transcript is used only once it is
confirmed for the PDF as it is. All data is fictional. Run: uv run python -m unittest discover -s tests -t ."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from jk import common
from jk.resumes import extract, process_resumes as proc, visual

TRANSCRIPT = ("Alex Example\n\nWORK EXPERIENCE\nNorthwind Traders   09/2021 - Present\nSenior Engineer\n"
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
        entries = visual.pending([self.pdf], {self.pdf: ("2026/scan.pdf", "scan.txt")})
        entries[0]["transcript"] = str(self.transcript)
        visual.cmd_confirm(entries, "scan.pdf")
        self.assertEqual(visual.state(self.pdf, self.transcript), "fresh")
        with self.assertRaises(common.ToolError):
            visual.cmd_confirm(entries, "other.pdf")

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
