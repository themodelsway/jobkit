"""Tests for plugins/jobkit/src/jk/resumes/visual_compare.py: comparing a visual reading of a PDF with what the parser
read from it. All data is fictional."""
import json
import unittest

from jk import common
from jk.resumes import parse_resume as pr
from jk.resumes import visual_compare as vc
from tests.resumes.visual.support import READING, TEXT


def parsed(text: str = TEXT) -> pr.Resume:
    saved = dict(pr.COMPANIES)
    found = pr.discover_companies(text)
    pr.set_companies({k: (v, pr.re.escape(v) + rf"(?:{pr.SEP}(?P<t>.+))?") for k, v in found.items()})
    try:
        result = pr.parse_resume(text, text)
    finally:
        pr.set_companies(saved)
    assert result["is_resume"] is True
    return result


class ParserCase(unittest.TestCase):
    def setUp(self):
        saved = dict(pr.COMPANIES)
        found = pr.discover_companies(TEXT)
        pr.set_companies({k: (v, pr.re.escape(v)) for k, v in found.items()})
        self.addCleanup(pr.set_companies, saved)


class CompareTests(ParserCase):
    def differences(self, **change) -> list[vc.Difference]:
        reading = json.loads(json.dumps(READING))
        for key, value in change.items():
            reading[key] = value
        return vc.compare(parsed(), reading)

    def test_equal_readings_agree(self):
        self.assertEqual(self.differences(), [])

    def test_a_bullet_only_the_visual_reading_has_is_missing_from_the_parser(self):
        bullets = [*READING["employers"][0]["bullets"], "Cut build time from 40 to 12 minutes."]
        found = self.differences(employers=[{**READING["employers"][0], "bullets": bullets}])
        self.assertEqual([(d.kind, d.visual) for d in found], [("missing", "Cut build time from 40 to 12 minutes.")])

    def test_a_bullet_only_the_parser_has_is_extra(self):
        found = self.differences(employers=[{**READING["employers"][0], "bullets": READING["employers"][0]["bullets"][:1]}])
        self.assertEqual([d.kind for d in found], ["extra"])

    def test_a_reworded_bullet_is_different_and_both_are_shown(self):
        bullets = ["Led migration of 41 services to Kubernetes, cutting hosting cost by 30%.",
                   READING["employers"][0]["bullets"][1]]
        found = self.differences(employers=[{**READING["employers"][0], "bullets": bullets}])
        self.assertEqual([d.kind for d in found], ["different"])
        self.assertIn("40 services", found[0].parsed)
        self.assertIn("41 services", found[0].visual)

    def test_dates_and_titles_are_compared(self):
        found = self.differences(employers=[{**READING["employers"][0], "start": "2020-09", "title": "People Director"}])
        self.assertEqual({d.section.rsplit(" ", 1)[1] for d in found}, {"title", "start"})

    def test_an_employer_the_parser_missed_is_reported(self):
        extra = {"name": "Acme 5", "title": "Engineer", "start": "2018-01", "end": "2021-08", "bullets": ["Built a queue."]}
        found = self.differences(employers=[*READING["employers"], extra])
        self.assertEqual([(d.section, d.kind) for d in found], [("employers", "missing")])

    def test_skills_education_and_certifications(self):
        found = self.differences(skills=["Python", "Terraform"], certifications=["Example Certification"], education=[])
        self.assertEqual(sorted((d.section, d.kind) for d in found),
                         [("certifications", "missing"), ("education", "extra"), ("skills", "extra"), ("skills", "missing")])

    def test_report_names_both_sides(self):
        text = vc.format_report("a.pdf", [vc.Difference("skills", "missing", "", "Terraform")])
        self.assertIn("[missing] skills", text)
        self.assertIn("parser: (nothing)", text)
        self.assertIn("visual: Terraform", text)
        self.assertIn("agree", vc.format_report("a.pdf", []))

    def test_a_bad_reading_is_a_clear_error(self):
        role = json.dumps(READING["employers"][0])
        for raw in ("not json", "[]", '{"employers": [{"name": 3}]}', '{"employers": [], "skills": [1]}',
                    '{"employers": [], "skills": null}', '{"employers": [], "skills": "Python"}',
                    '{"employers": [{"name": "A", "bullets": null}]}',
                    '{"employers": [{"name": "A", "bullets": "Built a cache."}]}',
                    '{"employers": [{"name": "A", "title": ["x"]}]}',
                    '{"employers": [{"name": "A", "start": "yesterday"}]}',
                    '{"employers": [{"name": "A", "end": 2022}]}', '{"employers": [], "summary": 3}',
                    '{"employers": [' + role + ', 3]}', '{"employers": [{"name": "A", "title": []}]}',
                    '{"employers": [{"name": "A", "title": {}}]}', '{"employers": [{"name": "A", "title": false}]}',
                    '{"employers": [{"name": "A", "title": 0}]}', '{"employers": [], "summary": []}',
                    '{"employers": [], "summary": false}', '{"employers": [], "summary": 0}',
                    '{"employers": [], "summary": {}}'):
            with self.assertRaises(common.ToolError, msg=raw):
                vc.read_reading(raw)
        with self.assertRaises(common.ToolError) as caught:
            vc.read_reading('{"employers": [{"name": "A", "bullets": null}]}')
        self.assertIn("employers[0].bullets", str(caught.exception))
        vc.read_reading(json.dumps({**READING, "employers": [{**READING["employers"][0], "start": "2021"}]}))
        vc.read_reading('{"employers": [{"name": "A", "title": null, "start": null}], "summary": null}')
        self.assertIn("employers", json.loads(vc.READING_SCHEMA))


class MeaningTests(ParserCase):
    """Each pair below once produced no difference at all."""

    def one(self, section: str, parsed_value: str, visual_value: str) -> list[vc.Difference]:
        parsed_resume = parsed()
        if section == "summary":
            parsed_resume["summary"] = parsed_value
            return vc.compare(parsed_resume, {**READING, "summary": visual_value})
        if section == "skills":
            parsed_resume["skills"] = {"Languages": [{"name": parsed_value, "source": "x"}]}   # type: ignore[typeddict-item]
            return vc.compare(parsed_resume, {**READING, "skills": [visual_value]})
        if section == "bullets":
            parsed_resume["work"][0]["bullets"] = [parsed_value]
            role = {**READING["employers"][0], "bullets": [visual_value]}
            return vc.compare(parsed_resume, {**READING, "employers": [role]})
        parsed_resume[section] = [parsed_value]                                              # type: ignore[literal-required]
        return vc.compare(parsed_resume, {**READING, section: [visual_value]})

    def test_close_but_different_content_is_reported(self):
        cases = [("education", "BS Computer Science", "MS Computer Science"),
                 ("skills", "C", "C++"),
                 ("certifications", "Example Certified Coach - Associate",
                  "Example Certified Coach - Professional"),
                 ("summary", "Designer with 10 years of product work.", "Designer with 20 years of product work."),
                 ("summary", "A nonempty opening summary.", ""),
                 ("summary", "", "A summary only the pages show."),
                 ("bullets", "Reduced processing time by 1.5 hours.", "Reduced processing time by 15 hours.")]
        for section, left, right in cases:
            found = [d for d in self.one(section, left, right) if section in d.section]
            self.assertTrue(found, (section, left, right))
            self.assertIn(left or "(nothing)", [d.parsed or "(nothing)" for d in found])

    def test_titles_are_compared_as_wording(self):
        for parsed_title, visual_title in (("C Developer", "C++ Developer"), ("C Developer", "C# Developer"),
                                           ("Ingénieur", "Ingenieur")):
            resume = parsed()
            resume["work"][0]["title"] = parsed_title
            role = {**READING["employers"][0], "title": visual_title}
            found = vc.compare(resume, {**READING, "employers": [role]})
            self.assertEqual([(d.kind, d.parsed, d.visual) for d in found], [("different", parsed_title, visual_title)])
        resume = parsed()
        resume["work"][0]["title"] = "Senior Strategist \u2013 Platform"
        role = {**READING["employers"][0], "title": "senior strategist - platform"}
        self.assertEqual(vc.compare(resume, {**READING, "employers": [role]}), [])

    def test_typography_alone_is_not_a_difference(self):
        self.assertEqual(self.one("bullets", "Led the \u201cplatform\u201d team \u2013 7 people.",
                                  'Led the "platform" team - 7 people'), [])
        self.assertEqual(self.one("skills", "Python", " python "), [])
