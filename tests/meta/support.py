"""Shared helpers for the checks on the repository's own files: the plugin manifests and marketplace catalogs."""
import json
import tomllib
from pathlib import Path

from tests.support import PLUGIN_ROOT, REPO_ROOT

MANIFESTS = (PLUGIN_ROOT / ".claude-plugin" / "plugin.json", PLUGIN_ROOT / "plugin.json")
MARKETPLACES = (REPO_ROOT / ".claude-plugin" / "marketplace.json", REPO_ROOT / ".agents" / "plugins" / "marketplace.json")


def pyproject() -> dict:
    """The plugin's parsed `pyproject.toml`."""
    return tomllib.loads((PLUGIN_ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def load(path: Path) -> dict:
    """A JSON file, parsed."""
    return json.loads(path.read_text(encoding="utf-8"))


def rel(path: Path) -> str:
    """A path relative to the repository, for messages."""
    return str(path.relative_to(REPO_ROOT))
