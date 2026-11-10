"""Copy the plugin into a clean folder: the files Git tracks, plus new files it does not ignore.

    python3 setup/clean_copy.py OUTPUT-FOLDER

The copy has no `.git`, `.venv`, `tmp/` or other ignored files, so it is the right thing to add as a
local marketplace from a working checkout. The output folder must not exist yet, or must be empty.
Needs Git and Python 3.11 or newer; changes nothing in the checkout.
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def listed_files() -> list[str]:
    """Paths (relative to the checkout) of tracked files and new files Git does not ignore."""
    out = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        check=True, capture_output=True,
    ).stdout.decode("utf-8")
    return sorted(name for name in out.split("\0") if name and (ROOT / name).is_file())


def copy_to(target: Path) -> int:
    """Copy every listed file to `target`, keeping folders; return how many files were copied."""
    if target.exists() and any(target.iterdir()):
        raise SystemExit(f"{target} is not empty; pick a new folder.")
    names = listed_files()
    for name in names:
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, destination)
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
