# jobkit manual

jobkit provides three skills for Claude Code and Codex. Requests use plain language, and the skills run the required commands. Each guide describes the workflow before presenting the command reference; typing a command is never required.

| Skill | Purpose | Page |
| --- | --- | --- |
| interview-prep | Mock interviews with role questions, leadership questions and personal stories. | [interview-prep.md](guides/interview-prep.md) |
| tutor | Teaching before quizzing, and interview readiness reports. | [tutor.md](guides/tutor.md) |
| resume-workflows | Resume import, tailoring for a job posting, and match scoring (early preview). | [resume-workflows.md](guides/resume-workflows.md) |

The pages in `plugins/jobkit/skills/` are the agent's instructions; these pages are for users of jobkit. Settings and interview progress can be checked from the command line with the [top commands to explore](explore.md).

## Running the commands directly

Fourteen commands are installed by `uv sync` into `.venv`. The commands run from the repository root as `uv run <command>`, or as `uv run python -m jk.<group>.<tool>`. `--help` works on every command and subcommand.

Conventions shared by all commands:

- Messages go to stdout; problems go to stderr with exit status 1. Usage errors (bad choice, missing argument) exit with status 2.
- A file argument written as `-` reads stdin (job descriptions, seeds, long answers).
- Verbs are the same everywhere: `init`, `status`, `list`, `show ID`, `next`, `set ID FIELD VALUE`, `for-jd JD`.
- `[x]` means optional, `x...` means repeatable, `A|B` means one of.
- All data lives in one database, `data/jobkit.db` under the home folder (`~/.jobkit` on macOS and Linux, `%USERPROFILE%\.jobkit` (the `.jobkit` folder in your user home folder) on Windows, or the folder named by `JOBKIT_HOME`). Text files are read and written as UTF-8 on every platform. It is read and written only through these commands. Each command's changes are stored together or not at all, and several commands can run at once. Run `jobkit init` once before anything else.
- The shape of the files these commands read and write is in [data-structures.md](references/data-structures.md).

| Command | What it does | Described in |
|---|---|---|
| `cards` | Role-knowledge cards for the fields or technologies an interview covers | [interview-prep.md](guides/interview-prep.md#cards) |
| `build-resume` | Write a tailored resume | [resume-workflows.md](guides/resume-workflows.md#build-resume) |
| `jobkit` | The home folder and database: init, status, export, backup | [below](#jobkit) |
| `lead` | Leadership questions | [interview-prep.md](guides/interview-prep.md#lead) |
| `match-score` | Rate how well resume lines cover a posting (early preview) | [resume-workflows.md](guides/resume-workflows.md#match-score) |
| `prep` | Interview stories and engagements | [interview-prep.md](guides/interview-prep.md#prep) |
| `questions` | Search records, local prompts and practice progress for a role | [interview-prep.md](guides/interview-prep.md#questions) |
| `resume-lines` | Find lines over 200 characters and check a shorter wording | [resume-workflows.md](guides/resume-workflows.md#resume-lines) |
| `process-resumes` | Read resumes into the data | [resume-workflows.md](guides/resume-workflows.md#process-resumes) |
| `profile` | Settings and open items | [below](#profile) |
| `query-resume` | Rank and search resume lines | [resume-workflows.md](guides/resume-workflows.md#query-resume) |
| `readiness` | The readiness report | [tutor.md](guides/tutor.md#readiness) |
| `sessions` | Resumable practice sessions | [interview-prep.md](guides/interview-prep.md#sessions) |
| `target` | Researched target companies | [interview-prep.md](guides/interview-prep.md#target) |

---

## Commands every skill uses

### `jobkit`

The home folder and its database. Standard library only.

| Subcommand | Arguments and options | What it does |
|---|---|---|
| `jobkit init` | none | Create the home folder and an empty database. Safe to repeat: existing data is never changed. |
| `jobkit status` | `--setup`, `--summary` | Show the database location, schema version, size and the number of records per kind of data. With `--setup`, print only how far setup has got, as one word: `no-database`, `no-resumes` (no resumes imported), `no-target` (resumes imported, but "what are you preparing for" has not been finished: `preparing_for` is not saved yet, even if some of its stories, leadership questions or drill cards were) or `ready`. When the check itself fails it prints why instead, decided from the error's type and SQLite's result code: `blocked` (saving not allowed), `busy` (another command holds the database), `too-new` (written by a newer version) or `failed` (anything else); it then exits 1 with one error line (type and message, the home folder shown as `~`, or `%USERPROFILE%` on Windows) and the troubleshooting line on standard error. With `--summary`, print the setup line; then, always, where this running copy keeps its data (`JOBKIT_HOME`), the launchers it was started from (`JOBKIT_COMMANDS_DIR`) and its Python environment with the jobkit and Python versions (`JOBKIT_PROGRAM_DIR`), with the home folder shown the same way; and, once resumes are imported, the open sessions and the latest one, how many items are due for a retest, each researched company's state and the default target company. Neither option creates the database (like every command, they upgrade an existing one from an older version when opening it); the skills act on their output. |
| `jobkit --version` | none | Print the installed version (`jobkit` and the version number). The plugin's setup check compares it with the plugin's version: same is ready, lower is offered an update, higher is left alone. |
| `jobkit export` | `--format json\|md`, `--only KIND`, `-o DIR` | The way to look at stored data. Prints all of it (or one kind) as JSON (default) or Markdown; with `-o` writes one file per kind into `DIR`. Never changes the database and writes nothing unless `-o` is given. Kinds: `stories`, `engagements`, `themes`, `cards-catalog`, `cards-progress`, `cards-tracks`, `lead-questions`, `lead-progress`, `lead-scope`, `sessions`, `research`, `settings`, `employers`, `open-items`, `terms`, `resume-companies`, `resume-skills`, `resume-profile`, `resume-index`, `resume-ledger`, `resume-unparsed`, `curated`, `curation-themes`, `match-results`. |
| `jobkit backup` | `-o FILE`, `--restore FILE` | Write a consistent copy of the database to `backup/` (or `FILE`), also while other commands are running. `--restore FILE` replaces the database with a backup after saving the current one; a current database is saved without being upgraded, so one from a newer version or with missing tables is saved too; one SQLite cannot read (damaged) is saved file by file, and a missing one is not needed. The file is first checked on a temporary copy, together with its write-ahead log (`FILE-wal`) when there is one: integrity, upgrade, every table, column and protective trigger, no broken references, every stored record readable. The file only needs to be readable. A file that is damaged, incomplete, not a jobkit database, or from a newer version is refused and nothing is changed. The database is replaced with the same copy that was checked, at the file's own version (the next command upgrades it); the backup file itself is never changed. When another command holds the database for more than a few seconds, the restore stops with a busy message and the database is not replaced. A refusal names the table, never the record's content. |

The first command after an update that changes the database layout upgrades the database by itself. An existing database is first copied to `backup/jobkit-before-upgrade-v<old version>-<timestamp>.db`; if that copy cannot be written, nothing is upgraded. An upgrade cannot be reversed: to go back, run `jobkit backup --restore` with that copy, then switch to the older release before any other jobkit command runs (the next command of the newer release upgrades the database again). These copies are not removed automatically.

### `profile`

Per-user settings, stored in the database. Standard library only.

| Subcommand | Arguments and options | What it does |
|---|---|---|
| `profile status` | none | Show the saved profile and what is missing. |
| `profile init` | `--resume-root PATH` (required), `--resume-dir SUB...`, `--name NAME`, `--replace` | Record where the resume files are. `--resume-dir` limits the scan to subfolders (repeatable). Run again, it only fills in what is unset and keeps existing answers (it says so); change the name or resume root with `profile set`. With `--replace`, the resume root and subfolders are set to exactly what is given (the whole folder when no `--resume-dir` is given) and every other setting is kept: the way to correct the folder choice; the next `process-resumes` drops resumes that are no longer in it. |
| `profile set` | `KEY VALUE` | Change one setting. `KEY` is `name`, `resume_root`, `years_experience` (a whole number from 1 to 60, such as `12` or `12+`; built summaries show it as "12+ years" in place of the years written in the stored summary), `reassess_days` (the retest window: a whole number of days from 1 to 365, default 30; `profile status` shows it), `answer_style` (`star`, `soar` or `carl`: the default way a story is shown and judged complete, `star` when not set; a `--style` option overrides it for one run and `profile status` shows it), `research_days` (a whole number of days of 1 or more, default 30: company facts and role-question citations older than this count as stale), `question_research` (`yes` or `no` for role-question web research, or `unset` to clear the answer), `target_company` (a researched company, in any letter case, used by `target show` and `prep for-target` when no company is given and by no other command; `""` clears it; an unknown company, or one recorded as none found, is refused) or `preparing_for` (what the user is preparing for, in a few words, up to 200 characters; the skills save it last in "what are you preparing for", and `jobkit status --setup` prints `ready` only once it is saved); any other key is an error. |
| `profile companies` | `[rename ID NAME \| merge FROM INTO]` | List the employers found by the first resume scan. `rename` changes the name shown for an employer; `merge` folds the employer `FROM` into `INTO`, so both spellings count as one. Run `process-resumes --force` afterwards to rebuild with the change. |
| `profile key-topics` | `[TOPIC ...]` | Pin your own key topics (tier 1, any track, matched by name). No arguments shows the current list. |
| `profile header` | `[set NAME CONTACT_LINE]` | The name and contact line printed at the top of built resumes. No arguments shows it; `set` saves it. It is the only place contact details are kept. |
| `profile terms` | `[list \| add TEXT \| ignore TEXT \| rm TEXT \| import FILE \| check]`, `--kind`, `--match`, `--staged`, `--all`, `--history`, `--exhaustive`, `PATH ...` | For contributors who commit: personal words and stored text that must never reach a commit. `list` (default) shows every term with its source: derived from the contributor's name, header contact details, resume folder and employer names (never copied), or stored by the contributor. `add TEXT` stores a product, client or pattern (`--kind`; `--match word\|phrase\|regex`, by default a pattern if it looks like one, a whole word if short); `ignore TEXT` hides a term on purpose (a common word like an employer named Acme); `rm TEXT` removes a stored term or an ignore; `import FILE` stores one term per line. `check` scans the paths given, `--staged` the staged files as staged (the pre-commit hook), `--all` every file git would commit, `--history` every version of every file in the history of all branches (for a manual review), and exits 1 on any hit. Besides the terms, `check` compares each line with the contributor's stored data (resume lines and their other wordings, summaries, titles, certifications, education, stories, practice notes, the contributor's own vocabulary and the extracted resume text): a shared run of five words, a near-copy, an exact title, certification or degree, two of the contributor's figures, or three distinctive terms in one line is a hit. Such a hit shows only its kind and where the stored text comes from, never the text. With `--staged` it also warns, without failing, when the staged changes remove lines that match stored data. `--exhaustive` also checks the ignored common words and prints one block per word (`Word: NAME`, then one line per file with its line numbers, or `multiple lines: N` when a file has more than two), for a manual review (never run by the hook; expect false alarms). See [Keeping personal data out of commits](contributing.md#keeping-personal-data-out-of-commits) in the contributor guide. |
| `profile open` | `[add TEXT \| done ID]` | Open items and data notes. No arguments lists them; `add` records one; `done` closes one by its number. |
