"""Checks the plugin packaging for both agents: manifests, marketplace catalogs, and what the plugin folder holds."""
import os
import shutil
import subprocess
import tomllib
import unittest

from tests.meta.support import MANIFESTS, MARKETPLACES, load, pyproject, rel
from tests.support import PLUGIN_ROOT, REPO_ROOT


class ManifestTests(unittest.TestCase):
    def test_every_manifest_has_the_package_name_and_version(self):
        version = pyproject()["project"]["version"]
        for path in MANIFESTS:
            manifest = load(path)
            self.assertEqual((manifest["name"], manifest["version"]), ("jobkit", version), rel(path))
            self.assertTrue(manifest["description"].strip(), rel(path))

    def test_no_other_manifest_exists(self):
        self.assertFalse((PLUGIN_ROOT / ".codex-plugin").exists(), "the plugin's plugin.json is the only Codex manifest")
        for name in ("plugin.json", ".claude-plugin/plugin.json", ".codex-plugin"):
            self.assertFalse((REPO_ROOT / name).exists(), f"{name} belongs in plugins/jobkit, not the repository root")

    def test_both_marketplaces_point_at_the_plugin_folder(self):
        for path in MARKETPLACES:
            market = load(path)
            (entry,) = market["plugins"]
            self.assertEqual((market["name"], entry["name"], entry["source"]),
                             ("themodelsway", "jobkit", "./plugins/jobkit"), rel(path))
            self.assertTrue((REPO_ROOT / entry["source"] / "plugin.json").is_file(), rel(path))
        self.assertTrue(load(MARKETPLACES[0])["owner"]["name"])

    def test_codex_entry_has_policy_and_category(self):
        (entry,) = load(MARKETPLACES[1])["plugins"]
        self.assertIn(entry["policy"]["installation"], ("AVAILABLE", "INSTALLED_BY_DEFAULT", "NOT_AVAILABLE"))
        self.assertTrue(entry["policy"]["authentication"])
        self.assertTrue(entry["category"])

    def test_validator_accepts_the_plugin(self):
        claude = shutil.which("claude")
        if claude is None:
            self.skipTest("claude is not installed")
        for target in (REPO_ROOT, PLUGIN_ROOT):
            result = subprocess.run([claude, "plugin", "validate", str(target)], capture_output=True, text=True,
                                    timeout=300, check=False, env={**os.environ, "NO_COLOR": "1"})
            self.assertEqual(result.returncode, 0, f"{target}\n{result.stdout}{result.stderr}")


CONTRIBUTOR_ONLY = ("tests", "docs", "openspec", ".claude", ".githooks", "tools", "AGENTS.md", "CLAUDE.md",
                    "ruff.toml", ".pylintrc", "pyrightconfig.json", "uv.lock")


class PluginFolderTests(unittest.TestCase):
    """The plugin folder is complete on its own and holds nothing that belongs to contributors."""

    def test_license_copy_matches_the_canonical_license(self):
        self.assertEqual((PLUGIN_ROOT / "LICENSE").read_bytes(), (REPO_ROOT / "LICENSE").read_bytes())

    def test_plugin_holds_what_setup_builds_from(self):
        for name in ("pyproject.toml", ".python-version", "LICENSE", "README.md", "src/jk/common.py",
                     "setup/install", "setup/install.ps1", "setup/constraints.txt"):
            self.assertTrue((PLUGIN_ROOT / name).is_file(), f"plugins/jobkit/{name} is missing")

    def test_plugin_holds_no_contributor_files(self):
        for name in CONTRIBUTOR_ONLY:
            self.assertFalse((PLUGIN_ROOT / name).exists(), f"plugins/jobkit/{name} must stay at the repository root")

    def test_repository_root_holds_no_plugin_files(self):
        for name in ("skills", "src", "setup"):
            self.assertFalse((REPO_ROOT / name).exists(), f"{name} belongs in plugins/jobkit")

    def test_root_is_a_workspace_that_holds_the_lock(self):
        root = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(root["tool"]["uv"]["workspace"]["members"], ["plugins/jobkit"])
        self.assertNotIn("scripts", root["project"], "the commands belong to the plugin's own pyproject.toml")
        self.assertTrue((REPO_ROOT / "uv.lock").is_file())
        lock = tomllib.loads((REPO_ROOT / "uv.lock").read_text(encoding="utf-8"))
        jobkit = next(p for p in lock["package"] if p["name"] == "jobkit")
        self.assertEqual((jobkit["version"], jobkit["source"]), (pyproject()["project"]["version"], {"editable": "plugins/jobkit"}),
                         "run uv lock after changing the version")

    def test_uv_minimum_is_the_same_at_the_root_and_in_the_plugin(self):
        """The installers read the plugin's value; uv itself reads the root's."""
        root = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(root["tool"]["uv"]["required-version"], pyproject()["tool"]["uv"]["required-version"])

    def test_python_pin_is_the_same_at_the_root_and_in_the_plugin(self):
        """A root `uv sync` reads the root pin; the installers read the plugin's."""
        root = (REPO_ROOT / ".python-version").read_text(encoding="utf-8").strip()
        plugin = (REPO_ROOT / "plugins" / "jobkit" / ".python-version").read_text(encoding="utf-8").strip()
        self.assertEqual(root, plugin)

    def test_contributor_scripts_do_not_ship(self):
        for name in ("pins.py", "clean_copy.py"):
            self.assertTrue((REPO_ROOT / "tools" / name).is_file(), name)
            self.assertFalse((PLUGIN_ROOT / "setup" / name).exists(), name)

    def test_pyright_config_points_at_the_plugin(self):
        config = load(REPO_ROOT / "pyrightconfig.json")
        self.assertEqual((config["venvPath"], config["venv"], config["include"]),
                         (".", ".venv", ["plugins/jobkit/src/jk"]))
        self.assertNotIn("pyright", pyproject().get("tool", {}))
