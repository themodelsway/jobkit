"""Write `plugins/jobkit/setup/constraints.txt`: the exact package versions the helper install uses.

    uv run python tools/pins.py            # rewrite the constraints file
    uv run python tools/pins.py --print    # print what it should hold, change nothing

The versions come from the workspace's `uv.lock` at the repository root, for the `jobkit` package only.
Run it after every `uv lock`.
A changed pin needs a new package version in `plugins/jobkit/pyproject.toml` (the tests check both).
For contributors only: the installers read the file, they never run this.
"""
import subprocess
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PLUGIN = REPO / "plugins" / "jobkit"
TARGET = PLUGIN / "setup" / "constraints.txt"
EXPORT = ("uv", "export", "--frozen", "--package", "jobkit", "--no-dev", "--no-emit-project", "--no-emit-workspace",
          "--no-hashes", "--no-header", "--no-annotate")


def package_version() -> str:
    """The package version in the plugin's `pyproject.toml`."""
    return tomllib.loads((PLUGIN / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


def wanted() -> str:
    """The text the constraints file should hold: a header naming the package version, then the pins."""
    done = subprocess.run(EXPORT, cwd=REPO, capture_output=True, text=True, check=True)
    pins = "\n".join(sorted(line.strip() for line in done.stdout.splitlines() if line.strip()))
    return (f"# jobkit {package_version()}\n"
            "# Exact versions for the helper install. Generated from uv.lock by tools/pins.py; do not edit.\n"
            f"{pins}\n")


def main(argv: list[str]) -> int:
    """Print the wanted text, or write it to the file."""
    text = wanted()
    if "--print" in argv:
        sys.stdout.write(text)
        return 0
    TARGET.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {TARGET.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
