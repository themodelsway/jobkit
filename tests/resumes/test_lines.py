"""Tests for src/jobkit/resumes/lines.py: the line-length limit and the checks on a proposed shorter wording."""
import unittest
from unittest import mock

from jobkit.common import ToolError
from jobkit.resumes import build_resume as br, curate, lines, resume_data as rd
from tests.resumes.test_resume_pipeline import PipelineCase

ORIGINAL = ("Designed request throttling with Redis and Kafka during a platform upgrade; "
            "improved placement by 70 percent by updating the way shifts were assigned, "
            "and documented the approach for the platform team, which adopted it across 12 teams.")


class WordingChecks(unittest.TestCase):
    def test_figures_are_compared_in_one_spelling(self):
        self.assertEqual(lines.figures("cut cost by 70 percent and $1.5 million in 12 teams"), {"70%", "$1.5m", "12"})
        self.assertEqual(lines.figures("Route53 and S3 on EC2"), set())

    def test_a_changed_sign_is_a_changed_figure(self):
        self.assertEqual(lines.figures("margin from -5% to 2%, a \u22125% swing, -$2M, 5-10%, 2020-2022"),
                         {"-5%", "2%", "-$2m", "5", "10%", "2020", "2022"})
        errors, _ = lines.problems("Moved operating margin from -5% to 2%.", "Moved operating margin from 5% to 2%.")
        self.assertTrue(any("dropped" in e and "-5%" in e for e in errors))
        self.assertTrue(any("added" in e and "5%" in e for e in errors))
        errors, _ = lines.problems("Cut a $-2M loss.", "Cut a $2M loss.")
        self.assertTrue(errors)
        self.assertEqual(lines.problems("Moved margin from -5% to 2%.", "Moved margin from \u22125% to 2%.")[0], [])

    def test_good_wording_is_accepted(self):
        short = "Built cached vs. uncached API paths with Redis and Kafka, cutting costs 70%; 12 teams adopted it."
        errors, _ = lines.problems(ORIGINAL, short)
        self.assertEqual(errors, [])

    def test_dropped_or_changed_figure_is_refused(self):
        errors, _ = lines.problems(ORIGINAL, "Built cached paths for API calls with Redis and Kafka, cutting costs 80%.")
        self.assertTrue(any("dropped" in e and "70%" in e for e in errors))
        self.assertTrue(any("added" in e and "80%" in e for e in errors))

    def test_over_the_limit_or_empty_is_refused(self):
        self.assertTrue(any("limit" in e for e in lines.problems(ORIGINAL, "70% " + "w" * 250)[0]))
        self.assertEqual(lines.problems(ORIGINAL, "  ")[0], ["the wording is empty"])

    def test_dropped_names_are_warnings_not_errors(self):
        errors, warnings = lines.problems(ORIGINAL, "Cut API costs 70% across 12 teams.")
        self.assertEqual(errors, [])
        self.assertIn("redis", warnings[0])
        self.assertIn("kafka", warnings[0])


class SavedWording(PipelineCase):
    def first_line(self):
        return next(b for c in self.data["companies"].values() for b in c["bullets"])

    def test_save_applies_the_same_checks(self):
        bullet = self.first_line()
        items: dict[str, str] = {}
        spec = curate.SPECS["short-wording"]
        with self.assertRaises(ToolError):
            curate.add_entry(spec, items, [bullet["id"], "w" * 201], mock.Mock())
        with self.assertRaises(ToolError):
            curate.add_entry(spec, items, ["no-such-line", "Short."], mock.Mock())
        self.assertEqual(items, {})

    def test_validate_and_show_commands(self):
        bullet = self.first_line()
        code, out, _ = self.cli(lines.main, "validate", bullet["id"], "w" * 201)
        self.assertEqual(code, 1)
        self.assertIn("not acceptable", out)
        code, out, _ = self.cli(lines.main, "show", bullet["id"])
        self.assertEqual(code, 0)
        self.assertIn("no approved wording", out)
        self.assertEqual(self.cli(lines.main, "show", "nope")[0], 1)


class StaleApprovals(PipelineCase):
    def test_wording_for_a_line_that_no_longer_exists_is_reported(self):
        curated = {"short_wording": {"gone-line": "Old wording."}}
        orphans = rd.orphan_curation(rd.load_companies(), rd.load_profile(), rd.load_themes_file(), curated)
        self.assertEqual(orphans, ["short wording gone-line"])

    def test_approved_wording_that_no_longer_matches_its_line_is_not_used(self):
        bullet = {"id": "b1", "text": "Cut costs by 30% for the platform team.", "variants": []}
        self.assertEqual(br.fitting_text(bullet, {"b1": "Cut costs for the platform team."}), bullet["text"])
        self.assertEqual(br.fitting_text(bullet, {"b1": "Cut costs 30% for the platform."}), "Cut costs 30% for the platform.")
