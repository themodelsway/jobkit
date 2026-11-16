"""Tests for plugins/jobkit/src/jk/resumes/visual_render.py: page images for a visual reading. All data is fictional."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pypdf import PdfWriter

from jk import common
from jk.resumes import visual_render as vr

JPEG = b"\xff\xd8\xff\xe0" + b"j" * 40 + b"\xff\xd9"


WHOLE = "q 100 0 0 100 0 0 cm /Im0 Do Q"


def scan_pdf(pages: list[list[tuple[str, bytes]]], content: str = WHOLE, rotate: int = 0, page_extra: str = "",
             image_extra: str = "") -> bytes:
    """A PDF whose pages each hold the given (filter, data) images, drawn by `content` (all data is fictional)."""
    objects: list[bytes] = [b"", b""]
    kids = []
    for images in pages:
        refs = []
        for filt, data in images:
            objects.append(b"<< /Type /XObject /Subtype /Image /Width 1 /Height 1 " + (image_extra or "/ColorSpace /DeviceGray").encode()
                           + b" /BitsPerComponent 8 /Filter /" + filt.encode() + b" /Length %d >>\nstream\n" % len(data)
                           + data + b"\nendstream")
            refs.append(len(objects))
        names = " ".join(f"/Im{n} {ref} 0 R" for n, ref in enumerate(refs))
        body = content.encode()
        objects.append(b"<< /Length %d >>\nstream\n" % len(body) + body + b"\nendstream")
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100 100] /Rotate {rotate} /Contents {len(objects)} 0 R "
                       f"/Resources << /XObject << {names} >> >> {page_extra} >>".encode())
        kids.append(len(objects))
    objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[1] = b"<< /Type /Pages /Kids [" + " ".join(f"{k} 0 R" for k in kids).encode() + b"] /Count %d >>" % len(kids)
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    start = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    return bytes(out + b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, start))


class RenderCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.pdf = self.tmp / "scan.pdf"
        self.pdf.write_bytes(b"%PDF-1.4")
        self.folder = self.tmp / "pages" / "scan"

    def fake_poppler(self, names):
        def run(cmd, **_):
            for name in names:
                (self.folder / name).write_bytes(b"png")
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return run

    def refused(self, data: bytes) -> None:
        self.pdf.write_bytes(data)
        with mock.patch.object(shutil, "which", return_value=None):
            with self.assertRaises(common.ToolError) as caught:
                vr.render(self.pdf, self.folder)
        self.assertIn("poppler", str(caught.exception))
        self.assertFalse(self.folder.exists())


class RenderTests(RenderCase):
    def test_pdftoppm_pages_come_back_in_page_order_and_old_images_go(self):
        self.folder.mkdir(parents=True)
        (self.folder / "page-old.png").write_bytes(b"old")
        with (mock.patch.object(shutil, "which", return_value="/bin/pdftoppm"),
              mock.patch.object(subprocess, "run", side_effect=self.fake_poppler(["page-10.png", "page-2.png", "page-1.png"])) as run):
            pages = vr.render(self.pdf, self.folder)
        self.assertEqual([p.name for p in pages], ["page-1.png", "page-2.png", "page-10.png"])
        self.assertFalse((self.folder / "page-old.png").exists())
        self.assertIn("-png", run.call_args.args[0])
        self.assertIn(str(vr.MAX_PAGES + 1), run.call_args.args[0])

    def test_pdftoppm_failure_is_reported(self):
        failed = subprocess.CompletedProcess([], 1, "", "Syntax Error: broken")
        with (mock.patch.object(shutil, "which", return_value="/bin/pdftoppm"),
              mock.patch.object(subprocess, "run", return_value=failed)):
            with self.assertRaises(common.ToolError) as caught:
                vr.render(self.pdf, self.folder)
        self.assertIn("Syntax Error: broken", str(caught.exception))

    def test_without_poppler_a_plain_scan_is_copied_out(self):
        other = JPEG + b"more" * 10
        self.pdf.write_bytes(scan_pdf([[("DCTDecode", JPEG)]]))
        with mock.patch.object(shutil, "which", return_value=None):
            result = vr.render(self.pdf, self.folder)
        self.assertEqual([p.name for p in result], ["page-1.jpg"])
        self.assertEqual(result[0].read_bytes(), JPEG)
        self.pdf.write_bytes(scan_pdf([[("DCTDecode", other)], [("DCTDecode", JPEG)]]))
        with mock.patch.object(shutil, "which", return_value=None):
            self.assertEqual(len(vr.render(self.pdf, self.folder)), 2)

    def test_a_page_of_two_tiles_is_not_returned_as_one_tile(self):
        tiles = "q 100 0 0 50 0 50 cm /Im0 Do Q q 100 0 0 50 0 0 cm /Im1 Do Q"
        self.refused(scan_pdf([[("DCTDecode", JPEG), ("DCTDecode", JPEG + b"x")]], content=tiles))

    def test_an_image_with_text_over_it_is_not_a_plain_scan(self):
        self.refused(scan_pdf([[("DCTDecode", JPEG)]], content=WHOLE + " BT /F1 12 Tf (Alex) Tj ET"))

    def test_a_rotated_page_is_not_a_plain_scan(self):
        self.refused(scan_pdf([[("DCTDecode", JPEG)]], rotate=90))

    def test_an_image_that_covers_only_part_of_the_page_is_not_a_plain_scan(self):
        self.refused(scan_pdf([[("DCTDecode", JPEG)]], content="q 100 0 0 50 0 0 cm /Im0 Do Q"))

    def test_a_clipped_image_is_not_a_plain_scan(self):
        self.refused(scan_pdf([[("DCTDecode", JPEG)]], content="q 0 0 50 100 re W n " + WHOLE))

    def test_a_pdf_over_the_page_limit_is_refused_not_cut_short(self):
        self.pdf.write_bytes(scan_pdf([[("DCTDecode", JPEG)]] * (vr.MAX_PAGES + 1)))
        with mock.patch.object(shutil, "which", return_value=None):
            with self.assertRaises(common.ToolError) as caught:
                vr.render(self.pdf, self.folder)
        self.assertIn("more than", str(caught.exception))
        self.assertFalse(self.folder.exists())

    def test_poppler_output_over_the_limit_is_refused(self):
        names = [f"page-{n}.png" for n in range(1, vr.MAX_PAGES + 2)]
        with (mock.patch.object(shutil, "which", return_value="/bin/pdftoppm"),
              mock.patch.object(subprocess, "run", side_effect=self.fake_poppler(names))):
            with self.assertRaises(common.ToolError) as caught:
                vr.render(self.pdf, self.folder)
        self.assertIn("more than", str(caught.exception))

    def test_no_pillow_is_needed(self):
        self.pdf.write_bytes(scan_pdf([[("DCTDecode", JPEG)]]))
        with mock.patch.object(shutil, "which", return_value=None), mock.patch.dict("sys.modules", {"PIL": None}):
            self.assertEqual(len(vr.render(self.pdf, self.folder)), 1)

    def test_a_page_without_a_jpeg_is_a_clear_error_and_leaves_no_folder(self):
        self.pdf.write_bytes(scan_pdf([[("DCTDecode", JPEG)], [("FlateDecode", b"x")]]))
        with mock.patch.object(shutil, "which", return_value=None):
            with self.assertRaises(common.ToolError) as caught:
                vr.render(self.pdf, self.folder)
        self.assertIn("poppler", str(caught.exception))
        self.assertFalse(self.folder.exists())

    def test_an_unreadable_pdf_without_poppler_is_the_same_clear_error(self):
        with mock.patch.object(shutil, "which", return_value=None):
            with self.assertRaises(common.ToolError):
                vr.render(self.pdf, self.folder)

    @unittest.skipUnless(shutil.which("pdftoppm"), "poppler is not installed")
    def test_a_real_pdf_is_drawn(self):
        writer = PdfWriter()
        writer.add_blank_page(200, 200)
        writer.add_blank_page(200, 200)
        with self.pdf.open("wb") as handle:
            writer.write(handle)
        pages = vr.render(self.pdf, self.folder)
        self.assertEqual(len(pages), 2)
        self.assertTrue(all(p.stat().st_size > 0 for p in pages))


class PaintedPageTests(RenderCase):
    """Pages whose JPEG alone is not what the page shows (review RV-02)."""

    def test_vector_painting_over_the_image_is_not_a_plain_scan(self):
        """A white box painted over part of the scan hides text; the JPEG alone would show it (review RV-02)."""
        self.refused(scan_pdf([[("DCTDecode", JPEG)]], content=WHOLE + " 1 1 1 rg 0 60 100 40 re f"))

    def test_other_operators_around_the_image_are_not_a_plain_scan(self):
        for content in ("/GS0 gs " + WHOLE, WHOLE + " 0 0 m 100 100 l S", "q 100 0 0 100 0 0 cm /Im0 Do /Im0 Do Q",
                        "q 100 0 0 100 0 0 cm 1 0 0 1 0 0 cm /Im0 Do Q"):
            self.refused(scan_pdf([[("DCTDecode", JPEG)]], content=content))

    def test_an_image_placed_larger_or_shifted_off_the_page_is_not_a_plain_scan(self):
        for matrix in ("200 0 0 200 0 0", "100 0 0 100 -50 0", "100 0 0 100 0 -40", "-100 0 0 100 100 0"):
            self.refused(scan_pdf([[("DCTDecode", JPEG)]], content=f"q {matrix} cm /Im0 Do Q"))

    def test_annotations_a_crop_box_or_a_masked_image_are_not_a_plain_scan(self):
        self.refused(scan_pdf([[("DCTDecode", JPEG)]], page_extra="/Annots [ << /Type /Annot /Subtype /Square "
                                                                  "/Rect [0 0 100 50] >> ]"))
        self.refused(scan_pdf([[("DCTDecode", JPEG)]], page_extra="/CropBox [0 0 100 50]"))
        self.refused(scan_pdf([[("DCTDecode", JPEG)]], image_extra="/ColorSpace /DeviceGray /Decode [1 0]"))
        self.refused(scan_pdf([[("DCTDecode", JPEG)]], image_extra="/ColorSpace /DeviceCMYK"))

    def test_a_plain_scan_without_q_and_with_rgb_colour_is_copied_out(self):
        self.pdf.write_bytes(scan_pdf([[("DCTDecode", JPEG)]], content="100 0 0 100 0 0 cm /Im0 Do",
                                      image_extra="/ColorSpace /DeviceRGB"))
        with mock.patch.object(shutil, "which", return_value=None):
            self.assertEqual(vr.render(self.pdf, self.folder)[0].read_bytes(), JPEG)
