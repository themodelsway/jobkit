"""Contract tests for the command-line tools: every tool answers --help, and the AWS seed data is well formed.
Run: uv run python -m unittest discover -s tests -t ."""
import importlib
import subprocess
import sys
import tomllib
import unittest
from collections import Counter
from pathlib import Path

from jk.interview.aws import arch_seed as seed

PLUGIN_ROOT = Path(__file__).resolve().parents[1] / "plugins" / "jobkit"

TOOLS = ["jk.user.profile", "jk.resumes.process_resumes", "jk.resumes.query_resume",
         "jk.resumes.build_resume", "jk.resumes.lines", "jk.resumes.match_score", "jk.interview.arch", "jk.interview.lead",
         "jk.interview.prep", "jk.interview.sessions", "jk.interview.readiness", "jk.interview.target", "jk.admin"]

# The commands each released package version installs. The installers reinstall only when the version changes, so a
# new or removed command needs a new version: add an entry for it and never edit a released one.
RELEASED_COMMANDS = {
    "0.4.0": {"jobkit", "profile", "process-resumes", "query-resume", "build-resume", "resume-lines", "match-score",
              "arch", "lead", "prep", "sessions", "readiness"},
    "0.5.0": {"jobkit", "profile", "process-resumes", "query-resume", "build-resume", "resume-lines", "match-score",
              "arch", "lead", "prep", "sessions", "readiness", "target"},
}


class HelpTests(unittest.TestCase):
    def test_every_tool_answers_help(self):
        for tool in TOOLS:
            with self.subTest(tool=tool):
                p = subprocess.run([sys.executable, "-m", tool, "--help"],
                                   capture_output=True, text=True, check=False)
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertTrue(p.stdout.startswith("usage:"))

    def test_entry_points_name_each_tool_main(self):
        scripts = tomllib.loads((PLUGIN_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["scripts"]
        self.assertEqual(sorted(v.split(":")[0] for v in scripts.values()), sorted(TOOLS))
        for target in scripts.values():
            module, func = target.split(":")
            self.assertTrue(callable(getattr(importlib.import_module(module), func)), target)

    def test_a_changed_command_list_has_a_new_version(self):
        project = tomllib.loads((PLUGIN_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
        self.assertIn(project["version"], RELEASED_COMMANDS,
                      "a new package version needs its command list in RELEASED_COMMANDS")
        self.assertEqual(set(project["scripts"]), RELEASED_COMMANDS[project["version"]],
                         "the commands changed: give the package a new version (see AGENTS.md, Versions)")


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
