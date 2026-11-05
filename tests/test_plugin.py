"""Checks the Claude Code plugin packaging: manifests, shipped skills, shared text and plain wording.

Run: .venv/bin/python -m unittest discover -s tests -t .
"""
import argparse
import importlib
import json
import os
import re
import shutil
import subprocess
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
SHIPPED = {"interview-prep", "tutor", "resume-workflows"}
SHARED = ("preflight", "talking", "rules")

# Words that must not appear in what a skill says to the user (lines that start with `>`).
BANNED = re.compile(
    r"\b(json|database|hash|seed|tier|confidence|curation|needs[ _]review|jobkit|process-resumes|query-resume|"
    r"build-resume|sessions? (?:log|new)|id)\b|\bJD\b|~/|\.json\b|\.md\b|\.db\b|--\w",
    re.IGNORECASE)


def pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def skill_text(name: str) -> str:
    return (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")


def shared_block(text: str, name: str) -> str:
    match = re.search(rf"<!-- shared:{name} -->\n(.*?)<!-- /shared:{name} -->", text, re.DOTALL)
    assert match, f"shared block {name!r} not found"
    return match.group(1)


def all_skill_files() -> list[Path]:
    return sorted(p for p in SKILLS.rglob("*") if p.is_file())


def parser_words(parser: argparse.ArgumentParser) -> set[str]:
    """Every sub-command name found under a parser, at any depth."""
    words: set[str] = set()
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, sub in action.choices.items():
                words.add(name)
                words |= parser_words(sub)
    return words


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))

    def test_version_equals_package_version(self):
        self.assertEqual(self.plugin["version"], pyproject()["project"]["version"])

    def test_marketplace_points_at_the_plugin(self):
        (entry,) = self.market["plugins"]
        self.assertEqual((entry["name"], entry["source"]), (self.plugin["name"], "./"))
        self.assertTrue(self.market["owner"]["name"])

    def test_validator_accepts_the_plugin(self):
        claude = shutil.which("claude")
        if claude is None:
            self.skipTest("claude is not installed")
        result = subprocess.run([claude, "plugin", "validate", str(ROOT)], capture_output=True, text=True,
                                timeout=120, check=False, env={**os.environ, "NO_COLOR": "1"})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class ShippedSkillTests(unittest.TestCase):
    def test_only_the_user_skills_ship(self):
        self.assertEqual({p.name for p in SKILLS.iterdir() if p.is_dir()}, SHIPPED)

    def test_frontmatter(self):
        for name in SHIPPED:
            head = re.match(r"---\n(.*?)\n---\n", skill_text(name), re.DOTALL)
            self.assertIsNotNone(head, name)
            fields = dict(line.split(": ", 1) for line in head.group(1).splitlines() if ": " in line)
            self.assertEqual(fields.get("name"), name)
            self.assertTrue(fields.get("description", "").strip(), name)

    def test_no_checkout_references(self):
        for path in all_skill_files():
            text = path.read_text(encoding="utf-8")
            for bad in (".venv", ".claude/", "CLAUDE.md"):
                self.assertNotIn(bad, text, f"{path.relative_to(ROOT)} mentions {bad}")

    def test_skills_stay_under_500_lines(self):
        for name in SHIPPED:
            self.assertLess(len(skill_text(name).splitlines()), 500, name)

    def test_data_model_notes_ship_with_resume_workflows(self):
        self.assertTrue((SKILLS / "resume-workflows" / "data-model.md").is_file())
        self.assertIn("${CLAUDE_SKILL_DIR}/data-model.md", skill_text("resume-workflows"))

    def test_sibling_files_named_in_skills_exist(self):
        for name in SHIPPED:
            for ref in re.findall(r"\$\{CLAUDE_SKILL_DIR\}/([\w./-]+\.md)", skill_text(name)):
                self.assertTrue((SKILLS / name / ref).resolve().is_file(), f"{name}: {ref}")


class CommandNameTests(unittest.TestCase):
    def test_commands_named_in_skills_exist(self):
        entry_points = pyproject()["project"]["scripts"]
        words = set(entry_points)
        for target in entry_points.values():
            module, func = target.split(":")
            self.assertEqual(func, "main")
            words |= parser_words(importlib.import_module(module).build_parser())
        for name in SHIPPED:
            for span in re.findall(r"`([^`\n]+)`", skill_text(name)):
                tokens = span.split()
                if len(tokens) >= 2 and re.fullmatch(r"[a-z][a-z0-9-]*", tokens[0]) and tokens[1] in words:
                    self.assertIn(tokens[0], words, f"{name}: `{span}` starts with an unknown command")


class SharedTextTests(unittest.TestCase):
    def test_shared_blocks_are_identical(self):
        for block in SHARED:
            texts = {name: shared_block(skill_text(name), block) for name in SHIPPED}
            self.assertEqual(len(set(texts.values())), 1, f"{block} differs between skills")

    def test_rules_block_has_the_five_rules(self):
        rules = shared_block(skill_text("tutor"), "rules")
        for phrase in ("only through the commands", "read-only", "Never invent", "phone number", "~/.jobkit/output"):
            self.assertIn(phrase, rules)

    def test_preflight_asks_before_installing(self):
        text = shared_block(skill_text("tutor"), "preflight")
        self.assertLess(text.index("Is that OK?"), text.index('setup/install"`'))
        self.assertIn("install nothing", text)


class PlainLanguageTests(unittest.TestCase):
    def test_user_facing_lines_have_no_technical_words(self):
        for name in SHIPPED:
            for number, line in enumerate(skill_text(name).splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith(">"):
                    hit = BANNED.search(stripped)
                    self.assertIsNone(hit, f"{name}:{number} says {hit.group(0) if hit else ''!r}: {stripped}")

    def test_there_is_user_facing_wording(self):
        for name in SHIPPED:
            said = [x for x in skill_text(name).splitlines() if x.strip().startswith(">")]
            self.assertGreaterEqual(len(said), 8, name)


class SetupScriptTests(unittest.TestCase):
    def test_install_script_is_present_and_strict(self):
        script = ROOT / "setup" / "install"
        self.assertTrue(script.is_file())
        self.assertTrue(os.access(script, os.X_OK))
        text = script.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("#!/bin/sh"))
        self.assertIn("set -eu", text)
        self.assertIn("UV_NO_MODIFY_PATH=1", text)

    def test_install_script_syntax(self):
        result = subprocess.run(["sh", "-n", str(ROOT / "setup" / "install")], capture_output=True, text=True,
                                check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_check_reports_a_known_state(self):
        result = subprocess.run(["sh", str(ROOT / "setup" / "install"), "--check"], capture_output=True, text=True,
                                timeout=60, check=False)
        self.assertRegex(result.stdout.strip(), r"^(ok:.+|older:.+|missing|unsupported)$")


if __name__ == "__main__":
    unittest.main()
