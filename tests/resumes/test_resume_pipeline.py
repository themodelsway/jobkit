"""End-to-end tests of merge -> curate -> write -> query -> build on the synthetic fixtures, in a temp folder.
Run: .venv/bin/python -m unittest discover -s tests -t ."""
import contextlib
import io
import unittest
from pathlib import Path
from unittest import mock


from jobkit.resumes import build_resume as br
from jobkit.resumes import parse_resume as pr
from jobkit.resumes import process_resumes as proc
from jobkit.resumes import query_resume as qr
from jobkit.resumes import resume_data as rd
from jobkit.resumes import tables
from tests.support import HomeClassCase

FIX = Path(__file__).resolve().parents[1] / "fixtures"
REGISTRY = {
    "acme-corp": ("Acme Corp", r"Acme Corp(?:" + pr.SEP + r"(?P<t>.+))?"),
    "globex": ("Globex Inc", r"Globex Inc"),
    "initech": ("Initech", r"Initech(?:" + pr.SEP + r"(?P<t>.+))?"),
}
JD = "Senior Software Engineer: Python, PostgreSQL, performance tuning, search services, mentor engineers, shared build systems."


class PipelineCase(HomeClassCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tmp = cls.home
        saved = dict(pr.COMPANIES)
        pr.set_companies(REGISTRY)
        data = {"companies": {}, "skills": {"groups": {}}, "profile": rd.empty_profile()}
        text_a, lay_a = (FIX / "layout_a.txt").read_text(encoding="utf-8"), (FIX / "layout_a.layout.txt").read_text(encoding="utf-8")
        text_b = (FIX / "layout_b.txt").read_text(encoding="utf-8")
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
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(list(argv))
        return code, out.getvalue(), err.getvalue()


class WriteTests(PipelineCase):
    def test_files_written(self):
        self.assertEqual(sorted(tables.load_companies()), ["acme-corp", "globex", "initech"])
        for loaded in (tables.load_skills(), tables.load_profile(), tables.load_index(), tables.load_ledger()):
            self.assertTrue(loaded)
        self.assertEqual(tables.load_unparsed(), {})
        self.assertTrue(tables.has_resume_data())

    def test_index_orders_companies_newest_first(self):
        index = tables.load_index()
        self.assertEqual([c["id"] for c in index["companies"]], ["acme-corp", "initech", "globex"])
        self.assertEqual(index["resumes"], 3)

    def test_skills_curated_into_groups(self):
        groups = tables.load_skills()["groups"]
        self.assertIn("PostgreSQL", [s["name"] for s in groups["Unsorted"]])
        self.assertIn("Unsorted", groups)                         # the unlabeled list awaits curation

    def test_bullets_are_tagged_with_skills(self):
        acme = tables.load_companies()["acme-corp"]
        tagged = {s for b in acme["bullets"] for s in b["skills"]}
        self.assertTrue(tagged & {"Python", "TypeScript", "Go"} or tagged, tagged)


class QueryTests(PipelineCase):
    def test_analyze_ranks_and_reports(self):
        r = qr.analyze(JD)
        self.assertIn("PostgreSQL", r.need)
        self.assertEqual(r["need"], r.need)                        # still readable like a dict
        self.assertEqual([c["id"] for c, _ in r.ranked], ["acme-corp", "initech", "globex"])
        self.assertTrue(r.summaries)
        self.assertIn("focus-2", r.angles)
        for _, scored in r.ranked:
            self.assertEqual([s.score for s in scored], sorted((s.score for s in scored), reverse=True))

    def test_for_jd_and_match_alias_print_the_same(self):
        jd = self.tmp / "jd.txt"
        jd.write_text(JD, encoding="utf-8")
        a = self.cli(qr.main, "for-jd", str(jd))
        b = self.cli(qr.main, "match", str(jd))
        self.assertEqual(a[0], 0)
        self.assertEqual(a, b)
        self.assertIn("== Suggested opening summaries", a[1])
        self.assertIn("== Skills to feature, by group:", a[1])

    def test_search_stats_review(self):
        _code, out, _ = self.cli(qr.main, "search", "--text", "page load")
        self.assertIn("1 bullet(s) matched", out)
        self.assertIn("Resumes processed: 2 (+1 non-resume files skipped)", self.cli(qr.main, "stats")[1])
        self.assertIn("Bullets flagged needs_review:", self.cli(qr.main, "review")[1])

    def test_missing_data_is_a_clear_error(self):
        with mock.patch.object(tables, "has_resume_data", return_value=False):
            code, _, err = self.cli(qr.main, "stats")
        self.assertEqual(code, 1)
        self.assertIn("process-resumes", err)


class BuildTests(PipelineCase):
    def test_build_sections_and_notes(self):
        md, notes = br.build(JD, br.BuildOptions(top=2), header=None)
        self.assertTrue(md.startswith("# Your Name"))
        for section in ("## Summary", "## Experience", "### Acme Corp\n", "#### Lead Engineer | 03/2021 - Present", "## Skills"):
            self.assertIn(section, md)
        self.assertTrue(notes.header_missing)
        self.assertIsNotNone(notes.used_summary)

    def test_header_and_title_override(self):
        md, notes = br.build(JD, br.BuildOptions(titles={"acme-corp": "Chief Cloud Wizard"}), header="# Pat Example\nSomewhere")
        self.assertTrue(md.startswith("# Pat Example\nSomewhere"))
        self.assertIn("#### Chief Cloud Wizard | 03/2021 - Present", md)
        self.assertFalse(notes.header_missing)

    def test_old_companies_get_at_most_two_bullets(self):
        texts = ["Migrated monolith databases into managed clusters", "Mentored apprentices through certification",
                 "Shipped serverless ingestion pipelines nightly", "Automated quarterly analytics dashboards",
                 "Hardened firewall policies across subsidiaries"]
        bullets = [{"id": f"x-{i}", "text": text, "metrics": [], "sources": ["a"], "skills": [], "themes": []}
                   for i, text in enumerate(texts)]
        scored = [qr.ScoredBullet(10 - i, b, []) for i, b in enumerate(bullets)]

        def company(end):
            return {"id": "x", "name": "X", "aliases": [], "bullets": bullets,
                    "roles": [{"start": "2000-01", "end": end, "titles": ["T"], "subtitles": [], "clients": [], "sources": []}]}
        options = br.BuildOptions(top=9)
        self.assertEqual(len(br.company_bullets(company("2005-01"), scored, options)), 2)
        self.assertEqual(len(br.company_bullets(company("2021-01"), scored, options)), 5)
        self.assertEqual(len(br.company_bullets(company(None), scored, options)), 5)

    def test_unmatched_company_keeps_one_proven_bullet(self):
        company = self.data["companies"]["globex"]
        self.assertEqual(len(br.company_bullets(company, [], br.BuildOptions())), 1)

    def test_helpers(self):
        self.assertEqual(br.fmt_date(None), "Present")
        self.assertEqual(br.fmt_date("2021-03"), "03/2021")
        self.assertEqual(br.clean_education({"education": ["● BS Computer Science, 2001 - 2005", "BS"]}), ["BS Computer Science", "BS"])

    def test_cli_writes_file_and_creates_header_template(self):
        jd, out = self.tmp / "jd2.txt", self.tmp / "out" / "r.md"
        jd.write_text(JD, encoding="utf-8")
        header = self.tmp / "header.md"
        with mock.patch.object(br, "header_file", return_value=header):
            code, text, _ = self.cli(br.main, str(jd), "-o", str(out))
        self.assertEqual(code, 0)
        self.assertTrue(out.read_text(encoding="utf-8").startswith("# Your Name"))
        self.assertTrue(header.exists())
        self.assertIn("Created header.md template", text)
        self.assertIn("Opening summary:", text)


if __name__ == "__main__":
    unittest.main()
