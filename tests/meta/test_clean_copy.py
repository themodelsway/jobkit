"""`tools/clean_copy.py` writes a complete marketplace: both catalogs and the plugin, without ignored or contributor files."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.support import REPO_ROOT

SCRIPT = REPO_ROOT / "tools" / "clean_copy.py"
CATALOGS = (".claude-plugin/marketplace.json", ".agents/plugins/marketplace.json")
NEEDED = (*CATALOGS, "plugins/jobkit/plugin.json", "plugins/jobkit/.claude-plugin/plugin.json",
          "plugins/jobkit/pyproject.toml", "plugins/jobkit/.python-version",
          "plugins/jobkit/LICENSE", "plugins/jobkit/README.md", "plugins/jobkit/setup/install",
          "plugins/jobkit/setup/install.ps1", "plugins/jobkit/setup/constraints.txt",
          "plugins/jobkit/setup/preflight.md", "plugins/jobkit/setup/first-run.md",
          "plugins/jobkit/setup/welcome.md", "plugins/jobkit/setup/troubleshoot.md",
          "plugins/jobkit/src/jk/common.py", "plugins/jobkit/skills/tutor/SKILL.md",
          "plugins/jobkit/skills/interview-prep/role-knowledge.md")
ABSENT = (".git", ".venv", "tmp", ".ruff_cache", ".DS_Store", "tests", "docs", "openspec", ".claude", ".githooks",
          "tools", "AGENTS.md", "CLAUDE.md", "README.md", "LICENSE", "ruff.toml", ".pylintrc", "pyrightconfig.json",
          "plugins/jobkit/.venv", "plugins/jobkit/tests", "pyproject.toml", "uv.lock", "plugins/jobkit/uv.lock")


def run(*args: str) -> subprocess.CompletedProcess:
    """Run the script with the given arguments."""
    return subprocess.run([sys.executable, "-I", str(SCRIPT), *args], capture_output=True, text=True, check=False)


class CleanCopyTests(unittest.TestCase):
    def test_copy_is_a_complete_marketplace_and_nothing_else(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "copy"
            result = run(str(target))
            self.assertEqual(result.returncode, 0, result.stderr)
            for name in NEEDED:
                self.assertTrue((target / name).is_file(), f"missing {name}")
            for name in ABSENT:
                self.assertFalse((target / name).exists(), f"{name} should not be copied")
            top = {p.name for p in target.iterdir()}
            self.assertEqual(top, {".claude-plugin", ".agents", "plugins"})
            for name in CATALOGS:
                (entry,) = json.loads((target / name).read_text(encoding="utf-8"))["plugins"]
                self.assertEqual(entry["source"], "./plugins/jobkit")

    def test_copy_has_no_ignored_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "copy"
            self.assertEqual(run(str(target)).returncode, 0)
            names = [p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file()]
            ignored = subprocess.run(["git", "-C", str(REPO_ROOT), "check-ignore", "--stdin"], input="\n".join(names),
                                     capture_output=True, text=True, check=False).stdout.split()
            self.assertEqual(ignored, [])

    def test_refuses_a_folder_that_is_not_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "keep.txt").write_text("x", encoding="utf-8")
            result = run(tmp)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("not empty", result.stderr)

    def test_refuses_a_folder_inside_the_checkout(self):
        inside = REPO_ROOT / "tmp" / "clean-copy-inside-test"
        result = run(str(inside))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("inside the checkout", result.stderr)
        self.assertFalse(inside.exists())

    def test_no_argument_prints_usage(self):
        result = run()
        self.assertEqual(result.returncode, 2)
        self.assertIn("OUTPUT-FOLDER", result.stdout)
