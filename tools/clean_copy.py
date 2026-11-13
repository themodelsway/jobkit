"""Copy the marketplace into a clean folder: the two catalogs and the plugin, nothing else.

    python3 tools/clean_copy.py OUTPUT-FOLDER

The copy holds `.claude-plugin/marketplace.json`, `.agents/plugins/marketplace.json` and the files of
`plugins/jobkit/` that Git tracks or does not ignore. It has no `.git`, no `.venv`, no `tmp/`, no ignored
files and none of the contributor-only files at the repository root. Add the output folder (not the plugin
folder inside it) as a local marketplace. The output folder must be new or empty, and outside the checkout.
Needs Git and Python 3.11 or newer; changes nothing in the checkout.
"""
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PLUGIN_DIR = "plugins/jobkit"
CATALOGS = (".claude-plugin/marketplace.json", ".agents/plugins/marketplace.json")


def listed_files() -> list[str]:
    """Paths (relative to the checkout) of the catalogs and the plugin's tracked or non-ignored files."""
    out = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        check=True, capture_output=True,
    ).stdout.decode("utf-8")
    wanted = (name for name in out.split("\0") if name in CATALOGS or name.startswith(PLUGIN_DIR + "/"))
    return sorted(name for name in wanted if (REPO / name).is_file())


def check_target(target: Path) -> None:
    """Refuse a destination inside the checkout, or one that already holds files."""
    if target == REPO or REPO in target.parents:
        raise SystemExit(f"{target} is inside the checkout; pick a folder outside it.")
    if target.exists() and any(target.iterdir()):
        raise SystemExit(f"{target} is not empty; pick a new folder.")


def copy_to(target: Path) -> int:
    """Copy every listed file to `target`, keeping folders; return how many files were copied."""
    check_target(target)
    names = listed_files()
    for name in names:
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / name, destination)
    return len(names)


def main(argv: list[str]) -> int:
    """Command line entry: one argument, the output folder."""
    if len(argv) != 1:
        print(__doc__)
        return 2
    count = copy_to(Path(argv[0]).expanduser().resolve())
    print(f"Copied {count} files to {argv[0]}. Add that folder as a local marketplace.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
