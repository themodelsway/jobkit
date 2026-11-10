"""Write `setup/constraints.txt`: the exact package versions the helper install uses, taken from `uv.lock`.

    uv run python setup/pins.py            # rewrite setup/constraints.txt
    uv run python setup/pins.py --print    # print what the file should hold, change nothing

Run it after every `uv lock`. A changed pin needs a new package version in `pyproject.toml`
(the tests check both). For contributors only: the installers read the file, they never run this.
"""
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "setup" / "constraints.txt"
EXPORT = ("uv", "export", "--frozen", "--no-dev", "--no-emit-project", "--no-hashes", "--no-header", "--no-annotate")


def package_version() -> str:
    """The package version in `pyproject.toml`."""
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


def wanted() -> str:
    """The text `setup/constraints.txt` should hold: a header naming the package version, then the pins."""
    done = subprocess.run(EXPORT, cwd=ROOT, capture_output=True, text=True, check=True)
    pins = "\n".join(sorted(line.strip() for line in done.stdout.splitlines() if line.strip()))
    return (f"# jobkit {package_version()}\n"
            "# Exact versions for the helper install. Generated from uv.lock by setup/pins.py; do not edit.\n"
            f"{pins}\n")


def main(argv: list[str]) -> int:
    """Print the wanted text, or write it to the file."""
    text = wanted()
    if "--print" in argv:
        sys.stdout.write(text)
        return 0
    TARGET.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {TARGET.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
