"""Checks the plugin packaging for both apps: manifests, shipped skills, shared text and plain wording.

Run: uv run python -m unittest discover -s tests -t .
"""
import argparse
import importlib
import json
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
SKILLS = PLUGIN_ROOT / "skills"
SHIPPED = {"interview-prep", "tutor", "resume-workflows"}
SHARED = ("preflight", "talking", "rules")

# Words that must not appear in what a skill says to the user (lines that start with `>`).
BANNED = re.compile(
    r"\b(json|database|hash|seed|tier|confidence|curation|needs[ _]review|jobkit|process-resumes|query-resume|"
    r"build-resume|sessions? (?:log|new)|id)\b|\bJD\b|~/|\.json\b|\.md\b|\.db\b|--\w",
    re.IGNORECASE)


def pyproject() -> dict:
    return tomllib.loads((PLUGIN_ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def skill_text(name: str) -> str:
    return (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")


def shared_block(text: str, name: str) -> str:
    match = re.search(rf"<!-- shared:{name} -->\n(.*?)<!-- /shared:{name} -->", text, re.DOTALL)
    assert match, f"shared block {name!r} not found"
    return match.group(1)


def all_skill_files() -> list[Path]:
    return sorted(p for p in SKILLS.rglob("*") if p.is_file())


def parser_words(parser: argparse.ArgumentParser) -> set[str]:
    """Every sub-command name found under a parser, at any depth."""
    words: set[str] = set()
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, sub in action.choices.items():
                words.add(name)
                words |= parser_words(sub)
    return words


MANIFESTS = (PLUGIN_ROOT / ".claude-plugin" / "plugin.json", PLUGIN_ROOT / "plugin.json")
MARKETPLACES = (REPO_ROOT / ".claude-plugin" / "marketplace.json", REPO_ROOT / ".agents" / "plugins" / "marketplace.json")
# An agent app, a model vendor or an app-specific tool or variable: none may be named in shipped skill text.
APP_NAMES = re.compile(r"claude|codex|anthropic|openai|chatgpt|gemini|copilot|cursor\b|websearch|webfetch|"
                       r"\bmcp\b|\$\{|plugin_root|skill_dir", re.IGNORECASE)
# Wording that promises more than local storage.
STAYS_LOCAL = re.compile(r"everything (personal )?stays on your|all your data kept on|never leaves your|"
                         r"keep your data on your own computer", re.IGNORECASE)
GUIDE_REF = re.compile(r"`([\w./-]+\.md)` \((?:in|a path from) this skill's folder\)")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def rel(path: Path) -> str:
    """A path relative to the repository, for messages."""
    return str(path.relative_to(REPO_ROOT))


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


class PrivacyWordingTests(unittest.TestCase):
    def test_no_user_facing_text_says_everything_stays_on_the_computer(self):
        texts = {name: (REPO_ROOT / name).read_text(encoding="utf-8")
                 for name in ("README.md", "plugins/jobkit/README.md")}
        texts |= {rel(path): path.read_text(encoding="utf-8") for path in (*MANIFESTS, *MARKETPLACES)}
        texts |= {rel(p): p.read_text(encoding="utf-8") for p in all_skill_files()}
        for name, text in texts.items():
            hit = STAYS_LOCAL.search(text)
            self.assertIsNone(hit, f"{name} says {hit.group(0) if hit else ''!r}")

    def test_readme_points_at_the_app_for_how_the_model_handles_content(self):
        privacy = (REPO_ROOT / "README.md").read_text(encoding="utf-8").split("## Privacy", 1)[1]
        self.assertIn("stored in the `~/.jobkit` folder", privacy)
        self.assertIn("privacy settings you have configured", privacy)

    def test_consent_question_says_where_the_data_is_kept(self):
        text = shared_block(skill_text("tutor"), "preflight")
        (question,) = [x for x in text.splitlines() if "Is that OK?" in x]
        self.assertIn("kept in a folder on your own computer", question)


class ShippedSkillTests(unittest.TestCase):
    def test_only_the_user_skills_ship(self):
        self.assertEqual({p.name for p in SKILLS.iterdir() if p.is_dir()}, SHIPPED)

    def test_frontmatter(self):
        for name in SHIPPED:
            head = re.match(r"---\n(.*?)\n---\n", skill_text(name), re.DOTALL)
            self.assertIsNotNone(head, name)
            fields = dict(line.split(": ", 1) for line in head.group(1).splitlines() if ": " in line)
            self.assertEqual(fields.get("name"), name)
            self.assertTrue(fields.get("description", "").strip(), name)

    def test_no_checkout_references(self):
        for path in all_skill_files():
            text = path.read_text(encoding="utf-8")
            for bad in (".venv", ".claude/", "CLAUDE.md", "AGENTS.md"):
                self.assertNotIn(bad, text, f"{rel(path)} mentions {bad}")

    def test_skills_stay_under_500_lines(self):
        for name in SHIPPED:
            self.assertLess(len(skill_text(name).splitlines()), 500, name)

    def test_data_model_notes_ship_with_resume_workflows(self):
        self.assertTrue((SKILLS / "resume-workflows" / "data-model.md").is_file())
        self.assertIn("`data-model.md` (in this skill's folder)", skill_text("resume-workflows"))

    def test_guides_named_in_skills_exist(self):
        named: set[Path] = set()
        for name in SHIPPED:
            refs = GUIDE_REF.findall(skill_text(name))
            for ref in refs:
                target = (SKILLS / name / ref).resolve()
                self.assertTrue(target.is_file(), f"{name}: {ref}")
                named.add(target)
        guides = {p.resolve() for p in all_skill_files() if p.name != "SKILL.md"}
        self.assertEqual(guides - named, set(), "a guide ships that no skill names")

    def test_tutor_reads_the_architecture_guide_from_interview_prep(self):
        self.assertIn("`../interview-prep/architecture.md` (a path from this skill's folder)", skill_text("tutor"))

    def test_skills_and_guides_name_no_app_vendor_or_app_tool(self):
        for path in all_skill_files():
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                hit = APP_NAMES.search(line)
                self.assertIsNone(hit, f"{rel(path)}:{number} names {hit.group(0) if hit else ''!r}")

    def test_vendor_facts_come_from_official_documentation(self):
        text = (SKILLS / "interview-prep" / "architecture.md").read_text(encoding="utf-8")
        self.assertIn("search and read the vendor's official documentation", text)


def tool_parsers() -> dict[str, argparse.ArgumentParser]:
    """Every installed command name with its parser."""
    parsers = {}
    for name, target in pyproject()["project"]["scripts"].items():
        module, func = target.split(":")
        assert func == "main", f"{name} must point at main"
        parsers[name] = importlib.import_module(module).build_parser()
    return parsers


def subparsers_of(parser: argparse.ArgumentParser) -> dict | None:
    """The sub-command choices of a parser, or None when it has none."""
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action.choices
    return None


def shell_part(span: str) -> str:
    """The span up to a pipe into another program (a pipe inside [...] is a choice, not a pipe)."""
    depth = 0
    for index, char in enumerate(span):
        depth += (char == "[") - (char == "]")
        if char == "|" and depth <= 0 and span[index - 1:index] == " ":
            return span[:index]
    return span


def check_span(span: str, parsers: dict[str, argparse.ArgumentParser]) -> str | None:
    """Why a written command is wrong, or None when it is right or not a command."""
    tokens = shell_part(span).split()
    if not tokens or tokens[0] not in parsers:
        return None
    chain = [parsers[tokens[0]]]
    rest = tokens[1:]
    while rest and re.fullmatch(r"[a-z][a-z0-9-]*", rest[0]):
        choices = subparsers_of(chain[-1])
        if choices is None:
            break
        if rest[0] not in choices:
            return f"unknown subcommand {rest[0]!r}"
        chain.append(choices[rest[0]])
        rest = rest[1:]
    known = {"-h", "--help"}
    for parser in chain:
        known |= set(parser._option_string_actions)
    tail = re.sub(r'"[^"]*"', "", " ".join(rest))
    for option in re.findall(r"(?<![\w-])(--?[A-Za-z][\w-]*)", tail):
        if option not in known:
            return f"unknown option {option!r}"
    return None


def checked_files() -> list[Path]:
    """Skill pages and user docs whose written commands are checked."""
    docs = REPO_ROOT / "docs"
    return sorted([*SKILLS.glob("*/*.md"), *(docs / "guides").glob("*.md"), docs / "explore.md", docs / "manual.md"])


class CommandNameTests(unittest.TestCase):
    def test_check_span(self):
        parsers = tool_parsers()
        for span in ('prep set STORY_ID FIELD "VALUE"', 'sessions new "title" --mode tutor [--area A]',
                     "profile terms [list | add TEXT]", "readiness --jd -", "lead profile show",
                     'build-resume --title COMPANY-ID="Title"', "sessions resume ID"):
            self.assertIsNone(check_span(span, parsers), span)
        for span in ("sessions log ID --due", "arch drill ID"):
            self.assertIsNotNone(check_span(span, parsers), span)

    def test_written_commands_exist(self):
        parsers = tool_parsers()
        failures = []
        for path in checked_files():
            for span in re.findall(r"`([^`\n]+)`", path.read_text(encoding="utf-8")):
                problem = check_span(span, parsers)
                if problem:
                    failures.append(f"{rel(path)}: `{span}`: {problem}")
        self.assertEqual(failures, [], "\n".join(failures))


class SharedTextTests(unittest.TestCase):
    def test_helpers_keep_the_skill_rules(self):
        """Each helper definition, for both tools, carries the same rules as the skill (one source of truth)."""
        import tomllib  # pylint: disable=import-outside-toplevel

        def block(text: str, name: str) -> str:
            return " ".join(shared_block(text, name).split())
        skill = skill_text("resume-workflows")
        helpers = {"resume-visual-scanner": ("visual-transcript", "visual-json"), "jd-matcher": ("match-pass-one",)}
        for helper, blocks in helpers.items():
            claude = (PLUGIN_ROOT / "agents" / f"{helper}.md").read_text(encoding="utf-8")
            codex = tomllib.loads((REPO_ROOT / ".codex" / "agents" / f"{helper}.toml").read_text(encoding="utf-8"))
            self.assertTrue(claude.startswith(f"---\nname: {helper}\n"), helper)
            self.assertEqual(codex["name"], helper)
            self.assertIn(f"`{helper}`", skill)
            for name in blocks:
                self.assertEqual(block(claude, name), block(skill, name), name)
                self.assertEqual(block(codex["developer_instructions"], name), block(skill, name), name)

    def test_shared_blocks_are_identical(self):
        for block in SHARED:
            texts = {name: shared_block(skill_text(name), block) for name in SHIPPED}
            self.assertEqual(len(set(texts.values())), 1, f"{block} differs between skills")

    def test_rules_block_has_the_five_rules(self):
        rules = shared_block(skill_text("tutor"), "rules")
        for phrase in ("only through the commands", "read-only", "Never invent", "phone number", "JOBKIT_HOME"):
            self.assertIn(phrase, rules)

    def test_preflight_asks_before_installing(self):
        text = shared_block(skill_text("tutor"), "preflight")
        for line in text.splitlines():
            if "setup/install" in line:
                self.assertIn("--check", line, "only the read-only check may be named before the user agrees")
        self.assertLess(text.index("Is that OK?"), text.index("without `--check`"))
        self.assertIn("install nothing", text)

    def test_preflight_picks_the_helper_by_platform(self):
        text = shared_block(skill_text("tutor"), "preflight")
        self.assertIn('sh "PLUGIN/setup/install" --check', text)
        self.assertIn('powershell.exe -NoProfile -ExecutionPolicy Bypass -File '
                      '"PLUGIN/setup/install.ps1" --check', text)
        self.assertIn("PLUGIN below is the folder two levels above this skill file", text)
        self.assertIn("never from the working folder", text)
        self.assertNotIn("Set-ExecutionPolicy", text)

    def said(self) -> list[str]:
        """The lines of the preflight that the user reads."""
        return [x.strip() for x in shared_block(skill_text("tutor"), "preflight").splitlines()
                if x.strip().startswith(">")]

    def test_newer_helper_is_ready_and_never_installed_over(self):
        text = shared_block(skill_text("tutor"), "preflight")
        self.assertIn("`ok:FOLDER` or `newer:FOLDER`: the helper is ready", text)
        self.assertIn("never offer to install over it", text)
        self.assertNotIn("`newer:FOLDER`: the helper must", text)

    def test_failure_line_does_not_claim_nothing_changed(self):
        failed = [x for x in self.said() if x.startswith("> Setup did not finish")]
        self.assertEqual(len(failed), 2)
        for line in failed:
            self.assertNotIn("Nothing was changed", line)
        self.assertTrue(any("try again" in x for x in failed))
        self.assertTrue(any("too old" in x and "won't replace" in x for x in failed))

    def test_blocked_write_names_the_folder_and_keeps_protections_on(self):
        text = shared_block(skill_text("tutor"), "preflight")
        self.assertIn("never suggest turning the app's protections off", text)
        self.assertTrue(any("nothing was saved" in x and x.endswith("DATA_FOLDER") for x in self.said()))

    def test_unsupported_environment_is_said_plainly_and_installs_nothing(self):
        text = shared_block(skill_text("tutor"), "preflight")
        self.assertIn("`unsupported`: install nothing", text)
        self.assertTrue(any("isn't available with this app on this kind of computer yet" in x for x in self.said()))

    def test_preflight_explains_git_for_windows_in_plain_words(self):
        said = [x for x in shared_block(skill_text("tutor"), "preflight").splitlines() if x.strip().startswith(">")]
        self.assertTrue(any("Git for Windows" in x and "git-scm.com" in x for x in said))

    def test_commands_run_by_full_path_not_by_editing_the_search_path(self):
        for name in SHIPPED:
            text = skill_text(name)
            self.assertNotIn('PATH="', text, name)
            self.assertIn('"FOLDER/arch" next', text, name)

    def test_folders_are_quoted_because_they_may_have_spaces(self):
        for name in SHIPPED:
            text = skill_text(name)
            self.assertIn('--resume-root "FOLDER"', text, name)
            self.assertIn("in quotes", text, name)


PRODUCT_NAME = "Jobkit engine"   # the one place the product name may appear in user-facing lines (the setup question)


class PlainLanguageTests(unittest.TestCase):
    def test_user_facing_lines_have_no_technical_words(self):
        for name in SHIPPED:
            for number, line in enumerate(skill_text(name).splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith(">"):
                    hit = BANNED.search(stripped.replace(PRODUCT_NAME, ""))
                    self.assertIsNone(hit, f"{name}:{number} says {hit.group(0) if hit else ''!r}: {stripped}")

    def test_there_is_user_facing_wording(self):
        for name in SHIPPED:
            said = [x for x in skill_text(name).splitlines() if x.strip().startswith(">")]
            self.assertGreaterEqual(len(said), 8, name)


ON_WINDOWS = sys.platform == "win32"
POWERSHELL = shutil.which("pwsh") or shutil.which("powershell")


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
        self.assertRegex(result.stdout.strip(), r"^(ok:.+|older:.+|newer:.+|missing|unsupported)$")

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
                       "tool install --force", "$ErrorActionPreference = 'Stop'", "Remove-Item"):
            self.assertIn(needed, text)
        for forbidden in ("Read-Host", "Set-ExecutionPolicy", "| iex", "Invoke-Expression", "SetEnvironmentVariable"):
            self.assertNotIn(forbidden, text)

    def test_same_check_answers_as_the_shell_script(self):
        text = self.SCRIPT.read_text(encoding="utf-8")
        for form in ("ok:", "older:", "newer:", "missing", "unsupported"):
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
        self.assertRegex(result.stdout.strip(), r"^(ok:.+|older:.+|newer:.+|missing|unsupported)$")


if __name__ == "__main__":
    unittest.main()
