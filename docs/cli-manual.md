# jobkit command-line manual

Ten commands, installed into `.venv/bin/` by `uv sync`. Run them from the project folder (`.venv/bin/<command>`), or as `.venv/bin/python -m jobkit.<group>.<tool>`. `--help` works on every command and subcommand.

Conventions shared by all commands:

- Messages go to stdout; problems go to stderr with exit status 1. Usage errors (bad choice, missing argument) exit with status 2.
- A file argument written as `-` reads stdin (job descriptions, seeds, long answers).
- Verbs are the same everywhere: `init`, `status`, `list`, `show ID`, `next`, `set ID FIELD VALUE`, `for-jd JD`.
- All data lives in one database, `data/jobkit.db` under the home folder (`~/.jobkit`, or the folder named by `JOBKIT_HOME`). It is read and written only through these commands. Each command's changes are stored together or not at all, and several commands can run at once. Run `jobkit init` once before anything else.
- `[x]` means optional, `x...` means repeatable, `A|B` means one of.
- The shape of the files these commands read and write is in [data-structures.md](data-structures.md).

| Group | Commands |
|---|---|
| [Home folder](#home-folder) | `jobkit` |
| [Settings](#settings) | `profile` |
| [Resume data](#resume-data) | `process-resumes`, `query-resume`, `build-resume` |
| [Interview prep](#interview-prep) | `prep`, `arch`, `lead`, `sessions`, `readiness` |

---

## Home folder

### `jobkit`

The home folder and its database. Standard library only.

| Subcommand | Arguments and options | What it does |
|---|---|---|
| `jobkit init` | none | Create the home folder and an empty database. Safe to repeat: existing data is never changed. |
| `jobkit status` | none | Show the database location, schema version, size and the number of records per kind of data. |
| `jobkit --version` | none | Print the installed version (`jobkit 0.1.0`). The plugin uses it to check that the installed commands match the plugin. |
| `jobkit migrate` | `--from PATH`, `--dry-run`, `--replace`, `--remove-old` | Import the old JSON files (`profile/`, `prep/`, `resume-data/` under `PATH`, default the current folder). It first copies them to `backup/json-<timestamp>/` and checks the copy, imports everything in one transaction, then exports the data again and compares record counts and checksums with the old files; any mismatch undoes the import and exits with status 1. The old files are never changed. `--dry-run` shows what would be imported and writes nothing. A second run reports that the data is already imported; `--replace` imports again after saving the current database. `--remove-old` deletes the old JSON files, but only after the database matches the backup copy; the backup stays. |
| `jobkit export` | `--format json\|md`, `--only KIND`, `-o DIR` | The way to look at your data. Prints all of it (or one kind) as JSON (default) or Markdown; with `-o` writes one file per kind into `DIR`. Never changes the database and writes nothing unless `-o` is given. Kinds: `stories`, `engagements`, `themes`, `arch-catalog`, `arch-progress`, `arch-tracks`, `lead-questions`, `lead-progress`, `lead-scope`, `sessions`, `settings`, `employers`, `open-items`, `resume-companies`, `resume-skills`, `resume-profile`, `resume-index`, `resume-ledger`, `resume-unparsed`, `curated`, `curation-themes`. |
| `jobkit backup` | `-o FILE`, `--restore FILE` | Write a consistent copy of the database to `backup/` (or `FILE`), also while other commands are running. `--restore FILE` replaces the database with a backup after saving the current one; a file that is not a jobkit database, or is from a newer version, is refused. |

---

## Settings

### `profile`

Per-user settings, stored in the database. Standard library only.

| Subcommand | Arguments and options | What it does |
|---|---|---|
| `profile status` | none | Show the saved profile and what is missing. |
| `profile init` | `--resume-root PATH` (required), `--resume-dir SUB...`, `--name NAME` | Record where the resume files are. `--resume-dir` limits the scan to subfolders (repeatable). |
| `profile set` | `KEY VALUE` | Change one setting. `KEY` is `name` or `resume_root`; any other key is an error. |
| `profile companies` | `[rename ID NAME \| merge FROM INTO]` | List the employers found by the first resume scan. `rename` changes the name shown for an employer; `merge` folds the employer `FROM` into `INTO`, so both spellings count as one. Run `process-resumes --force` afterwards to rebuild with the change. |
| `profile tier1` | `[SERVICE ...]` | Pin your own tier-1 topics (any track, matched by name). No arguments shows the current list. |
| `profile open` | `[add TEXT \| done ID]` | Open items and data notes. No arguments lists them; `add` records one; `done` closes one by its number. |

---

## Resume data

### `process-resumes`

Builds the resume data from every `.pdf`, `.docx`, `.md` and `.txt` resume under the folders in the profile. Read-only on the resume folders; raw extracted text goes to `output/` under the home folder. Incremental: unchanged files are skipped, deleted or renamed files are pruned.

| Option | What it does |
|---|---|
| (none) | Parse new or changed resumes and merge them in. |
| `--survey` | Show what each resume parses into; write nothing. |
| `--force` | Ignore the ledger and rebuild everything. |
| `process-resumes curate list` `[KIND]` | List your curation entries (all kinds, or one). |
| `process-resumes curate add` `KIND VALUE...` | Add or replace one curation entry. `--issued YYYY-MM` and `--expires YYYY-MM` apply to `certification`. |
| `process-resumes curate rm` `KIND VALUE...` | Remove one entry. For `extra-skill`, a second value removes one skill instead of the whole group. |

Curation (`process-resumes curate`) is what you decide about your data; it survives every rebuild and is applied after each one (run `process-resumes` to apply a change). It is changed only with `curate`, never by editing files. The kinds and their arguments:

| Kind | `add` arguments | Effect |
|---|---|---|
| `certification` | `NAME [--issued] [--expires]` | Certifications shown on built resumes. |
| `education` | `TEXT` | Education lines shown on built resumes. |
| `wrong-metric` | `FIGURE` | Bullets containing this figure are flagged `needs_review` and hidden from `for-jd` by default. |
| `skill-merge` | `FROM TO` | Spell the skill `FROM` as `TO`. |
| `skill-drop` | `NAME` | Not a skill; left out. |
| `tag-only` | `NAME` | A quality word kept as a bullet tag, never a skill. |
| `skill-group` | `SKILL GROUP` | Put the skill in this group. |
| `extra-skill` | `GROUP NAME [ALIAS ...]` | A skill no resume mentions, added to a group. |
| `theme` | `BULLET_ID THEME...` | Themes of one bullet (replaces the inferred ones). |
| `ignore` | `BULLET_ID` | A fragment, not a bullet; left out. |
| `summary-angle` | `SUMMARY_ID ANGLE...` | The angles one opening summary suits. |

A bullet id is a hash of its text, so editing a resume can leave a `theme` or `ignore` entry pointing at nothing; `query-resume review` and the end of a rebuild list such entries and never remove them.

### `query-resume`

Reads the resume data. Read-only.

| Subcommand | Arguments and options | What it does |
|---|---|---|
| `query-resume for-jd` (same as `query-resume match`) | `JD`; `--top N` (3), `--recency X` (2.0), `--summaries N` (2), `--include-review`, `--theme T...` | Rank bullets per employer for a job description, suggest opening summaries, list JD skills with no supporting bullet, group skills to feature. `JD` is a text file or `-`. `--top` is bullets per employer. `--recency` is the maximum score bonus for bullets from recently edited resumes (`0` turns it off). `--include-review` also shows bullets flagged `needs_review`. `--theme` favours an extra theme (repeatable). |
| `query-resume search` | `--skill S`, `--company C`, `--text T`, `--theme T`, `--limit N` (20) | Filter bullets. Filters combine (all must match). |
| `query-resume review` | none | Items needing a human look: bullets flagged `needs_review`, single-source skills, untagged themes, orphaned curation ids. |
| `query-resume stats` | none | Counts per employer and skill group. |

The ranking is keyword and tag based. Make the final picks yourself.

### `build-resume`

`build-resume JD [-o FILE] [--top N] [--title ID="Title"]... [--recency X] [--include-review]`

Writes a tailored Markdown resume: the best opening summary, the best bullets per employer, the skills the JD asks for, certifications and education. Every bullet comes from the resume data. Name and contact lines come from `profile/header.md` (a template is created on first run).

| Argument or option | What it does |
|---|---|
| `JD` | Job description text file, or `-` for stdin. |
| `-o`, `--output FILE` | Output path (default `output/resumes/<jd file name>.md`). |
| `--top N` | Bullets per employer (default 4; old employers get at most 2). |
| `--title ID="Title"` | Override the job title shown for one employer id (repeatable). |
| `--recency X` | Recency weight, as in `query-resume for-jd` (default 2.0). |
| `--include-review` | Allow bullets flagged `needs_review`. |

---

## Interview prep

### `prep`

STAR stories and engagements, stored in the database.

**Stories**

| Subcommand | Arguments and options | What it does |
|---|---|---|
| `prep init` (same as `prep skeleton`) | none | Create or extend stories and themes from the resume data. Never overwrites answers you filled in. |
| `prep status` | none | Stories per employer, and how many are filled. |
| `prep list` | `[--company ID]` | Every story: id, status, headline. |
| `prep next` | `[--company ID]` | Print the next empty story to work on. |
| `prep show` | `STORY_ID` | Print one story. |
| `prep set` | `STORY_ID FIELD VALUE` | Set a field. `FIELD`: `situation task action result metric lessons notes status`, `spoken.60s`, `spoken.2min`, or a list field (`follow_ups likely_questions never_say also_themes`, items separated by ` \| `). `status` is `empty`, `draft` or `done`; `done` is blocked while `validate` reports errors. |
| `prep new` | `STORY_ID --company ID --theme T [--headline H] [--engagement E]` | Add a story beyond the generated ones. |
| `prep for-jd` | `JD [--top N]` | Rank stories for a job description (default 8), with typical questions. |
| `prep search` | `TEXT` | Search stories and engagements. |
| `prep validate` | `[ID]` | Check one story or all. Errors block `done` and exit 1; warnings are advice. |
| `prep export` | `[--story S \| --engagement E] [--format json\|md] [-o FILE]` | Export to JSON (default) or Markdown. |
| `prep evidence` | `STORY` | Dates the story was practised in sessions (read-only). |
| `prep migrate` | none | Bring stories and engagements to the current layout (idempotent). |

**Engagements** (one real project, reusable by several stories)

| Subcommand | Arguments and options | What it does |
|---|---|---|
| `prep engagement add` | `ID --company ID --title T [--role R] [--period P] [--summary S]` | Create an engagement. |
| `prep engagement list` | none | List engagements. |
| `prep engagement show` | `ID` | Print one engagement. |
| `prep engagement set` | `ID FIELD VALUE` | `FIELD`: `title my_role period summary notes`. |
| `prep fact add` | `ENG "text" --basis B [--source URL] [--note N]` | Record a fact. `B`: `stated estimate unsure verified-doc proposed`. `verified-doc` needs a URL. |
| `prep fact set` | `ENG FACT_ID [--text T] [--basis B] [--source URL] [--note N]` | Change a fact. |
| `prep fact rm` | `ENG FACT_ID` | Remove a fact. |
| `prep decision add` | `ENG --what W [--why Y] [--alternatives "a \| b"] [--tradeoffs T] [--ownership O]` | Record a decision. `O`: `mine team client shared unsure` (default `unsure`). |
| `prep decision rm` | `ENG DECISION_ID` | Remove a decision. |
| `prep person add` | `ENG --role R [--note N]` | Record someone involved. |

**Linking, numbers, follow-ups**

| Subcommand | Arguments and options | What it does |
|---|---|---|
| `prep link` | `STORY ENG [--facts f1,f2]` | Attach an engagement and the facts the story relies on. Only `stated`, `estimate` and `verified-doc` facts may back a story. |
| `prep unlink` | `STORY [--facts f1,f2]` | Without `--facts`, detach the engagement entirely. |
| `prep metric add` | `STORY [--name N] [--value V] [--basis B] [--note N]` | Add a number the story quotes. `B`: `measured estimated stated unknown`. |
| `prep metric rm` | `STORY NAME` | Remove a metric. |
| `prep followup add` | `STORY "question"` | Add a follow-up question. |
| `prep followup resolve` | `STORY INDEX_OR_TEXT [--answer A]` | Mark one answered, with what you said. |

### `arch`

Architecture drill cards for one or more technologies (tracks), stored in the database. A card is a service, a decision pair or a scenario. AWS is bundled; any other technology is added from a JSON seed with no code.

| Subcommand | Arguments and options | What it does |
|---|---|---|
| `arch tracks` | none | List the tracks you can drill and which are enabled. |
| `arch track add` | `NAME --seed FILE\|-` | Validate and register a technology from a JSON seed. `NAME` is 2-31 lower-case letters, digits or `-`, and not `aws`. Seed shape: [data-structures.md](data-structures.md#preparchtracksnamejson-track-seed). |
| `arch init` | `[--track NAME ...]` | Create or extend the catalog and progress. Default: the enabled tracks, else `aws`. Tier 1 is derived from your resumes (or `profile tier1`). |
| `arch status` | none | Cards by confidence, per area (per track and area when several tracks are enabled). |
| `arch next` | `[--track T] [--area A] [--tier N] [--kind K] [--order O]` | The next card to drill. `K`: `service pair scenario`. `O`: `default` or `random`. |
| `arch list` | `[--track T] [--area A] [--tier N] [--kind K]` | List cards. |
| `arch show` | `ID` | Print a card with its track, lifecycle facts and your notes. |
| `arch set` | `ID confidence\|notes VALUE` | Confidence is `0` none, `1` some gaps, `2` solid. |
| `arch for-jd` | `JD` | Cards the job description mentions, weakest first (across all tracks). |
| `arch stale` | `[--months N]` | Cards whose facts are unverified or older than N months (default 6). |
| `arch refresh` | `ID --status S --source URL [--date D] [--note T] [--change "DATE\|SUMMARY"]...` | Record researched facts. `S`: `active maintenance sunset unverified`. `--source` is required and must be an https page on one of the card's track hosts. |

`--tier N` keeps cards of tier N or lower (`--tier 2` = tiers 1 and 2). `--area` matches part of the area name.

Lifecycle words: maintenance means closed to new customers with no new features; sunset means it has an end date.

### `lead`

Leadership questions, stored in the database. Each question holds your principle plus one STAR example per recent employer (the top three).

| Subcommand | Arguments and options | What it does |
|---|---|---|
| `lead init` | none | Create or extend the questions and progress (never overwrites answers). |
| `lead status` | none | Confidence per category, and profile gaps. |
| `lead next` | `[--category C] [--order default\|random]` | The next question. |
| `lead list` | `[--category C]` | List questions. |
| `lead show` | `ID` | The question, profile facts, candidate stories and saved answers. |
| `lead set` | `ID principle\|notes\|confidence VALUE` | `principle` is "how I handle this" in your words. |
| `lead example` | `ID COMPANY FIELD VALUE` | `FIELD`: `situation task action result metric`. |
| `lead profile` | `show` or `set COMPANY FIELD VALUE` | Factual scope per employer. `FIELD`: `title direct_reports indirect_team team_composition budget stakeholders reporting_to cadence notes`. Values come from you, never guessed. |

### `sessions`

Resumable practice sessions, stored in the database. A session keeps your complete answers; later drills add entries and never edit old ones.

| Subcommand | Arguments and options | What it does |
|---|---|---|
| `sessions new` | `TITLE [--mode M] [--topic T] [--order O] [--category C] [--jd FILE] [--track T] [--area A] [--tier N] [--kind K] [--company C] [--count N]` | Start a session with a queue of items. `--mode`: `architecture` (default), `stories`, `jd`, `leadership`, `tutor`. `--topic` (tutor mode only): `architecture`, `leadership` or `stories`. `--count` is the queue length (default 10). The filters apply to the matching mode; `--tier N` means tier N or lower. |
| `sessions list` | none | List sessions. |
| `sessions resume` | `ID` | What was covered, the last answers and the next item. |
| `sessions log` | `ID ITEM --question Q --answer A\|- [--grade G] [--confidence 0\|1\|2] [--quiz]` | Record one answered item. `--answer -` reads the full answer from stdin. `--quiz` (tutor mode) says a quiz was answered correctly and needs `--grade` and `--confidence 2`. |
| `sessions close` | `ID` | Close a session. |
| `sessions reopen` | `ID` | Continue a closed session. |

Teaching caps a card's confidence at 1; a passed quiz allows 2.

### `readiness`

`readiness [--jd FILE] [--days N]`: coverage and evidence per area across cards, leadership questions and stories. Read-only. `--jd` limits it to what a job description touches (architecture and stories). `--days` (default 30) is how old a solid answer may be before it reads as aging.

Labels: `untested`, `some gaps`, `solid-unlogged`, `solid-once`, `solid-repeated`, `aging`. There is deliberately no single score.
