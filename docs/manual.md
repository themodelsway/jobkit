# jobkit manual

jobkit provides three skills for Claude Code and Codex. Requests use plain language, and the skills run the required commands. Each guide describes the workflow before presenting the command reference; typing a command is never required.

| Skill | Purpose | Page |
| --- | --- | --- |
| interview-prep | Mock interviews: technical questions, leadership questions and personal stories. | [interview-prep.md](guides/interview-prep.md) |
| tutor | Teaching before quizzing, and interview readiness reports. | [tutor.md](guides/tutor.md) |
| resume-workflows | Resume import, tailoring for a job posting, and match scoring (early preview). | [resume-workflows.md](guides/resume-workflows.md) |

The pages in `plugins/jobkit/skills/` are the agent's instructions; these pages are for users of jobkit. Settings and interview progress can be checked from the command line with the [top commands to explore](explore.md).

## Running the commands directly

Twelve commands are installed by `uv sync` into `.venv`. The commands run from the repository root as `uv run <command>`, or as `uv run python -m jk.<group>.<tool>`. `--help` works on every command and subcommand.

Conventions shared by all commands:

- Messages go to stdout; problems go to stderr with exit status 1. Usage errors (bad choice, missing argument) exit with status 2.
- A file argument written as `-` reads stdin (job descriptions, seeds, long answers).
- Verbs are the same everywhere: `init`, `status`, `list`, `show ID`, `next`, `set ID FIELD VALUE`, `for-jd JD`.
- `[x]` means optional, `x...` means repeatable, `A|B` means one of.
- All data lives in one database, `data/jobkit.db` under the home folder (`~/.jobkit` on macOS and Linux, `%USERPROFILE%\.jobkit` (the `.jobkit` folder in your user home folder) on Windows, or the folder named by `JOBKIT_HOME`). Text files are read and written as UTF-8 on every platform. It is read and written only through these commands. Each command's changes are stored together or not at all, and several commands can run at once. Run `jobkit init` once before anything else.
- The shape of the files these commands read and write is in [data-structures.md](references/data-structures.md).

| Command | What it does | Described in |
|---|---|---|
| `arch` | Drill cards for the technologies an interview covers | [interview-prep.md](guides/interview-prep.md#arch) |
| `build-resume` | Write a tailored resume | [resume-workflows.md](guides/resume-workflows.md#build-resume) |
| `jobkit` | The home folder and database: init, status, export, backup | [below](#jobkit) |
| `lead` | Leadership questions | [interview-prep.md](guides/interview-prep.md#lead) |
| `match-score` | Rate how well resume lines cover a posting (early preview) | [resume-workflows.md](guides/resume-workflows.md#match-score) |
| `prep` | Interview stories and engagements | [interview-prep.md](guides/interview-prep.md#prep) |
| `resume-lines` | Find lines over 200 characters and check a shorter wording | [resume-workflows.md](guides/resume-workflows.md#resume-lines) |
| `process-resumes` | Read resumes into the data | [resume-workflows.md](guides/resume-workflows.md#process-resumes) |
| `profile` | Settings and open items | [below](#profile) |
| `query-resume` | Rank and search resume lines | [resume-workflows.md](guides/resume-workflows.md#query-resume) |
| `readiness` | The readiness report | [tutor.md](guides/tutor.md#readiness) |
| `sessions` | Resumable practice sessions | [interview-prep.md](guides/interview-prep.md#sessions) |

---

## Commands every skill uses

### `jobkit`

The home folder and its database. Standard library only.

| Subcommand | Arguments and options | What it does |
|---|---|---|
| `jobkit init` | none | Create the home folder and an empty database. Safe to repeat: existing data is never changed. |
| `jobkit status` | `--setup`, `--summary` | Show the database location, schema version, size and the number of records per kind of data. With `--setup`, print only how far setup has got, as one word: `no-database`, `no-resumes` (no resumes imported), `no-target` (resumes imported, but "what are you preparing for" has not been finished: `preparing_for` is not saved yet, even if some of its stories, leadership questions or drill cards were) or `ready`. When the check itself fails it prints why instead, decided from the error's type and SQLite's result code: `blocked` (saving not allowed), `busy` (another command holds the database), `too-new` (written by a newer version) or `failed` (anything else); it then exits 1 with one error line (type and message, the home folder shown as `~`, or `%USERPROFILE%` on Windows) and the troubleshooting line on standard error. With `--summary`, print the setup line; then, always, where this running copy keeps its data (`JOBKIT_HOME`), the launchers it was started from (`JOBKIT_COMMANDS_DIR`) and its Python environment with the jobkit and Python versions (`JOBKIT_PROGRAM_DIR`), with the home folder shown the same way; and, once resumes are imported, the open sessions and the latest one, how many items are due for a retest, each researched company's state and the default target company. Neither option creates the database (like every command, they upgrade an existing one from an older version when opening it); the skills act on their output. |
| `jobkit --version` | none | Print the installed version (`jobkit 0.3.0`). The plugin's setup check compares it with the plugin's version: same is ready, lower is offered an update, higher is left alone. |
| `jobkit export` | `--format json\|md`, `--only KIND`, `-o DIR` | The way to look at stored data. Prints all of it (or one kind) as JSON (default) or Markdown; with `-o` writes one file per kind into `DIR`. Never changes the database and writes nothing unless `-o` is given. Kinds: `stories`, `engagements`, `themes`, `arch-catalog`, `arch-progress`, `arch-tracks`, `lead-questions`, `lead-progress`, `lead-scope`, `sessions`, `settings`, `employers`, `open-items`, `terms`, `resume-companies`, `resume-skills`, `resume-profile`, `resume-index`, `resume-ledger`, `resume-unparsed`, `curated`, `curation-themes`. |
| `jobkit backup` | `-o FILE`, `--restore FILE` | Write a consistent copy of the database to `backup/` (or `FILE`), also while other commands are running. `--restore FILE` replaces the database with a backup after saving the current one; a current database that cannot be opened (damaged, or from a newer version) is saved file by file, and a missing one is not needed. The file is first checked on a temporary copy (integrity, upgrade, every table, column and protective trigger, no broken references, every stored record readable); a file that is damaged, incomplete, not a jobkit database, or from a newer version is refused and nothing is changed. A refusal names the table, never the record's content. |

The first command after an update that changes the database layout upgrades the database by itself. An existing database is first copied to `backup/jobkit-before-upgrade-v<old version>-<timestamp>.db`; if that copy cannot be written, nothing is upgraded. An upgrade cannot be reversed: to go back, run `jobkit backup --restore` with that copy and use the older release. These copies are not removed automatically.

### `profile`

Per-user settings, stored in the database. Standard library only.

| Subcommand | Arguments and options | What it does |
|---|---|---|
| `profile status` | none | Show the saved profile and what is missing. |
| `profile init` | `--resume-root PATH` (required), `--resume-dir SUB...`, `--name NAME`, `--replace` | Record where the resume files are. `--resume-dir` limits the scan to subfolders (repeatable). Run again, it only fills in what is unset and keeps existing answers (it says so); change the name or resume root with `profile set`. With `--replace`, the resume root and subfolders are set to exactly what is given (the whole folder when no `--resume-dir` is given) and every other setting is kept: the way to correct the folder choice; the next `process-resumes` drops resumes that are no longer in it. |
| `profile set` | `KEY VALUE` | Change one setting. `KEY` is `name`, `resume_root`, `years_experience` (a whole number such as `26` or `26+`; built summaries show it as "placeholder" in place of the years written in the stored summary) `reassess_days` (the retest window: a whole number of days from 1 to 365, default 30; `profile status` shows it) `answer_style` (`star`, `soar` or `carl`: the default way a story is shown and judged complete, `star` when not set; a `--style` option overrides it for one run and `profile status` shows it), `research_days` (a whole number of days of 1 or more, default 30: researched company facts older than this make the company stale) `target_company` (a researched company, in any letter case, used by `target show` and `prep for-target` when no company is given and by no other command; `""` clears it; an unknown company, or one recorded as none found, is refused) or `preparing_for` (what the user is preparing for, in a few words, up to 200 characters; the skills save it last in "what are you preparing for", and `jobkit status --setup` prints `ready` only once it is saved); any other key is an error. |
| `profile companies` | `[rename ID NAME \| merge FROM INTO]` | List the employers found by the first resume scan. `rename` changes the name shown for an employer; `merge` folds the employer `FROM` into `INTO`, so both spellings count as one. Run `process-resumes --force` afterwards to rebuild with the change. |
| `profile tier1` | `[SERVICE ...]` | Pin custom tier-1 topics (any track, matched by name). No arguments shows the current list. |
| `profile header` | `[set NAME CONTACT_LINE]` | The name and contact line printed at the top of built resumes. No arguments shows it; `set` saves it. It is the only place contact details are kept. |
| `profile terms` | `[list \| add TEXT \| ignore TEXT \| rm TEXT \| import FILE \| check]`, `--kind`, `--match`, `--staged`, `--all`, `--exhaustive`, `PATH ...` | For contributors who commit: personal words that must never reach a commit. `list` (default) shows every term with its source: derived from the contributor's name, header contact details, resume folder and employer names (never copied), or stored by the contributor. `add TEXT` stores a product, client or pattern (`--kind`; `--match word\|phrase\|regex`, by default a pattern if it looks like one, a whole word if short); `ignore TEXT` hides a term on purpose (a common word like an employer named Acme); `rm TEXT` removes a stored term or an ignore; `import FILE` stores one term per line. `check` scans the paths given, `--staged` the staged files as staged (the pre-commit hook), `--all` every file git would commit, and exits 1 on any hit. `--exhaustive` also checks the ignored common words and prints one block per word (`Word: NAME`, then one line per file with its line numbers, or `multiple lines: N` when a file has more than two), for a manual review (never run by the hook; expect false alarms). See [For contributors](#for-contributors-keeping-personal-data-out-of-commits). |
| `profile open` | `[add TEXT \| done ID]` | Open items and data notes. No arguments lists them; `add` records one; `done` closes one by its number. |

## For contributors: keeping personal data out of commits

This section is for contributors who commit to this repository. Users of jobkit who only use the skills can skip it.

Committed files must hold nothing personal: the contributor's name, phone, email, LinkedIn, resume folder, employers, clients or products. The pre-commit hook and `tests/test_no_personal.py` enforce it against a list of personal terms kept in the contributor's own database (`~/.jobkit`), never in the repository.

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
profile terms add "acme[ _.-]?ai" --kind client      # a pattern (regular expression), recognised by its characters
profile terms ignore Acme           # a common word left out on purpose (it is not removed from the data)
profile terms rm acme.ai           # remove a stored term, or an ignore
profile terms import terms.txt       # one term per line, a line with pattern characters is a pattern
profile terms check --staged         # what the hook runs: the staged files as staged
profile terms check --all            # every file git would commit
profile terms check --all --exhaustive   # also the ignored common words, for a manual review
```

Run them as `uv run profile terms ...`. A hit prints `path:line: kind term 'text'` and the command exits 1. Fix the file, or ignore the term if it is a false alarm.

### Common words

A name that is also an ordinary word (an employer called Acme) would flag many harmless lines, so the normal check and the hook skip it. Mark it with `profile terms ignore Acme`. A company folder name is already in the list (derived), so it only needs marking; it stays in the list, labelled as a common word. Before publishing, run `profile terms check --all --exhaustive`: it checks the ignored words too and prints one line for each word, with the files that contain it separated by commas. Read the hits and judge each one; many will be harmless. The command is never part of the hook.

### When it runs

- `.githooks/pre-commit` runs `profile terms check --staged` before ruff and the tests. Enable the hook once per clone with `git config core.hooksPath .githooks`.
- `tests/test_no_personal.py` runs the same check on every committable file, using the contributor's real home folder.
- With no database on the machine (a fresh clone, CI) both skip with a message. Only the generic checks (home paths, emails, phone numbers) run.

The term list is personal data: `jobkit export --only terms` shows it and `jobkit backup` includes it. Do not paste it into the repository, an issue or a pull request.
