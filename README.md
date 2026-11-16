# jobkit

jobkit supports interview preparation through tutoring, mock interviews and readiness reports. Stored resumes provide the experience behind the stories and questions. Resume tailoring for job postings is available as an early preview.

jobkit provides three skills for Claude Code and Codex: interview practice, tutoring with readiness reports, and resume workflows. Requests use plain language; each skill gives the agent instructions for a task.

Claude Code and Codex are coding agents, called **agents** here. The agent loads jobkit's skills and runs its commands within its permission settings. The **model** is the language model the agent uses: it interprets requests and the content supplied, such as resume text or page images, and writes the responses.

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

[Install on Claude Code](#install-on-claude-code) (at user scope, so it works in every folder) or [Install on Codex](#install-on-codex), or give the agent this repository's address, `https://github.com/themodelsway/jobkit`, and ask it to guide the installation. If installation or a first request does not work, see [Troubleshooting](#troubleshooting).

Once installed, start the agent in a new empty folder, not in the folder that holds the resumes. The agent accepts requests in plain words. On the first request the skill tells the agent to offer to set up the helper ([What setup installs](#what-setup-installs)); setup starts once the user responds with yes, subject to the permissions configured in the agent. After the first import, and at the start of a conversation whose request names no task, the skill tells the agent to list what it can do and to ask where to start.

1. **Resume import.** The skill takes the folder that holds the resumes, finds the resume files (PDF, Word, Markdown or text) in it and its subfolders, and imports them into the jobkit datastore. The jobkit commands only read the files in that folder, and the skills tell the agent never to change them.
2. **Topic instruction.** The tutor explains a topic, a question or one of the user's stories first, then checks understanding with a short quiz.
3. **Practice.** A mock interview asks first, gives no hints, then grades the answers. A session can be stopped and resumed later.
4. **Readiness assessment.** A report shows what has been rehearsed, what is solid and what is still untested, optionally for a supplied job posting.
5. **Early preview: resume tailoring.** For a supplied job posting, the skill builds a tailored draft resume or estimates how well the stored resumes match the posting.

## Features

Each step above is one of the three skills. The three skills share one datastore, so information recorded through one skill is available to the others.

### Resumes

- **One store from many resumes.** Every resume is read once, split by employer, and merged. Wording that appears in several resumes is kept once, with its sources.
- **Incremental.** Files that have not changed are skipped; new files are added; deleted or renamed files are removed.
- **Many layouts.** Resumes laid out with a side column (PDF columns, Word text boxes or tables), Markdown tables, headings written many ways (`Experience`, `Career Highlights`), dates such as `09/2021`, `Sep 2021` or `2012`, and several titles at one employer are read. After an update that changes how resumes are read, the next run saves a copy of the data and re-reads every resume once, keeping curation.
- **Scanned PDFs.** A PDF with no readable text (a scan or a damaged file) is reported with its reason. The skill tells the agent to ask first, and to read its pages as pictures once the user responds with yes; the agent then types out the text and shows it for checking. The commands use the typed-out text only after it is confirmed with `process-resumes visual confirm`, which the skill tells the agent to run once the user agrees with the text.
- **Checking a PDF against its pages.** For a PDF that reads as text, the parse can be compared with a reading of its pages; the skill tells the agent to do this only when the user asks. The agent shows each difference with both versions for the user to decide. Agreed corrections are kept in the data folder and used until the PDF changes; the jobkit commands do not write to the resume file.
- **Wrong figures can be flagged.** A figure known to be wrong can be listed, so lines that use it are marked and left out of matching.

### Learning with the tutor

The tutor teaches a card, question or story first, then checks understanding with a short quiz. What has been taught is recorded, so the readiness report can tell taught from tested.

### Mock interviews and practice

- **Stories.** Stories seeded from the resumes, one per employer and theme. Each is written once and can be told as STAR (situation, task, action, result), SOAR (situation, obstacle, action, result) or CARL (challenge, action, result, learning). Each can hold a metric with a recorded basis (measured, estimated, stated or unknown), spoken 60-second and 2-minute versions, and follow-up questions.
- **Knowledge drill cards for any role.** Cards for the topics, comparisons and scenarios of the technologies or fields an interview covers, plus cases (a question developed over several turns) and role-plays (the agent plays a part, such as a sceptical stakeholder). Each topic belongs to a role family (engineering, product, delivery, people or operations), and answers are graded against that topic's rubric. One example technology is bundled, and any other technology or field is added from a JSON topic list, with no code. Facts come from official sources (vendor documentation, regulators, standards bodies), for the user's country where it matters, never from memory. Coding exercises, tests with one right answer and written work samples are not covered.
- **Leadership questions.** A question set (roadmapping, mentoring, conflict, prioritisation and more), each with the user's principle and one example per recent employer.
- **Company research.** For a named company, where the agent can read web pages, the skill tells the agent to look up how that company hires (published values, interview rounds, what interviewers look for, typical questions) and to save each fact with its link, a short quote and the date read, leaving out reviews and other user-written posts. Stories and practice sessions can then be ranked against that company's values. Nothing about any company is shipped. The skill tells the agent to recheck stale facts when they are next needed; the default research window is 30 days. The commands refuse a fact without a link or quote, but cannot check that a quote is on its page; each fact keeps its link to open.
- **Practice sessions.** Resumable. A session keeps the complete answers and grades; later drills add entries and never edit old ones.
- **Mock interview.** The interview-prep skill asks first, gives no hints, then grades.

### Readiness

A report of coverage and evidence per area, optionally limited to one job posting. Each card or question reads as untested, some gaps, solid-once, solid-repeated, aging or solid-unlogged (confidence recorded by hand, no logged answer); stories show their status and recent rehearsal. There is deliberately no single score.

### Resume tailoring and match score (early preview)

Resume tailoring and match scoring are early previews. Their output requires review before use.

- **Tailoring.** Given a job posting, it builds a resume from the stored lines. It ranks the lines per employer, suggests opening summaries, lists the skills the posting asks for that no stored line supports, and writes a Markdown draft. The draft requires review before use.
- **Match score.** It rates how well the resume lines cover a posting: a lower and an upper score, the requirements the resumes do not show yet, and the assumptions made. It is an estimate of coverage. It is not any employer's applicant-tracking score, and it does not predict whether the user will be hired. The first step saves the posting in the data folder, so the later steps name it instead of passing it again. Each completed scoring run also removes saved postings unused for more than 30 days; nothing removes them on a schedule.

## Supported agents and systems

| Agent | Where | macOS | Linux | Windows |
|---|---|---|---|---|
| Claude Code | terminal, desktop app, IDE extensions | yes | yes | yes, with Git for Windows |
| Codex | command line (`codex`), running locally | yes | yes | not yet |

Not supported: Codex on Windows, the Codex IDE extension and hosted (cloud) Codex. The setup refuses, and installs nothing, only where it can tell: on an operating system other than macOS, Linux or Windows, and for Codex on Windows. It does not detect the Codex IDE extension or hosted Codex on macOS or Linux, so these are untested rather than blocked. Checked with Claude Code 2.1 and Codex CLI 0.167 on macOS.

## Before you begin

| Prerequisite | Purpose | Install |
|---|---|---|
| Claude Code or Codex, signed in and recent enough to have plugin commands (`claude plugin --help` or `codex plugin --help` in a terminal lists them) | the agent that runs jobkit | the agent's official documentation |
| [uv](https://github.com/astral-sh/uv) 0.13.7 or newer | Python package manager; downloads the Python version and packages jobkit uses. Python itself does not need to be installed | instructions at https://github.com/astral-sh/uv |
| Git for Windows (Windows only) | runs the agent's commands on Windows | [Windows](#windows) |

If uv is missing, the skill tells the agent to explain this prerequisite and to install uv only when the user asks.

The computer must be online: installation downloads the plugin from GitHub, and the first-time setup downloads Python and packages ([What setup installs](#what-setup-installs)).

Installation has two steps in either agent. This repository holds a marketplace catalog, so it is first registered as a marketplace in the agent, and jobkit is then installed from it. Three names are involved: `themodelsway/jobkit` is the GitHub repository, `themodelsway` is the marketplace and `jobkit` is the plugin. Cloning the repository is not needed; [Installing from a checkout](#installing-from-a-checkout) is an optional path for contributors and local testing.

| Step | Claude Code (in a session) | Codex (in a terminal) |
|---|---|---|
| Register the repository's marketplace | `/plugin marketplace add themodelsway/jobkit` | `codex plugin marketplace add themodelsway/jobkit` |
| Install the plugin | `/plugin install jobkit@themodelsway` | `codex plugin add jobkit@themodelsway` |

## Install on Claude Code

### macOS and Linux

1. Marketplace registration, in Claude Code: `/plugin marketplace add themodelsway/jobkit`
2. Plugin installation: `/plugin install jobkit@themodelsway`. When asked for a scope, choose user scope ("install for you"): it makes jobkit available in every folder on this computer. Project and local scope limit it to the current project, so it is missing from other folders. The terminal equivalent is `claude plugin install jobkit@themodelsway --scope user`.
3. A new session makes the installed skills available.
4. Check: jobkit is listed in the Installed tab of `/plugin`, or by `claude plugin list` in a terminal. If it is missing or disabled, see [Troubleshooting](#troubleshooting).
5. First request, for example:
   > Use jobkit to import my resumes.

   The skill tells the agent to offer the helper setup first. Once the user responds with yes, setup runs, subject to the permissions configured in the agent. The wording above is an example; any plain request works (see [Quick start](#quick-start)).

### Windows

Claude Code on Windows runs its commands through Git for Windows, a prerequisite that is not needed again when already installed:

1. Git installation, in a terminal: `winget install --id Git.Git -e`, or the installer from [git-scm.com](https://git-scm.com/download/win) with the standard options.
2. Restarting Claude Code makes Git available to it.
3. The same steps as for macOS and Linux follow.

uv is a prerequisite on Windows as on the other systems ([Before you begin](#before-you-begin)). [What setup installs](#what-setup-installs) explains when setup runs.

### After installing

- **Skills installed:** `jobkit:interview-prep` (mock interview), `jobkit:tutor` (teaching and readiness reports) and `jobkit:resume-workflows` (add a resume, tailor a resume for a job posting).
- **Helpers installed:** `resume-visual-scanner` (reads the pages of a PDF as pictures, once the user responds with yes to a visual reading) and `jd-matcher` (the first rating pass of a match score). The skills tell the agent to hand work to them, to keep page images and long postings out of the main conversation, and to do the work itself when the agent cannot run them.
- **Update:** in a terminal, `claude plugin marketplace update themodelsway` (refreshes the marketplace's list of versions), then `claude plugin update jobkit@themodelsway` (updates the installed plugin); in a session, the Installed tab of `/plugin` offers the same update. A new session applies it. The next time a skill starts, it tells the agent to notice that the commands are older and to offer to update them.
- **Remove:** `/plugin uninstall jobkit@themodelsway`. `~/.jobkit` and your data are left alone, and so are the commands (see [Removing the commands](#removing-the-commands)).
- **Trying it from a checkout:** `claude --plugin-dir plugins/jobkit` loads the three skills for one session.

## Install on Codex

Codex support is for the Codex command line on macOS and Linux, running locally.

1. Marketplace registration: `codex plugin marketplace add themodelsway/jobkit`
2. Plugin installation: `codex plugin add jobkit@themodelsway`
3. Starting `codex` makes the installed skills available.
4. Check: `codex plugin list --marketplace themodelsway` lists jobkit. If it is missing, see [Troubleshooting](#troubleshooting).
5. First request: the same as for Claude Code (step 5 under [macOS and Linux](#macos-and-linux)).

Codex runs commands in a sandbox that can read your files but, by default, cannot write outside the folder you started it in and cannot go online. jobkit keeps its data in `~/.jobkit`, so allow that one folder. The simplest way is to approve it when Codex asks. To allow it ahead of time with the workspace-write sandbox settings, edit `~/.codex/config.toml`, using the full path that `echo ~/.jobkit` prints in a terminal:

- If the file has no `[sandbox_workspace_write]` table, add one:

  ```
  [sandbox_workspace_write]
  writable_roots = ["FULL-PATH-OF-YOUR-HOME-FOLDER/.jobkit"]
  ```

- If the table is already there, do not add a second one (Codex then cannot read the file). Add the path to its existing `writable_roots` list and keep the folders already in it.

This setting applies to the workspace-write sandbox only; it has no effect in a read-only session. A setup that uses Codex permission profiles instead configures folders there, as described in the Codex documentation.

The first-time setup also downloads and installs software (see [What setup installs](#what-setup-installs)), which the sandbox blocks: approve that step when Codex asks. If it was blocked, the skill says that setup did not finish; allow it and ask again, and it carries on from where it stopped. If a save is blocked later, the skill says that nothing was saved and names the folder to allow. Do not turn the sandbox off for this.

- **Skills installed:** the same three, `interview-prep`, `tutor` and `resume-workflows`, from the same files as in Claude Code. An installed Codex plugin does not include the two helpers; the skills then use a separate helper where Codex can run one, or do that work themselves.
- **Update:** `codex plugin marketplace upgrade themodelsway`, then `codex plugin add jobkit@themodelsway` again. The next time a skill starts it offers to update the commands.
- **Remove:** `codex plugin remove jobkit@themodelsway`, and `codex plugin marketplace remove themodelsway` to forget the marketplace. Your data and the commands are left alone.

## Troubleshooting

The quickest help for any problem: give the agent this repository's address, `https://github.com/themodelsway/jobkit`, and ask it to help install jobkit or solve the problem.

Common problems:

- **The agent does not know a plugin command** (`/plugin` or `codex plugin` is not recognised): the agent is too old. Update it and try again.
- **jobkit or the marketplace is not found:** register the marketplace again (first row of the table in [Before you begin](#before-you-begin)), then install. In Claude Code, a plugin installed at project or local scope is missing from other folders; install it again at user scope. A plugin shown as disabled is turned on in the Installed tab of `/plugin` or with `claude plugin enable jobkit@themodelsway`.
- **The skills do not respond to a request:** start a new session after installing or updating, and name jobkit in the request.
- **Setup did not finish:** setup downloads software, so the computer must be online and the agent must allow the download (approve it when asked). Asking again carries on from where it stopped.

## What setup installs

The first time a skill runs, in either agent, the skill tells the agent to check for uv first. If uv is missing, the skill tells the agent to name it as a prerequisite, point to its instructions, and install it only when the user asks. The skill then tells the agent to say that a small helper needs to be set up and to ask whether that is OK, to install nothing on a no, and once the user responds with yes to run `setup/install` from the plugin folder (`setup/install.ps1` on Windows). That installer installs exactly this:

| What | Version | From | When |
|---|---|---|---|
| [uv](https://github.com/astral-sh/uv), the Python package manager | 0.13.7, the same on every system | astral.sh | only when uv is missing and the user asks the agent to install it |
| Python | 3.14 (the exact version is in `plugins/jobkit/.python-version`) | uv's own Python builds | if uv does not already have that version |
| Python packages | the exact versions in `plugins/jobkit/setup/constraints.txt` | PyPI | always |
| the jobkit commands | the plugin's version | the plugin's own files | always |

- **Own Python not required.** Setup uses a separate Python installation managed by uv, apart from any Python already on the computer; nothing else uses it. `uv python list --only-installed` lists Python installations managed by uv.
- A uv that is already on the computer is used as it is and never replaced. If it is older than the minimum in `plugins/jobkit/pyproject.toml` (`required-version`), setup stops and says so; uv must be updated before setup is requested again.
- Setup never downgrades: if the installed commands are newer than the plugin, it changes nothing.
- After setup, each skill tells the agent to check how far setup has got (`jobkit status --setup`) and to continue from there: create the data folder, import the resumes, or ask what the user is preparing for. When the check reports that saving is not allowed, or that the data comes from a newer version, the skill tells the agent to say so and stop. For any other failure, at setup or later, the skill tells the agent to follow the troubleshooting guide that ships with the plugin (`setup/troubleshoot.md`): it never repairs the data itself, retries only a busy database, once, and otherwise stops and offers a report without personal details for the user to post as a GitHub issue; jobkit does not post issues itself. A command that fails in a way its message does not explain ends its error output with a line that points to that guide. For a returning user, the list of what jobkit can do starts with an offer to continue an unfinished practice session (`jobkit status --summary`).
- It does not edit your shell settings. The commands go in uv's tool folder and the skills run them by full path.
- If setup stops half way (for example offline), what it already installed stays; asking again finishes it.
- Your data is kept in `~/.jobkit` on macOS and Linux, and in `%USERPROFILE%\.jobkit` (the `.jobkit` folder in your user home folder) on Windows. This README writes it as `~/.jobkit`.

## Using both agents

Claude Code and Codex share one set of installed commands and one `~/.jobkit`. Whatever is saved through one is available in the other: resumes, practice sessions, stories and match scores.

- The helper is set up once. The second agent finds it ready and installs nothing.
- Keep the jobkit plugin up to date in both agents, so their instructions match the commands. If the two differ, the commands stay at the newer version and are never downgraded.
- The database refuses to open with commands older than the ones that last wrote it, so a version mix does not damage your data.

### Removing the commands

Uninstalling a plugin leaves the commands, because the other agent may still use them. To remove them: `uv tool uninstall jobkit`. To remove your data as well, delete `~/.jobkit` yourself; nothing else does.

## Installing from a checkout

This is optional, for contributors and local testing; a normal installation does not use it. Installing from the `themodelsway/jobkit` repository requires no extra steps. The plugin is the `plugins/jobkit/` folder of the repository, so the installed copy holds that folder and not the contributor files at the repository root (tests, documentation, OpenSpec files). A local-folder installation from a working checkout (for example while developing) must be added as a marketplace, not as the plugin folder alone, and a plain copy of the checkout also carries `.git` and every file Git ignores. A clean copy holds the two marketplace catalogs and the plugin, without `.git` or any ignored file. The copy script needs Git and Python 3.11 or newer, on macOS, Linux or Windows (on Windows, use the `py -3` launcher or any Python 3.11 or newer):

```
python3 tools/clean_copy.py FULL-PATH-OF-A-NEW-FOLDER
```

The copy holds the tracked files and new files Git does not ignore, and nothing else. It must be a new or empty folder outside the checkout. The folder (not the plugin folder inside it) is then added as the marketplace, with `/plugin marketplace add FULL-PATH-OF-A-NEW-FOLDER` in Claude Code or `codex plugin marketplace add FULL-PATH-OF-A-NEW-FOLDER` in Codex, and installation proceeds as above. A local marketplace cannot be upgraded in place: an update means deleting the folder, running the script again and adding it again; editing the checkout does not change an installed copy.

## For contributors and command-line users

### Using the commands without a plugin

The commands can be installed on their own, the same way the plugin's setup installs them. From a checkout, with [uv](https://docs.astral.sh/uv/) available:

```
uv tool install --constraints plugins/jobkit/setup/constraints.txt ./plugins/jobkit
jobkit init
profile --help
```

uv installs all thirteen commands in its tool folder (`uv tool dir --bin` prints it). Direct invocation requires that folder on the shell search path; if `jobkit` is not found, run `uv tool update-shell` and open a new terminal. With the folder on the search path, no `uv run` and no project option are needed. The constraints file gives the same exact dependency versions as the plugin install. To remove them: `uv tool uninstall jobkit`. Contributors who edit the code use the checkout setup below instead, because an installed copy does not follow later edits.

### Setup from the command line

Requirements: macOS, Linux or Windows with Git for Windows (see above), [uv](https://docs.astral.sh/uv/) (it installs the pinned Python), and gitleaks for contributors who commit. poppler is optional: it improves PDF reading and draws the page pictures for a visual reading of any PDF (without it, pictures can be taken only from a plain scan).

```
uv sync                       # creates the environment and installs the commands into it
```

Optional tools, by system:

| Tool | macOS | Debian, Ubuntu | Fedora, RHEL | Arch |
|---|---|---|---|---|
| poppler (PDF reading and page pictures) | `brew install poppler` | `sudo apt install poppler-utils` | `sudo dnf install poppler-utils` | `sudo pacman -S poppler` |
| gitleaks (pre-commit secret scan) | `brew install gitleaks` | see the [gitleaks releases](https://github.com/gitleaks/gitleaks/releases) | see the releases | `sudo pacman -S gitleaks` |

On Windows neither is needed to try jobkit. Without `pdftotext` the PDF reader falls back to `pypdf`, which works with no extra install; poppler stays preferred when it is present. In testing, the `pypdf` layout gave the same employers, date lines and bullet counts as poppler.

The examples below use `uv run <command>`, the same on macOS, Linux and Windows. Run them from the repository root: its `pyproject.toml` is a uv workspace around `plugins/jobkit`, so the one `uv.lock` and its environment are there. The pre-commit hook and the skills run in Git Bash on Windows.

The home folder and database are created once (`~/.jobkit`, or the folder named by `JOBKIT_HOME`):

```
uv run jobkit init
```

The resume-folder setting is recorded once with:

```
uv run profile init --resume-root /path/to/resumes [--resume-dir <subfolder> ...] [--name NAME] [--replace]
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
uv run arch init --track NAME            # seed drill cards for a technology or field (see docs/guides/interview-prep.md)
uv run readiness --jd jd.txt             # what to rehearse for this job
```

Save the name and contact line once with `profile header set NAME CONTACT_LINE` (`build-resume` reports when none is saved).

| Command | What it does |
|---|---|
| `process-resumes` | Reads resumes from the resume folder, finds the employers on its own, and builds the resume data. `--survey` previews without writing; `--force` rebuilds. `curate` changes the hand curation (several entries at once from standard input); `visual` handles PDFs read from their pages (`list`, `render`, `text`, `schema`, `compare`, `confirm`). |
| `query-resume` | `for-jd` ranks lines for a posting; `search`, `review` and `stats` filter lines, list items that need a human look and show counts. |
| `match-score` | The match score, in three steps: `extract`, `check`, `run`. The model used by the agent rates each requirement against the lines; the command does the arithmetic. `extract` saves the posting, and the later steps can name it with `--key`. |
| `build-resume JD` | Writes a tailored Markdown resume. Name and contact come from the saved header (`profile header`), never from the resume data. |
| `prep`, `arch`, `lead` | Stories, drill cards and the leadership question set. |
| `target` | Researched target companies: each fact with its link, quote, label and date read. |
| `sessions`, `readiness` | Practice sessions and the readiness report. |

For the top commands to explore profile settings, interview preparation and tutoring progress, see [docs/explore.md](docs/explore.md). Full reference: [docs/manual.md](docs/manual.md) (how to use each skill, and every command and option under the skill that uses it) and [docs/references/data-structures.md](docs/references/data-structures.md) (the stored data). Every command has `--help`, and the verbs are the same everywhere: `init`, `status`, `list`, `show ID`, `next`, `set ID FIELD VALUE`, `for-jd JD`. Messages go to stdout, problems to stderr with exit status 1. Commands are also available as `uv run python -m jk.<group>.<tool>`.

### Layout

The plugin is the `plugins/jobkit/` folder, which holds everything used at run time: the skills, the commands and their project files, the installers and the manifests. The repository root holds the two marketplace catalogs and everything for contributors, none of which an installed plugin needs.

**The plugin (`plugins/jobkit/`)**

```
skills/                  the three skills: interview-prep, tutor, resume-workflows (with their guides)
agents/                  the two helpers for Claude Code: resume-visual-scanner, jd-matcher
src/jk/              the commands (Python package)
  common.py, base.py       helpers every tool shares: home folder, errors, exit status, one transaction per command
  store.py, schema.py      the database: connection, transactions, numbered schema upgrades, backup and restore
  records.py, export.py    the kinds of stored data, and `jobkit export`
  admin.py                 the `jobkit` command: init, status, export, backup
  user/                    settings, employers and open items (`profile`)
  resumes/                 reading, parsing, querying and building resumes, and the match score (`match_*` files)
  interview/               stories, leadership questions, drill cards, practice sessions and readiness
  interview/aws/           the one bundled example track; others are added with `arch track add`
setup/                   the helper setup the skills ask for; the skills tell the agent to run it once the user responds with yes
  install                  macOS and Linux
  install.ps1              Windows
  constraints.txt          the exact package versions setup installs (generated by `tools/pins.py`)
pyproject.toml, .python-version   the package and the Python version
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
tests/                   mirrors plugins/jobkit/src/jk; every test runs in a throw-away home folder
openspec/specs/          the behaviour each area promises (requirements and scenarios)
docs/                    manual.md (index), guides/ (one page per skill, with its commands), references/ (the stored data)
tools/                   pins.py (regenerate the pinned versions), clean_copy.py (clean marketplace copy for a local install)
pyproject.toml, uv.lock       the contributor workspace: one lockfile and one environment around plugins/jobkit
pyrightconfig.json, ruff.toml, .pylintrc   type-check and lint settings
.claude/skills/          OpenSpec workflow skills for working on this repository in Claude Code
.codex/agents/           the two helpers for Codex in this checkout (a test keeps their rules equal to the plugin's)
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
uv run pyright --project pyrightconfig.json         # type check (--project here is pyright's own option)
uv run ruff check plugins/jobkit/src tests tools    # lint (ruff.toml)
uv run pylint --rcfile .pylintrc plugins/jobkit/src # deeper lint (.pylintrc)
```

**Versions.** The version lives in `plugins/jobkit/pyproject.toml`; `plugins/jobkit/plugin.json` and `plugins/jobkit/.claude-plugin/plugin.json` must carry the same one (the tests check). After `uv lock`, regenerate the pinned versions with `uv run python tools/pins.py`. A change to any pin (`plugins/jobkit/setup/constraints.txt`, `plugins/jobkit/.python-version`, the uv version at the top of both installers) needs a new version in `plugins/jobkit/pyproject.toml`, so installed helpers are offered the update; the tests check this too.

A pre-commit hook runs gitleaks (secret scan of the staged changes), the personal-terms check ([manual](docs/manual.md#for-contributors-keeping-personal-data-out-of-commits)), ruff, pyright and the tests before every commit. Enable it once per clone:

```
git config core.hooksPath .githooks
```

New tools follow the same shape (`build_parser()`, `main(argv) -> int`, typed functions) and need a `[project.scripts]` entry in `plugins/jobkit/pyproject.toml`. Conventions for contributors and for coding agents are in `AGENTS.md`, which `CLAUDE.md` imports (the plugin's skills carry their own rules, because a plugin does not load either file); the promised behaviour is in `openspec/specs/`.

## Privacy

jobkit data is stored in the `~/.jobkit` folder (or the folder named by `JOBKIT_HOME`). Your own resume files are read from where you keep them.

When a skill runs, the agent sends the model what the task needs, such as resume lines, a job posting or your practice answers, and the model reads them wherever that provider runs it. The skills tell the agent to ask first, and to give pictures of a PDF's pages to the model once the user responds with yes. This rests on the agent following its instructions; the commands themselves do not check for a yes. Page images that `process-resumes visual render` writes go to `~/.jobkit/output/visual/pages/`, and `visual confirm` removes them. How that content is handled, kept or used is decided by the model provider (by default Anthropic for Claude Code and OpenAI for Codex, or whichever provider the agent is set up to use) and by the privacy settings you have configured with them, not by jobkit.

Setup downloads software as listed in [What setup installs](#what-setup-installs).

For contributors: committed files are meant to hold no names, employers or folders. The pre-commit hook and `tests/test_no_personal.py` check that against the contributor's own list of personal terms (see the [manual](docs/manual.md#for-contributors-keeping-personal-data-out-of-commits)). Look at any of your data with `jobkit export`; save a copy with `jobkit backup`.

## License

jobkit is licensed under the [Apache License 2.0](LICENSE). The software is provided "as is", without warranty of any kind.
