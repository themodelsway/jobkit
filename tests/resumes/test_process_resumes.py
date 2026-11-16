"""Tests for the `process-resumes` command (plugins/jobkit/src/jk/resumes/process_resumes.py): incremental builds,
pruning on rebuild, orphaned curation, unavailable folders, and the privacy rules on generated data and the resume folder."""
import contextlib
import hashlib
import io
import os
import re
import unittest
from pathlib import Path, PureWindowsPath
from unittest import mock

from jk import common, store
from jk.resumes import parse_resume as pr
from jk.resumes import process_resumes as proc
from jk.resumes import resume_data as rd
from jk.resumes import tables
from jk.user import profile as up
from tests.resumes.support import (
    DATA_DIR,
    DATA_REGISTRY,
    EXTRA_BULLET,
    EXTRAS,
    ExtractCase,
    RebuildCase,
    as_docx_body,
    as_txt,
    second_resume,
    write_docx,
)
from tests.support import HomeCase, call, real_resume_texts

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE = re.compile(r"(?<!\d)(?:\+?1[ .-]?)?\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}(?!\d)")


def snapshot(folder: Path) -> dict[str, tuple[int, float, str]]:
    """{relative path: (size, mtime, sha256)} for every file under folder."""
    return {str(p.relative_to(folder)): (p.stat().st_size, p.stat().st_mtime, hashlib.sha256(p.read_bytes()).hexdigest())
            for p in sorted(folder.rglob("*")) if p.is_file()}


def contact_hits() -> list[str]:
    """Stored resume records holding an email address or phone-like number."""
    return [name for name, text in sorted(tables.stored_texts().items()) if EMAIL.search(text) or PHONE.search(text)]


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

    def test_a_corrected_folder_choice_is_what_gets_imported(self):
        (self.resumes / "keep").mkdir()
        (self.resumes / "skip").mkdir()
        self.write("keep/one.txt", as_txt())
        self.write("skip/two.txt", as_txt().replace("WORK EXPERIENCE", f"WORK EXPERIENCE\nInitech      01/2010 - 12/2014\nEngineer\n• {EXTRA_BULLET}"))

        def import_as_the_profile_says() -> str:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                proc.build(proc.list_resumes(up.resume_dirs()), up.resume_root(), force=False)
            return out.getvalue()

        with contextlib.redirect_stdout(io.StringIO()):
            up.main(["init", "--resume-root", str(self.resumes)])
        import_as_the_profile_says()
        self.assertEqual(sorted(rd.load_ledger()), ["keep/one.txt", "skip/two.txt"])
        with contextlib.redirect_stdout(io.StringIO()):
            up.main(["init", "--replace", "--resume-root", str(self.resumes), "--resume-dir", "keep"])
        out = import_as_the_profile_says()
        self.assertEqual(sorted(rd.load_ledger()), ["keep/one.txt"])
        self.assertIn("pruned (file gone): skip/two.txt", out)
        self.assertNotIn(EXTRA_BULLET, self.bullets())

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
        """Run `process-resumes` with this folder setup; (status, stderr)."""
        with mock.patch.object(proc, "load_config", return_value=proc.Config(self.resumes, self.dirs)):
            code, _, err = call(proc.main, *argv)
        return code, err

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


class ProcessResumesTests(HomeCase):
    def setUp(self):
        super().setUp()
        self.tmp = self.home
        self.root = self.tmp / "resumes"
        self.root.mkdir()
        (self.root / "a.txt").write_text((DATA_DIR / "layout_b.txt").read_text(encoding="utf-8"))
        saved = dict(pr.COMPANIES)
        self.addCleanup(pr.set_companies, saved)
        pr.set_companies(DATA_REGISTRY)
        patcher = mock.patch.object(proc, "TEXT_DIR", self.tmp / "text")
        patcher.start()
        self.addCleanup(patcher.stop)
        for patcher in (mock.patch.object(proc, "load_config", return_value=proc.Config(self.root, [self.root])),
                        mock.patch.object(proc, "scan_companies")):
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_cli(self, *argv):
        """Run `process-resumes`; (status, stdout)."""
        code, out, _ = call(proc.main, *argv)
        return code, out

    def test_survey_writes_nothing(self):
        code, out = self.run_cli("--survey")
        self.assertEqual(code, 0)
        self.assertIn("a.txt", out)
        self.assertFalse(tables.has_resume_data())
        self.assertEqual(tables.load_companies(), {})

    def test_build_is_incremental_and_force_rebuilds(self):
        self.assertIn("1 new/changed", self.run_cli()[1])
        self.assertIn("0 new/changed, 1 unchanged", self.run_cli()[1])
        self.assertIn("1 new/changed, 0 unchanged", self.run_cli("--force")[1])
        self.assertEqual(list(tables.load_ledger()), ["a.txt"])

    def test_a_parser_change_backs_up_and_rebuilds_once(self):
        self.assertIn("1 new/changed", self.run_cli()[1])
        self.assertIn("0 new/changed, 1 unchanged", self.run_cli()[1])
        with mock.patch.object(pr, "PARSER_VERSION", pr.PARSER_VERSION + 1):
            text = self.run_cli()[1]
            self.assertIn("The resume parser changed", text)
            self.assertIn("1 new/changed, 0 unchanged", text)
            self.assertIn("0 new/changed, 1 unchanged", self.run_cli()[1])
        self.assertTrue(list((self.tmp / "backup").glob("jobkit-before-reparse-*.db")))

    def test_a_parser_change_retries_files_that_all_failed(self):
        (self.root / "a.txt").write_text("Not a resume at all.\n", encoding="utf-8")
        self.assertIn("0 companies", self.run_cli()[1])
        self.assertIn("0 new/changed, 1 unchanged", self.run_cli()[1])
        with mock.patch.object(pr, "PARSER_VERSION", pr.PARSER_VERSION + 1):
            self.assertIn("The resume parser changed", self.run_cli()[1])

    def test_data_from_before_the_parser_version_was_recorded_is_rebuilt(self):
        self.run_cli()
        with store.transaction() as conn:
            conn.execute("DELETE FROM meta WHERE key='resume.parser_version'")
        self.assertIn("The resume parser changed", self.run_cli()[1])

    def test_no_resumes_is_a_clear_error(self):
        (self.root / "a.txt").unlink()
        code, _ = self.run_cli()
        self.assertEqual(code, 1)
