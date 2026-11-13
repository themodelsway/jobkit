"""The helper installers: the four check states, no downgrade, pinned versions, and the pin records.

`setup/install` is driven against a fake `uv` and a fake `curl` in a throw-away folder, so nothing is
downloaded or installed. `setup/install.ps1` can only be fully run on Windows; here its text is compared
with the shell script.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = REPO_ROOT / "plugins" / "jobkit"
SCRIPT = PLUGIN_ROOT / "setup" / "install"
WINDOWS_SCRIPT = PLUGIN_ROOT / "setup" / "install.ps1"
CONSTRAINTS = PLUGIN_ROOT / "setup" / "constraints.txt"
ON_WINDOWS = sys.platform == "win32"
TOOLS = ("sh", "sed", "head", "tr", "uname", "dirname", "mktemp", "rm", "cat", "chmod", "mkdir")

FAKE_UV = """#!/bin/sh
# A stand-in for uv: answers the three calls the installer makes and records each one.
echo "$*" >> "$FAKE/uv.log"
case "$1 $2" in
    "--version ") echo "uv $FAKE_UV_VERSION (fake)" ;;
    "tool dir") echo "$FAKE/tools" ;;
    "tool install")
        [ -z "${FAKE_INSTALL_FAILS:-}" ] || exit 1
        mkdir -p "$FAKE/tools"
        printf '#!/bin/sh\\necho "jobkit %s"\\n' "$FAKE_PLUGIN_VERSION" > "$FAKE/tools/jobkit"
        chmod +x "$FAKE/tools/jobkit" ;;
esac
"""

FAKE_CURL = """#!/bin/sh
# A stand-in for curl: records the address and writes an "installer" that puts the fake uv in place.
echo "$*" >> "$FAKE/curl.log"
while [ "$#" -gt 1 ]; do
    if [ "$1" = "-o" ]; then target=$2; fi
    shift
done
printf '#!/bin/sh\\nmkdir -p "$HOME/.local/bin"\\ncp "$FAKE/uv.fake" "$HOME/.local/bin/uv"\\n' > "$target"
"""


def project() -> dict:
    """The parsed `pyproject.toml`."""
    return tomllib.loads((PLUGIN_ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def plugin_version() -> str:
    """The package version, which is the version the installers want."""
    return project()["project"]["version"]


def uv_minimum() -> str:
    """The oldest uv the installers accept."""
    return project()["tool"]["uv"]["required-version"].removeprefix(">=")


def pinned_uv(script: Path) -> str:
    """The uv release an installer downloads."""
    found = re.search(r"^\$?UV_?VERSION *= *'?([0-9.]+)'?", script.read_text(encoding="utf-8"), re.M | re.I)
    assert found, f"{script.name} names no uv version"
    return found.group(1)


def pins(text: str) -> list[str]:
    """The pin lines of a constraints file, without comments."""
    return [x.strip() for x in text.splitlines() if x.strip() and not x.startswith("#")]


def write_script(path: Path, text: str) -> None:
    """Write an executable shell script."""
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)


@unittest.skipIf(ON_WINDOWS, "needs a POSIX shell")
class ShellInstallerTests(unittest.TestCase):
    """`setup/install` against a fake uv, for each state."""

    def setUp(self):
        self.fake = Path(tempfile.mkdtemp(prefix="jobkit-installer-"))
        self.addCleanup(shutil.rmtree, self.fake, ignore_errors=True)
        self.bin = self.fake / "bin"
        self.bin.mkdir()
        (self.fake / "home").mkdir()
        for tool in TOOLS:
            found = shutil.which(tool)
            assert found, tool
            (self.bin / tool).symlink_to(found)
        (self.bin / "cp").symlink_to(shutil.which("cp") or "/bin/cp")
        write_script(self.fake / "uv.fake", FAKE_UV)

    def add_uv(self) -> None:
        """Put the fake uv on the search path."""
        shutil.copy(self.fake / "uv.fake", self.bin / "uv")

    def add_helper(self, version: str) -> None:
        """Pretend the jobkit commands are installed at this version."""
        (self.fake / "tools").mkdir(exist_ok=True)
        write_script(self.fake / "tools" / "jobkit", f'#!/bin/sh\necho "jobkit {version}"\n')

    def run_script(self, *args: str, uv_version: str | None = None, **extra: str) -> subprocess.CompletedProcess[str]:
        """Run the installer with only the fake tools on the search path."""
        env = {"PATH": str(self.bin), "HOME": str(self.fake / "home"), "FAKE": str(self.fake),
               "FAKE_UV_VERSION": uv_version or uv_minimum(), "FAKE_PLUGIN_VERSION": plugin_version(), **extra}
        return subprocess.run(["sh", str(SCRIPT), *args], capture_output=True, text=True, timeout=60, check=False,
                              env=env)

    def log(self, name: str) -> str:
        """What the fake uv or curl was asked, or nothing."""
        path = self.fake / f"{name}.log"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def snapshot(self) -> dict[str, bytes]:
        """Every file in the fake folder except the call logs."""
        return {str(p.relative_to(self.fake)): p.read_bytes() for p in sorted(self.fake.rglob("*"))
                if p.is_file() and not p.is_symlink() and p.suffix != ".log"}

    def bumped(self, step: int) -> str:
        """The plugin version with its middle number moved by `step`."""
        major, minor, patch = (int(x) for x in plugin_version().split("."))
        return f"{major}.{minor + step}.{patch}"

    def test_check_reports_each_state_and_writes_nothing(self):
        cases = {"missing-no-uv": None, "missing": None, "ok": plugin_version(), "older": "0.0.9",
                 "newer": self.bumped(1)}
        for name, version in cases.items():
            with self.subTest(name):
                if name != "missing-no-uv":
                    self.add_uv()
                if version:
                    self.add_helper(version)
                before = self.snapshot()
                result = self.run_script("--check")
                wanted = "missing" if version is None else f"{name}:{self.fake / 'tools'}"
                self.assertEqual((result.stdout.strip(), result.returncode), (wanted, 0), result.stderr)
                self.assertEqual(self.snapshot(), before, "the check changed a file")
                self.assertNotIn("tool install", self.log("uv"))
                self.assertEqual(self.log("curl"), "", "the check downloaded something")

    def test_versions_are_compared_as_numbers(self):
        self.add_uv()
        major, minor, patch = (int(x) for x in plugin_version().split("."))
        self.add_helper(f"{major}.{minor + 10}.{patch}")             # 0.12.0 is above 0.2.0, though "1" sorts before "2"
        self.assertTrue(self.run_script("--check").stdout.startswith("newer:"))
        self.add_helper(f"{major}.{minor}.{patch}.1")
        self.assertTrue(self.run_script("--check").stdout.startswith("newer:"))
        self.add_helper(f"{major}.{minor}.{patch}.0")                # a missing last number counts as zero
        self.assertTrue(self.run_script("--check").stdout.startswith("ok:"))

    def test_newer_commands_are_left_alone(self):
        self.add_uv()
        self.add_helper(self.bumped(1))
        before = self.snapshot()
        result = self.run_script()
        self.assertEqual((result.stdout.strip(), result.returncode), (f"newer:{self.fake / 'tools'}", 0))
        self.assertEqual(self.snapshot(), before)
        self.assertNotIn("tool install", self.log("uv"))

    def test_install_passes_the_python_version_and_the_constraints_file(self):
        self.add_uv()
        self.add_helper("0.0.9")
        result = self.run_script()
        self.assertEqual((result.stdout.strip(), result.returncode), (f"ok:{self.fake / 'tools'}", 0), result.stderr)
        python = (PLUGIN_ROOT / ".python-version").read_text(encoding="utf-8").strip()
        self.assertIn(f"tool install --force --python {python} --constraints {CONSTRAINTS} {PLUGIN_ROOT}", self.log("uv"))
        self.assertEqual(self.log("curl"), "", "uv was there, so nothing is downloaded")

    def test_a_helper_from_the_previous_release_is_upgraded(self):
        self.add_uv()
        self.add_helper(self.bumped(-1))                    # what an existing user has installed
        self.assertTrue(self.run_script("--check").stdout.startswith("older:"))
        result = self.run_script()
        self.assertEqual((result.stdout.strip(), result.returncode), (f"ok:{self.fake / 'tools'}", 0), result.stderr)
        self.assertIn("tool install --force", self.log("uv"))

    def test_missing_uv_is_downloaded_at_the_fixed_version(self):
        write_script(self.bin / "curl", FAKE_CURL)
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"https://astral.sh/uv/{pinned_uv(SCRIPT)}/install.sh", self.log("curl"))
        self.assertTrue(result.stdout.startswith("ok:"), result.stdout)

    def test_uv_below_the_minimum_stops_and_is_not_replaced(self):
        self.add_uv()
        write_script(self.bin / "curl", FAKE_CURL)
        before = self.snapshot()
        result = self.run_script(uv_version="0.1.0")
        self.assertEqual(result.returncode, 3)
        self.assertIn("failed: uv is too old", result.stderr)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.log("curl"), "")
        self.assertNotIn("tool install", self.log("uv"))

    def test_a_failed_install_can_be_retried(self):
        write_script(self.bin / "curl", FAKE_CURL)
        failed = self.run_script(FAKE_INSTALL_FAILS="1")
        self.assertEqual(failed.returncode, 1)
        self.assertIn("could not be installed", failed.stderr)
        self.assertTrue((self.fake / "home" / ".local" / "bin" / "uv").exists(), "uv stays from the first attempt")
        again = self.run_script()
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(self.run_script("--check").stdout.strip(), f"ok:{self.fake / 'tools'}")


class InstallersAgreeTests(unittest.TestCase):
    """Both installers pin the same things and read them from the same files."""

    def test_same_uv_version(self):
        self.assertEqual(pinned_uv(SCRIPT), pinned_uv(WINDOWS_SCRIPT))

    def test_both_read_the_same_files(self):
        for script in (SCRIPT, WINDOWS_SCRIPT):
            text = script.read_text(encoding="utf-8")
            for name in ("pyproject.toml", ".python-version", "constraints.txt", "--constraints", "--python",
                         "required-version", "newer:", "older:", "ok:", "missing", "uv is too old"):
                self.assertIn(name, text, f"{script.name}: {name}")
            self.assertNotIn("plugin.json", text, f"{script.name} reads the version from a manifest")

    def test_both_download_the_fixed_uv_version_only(self):
        for script, name in ((SCRIPT, "install.sh"), (WINDOWS_SCRIPT, "install.ps1")):
            text = script.read_text(encoding="utf-8")
            self.assertRegex(text, rf"https://astral\.sh/uv/\$\w+/{re.escape(name)}")
            self.assertNotIn(f"astral.sh/uv/{name}", text, f"{script.name} downloads the newest uv")

    def test_the_pinned_uv_meets_the_minimum(self):
        as_numbers = [tuple(int(x) for x in v.split(".")) for v in (pinned_uv(SCRIPT), uv_minimum())]
        self.assertGreaterEqual(as_numbers[0], as_numbers[1])
        self.assertRegex(project()["tool"]["uv"]["required-version"], r"^>=\d+(\.\d+)*$")


class PinRecordTests(unittest.TestCase):
    """`setup/constraints.txt` follows `uv.lock`, and a changed pin comes with a new package version."""

    def test_constraints_equal_a_fresh_export_of_the_lock_file(self):
        if shutil.which("uv") is None:
            self.skipTest("uv is not installed")
        fresh = subprocess.run([sys.executable, str(REPO_ROOT / "tools" / "pins.py"), "--print"], capture_output=True,
                               text=True, timeout=120, check=False)
        self.assertEqual(fresh.returncode, 0, fresh.stderr)
        self.assertEqual(CONSTRAINTS.read_text(encoding="utf-8"), fresh.stdout,
                         "run: uv run python tools/pins.py")

    def test_constraints_name_the_package_version_and_exact_pins(self):
        text = CONSTRAINTS.read_text(encoding="utf-8")
        self.assertEqual(text.splitlines()[0], f"# jobkit {plugin_version()}")
        self.assertTrue(pins(text))
        for line in pins(text):
            self.assertRegex(line, r"^[A-Za-z0-9._-]+==[^=<>~!]+$")
        self.assertTrue(any(x.startswith("pypdf==") for x in pins(text)))

    def test_python_version_is_exact(self):
        self.assertRegex((PLUGIN_ROOT / ".python-version").read_text(encoding="utf-8").strip(), r"^\d+\.\d+\.\d+$")

    def test_a_changed_pin_comes_with_a_new_package_version(self):
        """Compared with the last commit: pins may only differ when the package version differs too."""
        if shutil.which("git") is None or not (REPO_ROOT / ".git").exists():
            self.skipTest("not a git checkout")
        old = {name: self.committed(name) for name in ("setup/constraints.txt", ".python-version", "setup/install",
                                                       "setup/install.ps1", "pyproject.toml")}
        if old["setup/constraints.txt"] is None or old["pyproject.toml"] is None:
            self.skipTest("the last commit has no pin records yet")
        old_version = tomllib.loads(old["pyproject.toml"])["project"]["version"]
        if old_version != plugin_version():
            return
        self.assertEqual(pins(CONSTRAINTS.read_text(encoding="utf-8")), pins(old["setup/constraints.txt"] or ""),
                         "a package pin changed: raise the version in pyproject.toml")
        self.assertEqual((PLUGIN_ROOT / ".python-version").read_text(encoding="utf-8").strip(),
                         (old[".python-version"] or "").strip(), "the Python pin changed: raise the version")
        for name in ("setup/install", "setup/install.ps1"):
            found = re.search(r"^\$?UV_?VERSION *= *'?([0-9.]+)", old[name] or "", re.M | re.I)
            if found:
                self.assertEqual(pinned_uv(PLUGIN_ROOT / name), found.group(1), "the uv pin changed: raise the version")

    @classmethod
    def committed(cls, name: str) -> str | None:
        """A plugin file as it is in the last commit, or None when it is not there.

        The plugin folder is tried first; the old repository-root path is the fallback, so the check
        still compares against a commit made before the files moved into `plugins/jobkit/`.
        """
        return cls.shown(f"plugins/jobkit/{name}") or cls.shown(name)

    @staticmethod
    def shown(path: str) -> str | None:
        """A file as it is in the last commit, or None when it is not there."""
        shown = subprocess.run(["git", "-C", str(REPO_ROOT), "show", f"HEAD:{path}"], capture_output=True,
                               text=True, timeout=30, check=False, env={**os.environ, "LC_ALL": "C"})
        return shown.stdout if shown.returncode == 0 else None


if __name__ == "__main__":
    unittest.main()
