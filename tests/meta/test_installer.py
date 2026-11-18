"""The helper installers: the check states, uv installed only on request, no downgrade, pinned versions, and the pin records.

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

from tests.meta.support import pyproject
from tests.support import PLUGIN_ROOT, REPO_ROOT

SCRIPT = PLUGIN_ROOT / "setup" / "install"
WINDOWS_SCRIPT = PLUGIN_ROOT / "setup" / "install.ps1"
CONSTRAINTS = PLUGIN_ROOT / "setup" / "constraints.txt"
ON_WINDOWS = sys.platform == "win32"
POWERSHELL = shutil.which("pwsh") or shutil.which("powershell")
CHECK_STATES = r"^(ok:.+|older(\+python)?:.+|newer:.+|missing(\+python)?|old-uv|no-uv|unsupported)$"
TOOLS = ("sh", "sed", "head", "tr", "uname", "dirname", "mktemp", "rm", "cat", "chmod", "mkdir", "grep", "awk")

FAKE_UV = """#!/bin/sh
# A stand-in for uv: answers the calls the installer makes and records each one.
echo "$*" >> "$FAKE/uv.log"
case "$1 $2" in
    "--version ") echo "uv $FAKE_UV_VERSION (fake)" ;;
    "python find") [ -z "${FAKE_NO_PYTHON:-}" ] || exit 2; echo "$FAKE/python" ;;
    "python dir") echo "${FAKE_PYTHON_DIR:-$FAKE/pythons}" ;;
    "cache dir") echo "${FAKE_CACHE:-$FAKE/cache}" ;;
    "tool dir") echo "$FAKE/tools" ;;
    "tool install")
        [ -z "${FAKE_INSTALL_FAILS:-}" ] || { printf '%s\n' "$FAKE_INSTALL_FAILS" >&2; exit 1; }
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


def plugin_version() -> str:
    """The package version, which is the version the installers want."""
    return pyproject()["project"]["version"]


def uv_minimum() -> str:
    """The oldest uv the installers accept."""
    return pyproject()["tool"]["uv"]["required-version"].removeprefix(">=")


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
                wanted = ({"missing-no-uv": "no-uv", "missing": "missing"}[name] if version is None
                          else f"{name}:{self.fake / 'tools'}")
                self.assertEqual((result.stdout.strip(), result.returncode), (wanted, 0), result.stderr)
                self.assertEqual(self.snapshot(), before, "the check changed a file")
                self.assertNotIn("tool install", self.log("uv"))
                self.assertEqual(self.log("curl"), "", "the check downloaded something")

    def test_check_says_when_python_must_be_downloaded_too(self):
        self.add_uv()
        python = (PLUGIN_ROOT / ".python-version").read_text(encoding="utf-8").strip()
        self.assertEqual(self.run_script("--check", FAKE_NO_PYTHON="1").stdout.strip(), "missing+python")
        self.assertIn(f"python find --no-cache --system --no-project {python}", self.log("uv"))
        self.add_helper("0.0.9")
        self.assertEqual(self.run_script("--check", FAKE_NO_PYTHON="1").stdout.strip(),
                         f"older+python:{self.fake / 'tools'}")
        self.assertEqual(self.run_script("--check").stdout.strip(), f"older:{self.fake / 'tools'}")

    def test_check_reports_a_uv_below_the_minimum_before_anything_is_asked(self):
        self.add_uv()
        self.assertEqual(self.run_script("--check", uv_version="0.1.0").stdout.strip(), "old-uv")
        self.add_helper(plugin_version())
        self.assertTrue(self.run_script("--check", uv_version="0.1.0").stdout.startswith("ok:"),
                        "ready commands need no uv update")

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

    def test_the_release_before_visual_render_and_batch_curation_is_upgraded(self):
        """0.3.1 lacks `visual render`, `visual compare`, `curate themes` and `match-score --key`, which the skills use."""
        self.add_uv()
        self.add_helper("0.3.1")
        self.assertTrue(self.run_script("--check").stdout.startswith("older:"))

    def test_missing_uv_is_not_downloaded_unless_asked(self):
        write_script(self.bin / "curl", FAKE_CURL)
        before = self.snapshot()
        result = self.run_script()
        self.assertEqual(result.returncode, 4)
        self.assertIn("failed: uv is not installed", result.stderr)
        self.assertEqual(self.log("curl"), "", "uv was downloaded without --with-uv")
        self.assertEqual(self.snapshot(), before)

    def test_missing_uv_is_downloaded_at_the_fixed_version_when_asked(self):
        write_script(self.bin / "curl", FAKE_CURL)
        result = self.run_script("--with-uv")
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

    def test_a_folder_uv_may_not_write_stops_the_install_before_uv_runs(self):
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            self.skipTest("the superuser may write anywhere")
        self.add_uv()
        locked = self.fake / "home" / "locked"
        locked.mkdir()
        locked.chmod(0o500)
        self.addCleanup(locked.chmod, 0o700)
        result = self.run_script(FAKE_CACHE=str(locked / "cache"))
        self.assertEqual(result.returncode, 5, result.stderr)
        self.assertIn("failed: not allowed to write to ~/locked/cache", result.stderr)
        self.assertNotIn(str(self.fake / "home"), result.stderr, "the home folder is shown as ~")
        self.assertNotIn("tool install", self.log("uv"))

    def test_the_python_folder_is_checked_only_when_python_is_downloaded(self):
        self.add_uv()
        self.assertEqual(self.run_script().returncode, 0)
        self.assertNotIn("python dir", self.log("uv"))
        self.add_helper("0.0.9")
        self.assertEqual(self.run_script(FAKE_NO_PYTHON="1").returncode, 0)
        self.assertIn("python dir", self.log("uv"))
        self.assertTrue((self.fake / "pythons").is_dir())

    def test_a_blocked_download_is_named(self):
        self.add_uv()
        result = self.run_script(FAKE_INSTALL_FAILS="  cause: dns error: failed to lookup address information")
        self.assertEqual(result.returncode, 6)
        self.assertIn("failed: could not download the required packages", result.stderr)

    def test_another_uv_failure_shows_its_last_line_without_the_home_folder(self):
        self.add_uv()
        home = self.fake / "home"
        result = self.run_script(FAKE_INSTALL_FAILS=f"error: no wheel for this platform in {home}/wheels")
        self.assertEqual(result.returncode, 1)
        self.assertIn("could not be installed (error: no wheel for this platform in ~/wheels)", result.stderr)
        self.assertNotIn(str(home), result.stderr)

    def test_a_failed_install_can_be_retried(self):
        write_script(self.bin / "curl", FAKE_CURL)
        failed = self.run_script("--with-uv", FAKE_INSTALL_FAILS="1")
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
                         "required-version", "newer:", "older", "ok:", "missing", "no-uv", "old-uv", "+python",
                         "python', 'find'" if script == WINDOWS_SCRIPT else "python find", "--with-uv",
                         "uv is too old", "uv is not installed", "--no-cache", "not allowed to write to",
                         "cache', 'dir'" if script == WINDOWS_SCRIPT else "cache dir"):
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
        self.assertRegex(pyproject()["tool"]["uv"]["required-version"], r"^>=\d+(\.\d+)*$")


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


class SetupScriptTests(unittest.TestCase):
    def test_install_script_is_present_and_strict(self):
        script = PLUGIN_ROOT / "setup" / "install"
        self.assertTrue(script.is_file())
        if not ON_WINDOWS:                                # Windows checkouts have no executable bit
            self.assertTrue(os.access(script, os.X_OK))
        text = script.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("#!/bin/sh"))
        self.assertIn("set -eu", text)
        self.assertIn("UV_NO_MODIFY_PATH=1", text)

    @unittest.skipIf(ON_WINDOWS, "needs a POSIX shell")
    def test_install_script_syntax(self):
        result = subprocess.run(["sh", "-n", str(PLUGIN_ROOT / "setup" / "install")], capture_output=True, text=True,
                                check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipIf(ON_WINDOWS, "needs a POSIX shell")
    def test_check_reports_a_known_state(self):
        result = subprocess.run(["sh", str(PLUGIN_ROOT / "setup" / "install"), "--check"], capture_output=True, text=True,
                                timeout=60, check=False)
        self.assertRegex(result.stdout.strip(), CHECK_STATES)

    @unittest.skipIf(ON_WINDOWS, "needs a POSIX shell")
    def test_shell_script_refuses_windows(self):
        with tempfile.TemporaryDirectory() as tmp:
            stub = Path(tmp) / "uname"
            stub.write_text("#!/bin/sh\necho MINGW64_NT-10.0\n", encoding="utf-8")
            stub.chmod(0o755)
            result = subprocess.run(["sh", str(PLUGIN_ROOT / "setup" / "install"), "--check"], capture_output=True,
                                    text=True, timeout=60, check=False, env={**os.environ, "PATH": f"{tmp}:{os.environ['PATH']}"})
        self.assertEqual((result.stdout.strip(), result.returncode), ("unsupported", 2))


class WindowsInstallScriptTests(unittest.TestCase):
    SCRIPT = PLUGIN_ROOT / "setup" / "install.ps1"

    def test_script_is_ascii_only(self):
        data = self.SCRIPT.read_bytes()
        self.assertEqual(data.decode("ascii"), data.decode("utf-8"))

    def test_script_downloads_to_a_file_and_leaves_settings_alone(self):
        text = self.SCRIPT.read_text(encoding="utf-8")
        for needed in ("UV_NO_MODIFY_PATH", "https://astral.sh/uv/$UvVersion/install.ps1", "-OutFile", "--check",
                       "'tool', 'install', '--force'", "$ErrorActionPreference = 'Stop'", "Remove-Item"):
            self.assertIn(needed, text)
        for forbidden in ("Read-Host", "Set-ExecutionPolicy", "| iex", "Invoke-Expression", "SetEnvironmentVariable"):
            self.assertNotIn(forbidden, text)

    def test_programs_run_only_through_the_helper_that_relaxes_errors(self):
        """Windows PowerShell 5.1 stops on any standard error line of a redirected program while the preference is
        'Stop', so every program runs through Invoke-Native, which relaxes it, and nothing else redirects."""
        text = self.SCRIPT.read_text(encoding="utf-8")
        helper = text[text.index("function Invoke-Native"):text.index("function Find-Uv")]
        self.assertIn("$ErrorActionPreference = 'Continue'", helper)
        rest = text.replace(helper, "")
        for redirect in ("2>", "*>", "& $uv", "& powershell", "& (Join-Path"):
            self.assertNotIn(redirect, rest)

    def test_uv_is_looked_for_in_the_user_profile(self):
        self.assertIn("$env:USERPROFILE", self.SCRIPT.read_text(encoding="utf-8"))

    def test_same_check_answers_as_the_shell_script(self):
        text = self.SCRIPT.read_text(encoding="utf-8")
        for form in ("ok:", "older", "newer:", "missing", "+python", "old-uv", "no-uv", "--with-uv", "unsupported"):
            self.assertIn(form, text)

    @unittest.skipUnless(POWERSHELL, "PowerShell is not installed")
    def test_script_parses_and_answers_check(self):
        assert POWERSHELL
        parse = subprocess.run([POWERSHELL, "-NoProfile", "-Command",
                                "$e=$null;[void][System.Management.Automation.Language.Parser]::ParseFile("
                                f"'{self.SCRIPT}',[ref]$null,[ref]$e);if($e){{$e;exit 1}}"],
                               capture_output=True, text=True, timeout=60, check=False)
        self.assertEqual(parse.returncode, 0, parse.stdout + parse.stderr)
        result = subprocess.run([POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(self.SCRIPT),
                                 "--check"], capture_output=True, text=True, timeout=60, check=False)
        self.assertRegex(result.stdout.strip(), CHECK_STATES)
