"""Contract tests for the command-line tools: every tool answers --help, and each released version's commands."""
import importlib
import subprocess
import sys
import tomllib
import unittest

from tests.support import PLUGIN_ROOT, TOOLS

# The commands each released package version installs. The installers reinstall only when the version changes, so a
# new or removed command needs a new version: add an entry for it and never edit a released one.
RELEASED_COMMANDS = {
    "0.4.0": {"jobkit", "profile", "process-resumes", "query-resume", "build-resume", "resume-lines", "match-score",
              "arch", "lead", "prep", "sessions", "readiness"},
    "0.5.0": {"jobkit", "profile", "process-resumes", "query-resume", "build-resume", "resume-lines", "match-score",
              "arch", "lead", "prep", "sessions", "readiness", "target"},
    "0.5.1": {"jobkit", "profile", "process-resumes", "query-resume", "build-resume", "resume-lines", "match-score",
              "arch", "lead", "prep", "sessions", "readiness", "target"},
    "0.6.0": {"jobkit", "profile", "process-resumes", "query-resume", "build-resume", "resume-lines", "match-score",
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
