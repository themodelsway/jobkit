"""`setup/clean_copy.py` copies the plugin without `.git`, `.venv`, `tmp/` or other ignored files."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "setup" / "clean_copy.py"
NEEDED = ("plugin.json", ".claude-plugin/plugin.json", ".agents/plugins/marketplace.json", "pyproject.toml",
          "uv.lock", ".python-version", "setup/install", "setup/install.ps1", "setup/constraints.txt",
          "src/jobkit/common.py", "skills/tutor/SKILL.md", "skills/interview-prep/architecture.md")


def run(*args: str) -> subprocess.CompletedProcess:
    """Run the script with the given arguments."""
    return subprocess.run([sys.executable, "-I", str(SCRIPT), *args], capture_output=True, text=True, check=False)


class CleanCopyTests(unittest.TestCase):
    def test_copy_holds_the_plugin_and_nothing_else(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "copy"
            result = run(str(target))
            self.assertEqual(result.returncode, 0, result.stderr)
            for name in NEEDED:
                self.assertTrue((target / name).is_file(), f"missing {name}")
            for name in (".git", ".venv", "tmp", ".ruff_cache", ".DS_Store"):
                self.assertFalse((target / name).exists(), f"{name} should not be copied")

    def test_refuses_a_folder_that_is_not_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "keep.txt").write_text("x", encoding="utf-8")
            result = run(tmp)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("not empty", result.stderr)

    def test_no_argument_prints_usage(self):
        result = run()
        self.assertEqual(result.returncode, 2)
        self.assertIn("OUTPUT-FOLDER", result.stdout)


if __name__ == "__main__":
    unittest.main()
