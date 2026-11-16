# Contributing to jobkit

This page is for contributors who work on jobkit from a checkout of the repository. Conventions for contributors and for coding agents are in `AGENTS.md`, which `CLAUDE.md` imports; the plugin's skills carry their own rules, because a plugin does not load either file. The promised behavior is in `openspec/specs/`. Using jobkit, and running its commands without a plugin, is described in the [README](../README.md).

## Setting up a checkout

Requirements: macOS, Linux or Windows with Git for Windows, [uv](https://docs.astral.sh/uv/) (it installs the pinned Python), and gitleaks for contributors who commit. poppler is optional: it improves PDF reading and draws the page pictures for a visual reading of any PDF (without it, pictures can be taken only from a plain scan).

```
uv sync                       # creates the environment and installs the commands into it
```

Optional tools, by system:

| Tool | macOS | Debian, Ubuntu | Fedora, RHEL | Arch |
|---|---|---|---|---|
| poppler (PDF reading and page pictures) | `brew install poppler` | `sudo apt install poppler-utils` | `sudo dnf install poppler-utils` | `sudo pacman -S poppler` |
| gitleaks (pre-commit secret scan) | `brew install gitleaks` | see the [gitleaks releases](https://github.com/gitleaks/gitleaks/releases) | see the releases | `sudo pacman -S gitleaks` |

Commands in a checkout run as `uv run <command>`, the same on macOS, Linux and Windows. Run them from the repository root: its `pyproject.toml` is a uv workspace around `plugins/jobkit`, so the one `uv.lock` and its environment are there. The pre-commit hook and the skills run in Git Bash on Windows. The first run, and the commands themselves, are the same as in [Command-line use](../README.md#command-line-use), with `uv run` in front of each command:

```
uv run jobkit init
uv run profile init --resume-root /path/to/resumes
```

An installed copy of the commands (`uv tool install`) does not follow later edits, so contributors who edit the code use the checkout.

## Installing the plugin from a checkout

This is optional, for local testing; a normal installation does not use it. Installing from the `themodelsway/jobkit` repository requires no extra steps. The plugin is the `plugins/jobkit/` folder of the repository, so the installed copy holds that folder and not the contributor files at the repository root (tests, documentation, OpenSpec files).

- **One session:** `claude --plugin-dir plugins/jobkit` loads the three skills in Claude Code for that session only.
- **An installed copy:** a local-folder installation from a working checkout must be added as a marketplace, not as the plugin folder alone, and a plain copy of the checkout also carries `.git` and every file Git ignores. A clean copy holds the two marketplace catalogs and the plugin, without `.git` or any ignored file. The copy script needs Git and Python 3.11 or newer, on macOS, Linux or Windows (on Windows, use the `py -3` launcher or any Python 3.11 or newer):

```
python3 tools/clean_copy.py FULL-PATH-OF-A-NEW-FOLDER
```

The copy holds the tracked files and new files Git does not ignore, and nothing else. It must be a new or empty folder outside the checkout. The folder (not the plugin folder inside it) is then added as the marketplace, with `/plugin marketplace add FULL-PATH-OF-A-NEW-FOLDER` in Claude Code or `codex plugin marketplace add FULL-PATH-OF-A-NEW-FOLDER` in Codex, and installation proceeds as in the [README](../README.md#install-on-claude-code). A local marketplace cannot be upgraded in place: an update means deleting the folder, running the script again and adding it again; editing the checkout does not change an installed copy.

## Layout

The plugin is the `plugins/jobkit/` folder, which holds everything used at run time: the skills, the commands and their project files, the installers and the manifests. The repository root holds the two marketplace catalogs and everything for contributors, none of which an installed plugin needs.

**The plugin (`plugins/jobkit/`)**

```
skills/                  the three skills: interview-prep, tutor, resume-workflows (with their guides)
agents/                  the two helpers for Claude Code: resume-visual-scanner, jd-matcher
src/jk/                  the commands (Python package)
  common.py, base.py     helpers every tool shares: home folder, errors, exit status, one transaction per command
  store.py, schema.py    the database: connection, transactions, numbered schema upgrades, backup and restore
  records.py, export.py  the kinds of stored data, and `jobkit export`
  admin.py               the `jobkit` command: init, status, export, backup
  setup_state.py         how far setup has got (`jobkit status --setup`)
  summary.py             the overview in one call (`jobkit status --summary`)
  user/                  settings, employers, open items and personal terms (`profile`)
  resumes/               reading, parsing, querying and building resumes, and the match score (`match_*` files)
  interview/             stories, leadership questions, drill cards, target companies, practice sessions, readiness
  interview/aws/         the one bundled example track; others are added with `arch track add`
setup/                   the helper setup the skills ask for; the skills tell the agent to run it once the user responds with yes
  install                macOS and Linux
  install.ps1            Windows
  constraints.txt        the exact package versions setup installs (generated by `tools/pins.py`)
  *.md                   the shared setup steps the skills read: preflight, first run, welcome, troubleshooting
pyproject.toml           the package and its version (the one source of the version)
.python-version          the Python version
plugin.json              plugin manifest for Codex
.claude-plugin/          plugin manifest for Claude Code
LICENSE, README.md       a copy of the license (a test keeps it equal to the root one) and a short usage page
```

**Repository root**

```
.claude-plugin/          marketplace catalog for Claude Code (source: ./plugins/jobkit)
.agents/plugins/         marketplace catalog for Codex (source: ./plugins/jobkit)
README.md, LICENSE       the documentation and the canonical license
```

**For contributors only**

```
tests/                   mirrors plugins/jobkit/src/jk; meta/ checks the repository's own files; every test runs in a throw-away home folder
openspec/specs/          the behavior each area promises (requirements and scenarios)
docs/                    manual.md (index), guides/ (one page per skill, with its commands), references/ (the stored data), contributing.md
tools/                   pins.py (regenerate the pinned versions), clean_copy.py (clean marketplace copy for a local install)
pyproject.toml, uv.lock  the contributor workspace: one lockfile and one environment around plugins/jobkit
.python-version          the same Python version as the plugin's
pyrightconfig.json       type-check settings
ruff.toml, .pylintrc     lint settings
.claude/                 OpenSpec workflow skills and commands for working on this repository in Claude Code
.codex/agents/           the two helpers for Codex in this checkout (a test keeps their rules equal to the plugin's)
.githooks/               the pre-commit hook
AGENTS.md, CLAUDE.md     guidance for coding agents (CLAUDE.md imports AGENTS.md)
```

**Outside the repository**

```
~/.jobkit/               the data: data/jobkit.db (everything, including the header), output/, backup/
```

## Development

```
uv run python -m unittest discover -s tests -t .    # unit and end-to-end tests (synthetic fixtures)
uv run pyright --project pyrightconfig.json         # type check (--project here is pyright's own option)
uv run ruff check plugins/jobkit/src tests tools    # lint (ruff.toml)
uv run pylint --rcfile .pylintrc plugins/jobkit/src # deeper lint (.pylintrc)
```

**Versions.** The version lives in `plugins/jobkit/pyproject.toml`; `plugins/jobkit/plugin.json` and `plugins/jobkit/.claude-plugin/plugin.json` must carry the same one (the tests check). After `uv lock`, regenerate the pinned versions with `uv run python tools/pins.py`. A change to any pin (`plugins/jobkit/setup/constraints.txt`, `plugins/jobkit/.python-version`, the uv version at the top of both installers) needs a new version in `plugins/jobkit/pyproject.toml`, so installed helpers are offered the update; the tests check this too.

**Pre-commit hook.** It runs gitleaks (secret scan of the staged changes), the personal-terms check, ruff, pyright and the tests before every commit. Enable it once per clone:

```
git config core.hooksPath .githooks
```

**New tools** follow the same shape (`build_parser()`, `main(argv) -> int`, typed functions) and need a `[project.scripts]` entry in `plugins/jobkit/pyproject.toml`.

## Keeping personal data out of commits

Committed files are meant to hold no names, employers or folders. The pre-commit hook and `tests/meta/test_no_personal.py` check that against the contributor's own list of personal terms; the [manual](manual.md#for-contributors-keeping-personal-data-out-of-commits) describes the list and the checks.

## Modules not yet used by a command

### Preparation planner (`jk.interview.prep_plan`)

Its contract is the `interview/preparation-planner` spec in `openspec/specs/`.

A pure function over plain records: `plan(snapshot, today, focus=(), reassess_days=30)` returns ordered, explained actions. It reads no database; the caller builds the `Snapshot`. The date is passed in, so the same input gives the same plan.

- `Competency`: `id`, `name`, `kind` (`technical`, `leadership`, `general`), `aliases`, `requires` (prerequisites), `related`. Aliases resolve to one competency; related competencies (ECS and Kubernetes) are never merged. `check_vocabulary` rejects a prerequisite loop, an alias with two targets and a reference to nothing. `SEED` is a small neutral list.
- `Fact` (engagement, fact id, competencies, `status` confirmed/proposed/unsure, `ownership` own/team/unclear), `Story` (engagement, competencies, done, ownership, facts), `Attempt` (competency, day, `kind` drill/quiz/lesson, `grade` 0 weak, 1 some gaps, 2 good), `Lead` (competency, `ref` of a stored resume line). A lead is a hint for a question, never evidence: it is not a fact and counts as no experience. The caller leaves out lines that are flagged, ignored or not demonstrated for that skill (`evidence.lead_lines`).
- Three kinds of evidence stay apart: experience (confirmed, own facts and stories, counted by distinct engagement), knowledge (a passed quiz or a good drill answer) and performance (graded drill answers). A quiz never creates experience, and a self-rating is never turned into a grade.
- `Action`: `competency`, `type` (`clarify_fact`, `teach_prerequisite`, `practise_concept`, `rehearse_story`, `reassess`), `reason_code`, `reason`, `evidence` and `observations` (`story:ID`, `fact:ENGAGEMENT/ID`, `attempt:ID`), plus `target`, `age_days`, `choices` (other stories on the same engagement), `transferable`, `self_rated` and `leads` (line references, for `profile_gap` only) where they apply. Reason codes: `fact_unconfirmed`, `ownership_unclear` (category 1), `prerequisite_unmet` (2), `profile_gap`, `untested`, `untested_with_story` (3), `weak`, `weak_with_story` (4), `answer_old` (5). `profile_gap` means nothing is recorded yet that shows the person used the competency (no confirmed fact or story, no graded drill, whatever a quiz showed); it asks for an example and never says the person has no experience. `untested` means experience is recorded but no drill is graded yet.
- Order: factual blocker, unmet prerequisite, untested (`profile_gap` before plain `untested`), observed weakness, due reassessment. Within a group, focused competencies first, then by id.
- Knowledge never expires: a quiz passed long ago still counts. An old good answer only gives a `reassess` action.
- `reassess_days` (the window the caller passes as `reassess_days`): a profile setting stored in the `setting` table, a whole number of days from 1 to 365, default 30 when unset. `profile.reassess_days()` returns it; `readiness`, the `sessions` queue and the caller of `plan` all read it, and `--days N` overrides it for one run.
