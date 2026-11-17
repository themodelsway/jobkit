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
  interview/             stories, leadership questions, role-knowledge cards, target companies, practice sessions, readiness
  interview/aws/         the AWS example track (engineering family); every other field is added with `cards track add`
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

Committed files must hold nothing personal: the contributor's name, phone, email, LinkedIn, resume folder, employers, clients or products, and nothing taken from the contributor's own data (resume lines, titles, certifications, degrees, figures, story details, years of experience, own vocabulary). The pre-commit hook and `tests/meta/test_no_personal.py` enforce it in two ways, both against the contributor's own database (`~/.jobkit`), never against anything in the repository:

- **Personal terms**: a list of words and patterns (below).
- **Stored-data check**: each line is compared with the stored data itself (below).

Examples in tests, docs and specs are made up and span role families (people, design, strategy, product, operations, engineering). Fictional employers are Acme names (Acme Corp, Acme 2, Acme-Labs); docs and specs may use Company X and Company Y. Real companies and brands are not used.

### Where the terms come from

| Source | What | How it is kept |
| --- | --- | --- |
| Derived | the contributor's name, the phone, email and LinkedIn in the saved header, the resume folder, the employer names found by `process-resumes`, the company folder of each resume file (the first folder on its path that is not a year, quarter, month or setup folder: `2026/Acme Air/me.docx` and `Acme Air/October/me.pdf` give Acme Air; a file directly in the resume folder gives none) | read from the database each time, so a new resume import or a header change is picked up at once; nothing is copied |
| Stored | products, extra clients, custom patterns, and the derived terms marked as ignored | the `term` table, changed with `profile terms` |

A derived term of four characters or fewer (for example ACME) matches only as a whole word. Other terms match anywhere, ignoring letter case.

### Commands

```
profile terms                        # list every term with its kind, match mode and source
profile terms add acme.ai --kind product
profile terms add "acme[ _.-]?ai" --kind client      # a pattern (regular expression), recognized by its characters
profile terms ignore WORD           # a personal term that is also an everyday word (it is not removed from the data)
profile terms rm acme.ai           # remove a stored term, or an ignore
profile terms import terms.txt       # one term per line, a line with pattern characters is a pattern
profile terms check --staged         # what the hook runs: the staged files as staged
profile terms check --all            # every file git would commit
profile terms check --all --exhaustive   # also the ignored common words, for a manual review
profile terms check --history       # every version of every file in the history, for a review before publishing
```

Run them as `uv run profile terms ...`. A hit prints `path:line: kind term 'text'` and the command exits 1. Fix the file, or ignore the term if it is a false alarm.

### Stored-data check

`profile terms check` also compares every line it reads with the contributor's stored data: resume lines with their variants and the wording of each file, summaries, headlines, profile points, titles, clients, education, certifications, stories and engagements, practice and leadership notes, the contributor's own theme and positioning words, what they are preparing for, and the extracted resume text in the output folder. jobkit's own seeded text (the card catalog, built-in questions and themes, the role families) is left out, so lines that quote it are not hits.

| Kind | A line is a hit when it |
| --- | --- |
| `phrase` | shares a run of five words with stored text, three of them not common words |
| `near-copy` | is at least 75% similar to a stored sentence (lines of 25 characters or more) |
| `value` | names a stored title, certification, degree or headline of two or more words |
| `figures` | holds two of the contributor's figures: percentages, amounts, or counts of something such as "40 accounts" |
| `fingerprint` | combines three distinctive terms: titles, certifications, the contributor's own vocabulary, skills of two or more words |

A hit prints `path:line: kind (source)`, where the source names the kind of record and its id, never the stored text. The comparison is rebuilt in memory from the database on every run and nothing is written to disk, so new data is checked from the next commit. A false alarm is cleared with `profile terms ignore TEXT`: ignored text is removed from a line before it is compared.

With `--staged` the check also warns, without failing, when the staged changes remove lines that match stored data: removed text stays in earlier commits. `profile terms check --history` reads every version of every file in the history of all branches, for a review before publishing.

### Common words

Some personal terms are also everyday words, for example an employer whose name is a common English word. Checking for such a term would flag many harmless lines, so mark it as a common word with `profile terms ignore WORD`; the hook and the normal check then skip it.

Before publishing, check the common words too with `profile terms check --all --exhaustive`. It lists each common word with the files and lines where it appears. Review the list by hand: most hits are harmless. The hook never runs this check.

### When it runs

- `.githooks/pre-commit` prints `Running pre-commit hooks ...` and runs `profile terms check --staged` (the step `personal terms and phrases`) before ruff and the tests. Enable the hook once per clone with `git config core.hooksPath .githooks`.
- `tests/meta/test_no_personal.py` runs the same check on every committable file, using the contributor's real home folder.
- With no database on the machine (a fresh clone, CI) both skip with a message. Only the generic checks (home paths, emails, phone numbers) run.

The term list is personal data: `jobkit export --only terms` shows it and `jobkit backup` includes it. Do not paste it into the repository, an issue or a pull request.
