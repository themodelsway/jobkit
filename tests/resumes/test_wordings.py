"""Tests for requirements shown by any stored wording of a line (text, variants, per-file wordings): evidence,
ranking, tags, the printed wording a build chooses, and the match-score fingerprint."""
import unittest

from jk.resumes import build_resume as br
from jk.resumes import evidence
from jk.resumes import match_facts as mf
from jk.resumes import process_resumes as proc
from jk.resumes import query_resume as qr
from jk.resumes import resume_data as rd
from tests.resumes.support import line

NEWEST = "Improved hiring for 12 teams across the region."
OLDER = "Ran structured interviews for 12 teams across the region."


def hiring_line(**extra):
    return line(NEWEST, id="h1", variants=[OLDER], wordings={"old.pdf": [OLDER], "new.pdf": [NEWEST]}, **extra)


class WordingsOfTests(unittest.TestCase):
    def test_every_wording_once_with_the_text_first(self):
        self.assertEqual(rd.wordings_of(hiring_line()), [NEWEST, OLDER])
        self.assertEqual(rd.wordings_of({"text": "Only one."}), ["Only one."])


class EvidenceTests(unittest.TestCase):
    def test_a_requirement_shown_only_by_an_older_wording_counts(self):
        ctx = qr.JdContext(qr.Counter(), {"interviews"}, set(), {"h1": 0.0}, 0.0, plain=("structured interviews",))
        self.assertEqual(qr.shown_terms(hiring_line(), ctx), ["structured interviews"])
        scored = qr.score_bullet(hiring_line(), ctx)
        self.assertIsNotNone(scored)
        self.assertIn("structured interviews", scored.why)

    def test_a_denial_in_any_wording_wins(self):
        denied = line("Ran payroll reports.", id="p", skills=["Payroll"], variants=["Ran reports; no professional use of Payroll"])
        self.assertEqual(evidence.line_state(denied, "Payroll"), evidence.NOT_DEMONSTRATED)

    def test_training_in_one_wording_and_use_in_another_is_ok(self):
        mixed = line("Completed a Payroll course.", id="m", skills=["Payroll"], variants=["Ran Payroll for 3 offices."])
        self.assertEqual(evidence.line_state(mixed, "Payroll"), evidence.OK)

    def test_search_reads_every_wording(self):
        self.assertTrue(qr.bullet_matches(hiring_line(), None, "structured interviews", None))


class TagTests(unittest.TestCase):
    def test_tags_come_from_every_wording(self):
        data = {"companies": {"a": {"bullets": [hiring_line()]}},
                "skills": {"groups": {"People": [{"name": "Structured interviews", "aliases": []}]}}}
        proc.retag(data)       # type: ignore[arg-type]
        self.assertEqual(data["companies"]["a"]["bullets"][0]["skills"], ["Structured interviews"])


class PrintedWordingTests(unittest.TestCase):
    def test_build_prints_the_wording_that_shows_the_posting(self):
        self.assertEqual(br.fitting_text(hiring_line(), {}), NEWEST)
        self.assertEqual(br.fitting_text(hiring_line(), {}, ["structured interviews"]), OLDER)
        self.assertEqual(br.fitting_text(hiring_line(), {}, ["hiring"]), NEWEST)        # the text already shows it

    def test_an_approved_wording_still_wins(self):
        self.assertEqual(br.fitting_text(hiring_line(), {"h1": "Hired for 12 teams."}, ["structured interviews"]),
                         "Hired for 12 teams.")

    def test_the_printed_line_keeps_only_tags_its_words_name(self):
        tagged = hiring_line(skills=["Structured interviews"])
        shown = br.printed(tagged, {})
        self.assertEqual((shown["text"], shown["skills"], shown["variants"]), (NEWEST, [], []))
        chosen = br.printed(tagged, {}, ["Structured interviews"])
        self.assertEqual((chosen["text"], chosen["skills"]), (OLDER, ["Structured interviews"]))

    def test_coverage_counts_the_wording_chosen_for_the_posting(self):
        company = {"id": "a", "name": "A", "roles": [], "bullets": []}
        tagged = hiring_line(skills=["Structured interviews"])
        self.assertEqual(br.shown_skills([(company, [tagged])], ["Structured interviews"], None, {}),
                         {"Structured interviews"})
        self.assertEqual(br.other_wordings([(company, [tagged])], ["Structured interviews"], {}), ["h1"])


class FingerprintTests(unittest.TestCase):
    def test_a_new_variant_changes_the_fingerprint(self):
        company = {"name": "Acme", "roles": [], "bullets": [line(NEWEST, id="h1")]}
        before = mf.resume_fingerprint(mf.ResumeFacts({"a": company}, {}, [], []))  # type: ignore[arg-type]
        company["bullets"] = [hiring_line()]
        self.assertNotEqual(mf.resume_fingerprint(mf.ResumeFacts({"a": company}, {}, [], [])), before)  # type: ignore[arg-type]
