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
from types import SimpleNamespace
from unittest import mock

from jobkit import common
from jobkit.resumes import extract, match_facts as mf, parse_resume as pr, process_resumes as proc, resume_data as rd, tables
from tests.resumes.test_extract import as_txt, REGISTRY as BASE_REGISTRY, write_docx
from tests.support import HomeCase, real_resume_texts

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


class UnavailableFolderTests(RebuildCase):
    """A configured folder that is missing or has emptied stops the run before anything is pruned."""

    def setUp(self):
        super().setUp()
        for sub in ("a", "b"):
            (self.resumes / sub).mkdir()
            self.write(f"{sub}/one.txt", as_txt())
        self.dirs = [self.resumes / "a", self.resumes / "b"]

    def run_main(self, *argv):
        err = io.StringIO()
        config = proc.Config(self.resumes, self.dirs)
        with mock.patch.object(proc, "load_config", return_value=config), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            code = proc.main(list(argv))
        return code, err.getvalue()

    def test_missing_folder_is_named_and_nothing_changes(self):
        self.assertEqual(self.run_main()[0], 0)
        before = tables.stored_texts()
        self.dirs.append(self.resumes / "gone")
        code, err = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn(str(self.resumes / "gone"), err)
        self.assertEqual(tables.stored_texts(), before)

    def test_emptied_folder_stops_unless_forced(self):
        self.run_main()
        before = tables.stored_texts()
        (self.resumes / "b" / "one.txt").unlink()
        code, err = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn(str(self.resumes / "b"), err)
        self.assertEqual(tables.stored_texts(), before)
        self.assertEqual(self.run_main("--force")[0], 0)
        self.assertEqual(sorted(rd.load_ledger()), ["a/one.txt"])


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
        tables.replace_profile({"summaries": [{"id": "s1", "text": "write to jane@example.com"}]})
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


def acme_roles() -> list[dict]:
    return rd.load_companies()["acme-corp"]["roles"]


ENDED = "03/2021 - 06/2022"


PRESENT = "03/2021 - Present"


def second_resume() -> str:
    """A tailored resume with its own headline, education, certification, project and a different Globex title."""
    text = as_txt().replace("Senior Software Engineer\n", "Senior Software Engineer\nWeb performance specialist\n")
    return text.replace("Senior Engineer", "Staff Engineer") + EXTRAS


EXTRAS = ("\nEDUCATION\nBSc Physics, Example University\nCERTIFICATIONS\n• Example Certified Practitioner\n"
          "PROJECTS\nBuilt a hobby compiler in Rust\n")


def bullet(text: str, metrics: list[str], **extra) -> dict:
    """A minimal stored bullet."""
    return {"id": text[:8], "text": text, "metrics": metrics, "skills": [], "sources": ["a"], **extra}


class OneJobTwoEndDatesTests(RebuildCase):
    def test_present_and_a_real_end_date_are_one_role_with_the_end_date(self):
        self.write("2024.txt", as_txt())
        self.write("2025.txt", as_txt().replace(PRESENT, ENDED))
        self.rebuild()
        roles = acme_roles()
        self.assertEqual([(r["start"], r["end"]) for r in roles], [("2021-03", "2022-06")])

    def test_end_date_goes_back_to_present_when_its_file_goes(self):
        self.write("2024.txt", as_txt())
        self.write("2025.txt", as_txt().replace(PRESENT, ENDED))
        self.rebuild()
        (self.resumes / "2025.txt").unlink()
        self.rebuild()
        self.assertEqual([(r["start"], r["end"]) for r in acme_roles()], [("2021-03", None)])

    def test_order_of_files_does_not_matter(self):
        self.write("a.txt", as_txt().replace(PRESENT, ENDED))
        self.write("b.txt", as_txt())
        self.rebuild()
        self.assertEqual([r["end"] for r in acme_roles()], ["2022-06"])

    def test_different_real_end_dates_stay_separate_roles(self):
        self.write("a.txt", as_txt().replace(PRESENT, ENDED))
        self.write("b.txt", as_txt().replace(PRESENT, "03/2021 - 09/2022"))
        self.rebuild()
        self.assertEqual(sorted(r["end"] for r in acme_roles()), ["2022-06", "2022-09"])

    def test_fingerprint_sorts_roles_with_and_without_an_end_date(self):
        role = {"start": "2021-03", "titles": ["Engineer"]}
        company = {"name": "Acme", "bullets": [], "roles": [{**role, "end": None}, {**role, "end": "2022-06"}]}
        facts = SimpleNamespace(skills={}, companies={"acme": company}, education=[], certifications=[])
        self.assertEqual(len(mf.resume_fingerprint(facts)), 64)  # type: ignore[arg-type]


class DeletedResumeTests(RebuildCase):
    def stored(self) -> dict:
        profile = rd.load_profile()
        return {"headlines": profile.get("headlines", []), "education": profile["education"],
                "certifications": profile["certifications"], "projects": profile["projects"]}

    def titles(self) -> list[str]:
        roles = rd.load_companies()["globex"]["roles"]
        return sorted(t for r in roles for t in r["titles"])

    def test_everything_a_deleted_resume_stated_goes_with_it(self):
        self.write("one.txt", as_txt())
        self.write("two.txt", second_resume())
        self.rebuild()
        stored = self.stored()
        self.assertEqual(stored["headlines"], ["Web performance specialist"])
        self.assertTrue(stored["education"] and stored["certifications"] and stored["projects"])
        self.assertEqual(self.titles(), ["Senior Engineer", "Staff Engineer"])
        (self.resumes / "two.txt").unlink()
        self.rebuild()
        self.assertEqual(self.stored(), {"headlines": [], "education": [], "certifications": [], "projects": []})
        self.assertEqual(self.titles(), ["Senior Engineer"])

    def test_an_item_another_resume_states_stays(self):
        self.write("one.txt", second_resume())
        self.write("two.txt", second_resume())
        self.rebuild()
        (self.resumes / "two.txt").unlink()
        self.rebuild()
        self.assertEqual(self.stored()["headlines"], ["Web performance specialist"])
        self.assertEqual(len(self.stored()["education"]), 1)

    def test_a_changed_resume_loses_what_it_no_longer_says(self):
        path = self.write("one.txt", second_resume())
        self.rebuild()
        path.write_text(as_txt() + EXTRAS.replace("BSc Physics", "MSc Physics"), encoding="utf-8")
        self.rebuild()
        self.assertEqual(self.stored()["headlines"], [])
        self.assertEqual([e for e in self.stored()["education"]], ["MSc Physics, Example University"])

    def test_data_stored_before_source_tracking_is_rebuilt_once(self):
        self.write("one.txt", second_resume())
        self.rebuild()
        profile = rd.load_profile()
        profile.pop("item_sources")
        tables.replace_profile(profile)
        self.assertIn("Upgrading the stored data", self.rebuild())
        self.assertNotIn("Upgrading", self.rebuild())


class PruneWordingTests(unittest.TestCase):
    A = "Led the migration of 40 legacy services to AWS Lambda across three regions."
    B = "Led migration of 40 legacy services to AWS Lambda across three regions."

    def data(self, *texts, strict=False):
        company = {"id": "acme", "bullets": [], "roles": []}
        for source, text in zip(("a.txt", "b.txt", "c.txt"), texts, strict=False):
            proc.merge_bullet(company, text, "2020-01", source)
        return {"companies": {"acme": company}, "skills": {"groups": {}}, "profile": rd.empty_profile()}

    def test_deleting_the_canonical_file_moves_text_to_the_remaining_wording(self):
        data = self.data(self.A, self.B)
        self.assertEqual(len(data["companies"]["acme"]["bullets"]), 1)
        proc.strip_source(data, "a.txt")
        bullet = data["companies"]["acme"]["bullets"][0]
        self.assertEqual((bullet["text"], bullet["sources"], bullet["variants"]), (self.B, ["b.txt"], []))

    def test_shared_wording_survives_one_deletion(self):
        data = self.data(self.A, self.A, self.B)
        proc.strip_source(data, "a.txt")
        bullet = data["companies"]["acme"]["bullets"][0]
        self.assertEqual((bullet["text"], bullet["sources"]), (self.A, ["b.txt", "c.txt"]))
        self.assertEqual(bullet["variants"], [self.B])

    def test_last_source_removes_the_bullet(self):
        data = self.data(self.A)
        proc.strip_source(data, "a.txt")
        self.assertEqual(data["companies"], {})

    def test_figures_follow_the_remaining_wording(self):
        data = self.data("Cut costs by 40% via rightsizing the compute fleet in every region.",
                         "Cut costs by 40% via rightsizing the compute fleet in every region now.")
        data["companies"]["acme"]["bullets"][0]["needs_review"] = True
        proc.strip_source(data, "a.txt")
        bullet = data["companies"]["acme"]["bullets"][0]
        self.assertEqual(bullet["text"].endswith("now."), True)
        self.assertFalse(bullet["needs_review"])

    def test_older_merged_data_is_flagged_for_a_rebuild(self):
        old = {"companies": {"acme": {"bullets": [{"text": "x", "sources": ["a", "b"]}]}}}
        self.assertTrue(proc.untraceable_wording(old))
        single = {"companies": {"acme": {"bullets": [{"text": "x", "sources": ["a"]}]}}}
        self.assertFalse(proc.untraceable_wording(single))
        traced = {"companies": {"acme": {"bullets": [{"text": "x", "sources": ["a", "b"], "wordings": {"a": ["x"]}}]}}}
        self.assertFalse(proc.untraceable_wording(traced))



class ContactLineTests(RebuildCase):
    PHONE = "555.010.0100"
    MAIL = "jane@example.com"

    def test_lines_that_are_only_contact_details(self):
        for line in (self.MAIL, self.PHONE, f"{self.PHONE} | {self.MAIL}", f"{self.PHONE} · {self.MAIL} • "
                     "linkedin.com/in/jane"):
            self.assertTrue(extract.is_contact_line(line), line)
        for line in ("Jane | Seattle", f"Reach me at {self.MAIL}", "Cut spend by 30% | saved 12 accounts", "•", ""):
            self.assertFalse(extract.is_contact_line(line), line)

    def test_stray_contact_line_is_not_the_headline(self):
        text = f"Jane Example\nSenior Software Engineer\n{self.PHONE} | {self.MAIL}\nWeb performance specialist\n"
        parsed = pr.parse_resume(text + as_txt().split("\n", 2)[2])
        self.assertEqual(parsed["headline"], "Web performance specialist")
        self.assertNotIn(self.MAIL, parsed["summary"])

    def test_contact_line_in_work_section_is_not_glued_to_a_bullet(self):
        text = as_txt().replace("• Built a search service on PostgreSQL.\n",
                                f"• Built a search service on PostgreSQL.\n{self.PHONE} | {self.MAIL}\n")
        bullets = [b for e in pr.parse_resume(text, text)["work"] for b in e["bullets"]]
        self.assertIn("Built a search service on PostgreSQL.", bullets)
        self.assertFalse(any(self.MAIL in b or self.PHONE in b for b in bullets))

    def test_layout_text_of_a_pdf_is_cleaned_too(self):
        layout = as_txt().replace("• Built a search service on PostgreSQL.\n",
                                  f"• Built a search service on PostgreSQL.\n   {self.MAIL}\n")
        bullets = [b for e in pr.parse_resume(as_txt(), layout)["work"] for b in e["bullets"]]
        self.assertIn("Built a search service on PostgreSQL.", bullets)
        self.assertFalse(any(self.MAIL in b for b in bullets))


if __name__ == "__main__":
    unittest.main()
