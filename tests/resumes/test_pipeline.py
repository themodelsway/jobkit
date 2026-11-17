"""End-to-end tests of merge -> curate -> write -> query -> build on the sample files in `data/`."""
from unittest import mock

from jk.resumes import build_resume as br
from jk.resumes import query_resume as qr
from jk.resumes import tables
from tests.resumes.support import JD, PipelineCase


class WriteTests(PipelineCase):
    def test_files_written(self):
        self.assertEqual(sorted(tables.load_companies()), ["acme-2", "acme-3", "acme-corp"])
        for loaded in (tables.load_skills(), tables.load_profile(), tables.load_index(), tables.load_ledger()):
            self.assertTrue(loaded)
        self.assertEqual(tables.load_unparsed(), {})
        self.assertTrue(tables.has_resume_data())

    def test_index_orders_companies_newest_first(self):
        index = tables.load_index()
        self.assertEqual([c["id"] for c in index["companies"]], ["acme-corp", "acme-3", "acme-2"])
        self.assertEqual(index["resumes"], 3)

    def test_skills_curated_into_groups(self):
        groups = tables.load_skills()["groups"]
        self.assertIn("UX", [s["name"] for s in groups["Design"]])
        self.assertIn("Unsorted", groups)                         # the unlabeled list awaits curation

    def test_bullets_are_tagged_with_skills(self):
        acme = tables.load_companies()["acme-corp"]
        tagged = {s for b in acme["bullets"] for s in b["skills"]}
        self.assertTrue(tagged & {"Python", "TypeScript", "Go"} or tagged, tagged)


class QueryTests(PipelineCase):
    def test_analyze_ranks_and_reports(self):
        tables.save_curation("themes", {"positioning_words": {"focus-a": ["design systems"]}})     # the user's own positioning word
        r = qr.analyze(JD)
        self.assertIn("Prototyping", r.need)
        self.assertEqual(r["need"], r.need)                        # still readable like a dict
        self.assertEqual([c["id"] for c, _ in r.ranked], ["acme-corp", "acme-3", "acme-2"])
        self.assertTrue(r.summaries)
        self.assertIn("focus-a", r.angles)
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
        _code, out, _ = self.cli(qr.main, "search", "--text", "drop-off")
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
        for section in ("## Summary", "## Experience", "### Acme Corp\n", "#### Lead Designer | 03/2021 - Present", "## Skills"):
            self.assertIn(section, md)
        self.assertTrue(notes.header_missing)
        self.assertIsNotNone(notes.used_summary)

    def test_skills_section_names_posting_skills_first_and_echoes_wording(self):
        skills = {"groups": {"Design": [{"name": "Prototyping", "sources": ["a"]}, {"name": "Design System Governance", "sources": ["a"]},
                                       {"name": "Wireframing", "sources": ["a"]}],
                             "Leadership": [{"name": "Stakeholder management", "sources": ["a", "b"]},
                                            {"name": "Collaborative Problem Solving", "sources": ["a"]}]}}
        result = qr.Analysis(need=qr.Counter({"Prototyping": 1}), themes=set(), angles={}, summaries=[], ranked=[],
                             skills=skills)
        text = "\n".join(br.render_skills(result, "We need prototyping, design systems and strong stakeholders."))
        self.assertIn("- **Design:** Prototyping, Design System Governance", text)
        self.assertIn("- **Leadership:** Stakeholder management", text)
        for left_out in ("Wireframing", "Collaborative"):
            self.assertNotIn(left_out, text)
        self.assertLess(text.index("Design"), text.index("Leadership"))

    def test_same_result_told_twice_is_a_repeat_but_other_results_sharing_a_number_are_not(self):
        def bullet(text, metrics):
            return {"text": text, "metrics": metrics}
        first = bullet("Built a pricing model comparing Acme CRM and Acme Ads data; cut costs by 70 percent.", [])
        again = bullet("Evaluated pricing data in Acme CRM versus Acme Ads, delivering 70% cost savings.", ["70%"])
        other = bullet("Moved the finance team to a new close process and reduced close time by 70%.", ["70%"])
        self.assertTrue(br.too_similar(again, [first]))
        self.assertFalse(br.too_similar(other, [first]))

    def test_skills_section_caps_each_group(self):
        names = [{"name": f"Skill{n}", "sources": []} for n in range(15)]
        result = qr.Analysis(need=qr.Counter({s["name"]: 1 for s in names}), themes=set(), angles={}, summaries=[],
                             ranked=[], skills={"groups": {"Data": names}})
        line = br.render_skills(result, "")[2]
        self.assertEqual(line.count("Skill"), br.SKILL_CAP)

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
        company = self.data["companies"]["acme-2"]
        self.assertEqual(len(br.company_bullets(company, [], br.BuildOptions())), 1)

    def test_helpers(self):
        self.assertEqual(br.fmt_date(None), "Present")
        self.assertEqual(br.fmt_date("2021-03"), "03/2021")
        self.assertEqual(br.clean_education({"education": ["● BS Computer Science, 2001 - 2005", "BS"]}), ["BS Computer Science", "BS"])

    def test_cli_writes_file_and_says_how_to_save_the_header(self):
        jd, out = self.tmp / "jd2.txt", self.tmp / "out" / "r.md"
        jd.write_text(JD, encoding="utf-8")
        with mock.patch.object(br, "stored_header", return_value=None):
            code, text, _ = self.cli(br.main, str(jd), "-o", str(out))
        self.assertEqual(code, 0)
        self.assertTrue(out.read_text(encoding="utf-8").startswith("# Your Name"))
        self.assertIn("profile header set NAME CONTACT_LINE", text)
        self.assertIn("Opening summary:", text)
