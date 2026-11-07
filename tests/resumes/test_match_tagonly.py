"""Tag-only skills (quality words kept as bullet tags) in the match score (ME-2)."""
import copy
import unittest
from types import SimpleNamespace

from jobkit import common
from jobkit.resumes import match_codepass as cp
from jobkit.resumes import match_facts as mf
from jobkit.resumes import match_score as ms
from jobkit.resumes import tables
from tests.resumes.match_fixtures import facts
from tests.resumes.test_match_score import POSTING, MatchCase, seed


def tagged_facts(tag_a_line: bool) -> mf.ResumeFacts:
    """The made-up resume with `Leadership` as a tag-only word, tagged on one line or on none."""
    base = facts()
    companies = copy.deepcopy(dict(base.companies))
    if tag_a_line:
        next(b for b in companies["acme"]["bullets"] if b["id"] == "b2")["skills"] = ["Leadership"]
    skills = {**base.skills, "tag_only": ["Leadership"]}
    return mf.ResumeFacts(companies, skills, base.education, base.certifications)


class ResolveTests(unittest.TestCase):
    def test_tag_only_name_with_a_tagged_line_resolves(self):
        self.assertEqual(mf.resolve("skill:leadership", tagged_facts(True)), "Leadership")

    def test_tag_only_name_with_no_tagged_line_is_rejected(self):
        with self.assertRaises(mf.EvidenceError):
            mf.resolve("skill:Leadership", tagged_facts(False))

    def test_regular_skills_resolve_as_before(self):
        self.assertEqual(mf.resolve("skill:k8s", tagged_facts(False)), "Kubernetes")


class CodePassTests(unittest.TestCase):
    TEXT = "We value Leadership and AWS."

    def items(self, tag_a_line):
        return {i["id"]: i for i in cp.code_pass(self.TEXT, tagged_facts(tag_a_line))}

    def test_tag_only_name_with_a_usable_line_is_rated_and_resolves(self):
        item = self.items(True)["code:skill:leadership"]
        for ref in item["evidence"]:
            mf.resolve(ref, tagged_facts(True))

    def test_tag_only_name_with_no_usable_line_is_left_out(self):
        found = self.items(False)
        self.assertNotIn("code:skill:leadership", found)
        self.assertIn("code:skill:aws", found)


class RunTests(MatchCase):
    def test_run_succeeds_for_a_posting_naming_a_tag_only_skill(self):
        data = tagged_facts(False)
        tables.save_skills(dict(data.skills))
        self.posting.write_text(POSTING + "- Leadership experience.\n", encoding="utf-8")
        result = self.run_json()
        self.assertIn("requirements", result)

    def test_run_succeeds_when_a_line_carries_the_tag(self):
        data = tagged_facts(True)
        seed(lambda companies: companies.update(copy.deepcopy(dict(data.companies))))
        tables.save_skills(dict(data.skills))
        self.posting.write_text(POSTING + "- Leadership experience.\n", encoding="utf-8")
        self.assertIn("requirements", self.run_json())


class RowsTests(unittest.TestCase):
    def test_unresolved_reference_is_a_one_line_tool_error(self):
        item = SimpleNamespace(id="r1", label="Leadership", quote="q", section="", reason="", confidence=1,
                               importance=1, evidence=["skill:Nonexistent"], related=None, flag=None,
                               source="claude", code_level=None)
        prep = SimpleNamespace(request=SimpleNamespace(items=[item]), facts=facts())
        with self.assertRaises(common.ToolError) as caught:
            ms._rows(prep)  # type: ignore[arg-type]
        self.assertNotIn("\n", str(caught.exception))
        self.assertIn("Leadership", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
