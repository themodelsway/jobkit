"""Tests for plugins/jobkit/src/jk/resumes/match_facts.py: resolving evidence references, including tag-only skills."""
import unittest

from jk.resumes import match_facts as mf
from tests.resumes.match.support import tagged_facts


class TagOnlyResolveTests(unittest.TestCase):
    def test_tag_only_name_with_a_tagged_line_resolves(self):
        self.assertEqual(mf.resolve("skill:leadership", tagged_facts(True)), "Leadership")

    def test_tag_only_name_with_no_tagged_line_is_rejected(self):
        with self.assertRaises(mf.EvidenceError):
            mf.resolve("skill:Leadership", tagged_facts(False))

    def test_regular_skills_resolve_as_before(self):
        self.assertEqual(mf.resolve("skill:k8s", tagged_facts(False)), "Kubernetes")
