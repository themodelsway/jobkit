"""Characterization tests for plugins/jobkit/src/jk/resumes/parse_resume.py. The sample files in `tests/resumes/data/`
are synthetic (no real names or employers); the golden `.expected.json` files record current behavior: regenerate them
only when a behavior change is intended."""
import json
import unittest

from jk.resumes import extract
from jk.resumes import parse_resume as pr
from tests.resumes.support import DATA_DIR, DATA_REGISTRY, EmployersCase, as_txt, parse_sample


class ParserTests(unittest.TestCase):
    def setUp(self):
        self._saved = (dict(pr.COMPANIES), dict(pr.COMPANY_RES))
        pr.set_companies(DATA_REGISTRY)
        self.addCleanup(self._restore)

    def _restore(self):
        pr.set_companies(self._saved[0])

    def test_layout_a_matches_golden(self):
        got = parse_sample("layout_a", "layout_a.layout")
        want = json.loads((DATA_DIR / "layout_a.expected.json").read_text(encoding="utf-8"))
        self.assertEqual(json.loads(json.dumps(got)), want)

    def test_layout_b_matches_golden(self):
        got = parse_sample("layout_b")
        want = json.loads((DATA_DIR / "layout_b.expected.json").read_text(encoding="utf-8"))
        self.assertEqual(json.loads(json.dumps(got)), want)

    def test_a_label_is_matched_by_its_words(self):
        for label, group in (("Machine Learning and AI", "AI/ML"), ("Data Platforms", "Data"), ("Leadership Skills", "Leadership")):
            skills, problems = pr.parse_skills({"skills": [f"• {label}: Topic One, Topic Two"]})
            self.assertEqual(problems, [], label)
            self.assertEqual([i["name"] for i in skills[group]], ["Topic One", "Topic Two"], label)

    def test_a_comma_label_needs_a_group_word_and_a_list_word(self):
        skills, _ = pr.parse_skills({"skills": ["• Web technologies, Topic One, Topic Two", "• Data Modeling, Query Tuning"]})
        self.assertEqual([i["name"] for i in skills["Web"]], ["Topic One", "Topic Two"])
        self.assertEqual([i["name"] for i in skills["Unsorted"]], ["Data Modeling", "Query Tuning"])
        self.assertFalse(pr.is_category_name("AI"))
        self.assertTrue(pr.is_category_name("Web technologies"))

    def test_not_a_resume(self):
        r = pr.parse_resume("just some text\nwith no work heading")
        self.assertEqual(r, {"is_resume": False, "problems": ["no work-experience heading found"]})

    def test_discover_companies(self):
        self.assertEqual(pr.discover_companies((DATA_DIR / "layout_a.layout.txt").read_text(encoding="utf-8")),
                         {"acme-corp": "Acme Corp", "acme-2": "Acme 2"})
        self.assertEqual(pr.discover_companies((DATA_DIR / "layout_b.txt").read_text(encoding="utf-8")),
                         {"acme-3": "Acme 3", "acme-corp": "Acme Corp"})
        self.assertEqual(pr.discover_companies("no sections here"), {})

    def test_three_line_entry_finds_company_above_title(self):
        text = "Work History\nAcme Corp\nSenior Strategist\n01/2020 - Present\n• Built things.\n"
        self.assertEqual(pr.discover_companies(text), {"acme-corp": "Acme Corp"})
        entries, _ = pr.parse_work(text.splitlines()[1:])
        self.assertEqual([(e["company_id"], e["title"]) for e in entries], [("acme-corp", "Senior Strategist")])

    def test_line_above_dates_after_bullet_is_the_employer(self):
        text = ("Work History\nAcme Corp\n01/2020 - Present\n• Led the platform team and shipped\n"
                "the new billing engine.\nAcme 2\n01/2015 - 12/2019\n• Built things.\n")
        self.assertEqual(pr.discover_companies(text), {"acme-corp": "Acme Corp", "acme-2": "Acme 2"})

    def test_company_and_title_on_one_line_ignores_line_above(self):
        text = "Work History\n• Wrapped bullet end\nAcme Corp – Senior Strategist\n01/2020 - Present\n• x\n"
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
        a, b = "Cut checkout drop-off by 30%.", "cut checkout drop-off by 30"
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


class HyphenatedEmployerTests(unittest.TestCase):
    def discover(self, header: str) -> dict[str, str]:
        text = f"WORK EXPERIENCE\n{header}\n01/2010 - 12/2014\n• Did things.\n"
        return pr.discover_companies(text)

    def test_hyphen_inside_a_name_is_kept(self):
        self.assertEqual(self.discover("Acme-Labs"), {"acme-labs": "Acme-Labs"})
        self.assertEqual(self.discover("X-Acme"), {"x-acme": "X-Acme"})

    def test_a_spaced_hyphen_or_a_dash_still_splits_name_and_title(self):
        self.assertEqual(self.discover("Acme-Works – Principal Strategist"), {"acme-works": "Acme-Works"})
        self.assertEqual(self.discover("Acme-Works - Principal Strategist"), {"acme-works": "Acme-Works"})
        self.assertEqual(self.discover("Acme-Works — Principal Strategist"), {"acme-works": "Acme-Works"})

    def test_a_resume_with_no_known_employer_is_reported(self):
        parsed = pr.parse_resume(as_txt(), company_res={})
        self.assertTrue(any("no known employer" in p for p in parsed["problems"]))


class ContactLineTests(EmployersCase):
    PHONE = "555.010.0100"
    MAIL = "jane@example.com"

    def test_lines_that_are_only_contact_details(self):
        for line in (self.MAIL, self.PHONE, f"{self.PHONE} | {self.MAIL}", f"{self.PHONE} · {self.MAIL} • "
                     "linkedin.com/in/jane"):
            self.assertTrue(extract.is_contact_line(line), line)
        for line in ("Jane | Seattle", f"Reach me at {self.MAIL}", "Cut wait time by 18% | served 7 regions", "•", ""):
            self.assertFalse(extract.is_contact_line(line), line)

    def test_stray_contact_line_is_not_the_headline(self):
        text = f"Jane Example\nSenior Product Designer\n{self.PHONE} | {self.MAIL}\nAccessibility specialist\n"
        parsed = pr.parse_resume(text + as_txt().split("\n", 2)[2])
        self.assertEqual(parsed["headline"], "Accessibility specialist")
        self.assertNotIn(self.MAIL, parsed["summary"])

    def test_contact_line_in_work_section_is_not_glued_to_a_bullet(self):
        text = as_txt().replace("• Built a design system with shared prototypes.\n",
                                f"• Built a design system with shared prototypes.\n{self.PHONE} | {self.MAIL}\n")
        bullets = [b for e in pr.parse_resume(text, text)["work"] for b in e["bullets"]]
        self.assertIn("Built a design system with shared prototypes.", bullets)
        self.assertFalse(any(self.MAIL in b or self.PHONE in b for b in bullets))

    def test_layout_text_of_a_pdf_is_cleaned_too(self):
        layout = as_txt().replace("• Built a design system with shared prototypes.\n",
                                  f"• Built a design system with shared prototypes.\n   {self.MAIL}\n")
        bullets = [b for e in pr.parse_resume(as_txt(), layout)["work"] for b in e["bullets"]]
        self.assertIn("Built a design system with shared prototypes.", bullets)
        self.assertFalse(any(self.MAIL in b for b in bullets))
