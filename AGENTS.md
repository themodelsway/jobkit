# jobkit

Resume tooling and interview prep. Features, setup and commands are in `README.md`; behaviour promises are in `openspec/specs/`; flags are in each tool's `--help`. This file holds only what is not obvious from those or from the code.

## Hard rules
- The resume folder (the `resume_root` setting; `profile status` shows it) is READ-ONLY. Never edit or write there, not even with Bash (an app's deny rules do not block shell writes).
- Committed files hold nothing personal (name, employers, folders, figures). Personal data lives only under the home folder (`~/.jobkit`, or `JOBKIT_HOME`), outside the repository; `tests/test_no_personal.py` enforces it.
- No phone, email or LinkedIn in the resume data. The test suite checks the stored data; `jobkit export --only resume-companies | grep -Ei '@|[0-9]{3}[ -][0-9]{3,4}'` shows any hit to review.
- Personal terms (name, contact details, resume folder, employers, products) are checked in every commit by `profile terms check --staged` (pre-commit hook) and `tests/test_no_personal.py`; add products with `profile terms add`. See the last section of `docs/manual.md`.
- Raw extracted text goes only in `output/` under the home folder.
- Never invent resume bullets; suggest edits to the user instead.
- Prefer Python scripts over `jq` for repeated tasks. If a question is needed, ask one at a time.

## Where to start
- The plugin is the `plugins/jobkit/` folder: skills, commands (`src/`, `pyproject.toml`, `.python-version`), `setup/` installers and both manifests. It ships for Claude Code and Codex, whose marketplace catalogs (`.claude-plugin/marketplace.json`, `.agents/plugins/marketplace.json`) stay at the repository root with `./plugins/jobkit` as the source. Everything else at the root (the uv workspace `pyproject.toml`, `uv.lock` and a `.python-version` equal to the plugin's, tests, docs, `openspec/`, `tools/`, `.claude/`) is for contributors and must not move into the plugin; a test enforces this. `.claude/skills/` holds only the OpenSpec tooling. A plugin does not load this file, so every rule a plugin user needs is repeated inside the skills.
- Build a resume for a job description, or add a resume file: `resume-workflows` skill.
- Helpers `resume-visual-scanner` (reads PDF pages) and `jd-matcher` (pass 1 of a match score): one definition per tool (`plugins/jobkit/agents/NAME.md`, and `.codex/agents/NAME.toml` for this checkout); the rules in both are copies of the `shared:visual-*` and `shared:match-pass-one` blocks in the `resume-workflows` skill, and a test keeps them equal.
- Quiz or mock interview: `interview-prep` skill. Teach, explain or readiness: `tutor` skill.
- Read personal open items at the start of resume work with `profile open`; add with `profile open add TEXT`.
- Run tools as `uv run <command>` from the repository root (the root `pyproject.toml` is a uv workspace around `plugins/jobkit`, with the one `uv.lock` and `.venv`; `uv sync` installs them; the skills and hooks run in Git Bash on Windows, which is a prerequisite).
- `query-resume for-jd` output is keyword and tag based; make the final picks yourself.

## Code conventions
- Code is the `jk` package (the import name of the `jobkit` distribution) in `plugins/jobkit/src/jk/`; the distribution, the plugin and the `jobkit` command keep the name `jobkit`. Import siblings as `from jk.resumes import resume_data`; never edit `sys.path`. A new tool needs a `[project.scripts]` entry in `plugins/jobkit/pyproject.toml` (`tests/test_cli_contract.py` checks the list).
- Every tool has `build_parser()` and `main(argv) -> int`, does no work at import time, and raises `common.ToolError` for user mistakes (`common.run` turns it into an exit status). Verbs, stdin (`-`), `-o/--output`, and exit codes follow the `cli-conventions` spec.
- Every function typed and documented; about 20 lines, 40 at most. Records are `TypedDict`s or dataclasses. Shared helpers go in `common.py` and `resume_data.py`, not copied between tools. Use the `pythonic-tools` skill when writing Python.
- Format readers live in `resumes/extract.py`: a new format is one `@register` class.
- Checks (all need `uv sync`, and run from the repository root): `uv run python -m unittest discover -s tests -t .`, `uv run pyright --project pyrightconfig.json`, `uv run ruff check plugins/jobkit/src tests tools`, `uv run pylint --rcfile .pylintrc plugins/jobkit/src` (for tests add `--disable=missing-function-docstring,missing-class-docstring,protected-access,consider-using-with`). The pre-commit hook runs gitleaks, ruff, pyright and the tests (not pylint); enable with `git config core.hooksPath .githooks`.
- Skill text (`plugins/jobkit/skills/`): what the user reads is plain English, in lines that start with `>`, with no commands, file names or technical words; commands and rules are for the agent. Skill and guide text names no app, model vendor or app-specific tool or variable: a skill finds its guides and `setup/` from its own folder, and describes a needed ability by what it does. The preflight, talking and rules blocks are identical in all three skills (`<!-- shared:... -->`); edit one and copy it to the others. `tests/test_plugin.py` enforces this, and `setup/install` is the only place that installs software, and only after the user says yes.
- Terms in user docs (README, `docs/`, specs): **jobkit** is the solution; **plugin** is the package installed into an app (install, update, remove); **app** is only the host, Claude Code or Codex; **agent** is the model running a skill (not "assistant"). The audience is "users of jobkit" and "contributors". What a skill does is agent driven: write it as "the skill tells the agent to...", never as a guarantee, and the user's go-ahead as "once the user responds with yes"; state as fact only what the code enforces.
- Versions: `plugins/jobkit/pyproject.toml` is the source; both plugin manifests carry the same version. After `uv lock` run `uv run python tools/pins.py`; a changed pin (packages, Python, uv) needs a new package version. The installers never downgrade and never replace an existing uv (`plugin/helper-versions` spec).
- Windows: every text file is read and written with `encoding="utf-8"` (ruff `PLW1514` enforces it); stored resume keys use forward slashes; `.gitattributes` keeps LF line endings; skills run commands by full path, not by editing the search path. `plugins/jobkit/setup/install` is macOS and Linux only, `plugins/jobkit/setup/install.ps1` is Windows only, and the skills choose by platform. The Windows installer can only be fully tested on Windows.
- A behaviour change updates the matching spec in `openspec/specs/` and the docs in the same change.

## Interview data
- All data is in one database, `~/.jobkit/data/jobkit.db`. Read and write it only through the commands (`prep`, `arch`, `lead`, `sessions`, `profile`, `process-resumes`; `readiness` and `jobkit export` are read-only); never open the database directly. To look at data use `jobkit export`. Each command is one transaction, and `jobkit backup` saves a copy. Run `jobkit init` once on a new machine.
- A match judgment's origin is `agent`, `code` or `fallback`, never an app or model name; stored `claude` values are legacy and are not rewritten.
- Teaching caps card confidence at 1; a passed quiz (`--quiz`) allows 2.
- Lifecycle words: maintenance = closed to new customers, no new features; sunset = has an end date. Seeded AWS values are unverified leads until refreshed.

## Resume data model
Parsing layouts, bullet ids and variants, and curation are described in `plugins/jobkit/skills/resume-workflows/data-model.md` (it ships with the skill). Read it when you work on `plugins/jobkit/src/jk/resumes/` or `tests/resumes/`.
