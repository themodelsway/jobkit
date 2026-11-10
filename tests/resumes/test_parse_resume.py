"""Characterization tests for parse_resume.py and the merge step in process_resumes.py.
Fixtures in tests/fixtures are synthetic (no real names or employers). Golden files record current behaviour:
regenerate them only when a behaviour change is intended. Run: .venv/bin/python -m unittest discover -s tests -t ."""
import copy
import json
import unittest
from pathlib import Path

from jobkit.resumes import parse_resume as pr, process_resumes as proc
from tests.resumes.match_fixtures import line
from tests.resumes.test_extract import as_txt
from tests.resumes.test_integrity import RebuildCase

FIX = Path(__file__).resolve().parents[1] / "fixtures"
REGISTRY = {
    "acme-corp": ("Acme Corp", r"Acme Corp(?:" + pr.SEP + r"(?P<t>.+))?"),
    "globex": ("Globex Inc", r"Globex Inc"),
    "initech": ("Initech", r"Initech(?:" + pr.SEP + r"(?P<t>.+))?"),
}


def parse(name, layout=None):
    text = (FIX / f"{name}.txt").read_text(encoding="utf-8")
    lay = (FIX / f"{layout}.txt").read_text(encoding="utf-8") if layout else text
    return pr.parse_resume(text, lay)


def empty_data():
    return {"companies": {}, "skills": {"groups": {}},
            "profile": {"summaries": [], "profile_points": [], "education": [], "certifications": [], "projects": []}}


class ParserTests(unittest.TestCase):
    def setUp(self):
        self._saved = (dict(pr.COMPANIES), dict(pr.COMPANY_RES))
        pr.set_companies(REGISTRY)
        self.addCleanup(self._restore)

    def _restore(self):
        pr.set_companies(self._saved[0])

    def test_layout_a_matches_golden(self):
        got = parse("layout_a", "layout_a.layout")
        want = json.loads((FIX / "layout_a.expected.json").read_text(encoding="utf-8"))
        self.assertEqual(json.loads(json.dumps(got)), want)

    def test_layout_b_matches_golden(self):
        got = parse("layout_b")
        want = json.loads((FIX / "layout_b.expected.json").read_text(encoding="utf-8"))
        self.assertEqual(json.loads(json.dumps(got)), want)

    def test_gen_ai_label_goes_to_ai_ml(self):
        for label in ("Gen AI", "GenAI"):
            skills, problems = pr.parse_skills({"skills": [f"• {label}: Topic One, Topic Two"]})
            self.assertEqual(problems, [], label)
            self.assertEqual([i["name"] for i in skills["AI/ML"]], ["Topic One", "Topic Two"], label)

    def test_not_a_resume(self):
        r = pr.parse_resume("just some text\nwith no work heading")
        self.assertEqual(r, {"is_resume": False, "problems": ["no work-experience heading found"]})

    def test_discover_companies(self):
        self.assertEqual(pr.discover_companies((FIX / "layout_a.layout.txt").read_text(encoding="utf-8")),
                         {"acme-corp": "Acme Corp", "globex-inc": "Globex Inc"})
        self.assertEqual(pr.discover_companies((FIX / "layout_b.txt").read_text(encoding="utf-8")),
                         {"initech": "Initech", "acme-corp": "Acme Corp"})
        self.assertEqual(pr.discover_companies("no sections here"), {})

    def test_three_line_entry_finds_company_above_title(self):
        text = "Work History\nAcme Corp\nSenior Engineer\n01/2020 - Present\n• Built things.\n"
        self.assertEqual(pr.discover_companies(text), {"acme-corp": "Acme Corp"})
        entries, _ = pr.parse_work(text.splitlines()[1:])
        self.assertEqual([(e["company_id"], e["title"]) for e in entries], [("acme-corp", "Senior Engineer")])

    def test_line_above_dates_after_bullet_is_the_employer(self):
        text = ("Work History\nAcme Corp\n01/2020 - Present\n• Led the platform team and shipped\n"
                "the new billing engine.\nGlobex Inc\n01/2015 - 12/2019\n• Built things.\n")
        self.assertEqual(pr.discover_companies(text), {"acme-corp": "Acme Corp", "globex-inc": "Globex Inc"})

    def test_company_and_title_on_one_line_ignores_line_above(self):
        text = "Work History\n• Wrapped bullet end\nAcme Corp – Senior Engineer\n01/2020 - Present\n• x\n"
        self.assertEqual(pr.discover_companies(text), {"acme-corp": "Acme Corp"})

    def test_registry_is_replaced_not_merged(self):
        pr.set_companies({})
        self.assertEqual(pr.COMPANIES, {})
        entries, _ = pr.parse_work(["Acme Corp", "03/2021 - Present", "• x"])
        self.assertEqual(entries, [])


class HelperTests(unittest.TestCase):
    def test_clean(self):
        self.assertEqual(pr.clean("Cross- functional  ( AWS )\xa0team"), "Cross-functional (AWS) team")

    def test_join_lines_hyphen_break(self):
        self.assertEqual(pr.join_lines(["multi-", "cloud design", "", "next"]), "multi-cloud design next")

    def test_norm_date(self):
        self.assertEqual(pr.norm_date("03/2021"), "2021-03")
        self.assertIsNone(pr.norm_date("Present"))
        self.assertIsNone(pr.norm_date("current"))

    def test_split_items(self):
        self.assertEqual(pr.split_items("AWS (Amazon Web Services), Lambda; Go and Python"),
                         ["AWS (Amazon Web Services)", "Lambda", "Go", "Python"])
        self.assertEqual(pr.split_items("NoSQL – DynamoDB, ."), ["DynamoDB"])

    def test_find_metrics(self):
        self.assertEqual(pr.find_metrics("Saved $4M and 15% on 7 million orders; 15% again"),
                         ["$4M", "15%", "7 million"])

    def test_bullet_identity(self):
        a, b = "Cut page load time by 30%.", "cut page load time by 30"
        self.assertEqual(pr.bullet_id("acme-corp", a), pr.bullet_id("acme-corp", b))
        self.assertTrue(pr.bullet_id("acme-corp", a).startswith("acme-"))
        self.assertGreater(pr.similar(a, b), 0.92)
        self.assertLess(pr.similar(a, "Mentored six engineers"), 0.5)

    def test_tag_skills(self):
        terms = pr.skill_terms({"Cloud": [{"name": "Lambda", "aliases": ["AWS Lambda"]},
                                           {"name": "Go", "aliases": []}]})
        self.assertIn("Go", terms)                        # 1-2 letter terms are kept; they match whole words only
        self.assertEqual(pr.tag_skills("Built on aws lambda and Lambda", terms), ["Lambda"])
        self.assertEqual(pr.tag_skills("Lambdas", terms), [])


class MergeTests(unittest.TestCase):
    def setUp(self):
        self._saved = dict(pr.COMPANIES)
        pr.set_companies(REGISTRY)
        self.addCleanup(lambda: pr.set_companies(self._saved))

    def merged(self, *sources):
        data = empty_data()
        for src, name, layout in sources:
            proc.merge_resume(data, src, parse(name, layout))
        return data

    def test_merge_is_idempotent(self):
        once = self.merged(("a.pdf", "layout_a", "layout_a.layout"))
        twice = copy.deepcopy(once)
        proc.merge_resume(twice, "a.pdf", parse("layout_a", "layout_a.layout"))
        self.assertEqual(once, twice)

    def test_second_source_accumulates_sources_and_roles(self):
        data = self.merged(("a.pdf", "layout_a", "layout_a.layout"), ("b.pdf", "layout_b", None))
        acme = data["companies"]["acme-corp"]
        self.assertEqual(len(acme["roles"]), 1)           # same (start, end) -> one role
        self.assertEqual(sorted(acme["roles"][0]["sources"]), ["a.pdf", "b.pdf"])
        self.assertEqual(sorted(acme["roles"][0]["titles"]), ["Lead Engineer", "Staff Engineer"])
        self.assertEqual(len(data["companies"]["initech"]["roles"]), 1)
        self.assertEqual(data["companies"]["initech"]["roles"][0]["clients"], ["Hooli"])

    def test_near_duplicate_becomes_variant(self):
        data = self.merged(("a.pdf", "layout_a", "layout_a.layout"))
        first = data["companies"]["acme-corp"]["bullets"][0]
        r = parse("layout_a", "layout_a.layout")
        r["work"][0]["bullets"] = [first["text"].rstrip(".") + " today."]
        proc.merge_resume(data, "c.pdf", r)
        self.assertEqual(len(data["companies"]["acme-corp"]["bullets"]), 2)
        self.assertEqual(first["variants"], [first["text"].rstrip(".") + " today."])
        self.assertIn("c.pdf", first["sources"])

    def test_skills_and_summary_merge(self):
        data = self.merged(("a.pdf", "layout_a", "layout_a.layout"))
        names = {g: [s["name"] for s in v] for g, v in data["skills"]["groups"].items()}
        self.assertIn("SQL", names["Unsorted"])
        sql = next(s for s in data["skills"]["groups"]["Unsorted"] if s["name"] == "SQL")
        self.assertEqual(sql["aliases"], ["Structured Query Language"])
        self.assertEqual(len(data["profile"]["summaries"]), 1)
        self.assertEqual(data["profile"]["headlines"], ["Senior Software Engineer"])


class HyphenatedEmployerTests(RebuildCase):
    def discover(self, header: str) -> dict[str, str]:
        text = f"WORK EXPERIENCE\n{header}\n01/2010 - 12/2014\n• Did things.\n"
        return pr.discover_companies(text)

    def test_hyphen_inside_a_name_is_kept(self):
        self.assertEqual(self.discover("Acme-Labs"), {"acme-labs": "Acme-Labs"})
        self.assertEqual(self.discover("X-Acme"), {"x-acme": "X-Acme"})

    def test_a_spaced_hyphen_or_a_dash_still_splits_name_and_title(self):
        self.assertEqual(self.discover("Acme-Works – Principal Engineer"), {"acme-works": "Acme-Works"})
        self.assertEqual(self.discover("Acme-Works - Principal Engineer"), {"acme-works": "Acme-Works"})
        self.assertEqual(self.discover("Acme-Works — Principal Engineer"), {"acme-works": "Acme-Works"})

    def test_a_resume_with_no_known_employer_is_reported(self):
        parsed = pr.parse_resume(as_txt(), company_res={})
        self.assertTrue(any("no known employer" in p for p in parsed["problems"]))


class FigureMergeTests(unittest.TestCase):
    def merged(self, first: str, second: str) -> dict:
        company = {"id": "acme", "bullets": [], "roles": []}
        proc.merge_bullet(company, first, "2020-01", "a.txt")
        proc.merge_bullet(company, second, "2020-01", "b.txt")
        return company

    def test_different_figures_are_separate_bullets(self):
        company = self.merged("Reduced warehouse operating costs by 40% through route consolidation.",
                              "Reduced warehouse operating costs by 90% through route consolidation.")
        self.assertEqual(len(company["bullets"]), 2)
        self.assertEqual([b["sources"] for b in company["bullets"]], [["a.txt"], ["b.txt"]])

    def test_same_figures_still_merge(self):
        company = self.merged("Reduced warehouse operating costs by 40% through route consolidation.",
                              "Reduced warehouse operating costs by 40% through route consolidation work.")
        self.assertEqual(len(company["bullets"]), 1)


class RetagTests(unittest.TestCase):
    """L2: a rebuild tags older bullets with short names and loses no existing tag."""

    def test_retag_adds_short_names_and_keeps_the_rest(self):
        bullets = [line("Built Python models in R for forecasting", skills=["Python"]),
                   line("Wrote Go services with SQL storage", skills=["SQL"], skills_manual=["Kafka"]),
                   line("Planned the R&D budget", skills=[])]
        data = {"companies": {"a": {"bullets": bullets}},
                "skills": {"groups": {"Languages": [{"name": n, "aliases": []} for n in ("Python", "R", "Go", "SQL")]}}}
        before = {b["id"]: set(b["skills"]) for b in bullets}
        proc.retag(data)       # type: ignore[arg-type]
        after = {b["id"]: set(b["skills"]) for b in bullets}
        for key, old in before.items():
            self.assertLessEqual(old, after[key])
        self.assertEqual(after[bullets[0]["id"]], {"Python", "R"})
        self.assertEqual(after[bullets[1]["id"]], {"Go", "SQL", "Kafka"})
        self.assertEqual(after[bullets[2]["id"]], set())


if __name__ == "__main__":
    unittest.main()
