"""Data-integrity tests: pruning on rebuild, orphaned curation, empty-extraction causes, and the privacy rules on
generated data and on the resume folder. Run: .venv/bin/python -m unittest discover -s tests -t ."""
import contextlib
import hashlib
import io
import os
import re
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock


from jobkit import common
from jobkit.resumes import extract
from jobkit.resumes import parse_resume as pr
from jobkit.resumes import process_resumes as proc
from jobkit.resumes import resume_data as rd
from jobkit.resumes import tables
from tests.support import HomeCase, real_resume_texts
from tests.resumes.test_extract import REGISTRY as BASE_REGISTRY
from tests.resumes.test_extract import as_txt, write_docx

ROOT = Path(__file__).resolve().parents[2]
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE = re.compile(r"(?<!\d)(?:\+?1[ .-]?)?\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}(?!\d)")
REGISTRY = {**BASE_REGISTRY, "initech": ("Initech", r"Initech")}
EXTRA_BULLET = "Reduced build times by 40% with a shared cache."


def snapshot(folder: Path) -> dict[str, tuple[int, float, str]]:
    """{relative path: (size, mtime, sha256)} for every file under folder."""
    return {str(p.relative_to(folder)): (p.stat().st_size, p.stat().st_mtime, hashlib.sha256(p.read_bytes()).hexdigest())
            for p in sorted(folder.rglob("*")) if p.is_file()}


def contact_hits() -> list[str]:
    """Stored resume records holding an email address or phone-like number."""
    return [name for name, text in sorted(tables.stored_texts().items()) if EMAIL.search(text) or PHONE.search(text)]


class RebuildCase(HomeCase):
    """A temporary resume folder and home; build() is run for real."""

    def setUp(self):
        super().setUp()
        tmp = self.home
        self.resumes, self.text_dir = tmp / "resumes", tmp / "output"
        self.resumes.mkdir()
        saved = dict(pr.COMPANIES)
        pr.set_companies(REGISTRY)
        self.addCleanup(lambda: pr.set_companies(saved))
        self.tmp = tmp
        for patch in (mock.patch.object(proc, "TEXT_DIR", self.text_dir), mock.patch.object(rd, "TEXT_DIR", self.text_dir)):
            patch.start()
            self.addCleanup(patch.stop)

    def write(self, name: str, text: str) -> Path:
        path = self.resumes / name
        path.write_text(text, encoding="utf-8")
        return path

    def rebuild(self) -> str:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            proc.build(proc.list_resumes([self.resumes]), self.resumes, force=False)
        return out.getvalue()

    def bullets(self) -> dict[str, list[str]]:
        """{bullet text: sources} over all companies."""
        companies = rd.load_companies()
        return {b["text"]: b["sources"] for c in companies.values() for b in c["bullets"]}


class PruneTests(RebuildCase):
    def test_deleted_resume_drops_only_its_own_bullets(self):
        self.write("one.txt", as_txt())
        self.write("two.txt", as_txt().replace("WORK EXPERIENCE", f"WORK EXPERIENCE\nInitech      01/2010 - 12/2014\nEngineer\n• {EXTRA_BULLET}"))
        self.rebuild()
        self.assertEqual(sorted(self.bullets()[EXTRA_BULLET]), ["two.txt"])
        (self.resumes / "two.txt").unlink()
        out = self.rebuild()
        self.assertNotIn(EXTRA_BULLET, self.bullets())
        self.assertIn("pruned (file gone): two.txt", out)
        shared = "Built a search service on PostgreSQL."
        self.assertEqual(self.bullets()[shared], ["one.txt"])
        self.assertNotIn("two.txt", rd.load_ledger())

    def test_company_with_no_source_left_loses_its_file(self):
        self.write("one.txt", as_txt())
        self.write("two.txt", as_txt().replace("WORK EXPERIENCE", f"WORK EXPERIENCE\nInitech      01/2010 - 12/2014\nEngineer\n• {EXTRA_BULLET}"))
        self.rebuild()
        self.assertTrue("initech" in tables.load_companies())
        (self.resumes / "two.txt").unlink()
        self.rebuild()
        self.assertFalse("initech" in tables.load_companies())

    def test_renamed_resume_appears_once_under_the_new_name(self):
        path = self.write("old.txt", as_txt())
        self.rebuild()
        path.rename(self.resumes / "new.txt")
        self.rebuild()
        self.assertEqual({tuple(v) for v in self.bullets().values()}, {("new.txt",)})
        self.assertEqual(list(rd.load_ledger()), ["new.txt"])

    def test_edited_resume_loses_a_removed_bullet(self):
        path = self.write("me.txt", as_txt())
        self.rebuild()
        self.assertIn("Built a search service on PostgreSQL.", self.bullets())
        path.write_text(as_txt().replace("• Built a search service on PostgreSQL.\n", ""), encoding="utf-8")
        stamp = path.stat().st_mtime + 10
        os.utime(path, (stamp, stamp))
        self.rebuild()
        self.assertNotIn("Built a search service on PostgreSQL.", self.bullets())
        self.assertIn("Moved 40 services to a shared build system.", self.bullets())

    def test_curated_skill_survives_when_its_file_is_gone(self):
        data = {"companies": {}, "skills": {"groups": {"Cloud": [{"name": "AWS", "aliases": [], "sources": ["a.txt", "curated"]},
                                                              {"name": "Go", "aliases": [], "sources": ["a.txt"]}]}},
                "profile": rd.empty_profile()}
        proc.strip_source(data, "a.txt")
        self.assertEqual([s["name"] for s in data["skills"]["groups"]["Cloud"]], ["AWS"])

    def test_empty_scan_refuses_and_leaves_data_alone(self):
        self.write("one.txt", as_txt())
        self.rebuild()
        before = tables.stored_texts()
        (self.resumes / "one.txt").unlink()
        with mock.patch.object(proc, "load_config", return_value=proc.Config(self.resumes, [self.resumes])):
            with self.assertRaises(common.ToolError):
                proc.cmd_process(mock.Mock(survey=False, force=False))
        self.assertEqual(tables.stored_texts(), before)


class OrphanTests(RebuildCase):
    def test_stale_ids_are_listed_and_the_file_is_untouched(self):
        self.write("one.txt", as_txt())
        self.rebuild()
        live = next(iter(rd.load_companies()["acme-corp"]["bullets"]))["id"]
        themes = {"themes": {live: ["cost"], "gone-bullet": ["x"]}, "ignore": ["gone-ignored"], "summary_angles": {"sum-gone": ["a"]}}
        tables.save_curation("themes", themes)
        before = tables.load_curation("themes")
        orphans = rd.orphan_curation(rd.load_companies(), rd.load_profile(), themes)
        self.assertEqual(orphans, ["ignore gone-ignored", "summary angle sum-gone", "theme gone-bullet"])
        self.assertIn("WARNING: 3 entr", self.rebuild())
        self.assertEqual(tables.load_curation("themes"), before)

    def test_no_orphans_when_every_id_matches(self):
        self.write("one.txt", as_txt())
        self.rebuild()
        live = rd.load_companies()["acme-corp"]["bullets"][0]["id"]
        self.assertEqual(rd.orphan_curation(rd.load_companies(), rd.load_profile(),
                                            {"themes": {live: ["x"]}}), [])


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


class PrivacyTests(RebuildCase):
    def test_generated_data_has_no_contact_details(self):
        self.write("one.txt", as_txt().replace("Jane Example", "Jane Example\njane@example.com\n555.010.0100"))
        self.rebuild()
        self.assertEqual(contact_hits(), [])

    def test_contact_check_catches_an_email(self):
        tables.save_profile({"summaries": [{"id": "s1", "text": "write to jane@example.com"}]})
        self.assertEqual(contact_hits(), ["profile"])

    def test_real_resume_data_has_no_contact_details(self):
        texts = real_resume_texts()
        if not texts:
            self.skipTest("no stored resume data in the real home (fresh install): nothing to check")
        hits = [name for name, text in sorted(texts.items()) if EMAIL.search(text) or PHONE.search(text)]
        self.assertEqual(hits, [], "email or phone-like number in stored resume data")

    def test_rebuild_leaves_the_resume_folder_untouched(self):
        self.write("one.txt", as_txt())
        self.write("two.txt", as_txt())
        (self.resumes / "sub").mkdir()
        write_docx(self.resumes / "sub" / "three.docx", "<w:p><w:r><w:t>nothing useful</w:t></w:r></w:p>")
        before = snapshot(self.resumes)
        self.rebuild()
        (self.resumes / "two.txt").rename(self.tmp / "moved.txt")    # simulate a deleted source
        before.pop("two.txt")
        self.rebuild()
        self.assertEqual(snapshot(self.resumes), before)


if __name__ == "__main__":
    unittest.main()
