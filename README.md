# jobkit

jobkit supports interview preparation through tutoring, mock interviews and readiness reports. Stored resumes provide the experience behind the stories and questions. Resume tailoring for job postings is available as an early preview.

jobkit provides three skills for Claude Code and Codex: interview practice, tutoring with readiness reports, and resume workflows. Requests use plain language; the skills run the required commands.

![License: Apache 2](https://img.shields.io/badge/License-Apache_2-2ea44f?labelColor=555555) ![macOS: Claude Code and Codex](https://img.shields.io/badge/macOS-Claude_Code_and_Codex-2ea44f?logo=apple&logoColor=white&labelColor=555555) ![Linux: Claude Code and Codex](https://img.shields.io/badge/Linux-Claude_Code_and_Codex-2ea44f?labelColor=555555&logo=data:image/svg%2Bxml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCI%2BPGVsbGlwc2UgY3g9IjEyIiBjeT0iMTQuNSIgcng9IjcuMiIgcnk9IjguNiIgZmlsbD0iIzM2MzYzNiIvPjxjaXJjbGUgY3g9IjEyIiBjeT0iNy41IiByPSI1IiBmaWxsPSIjMzYzNjM2Ii8%2BPGVsbGlwc2UgY3g9IjEyIiBjeT0iMTUuOCIgcng9IjQuMiIgcnk9IjYiIGZpbGw9IiNmZmYiLz48Y2lyY2xlIGN4PSIxMC4yIiBjeT0iNi42IiByPSIxLjIiIGZpbGw9IiNmZmYiLz48Y2lyY2xlIGN4PSIxMy44IiBjeT0iNi42IiByPSIxLjIiIGZpbGw9IiNmZmYiLz48Y2lyY2xlIGN4PSIxMC40IiBjeT0iNi43IiByPSIuNSIgZmlsbD0iIzAwMCIvPjxjaXJjbGUgY3g9IjEzLjYiIGN5PSI2LjciIHI9Ii41IiBmaWxsPSIjMDAwIi8%2BPGVsbGlwc2UgY3g9IjEyIiBjeT0iOS4yIiByeD0iMi4yIiByeT0iMS4xIiBmaWxsPSIjZjVhNjIzIi8%2BPGVsbGlwc2UgY3g9IjgiIGN5PSIyMi42IiByeD0iMyIgcnk9IjEuMiIgZmlsbD0iI2Y1YTYyMyIvPjxlbGxpcHNlIGN4PSIxNiIgY3k9IjIyLjYiIHJ4PSIzIiByeT0iMS4yIiBmaWxsPSIjZjVhNjIzIi8%2BPC9zdmc%2B) ![Windows: Claude Code](https://img.shields.io/badge/Windows-Claude_Code-007ec6?labelColor=555555&logo=data:image/svg%2Bxml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCI%2BPHBhdGggZmlsbD0iI2ZmZiIgZD0iTTAgMy40IDkuOCAydjkuNEgwek0xMSAxLjggMjQgMHYxMS40SDExek0wIDEyLjZoOS44VjIyTDAgMjAuNnpNMTEgMTIuNmgxM1YyNGwtMTMtMS44eiIvPjwvc3ZnPg==)

```
                                          Agent
                    ┌───────────────────────────────────────────────┐
  Resumes      ───► │            Claude Code / Codex                │
  Job posting  ───► │       (Skills + jobkit CLI tools)             │
                    └─────────────┬──────────────────────┬──────────┘
                  (organize as    │                      │ (use targeted context
                structured data)  │                      │ from the jobkit datastore)
                                  ▼                      ▼
                         jobkit datastore:          mock interviews and lessons,
                         resumes, stories,          readiness reports, draft
                         sessions, match results    resume (preview)
                     
```

**Where to go next**

- Using jobkit with Claude Code: [Install on Claude Code](#install-on-claude-code)
- Using jobkit with Codex: [Install on Codex](#install-on-codex)
- Using the commands directly, or contributing: [For contributors and command-line users](#for-contributors-and-command-line-users)

## Quick start

After installation, Claude Code or Codex accepts requests in plain words from any folder. The first request leads to an offer to set up the helper ([What setup installs](#what-setup-installs)); one yes is needed.

1. **Resume import.** The skill takes the folder that holds the resumes, finds the resume files (PDF, Word, Markdown or text) in it and its subfolders, previews what was found, and then reads them. Resume files are only read, never changed.
2. **Topic instruction.** The tutor explains a topic, a question or one of the user's stories first, then checks understanding with a short quiz.
3. **Practice.** A mock interview asks first, gives no hints, then grades the answers. A session can be stopped and resumed later.
4. **Readiness assessment.** A report shows what has been rehearsed, what is solid and what is still untested, optionally for a supplied job posting.
5. **Early preview: resume tailoring.** For a supplied job posting, the skill builds a tailored draft resume or estimates how well the stored resumes match the posting.

## Features

Each step above is one of the three skills. The three skills share one datastore, so information recorded through one skill is available to the others.

### Resumes

- **One store from many resumes.** Every resume is read once, split by employer, and merged. Wording that appears in several resumes is kept once, with its sources.
- **Incremental.** Files that have not changed are skipped; new files are added; deleted or renamed files are removed.
- **Wrong figures can be flagged.** A figure known to be wrong can be listed, so lines that use it are marked and left out of matching.

### Learning with the tutor

The tutor teaches a card, question or story first, then checks understanding with a short quiz. What has been taught is recorded, so the readiness report can tell taught from tested.

### Mock interviews and practice

- **Stories.** STAR stories (situation, task, action, result) seeded from the resumes, one per employer and theme. Each can hold a metric with a recorded basis (measured, estimated, stated or unknown), spoken 60-second and 2-minute versions, and follow-up questions.
- **Technical drill cards.** Cards for the services, decision pairs and scenarios of the technologies an interview covers. One example technology is bundled, and any other is added from a JSON topic list, with no code. Lifecycle facts such as "closed to new customers" or "sunset" are recorded only with a link to the vendor's own documentation, never from memory.
- **Leadership questions.** A question set (roadmapping, mentoring, conflict, prioritisation and more), each with the user's principle and one example per recent employer.
- **Practice sessions.** Resumable. A session keeps the complete answers and grades; later drills add entries and never edit old ones.
- **Mock interview.** The interview-prep skill asks first, gives no hints, then grades.

### Readiness

A report of coverage and evidence per area, optionally limited to one job posting. Each card or question reads as untested, some gaps, solid-once, solid-repeated, aging or solid-unlogged (confidence recorded by hand, no logged answer); stories show their status and recent rehearsal. There is deliberately no single score.

### Resume tailoring and match score (early preview)

Resume tailoring and match scoring are early previews. Their output requires review before use.

- **Tailoring.** Given a job posting, it builds a resume from the stored lines. It ranks the lines per employer, suggests opening summaries, lists the skills the posting asks for that no stored line supports, and writes a Markdown draft. The draft requires review before use.
- **Match score.** It rates how well the resume lines cover a posting: a lower and an upper score, the requirements the resumes do not show yet, and the assumptions made. It is an estimate of coverage. It is not any employer's applicant-tracking score, and it does not predict whether the user will be hired.

## Supported apps and systems

| App | Where | macOS | Linux | Windows |
|---|---|---|---|---|
| Claude Code | terminal, desktop app, IDE extensions | yes | yes | yes, with Git for Windows |
| Codex | command line (`codex`), running locally | yes | yes | not yet |

Not supported: Codex on Windows, the Codex IDE extension and hosted (cloud) Codex. On an unsupported combination the skills say so and install nothing. Checked with Claude Code 2.1 and Codex CLI 0.167 on macOS.

## Install on Claude Code

### macOS and Linux

1. Marketplace registration, in Claude Code: `/plugin marketplace add themodelsway/jobkit`
2. Plugin installation: `/plugin install jobkit@jobkit`
3. A new session makes the installed skills available; requests use plain language (see [Quick start](#quick-start)).

### Windows

Claude Code on Windows runs its commands through Git for Windows, a prerequisite that is not needed again when already installed:

1. Git installation, in a terminal: `winget install --id Git.Git -e`, or the installer from [git-scm.com](https://git-scm.com/download/win) with the standard options.
2. Restarting Claude Code makes Git available to it.
3. The same three steps as for macOS and Linux follow.

Setup installs [uv](https://docs.astral.sh/uv/) when it is missing. [What setup installs](#what-setup-installs) explains when setup runs.

### After installing

- **Skills installed:** `jobkit:interview-prep` (mock interview), `jobkit:tutor` (teaching and readiness reports) and `jobkit:resume-workflows` (add a resume, tailor a resume for a job posting).
- **Update:** `/plugin marketplace update jobkit`, then `/plugin update jobkit@jobkit`, then restart Claude Code. The next time a skill starts it notices the commands are older and offers to update them.
- **Remove:** `/plugin uninstall jobkit@jobkit`. `~/.jobkit` and your data are left alone, and so are the commands (see [Removing the commands](#removing-the-commands)).
- **Trying it from a checkout:** `claude --plugin-dir .` loads the three skills for one session.

## Install on Codex

Codex support is for the Codex command line on macOS and Linux, running locally.

1. Marketplace registration: `codex plugin marketplace add themodelsway/jobkit`
2. Plugin installation: `codex plugin add jobkit@jobkit`
3. Starting `codex` makes the installed skills available; requests use plain language (see [Quick start](#quick-start)).

Codex runs commands in a sandbox that can read your files but, by default, cannot write outside the folder you started it in and cannot go online. jobkit keeps its data in `~/.jobkit`, so allow that one folder. Either approve it when Codex asks, or add this to `~/.codex/config.toml`, with the full path that `echo ~/.jobkit` prints in a terminal:

```
[sandbox_workspace_write]
writable_roots = ["FULL-PATH-OF-YOUR-HOME-FOLDER/.jobkit"]
```

The first-time setup also downloads and installs software (see [What setup installs](#what-setup-installs)), which the sandbox blocks: approve that step when Codex asks. If it was blocked, the skill says that setup did not finish; allow it and ask again, and it carries on from where it stopped. If a save is blocked later, the skill says that nothing was saved and names the folder to allow. Do not turn the sandbox off for this.

- **Skills installed:** the same three, `interview-prep`, `tutor` and `resume-workflows`, from the same files as in Claude Code.
- **Update:** `codex plugin marketplace upgrade jobkit`, then `codex plugin add jobkit@jobkit` again. The next time a skill starts it offers to update the commands.
- **Remove:** `codex plugin remove jobkit@jobkit`, and `codex plugin marketplace remove jobkit` to forget the marketplace. Your data and the commands are left alone.

## What setup installs

The first time a skill runs, in either app, it says it needs to set up a small helper and asks whether that is OK. On a no it installs nothing. On a yes it runs `setup/install` (`setup/install.ps1` on Windows), which installs exactly this:

| What | Version | From | When |
|---|---|---|---|
| [uv](https://docs.astral.sh/uv/), the installer tool | 0.13.7, the same on every system | astral.sh | only if uv is not on the computer |
| Python | 3.14 (the exact version is in `.python-version`) | uv's own Python builds | if uv does not already have that version |
| Python packages | the exact versions in `setup/constraints.txt` | PyPI | always |
| the jobkit commands | the plugin's version | the plugin's own files | always |

- **Own Python not required.** Setup uses a separate Python installation managed by uv, apart from any Python already on the computer; nothing else uses it. `uv python list --only-installed` lists Python installations managed by uv.
- A uv that is already on the computer is used as it is and never replaced. If it is older than the minimum in `pyproject.toml` (`required-version`), setup stops and says so; uv must be updated before setup is requested again.
- Setup never downgrades: if the installed commands are newer than the plugin, it changes nothing.
- It does not edit your shell settings. The commands go in uv's tool folder and the skills run them by full path.
- If setup stops half way (for example offline), what it already installed stays; asking again finishes it.
- Your data is kept in `~/.jobkit` (on Windows, the `.jobkit` folder inside your user folder).

## Using both apps

Claude Code and Codex share one set of installed commands and one `~/.jobkit`. Whatever is saved through one is available in the other: resumes, practice sessions, stories and match scores.

- The helper is set up once. The second app finds it ready and installs nothing.
- Keep the jobkit plugin up to date in both apps, so their instructions match the commands. If the two differ, the commands stay at the newer version and are never downgraded.
- The database refuses to open with commands older than the ones that last wrote it, so a version mix does not damage your data.

### Removing the commands

Uninstalling a plugin leaves the commands, because the other app may still use them. To remove them: `uv tool uninstall jobkit`. To remove your data as well, delete `~/.jobkit` yourself; nothing else does.

## Installing from a checkout

Installing from `themodelsway/jobkit` needs nothing special. Codex copies the plugin's whole folder, so its installed copy also holds the repository's `.git` folder; that is harmless. A local-folder installation from a working checkout (for example while developing) also copies `.venv` and `tmp/`. A clean copy excludes those folders. The copy script needs Git and Python 3.11 or newer, on macOS, Linux or Windows:

```
python3 setup/clean_copy.py FULL-PATH-OF-A-NEW-FOLDER
```

The copy holds the tracked files and new files Git does not ignore, and nothing else. The folder is then added as the marketplace, with `/plugin marketplace add FULL-PATH-OF-A-NEW-FOLDER` in Claude Code or `codex plugin marketplace add FULL-PATH-OF-A-NEW-FOLDER` in Codex, and installation proceeds as above. A local marketplace cannot be upgraded in place: an update means deleting the folder, running the script again and adding it again.

## For contributors and command-line users

### Setup from the command line

Requirements: macOS, Linux or Windows with Git for Windows (see above), [uv](https://docs.astral.sh/uv/) (it installs the pinned Python), and gitleaks for contributors who commit. poppler is optional and only improves PDF reading.

```
uv sync                       # creates .venv and installs the commands into it
```

Optional tools, by system:

| Tool | macOS | Debian, Ubuntu | Fedora, RHEL | Arch |
|---|---|---|---|---|
| poppler (PDF reading) | `brew install poppler` | `sudo apt install poppler-utils` | `sudo dnf install poppler-utils` | `sudo pacman -S poppler` |
| gitleaks (pre-commit secret scan) | `brew install gitleaks` | see the [gitleaks releases](https://github.com/gitleaks/gitleaks/releases) | see the releases | `sudo pacman -S gitleaks` |

On Windows neither is needed to try jobkit. Without `pdftotext` the PDF reader falls back to `pypdf`, which works with no extra install; poppler stays preferred when it is present. On 13 real PDF resumes the `pypdf` layout gave the same employers, date lines and bullet counts as poppler.

The examples below use `uv run <command>`, the same on macOS, Linux and Windows. The pre-commit hook and the skills run in Git Bash on Windows.

The home folder and database are created once (`~/.jobkit`, or the folder named by `JOBKIT_HOME`):

```
uv run jobkit init
```

The resume-folder setting is recorded once with:

```
uv run profile init --resume-root /path/to/resumes [--resume-dir <subfolder> ...] [--name NAME]
```

Any `.pdf`, `.docx`, `.md` or `.txt` file below that folder is found, in any subfolders; files that are not resumes and Word lock files (`~$...`) are skipped. Legacy `.doc`, `.rtf` and `.odt` formats require conversion to `.docx` before import. This stores the setting in the database.

### Commands

The same steps as the [Quick start](#quick-start), run by hand:

```
uv run process-resumes --survey          # preview what would be parsed; writes nothing
uv run process-resumes                   # build the resume data
uv run query-resume for-jd jd.txt        # best lines per employer for a job posting ("-" = stdin)
uv run match-score extract --jd jd.txt   # first of three steps; the resume-workflows skill does all three
uv run build-resume jd.txt               # tailored resume in ~/.jobkit/output/resumes/
uv run prep init                         # seed interview stories from the resume data
uv run lead init                         # seed the leadership questions
uv run arch init --track NAME            # seed drill cards for a technology (see docs/guides/interview-prep.md)
uv run readiness --jd jd.txt             # what to rehearse for this job
```

Save the name and contact line once with `profile header set NAME CONTACT_LINE` (`build-resume` reports when none is saved).

| Command | What it does |
|---|---|
| `process-resumes` | Reads resumes from the resume folder, finds the employers on its own, and builds the resume data. `--survey` previews without writing; `--force` rebuilds. |
| `query-resume` | `for-jd` ranks lines for a posting; `search`, `review` and `stats` filter lines, list items that need a human look and show counts. |
| `match-score` | The match score, in three steps: `extract`, `check`, `run`. The model rates each requirement against the lines; the command does the arithmetic. |
| `build-resume JD` | Writes a tailored Markdown resume. Name and contact come from the saved header (`profile header`), never from the resume data. |
| `prep`, `arch`, `lead` | Stories, drill cards and the leadership question set. |
| `sessions`, `readiness` | Practice sessions and the readiness report. |

For the top commands to explore profile settings, interview preparation and tutoring progress, see [docs/explore.md](docs/explore.md). Full reference: [docs/manual.md](docs/manual.md) (how to use each skill, and every command and option under the skill that uses it) and [docs/references/data-structures.md](docs/references/data-structures.md) (the stored data). Every command has `--help`, and the verbs are the same everywhere: `init`, `status`, `list`, `show ID`, `next`, `set ID FIELD VALUE`, `for-jd JD`. Messages go to stdout, problems to stderr with exit status 1. Commands are also available as `uv run python -m jobkit.<group>.<tool>`.

### Layout

The whole repository is the plugin, so an install copies all of it. What is used at run time is `skills/`, `src/`, `setup/`, the manifests and the project files `pyproject.toml`, `uv.lock` and `.python-version`, because the plugin builds its commands from them. Everything else is for contributors.

**Used at run time**

```
skills/                  the three skills: interview-prep, tutor, resume-workflows (with their guides)
src/jobkit/              the commands (Python package)
  common.py, base.py       helpers every tool shares: home folder, errors, exit status, one transaction per command
  store.py, schema.py      the database: connection, transactions, numbered schema upgrades, backup and restore
  records.py, export.py    the kinds of stored data, and `jobkit export`
  admin.py                 the `jobkit` command: init, status, export, backup
  user/                    settings, employers and open items (`profile`)
  resumes/                 reading, parsing, querying and building resumes, and the match score (`match_*` files)
  interview/               stories, leadership questions, drill cards, practice sessions and readiness
  interview/aws/           the one bundled example track; others are added with `arch track add`
setup/                   the helper setup the skills ask for, only with the user's yes
  install                  macOS and Linux
  install.ps1              Windows
  constraints.txt          the exact package versions setup installs (generated by `setup/pins.py`)
  pins.py, clean_copy.py   contributor scripts: regenerate the pins; make a clean copy for a local install
.claude-plugin/          plugin and marketplace manifests for Claude Code
plugin.json              plugin manifest for Codex
.agents/plugins/         marketplace manifest for Codex
```

**For contributors only**

```
tests/                   mirrors src/jobkit; every test runs in a throw-away home folder
openspec/specs/          the behaviour each area promises (requirements and scenarios)
docs/                    manual.md (index), guides/ (one page per skill, with its commands), references/ (the stored data)
.claude/skills/          OpenSpec workflow skills for working on this repository in Claude Code
.githooks/               the pre-commit hook
AGENTS.md, CLAUDE.md     guidance for coding agents (CLAUDE.md imports AGENTS.md)
```

**Outside the repository**

```
~/.jobkit/               the data: data/jobkit.db (everything, including the header), output/, backup/
```

### Development

```
uv run python -m unittest discover -s tests -t .    # unit and end-to-end tests (synthetic fixtures)
uv run pyright                                      # type check
uv run ruff check src tests                         # lint (ruff.toml)
uv run pylint src                                   # deeper lint (.pylintrc)
```

**Versions.** The version lives in `pyproject.toml`; `plugin.json` and `.claude-plugin/plugin.json` must carry the same one (the tests check). After `uv lock`, regenerate the pinned versions with `uv run python setup/pins.py`. A change to any pin (`setup/constraints.txt`, `.python-version`, the uv version at the top of both installers) needs a new version in `pyproject.toml`, so installed helpers are offered the update; the tests check this too.

A pre-commit hook runs gitleaks (secret scan of the staged changes), the personal-terms check ([manual](docs/manual.md#for-contributors-keeping-personal-data-out-of-commits)), ruff, pyright and the tests before every commit. Enable it once per clone:

```
git config core.hooksPath .githooks
```

New tools follow the same shape (`build_parser()`, `main(argv) -> int`, typed functions) and need a `[project.scripts]` entry in `pyproject.toml`. Conventions for contributors and for coding agents are in `AGENTS.md`, which `CLAUDE.md` imports (the plugin's skills carry their own rules, because a plugin does not load either file); the promised behaviour is in `openspec/specs/`.

## Privacy

jobkit data is stored in the `~/.jobkit` folder (or the folder named by `JOBKIT_HOME`). Your own resume files are read from where you keep them.

When a skill runs, the app (Claude Code or Codex) gives its model what the task needs, such as resume lines, a job posting or your practice answers, and the model reads them wherever that provider runs it. How that content is handled, kept or used is decided by the model provider (Anthropic for Claude Code, OpenAI for Codex) and by the privacy settings you have configured with them, not by jobkit.

Setup downloads software as listed in [What setup installs](#what-setup-installs).

For contributors: committed files are meant to hold no names, employers or folders. The pre-commit hook and `tests/test_no_personal.py` check that against the contributor's own list of personal terms (see the [manual](docs/manual.md#for-contributors-keeping-personal-data-out-of-commits)). Look at any of your data with `jobkit export`; save a copy with `jobkit backup`.

## License

jobkit is licensed under the [Apache License 2.0](LICENSE). The software is provided "as is", without warranty of any kind.
