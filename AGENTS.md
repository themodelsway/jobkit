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
- The user-facing skills are in `skills/` and ship as one plugin for Claude Code (`.claude-plugin/`) and Codex (root `plugin.json`, `.agents/plugins/marketplace.json`); `.claude/skills/` holds only the OpenSpec tooling. A plugin does not load this file, so every rule a plugin user needs is repeated inside the skills.
- Build a resume for a job description, or add a resume file: `resume-workflows` skill.
- Quiz or mock interview: `interview-prep` skill. Teach, explain or readiness: `tutor` skill.
- Read personal open items at the start of resume work with `profile open`; add with `profile open add TEXT`.
- Run tools as `uv run <command>` from the project folder (`uv sync` installs them into `.venv`; the skills and hooks run in Git Bash on Windows, which is a prerequisite).
- `query-resume for-jd` output is keyword and tag based; make the final picks yourself.

## Code conventions
- Code is the `jobkit` package in `src/jobkit/`. Import siblings as `from jobkit.resumes import resume_data`; never edit `sys.path`. A new tool needs a `[project.scripts]` entry in `pyproject.toml` (`tests/test_cli_contract.py` checks the list).
- Every tool has `build_parser()` and `main(argv) -> int`, does no work at import time, and raises `common.ToolError` for user mistakes (`common.run` turns it into an exit status). Verbs, stdin (`-`), `-o/--output`, and exit codes follow the `cli-conventions` spec.
- Every function typed and documented; about 20 lines, 40 at most. Records are `TypedDict`s or dataclasses. Shared helpers go in `common.py` and `resume_data.py`, not copied between tools. Use the `pythonic-tools` skill when writing Python.
- Format readers live in `resumes/extract.py`: a new format is one `@register` class.
- Checks (all need `uv sync`): `uv run python -m unittest discover -s tests -t .`, `uv run pyright`, `uv run ruff check src tests`, `uv run pylint src` (for tests add `--disable=missing-function-docstring,missing-class-docstring,protected-access,consider-using-with`). The pre-commit hook runs gitleaks, ruff, pyright and the tests (not pylint); enable with `git config core.hooksPath .githooks`.
- Skill text (`skills/`): what the user reads is plain English, in lines that start with `>`, with no commands, file names or technical words; commands and rules are for the agent. Skill and guide text names no app, model vendor or app-specific tool or variable: a skill finds its guides and `setup/` from its own folder, and describes a needed ability by what it does. The preflight, talking and rules blocks are identical in all three skills (`<!-- shared:... -->`); edit one and copy it to the others. `tests/test_plugin.py` enforces this, and `setup/install` is the only place that installs software, and only after the user says yes.
- Versions: `pyproject.toml` is the source; both plugin manifests carry the same version. After `uv lock` run `uv run python setup/pins.py`; a changed pin (packages, Python, uv) needs a new package version. The installers never downgrade and never replace an existing uv (`plugin/helper-versions` spec).
- Windows: every text file is read and written with `encoding="utf-8"` (ruff `PLW1514` enforces it); stored resume keys use forward slashes; `.gitattributes` keeps LF line endings; skills run commands by full path, not by editing the search path. `setup/install` is macOS and Linux only, `setup/install.ps1` is Windows only, and the skills choose by platform. The Windows installer can only be fully tested on Windows.
- A behaviour change updates the matching spec in `openspec/specs/` and the docs in the same change.

## Interview data
- All data is in one database, `~/.jobkit/data/jobkit.db`. Read and write it only through the commands (`prep`, `arch`, `lead`, `sessions`, `profile`, `process-resumes`; `readiness` and `jobkit export` are read-only); never open the database directly. To look at data use `jobkit export`. Each command is one transaction, and `jobkit backup` saves a copy. Run `jobkit init` once on a new machine.
- A match judgment's origin is `agent`, `code` or `fallback`, never an app or model name; stored `claude` values are legacy and are not rewritten.
- Teaching caps card confidence at 1; a passed quiz (`--quiz`) allows 2.
- Lifecycle words: maintenance = closed to new customers, no new features; sunset = has an end date. Seeded AWS values are unverified leads until refreshed.

## Resume data model
Parsing layouts, bullet ids and variants, and curation are described in `skills/resume-workflows/data-model.md` (it ships with the skill). Read it when you work on `src/jobkit/resumes/` or `tests/resumes/`.
