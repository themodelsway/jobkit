"""Contract tests for the command-line tools: every tool answers --help, and the AWS seed data is well formed.
Run: .venv/bin/python -m unittest discover -s tests -t ."""
import importlib
import subprocess
import sys
import tomllib
import unittest
from collections import Counter
from pathlib import Path

from jobkit.interview.aws import arch_seed as seed

ROOT = Path(__file__).resolve().parents[1]

TOOLS = ["jobkit.user.profile", "jobkit.resumes.process_resumes", "jobkit.resumes.query_resume",
         "jobkit.resumes.build_resume", "jobkit.resumes.match_score", "jobkit.interview.arch", "jobkit.interview.lead",
         "jobkit.interview.prep", "jobkit.interview.sessions", "jobkit.interview.readiness", "jobkit.admin"]


class HelpTests(unittest.TestCase):
    def test_every_tool_answers_help(self):
        for tool in TOOLS:
            with self.subTest(tool=tool):
                p = subprocess.run([sys.executable, "-m", tool, "--help"],
                                   capture_output=True, text=True, check=False)
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertTrue(p.stdout.startswith("usage:"))

    def test_entry_points_name_each_tool_main(self):
        scripts = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["scripts"]
        self.assertEqual(sorted(v.split(":")[0] for v in scripts.values()), sorted(TOOLS))
        for target in scripts.values():
            module, func = target.split(":")
            self.assertTrue(callable(getattr(importlib.import_module(module), func)), target)


class SeedTests(unittest.TestCase):
    def test_service_names_are_unique(self):
        names = [s[1].lower() for s in seed.SERVICES]
        self.assertEqual([n for n, c in Counter(names).items() if c > 1], [])

    def test_tiers_are_two_or_three(self):
        self.assertEqual({s[2] for s in seed.SERVICES} - {2, 3}, set())

    def test_pairs_have_members(self):
        for pair in seed.PAIRS:
            self.assertGreaterEqual(len(pair[2]), 2, pair)

    def test_no_urls_or_facts_in_seed(self):
        text = Path(seed.__file__).read_text(encoding="utf-8")
        self.assertNotIn("http", text)                    # lifecycle facts come from `arch refresh --source`
        self.assertFalse(hasattr(seed, "SEED_FACTS"))


if __name__ == "__main__":
    unittest.main()
