# jobkit command-line manual

Eleven commands, installed into `.venv` by `uv sync`. Run them from the project folder as `uv run <command>`, or as `uv run python -m jobkit.<group>.<tool>`. `--help` works on every command and subcommand.

Conventions shared by all commands:

- Messages go to stdout; problems go to stderr with exit status 1. Usage errors (bad choice, missing argument) exit with status 2.
- A file argument written as `-` reads stdin (job descriptions, seeds, long answers).
- Verbs are the same everywhere: `init`, `status`, `list`, `show ID`, `next`, `set ID FIELD VALUE`, `for-jd JD`.
- All data lives in one database, `data/jobkit.db` under the home folder (`~/.jobkit`, which is `.jobkit` in your user folder on Windows, or the folder named by `JOBKIT_HOME`). Text files are read and written as UTF-8 on every platform. It is read and written only through these commands. Each command's changes are stored together or not at all, and several commands can run at once. Run `jobkit init` once before anything else.
- `[x]` means optional, `x...` means repeatable, `A|B` means one of.
- The shape of the files these commands read and write is in [data-structures.md](data-structures.md).

| Group | Commands |
|---|---|
| [Home folder](#home-folder) | `jobkit` |
| [Settings](#settings) | `profile` |
| [Resume data](#resume-data) | `process-resumes`, `query-resume`, `build-resume`, `match-score` |
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
| `jobkit export` | `--format json\|md`, `--only KIND`, `-o DIR` | The way to look at your data. Prints all of it (or one kind) as JSON (default) or Markdown; with `-o` writes one file per kind into `DIR`. Never changes the database and writes nothing unless `-o` is given. Kinds: `stories`, `engagements`, `themes`, `arch-catalog`, `arch-progress`, `arch-tracks`, `lead-questions`, `lead-progress`, `lead-scope`, `sessions`, `settings`, `employers`, `open-items`, `resume-companies`, `resume-skills`, `resume-profile`, `resume-index`, `resume-ledger`, `resume-unparsed`, `curated`, `curation-themes`. |
| `jobkit backup` | `-o FILE`, `--restore FILE` | Write a consistent copy of the database to `backup/` (or `FILE`), also while other commands are running. `--restore FILE` replaces the database with a backup after saving the current one. The file is first checked on a temporary copy (integrity, upgrade, every table, column and protective trigger, no broken references, every stored record readable); a file that is damaged, incomplete, not a jobkit database, or from a newer version is refused and nothing is changed. A refusal names the table, never the record's content. |

---

## Settings

### `profile`

Per-user settings, stored in the database. Standard library only.

| Subcommand | Arguments and options | What it does |
|---|---|---|
| `profile status` | none | Show the saved profile and what is missing. |
| `profile init` | `--resume-root PATH` (required), `--resume-dir SUB...`, `--name NAME` | Record where the resume files are. `--resume-dir` limits the scan to subfolders (repeatable). Run again, it only fills in what is unset and keeps existing answers (it says so); change the name or resume root with `profile set`. |
| `profile set` | `KEY VALUE` | Change one setting. `KEY` is `name`, `resume_root` or `reassess_days` (the retest window: a whole number of days from 1 to 365, default 30; `profile status` shows it); any other key is an error. |
| `profile companies` | `[rename ID NAME \| merge FROM INTO]` | List the employers found by the first resume scan. `rename` changes the name shown for an employer; `merge` folds the employer `FROM` into `INTO`, so both spellings count as one. Run `process-resumes --force` afterwards to rebuild with the change. |
| `profile tier1` | `[SERVICE ...]` | Pin your own tier-1 topics (any track, matched by name). No arguments shows the current list. |
| `profile open` | `[add TEXT \| done ID]` | Open items and data notes. No arguments lists them; `add` records one; `done` closes one by its number. |

---

## Resume data

### `process-resumes`

Builds the resume data from every `.pdf`, `.docx`, `.md` and `.txt` resume under the folders in the profile. Read-only on the resume folders; raw extracted text goes to `output/` under the home folder. Incremental: unchanged files are skipped, deleted or renamed files are pruned. Nothing is pruned when a configured folder is unavailable: a folder that does not exist, or one with no resume files although earlier runs read files from it, stops the run with an error naming the folder (exit status 1) and leaves the data unchanged. `--force` accepts an emptied folder as a deliberate removal.

| Option | What it does |
|---|---|
| (none) | Parse new or changed resumes and merge them in. |
| `--survey` | Show what each resume parses into; write nothing. |
| `--force` | Ignore the ledger and rebuild everything; also accepts a folder you emptied on purpose. |
| `process-resumes curate list` `[KIND]` | List your curation entries (all kinds, or one). |
| `process-resumes curate add` `KIND VALUE...` | Add or replace one curation entry. `--issued YYYY-MM` and `--expires YYYY-MM` apply to `certification`. |
| `process-resumes curate rm` `KIND VALUE...` | Remove one entry. For `extra-skill`, a second value removes one skill instead of the whole group. |

Curation (`process-resumes curate`) is what you decide about your data; it survives every rebuild and is applied after each one (run `process-resumes` to apply a change; a changed curation rebuilds the data from your resume files once). It is changed only with `curate`, never by editing files. The kinds and their arguments:

| Kind | `add` arguments | Effect |
|---|---|---|
| `certification` | `NAME [--issued] [--expires]` | Certifications shown on built resumes. Once there is any entry, the curated list replaces the certifications parsed from your resumes (`add` says so); with no entries the parsed ones are used. |
| `education` | `TEXT` | Education lines shown on built resumes. Replaces the parsed education once there is any entry, and the parsed education is back when the last entry is removed. |
| `wrong-metric` | `FIGURE` | Bullets containing this figure are flagged `needs_review` and hidden from `for-jd` by default. |
| `skill-merge` | `FROM TO` | Spell the skill `FROM` as `TO`. |
| `skill-drop` | `NAME` | Not a skill; left out. |
| `tag-only` | `NAME` | A quality word kept as a bullet tag, never a skill. |
| `skill-group` | `SKILL GROUP` | Put the skill in this group. |
| `extra-skill` | `GROUP NAME [ALIAS ...]` | A skill no resume mentions, added to a group. |
| `theme` | `BULLET_ID THEME...` | Themes of one bullet (replaces the inferred ones). |
| `ignore` | `BULLET_ID` | A fragment, not a bullet; left out. |
| `summary-angle` | `SUMMARY_ID ANGLE...` | The angles one opening summary suits. |

A bullet keeps its id through rebuilds while its claim continues, so only a real change (different numbers, or a bullet no longer similar) can leave a `theme` or `ignore` entry pointing at nothing; `query-resume review` and the end of a rebuild list such entries and never remove them.

### `query-resume`

Reads the resume data. Read-only.

| Subcommand | Arguments and options | What it does |
|---|---|---|
| `query-resume for-jd` (same as `query-resume match`) | `JD`; `--top N` (3), `--recency X` (2.0), `--summaries N` (2), `--include-review`, `--theme T...`, `--requirement NAME...` | Rank bullets per employer for a job description, suggest opening summaries, list JD skills with no supporting bullet, group skills to feature. `JD` is a text file or `-`. `--top` is bullets per employer. `--recency` is the maximum score bonus for bullets from recent roles, judged by the role's own start date and not by when a resume file was saved (`0` turns it off). A bullet shown in more resume files gains at most a small capped bonus; the file count is shown as provenance. A bullet that shows one skill the posting asks for is listed. `--include-review` also shows bullets flagged `needs_review`. `--theme` favours an extra theme (repeatable). `--requirement` names a skill or duty the posting asks for that may not be one of your stored skills (repeatable): it is searched for in the bullets and listed as a gap when nothing shows it. Without it the output says that such requirements were not checked. One- and two-letter skills (R, Go, HR) match as whole words with the same capitalisation; longer names ignore capitalisation. Skill names that are also ordinary words (Go, Make, Rust, Ruby, Dart, Ant, Pig, Chef, Swift, Spring, Puppet, Julia) match only with their own capitalisation and not at the start of a sentence ("Go to market"); such a use is listed as a possible match with its sentence to confirm, and `--requirement` counts it. |
| `query-resume search` | `--skill S`, `--company C`, `--text T`, `--theme T`, `--limit N` (20) | Filter bullets. Filters combine (all must match). Bullets are listed under their company, newest company first. `--limit` caps the total printed; when it cuts the list, the last line says how many matches each company has that were not shown (use `--company` or a higher `--limit` to see them). |
| `query-resume review` | none | Items needing a human look: bullets flagged `needs_review`, single-source skills, untagged themes, orphaned curation ids. |
| `query-resume stats` | none | Counts per employer and skill group. |

The ranking is keyword and tag based. Make the final picks yourself.

### `build-resume`

`build-resume JD [-o FILE] [--top N] [--max-bullets N] [--title ID="Title"]... [--recency X] [--include-review] [--requirement NAME]...`
`build-resume --approve RESUME` and `build-resume --status RESUME`

Writes a tailored Markdown resume: the best opening summary, the best bullets per employer, each employer once with every role under it showing its own title and dates (a gap between roles stays visible; `--title` applies to the latest role only). An employer with no usable bullet (for example every bullet is flagged) still shows its latest role's title and dates, and the build report names it; no employer is printed with nothing under it, the skills the JD asks for, certifications, every education entry as its own line, and a Projects section for stored projects that mention a skill the JD asks for. After upgrading, run `process-resumes --force` once so older bullets are tagged with short skill names too. Every bullet comes from the resume data, and no claim is repeated across employers (two different results that share a figure are both kept). Name and contact lines come from `profile/header.md` (a template is created on first run; re-run after filling it in). The result is a draft: the command ends with a review checklist. Next to the resume it writes `<name>.build.json` (job description fingerprint, settings, chosen bullet ids, gaps). It also lists JD skills you have evidence for that this draft does not show, apart from skills with no supporting bullet at all. The output lists, with the line text, every line that is not demonstrated for a skill the posting asks for (the line says the skill was not used at work) or reads like training (it still counts, so the draft may show it, but confirm whether you also used the skill at work).

| Argument or option | What it does |
|---|---|
| `JD` | Job description text file, or `-` for stdin. |
| `-o`, `--output FILE` | Output path (default `output/resumes/<jd file name>.md`; `-2`, `-3` ... is added when that file exists, so an earlier build is never overwritten). An explicit path is overwritten. |
| `--max-bullets N` | Limit the total number of bullets (the longest lists shrink first; each employer keeps one, so a limit below the number of employers is an error). |
| `--top N` | Bullets per employer (default 4; old employers get at most 2). |
| `--title ID="Title"` | Override the job title shown for one employer id (repeatable). |
| `--recency X` | Recency weight, as in `query-resume for-jd` (default 2.0). |
| `--include-review` | Allow bullets flagged `needs_review`. |
| `--requirement NAME` | A skill or duty the posting asks for, even if it is not a stored skill (repeatable), as in `query-resume for-jd`. A requirement with no supporting bullet is reported as a gap; without any, the output says requirements outside your stored skills were not checked. |
| `--approve RESUME` | After you have reviewed a built resume, record it as approved (with a fingerprint of the file). Refused while it still has the placeholder header. |
| `--status RESUME` | `draft`, `approved`, or `changed` (edited after approval). |

The build covers the whole posting: a JD skill your data backs up, but the first picks leave out, is covered by bringing in the best bullet that shows it. The output says how many JD skills the draft shows. A new build is always a draft.

### `match-score`

> **Experimental.** The levels, weights and wording are first versions and may change; treat the numbers as a rough guide.

Rates how well your stored resume lines cover a job posting, as a lower and an upper match score with the gaps. It is a match estimate: **not** any employer's applicant tracking system score and not a prediction of a hiring decision (every report says so). It is not `query-resume match` (an alias of `for-jd`), which ranks lines and gives no score. Claude rates the requirements (the `resume-workflows` skill); this command checks and adds up. The request and result are described in [data-structures.md](data-structures.md#match-scores-match-score). In the formula every credit, weight and threshold is a placeholder default. A skill line earns credit only when it is not flagged for review, not ignored and does not explicitly say that skill was not used professionally (a line that only reads like training counts for at most partial; both kinds are listed in the report's assumptions); a reviewer can contest a code-rated level with a reason (`contest`), and the report shows both levels.

| Subcommand | Arguments and options | What it does |
|---|---|---|
| `match-score extract` | `--jd FILE`, `-o`/`--output FILE` | Prints `cached: true` with the stored report when this posting was scored before the same day with the same resume lines (flagged, ignored and tagged lines count); otherwise prints the requirements code can rate (named skills, degree level, certifications, total years). Renews the stored result's last-used date. |
| `match-score check` | `REQUESTS`, `--jd FILE`, `--band NAME`, `-o`/`--output FILE` | Validates the requirements (every problem with its path, nothing repaired), applies the fixed priority rules and the code pass, and shows which close calls take their fallback with how far each moves the score. Writes nothing. |
| `match-score run` | `REQUESTS`, `--jd FILE`, `--band NAME`, `--json`, `-o`/`--output FILE` | Scores, stores the result, removes entries not used for 90 days and prints the report (gaps first, then the lower and upper scores, the assumptions and the caveat); `--json` prints the whole result. |
| `match-score list` | `--json`, `-o`/`--output FILE` | Stored results, newest first. |
| `match-score show` | `KEY`, `--json`, `-o`/`--output FILE` | Prints a stored result again (the first letters of the key are enough). |

`REQUESTS` and the posting file may each be `-` (stdin), but not both. `--band` replaces the band named in the request (a built-in one or one from `profile/match-bands.json`). Formula in short: category score = sum(weight x credit) / sum(weight) with credits full 1.00, substantial 0.75, partial 0.40, `profile_miss` 0, unknown 0 (lower) or 1 (upper); weights critical 3, required 2, preferred 1 times importance; the overall score combines populated categories by the band's weights rescaled to total 1; the upper score credits unresolved close calls at their higher reading.

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
| `lead status` | none | Confidence per category, and employers whose scope facts (reports, team, budget) are still missing. |
| `lead next` | `[--category C] [--order default\|random]` | The next question. |
| `lead list` | `[--category C]` | List questions. |
| `lead show` | `ID` | The question, profile facts, candidate stories and saved answers. |
| `lead set` | `ID principle\|notes\|confidence VALUE` | `principle` is "how I handle this" in your words. |
| `lead example` | `ID COMPANY FIELD VALUE` | `FIELD`: `situation task action result metric`. `COMPANY` is any employer in the resume data. Blank values are not counted; the target is up to three examples per question, fewer with fewer employers. |
| `lead skip` / `lead unskip` | `ID COMPANY [REASON]` | Mark an employer as not applicable for a question (never had that responsibility, no real example yet), in your own words; it counts as covered and shows as `N not applicable`. A real example replaces the mark; `skip` is refused when an example exists. |
| `lead profile` | `show` or `set COMPANY FIELD VALUE` | Factual scope per employer. `FIELD`: `title direct_reports indirect_team team_composition budget stakeholders reporting_to cadence notes`. Values come from you, never guessed. |

### `sessions`

Resumable practice sessions, stored in the database. A session keeps your complete answers; later drills add entries and never edit old ones.

| Subcommand | Arguments and options | What it does |
|---|---|---|
| `sessions new` | `TITLE [--mode M] [--topic T] [--order O] [--category C] [--jd FILE] [--track T] [--area A] [--tier N] [--kind K] [--company C] [--count N] [--only-open] [--due]` | Start a session with a queue of items. Unfinished stories and cards, leadership questions and cards that are not solid come first; finished stories and solid items follow (solid items not drilled for 30 days before recently solid ones), so strong material is still rehearsed and nothing saved changes. `--only-open` queues only the unfinished and weak ones. `--mode`: `architecture`, `stories`, `jd`, `leadership`, `tutor` (default: `jd` when `--jd` is given, else `architecture`; `--jd` with another mode is an error). `--topic` (tutor mode only): `architecture`, `leadership` or `stories`. `--count` is the queue length (default 10). A jd session takes a card and a story in turn, so the count cannot leave one kind out; when one kind runs out the other fills the rest. The start message gives the number of each kind queued and how many matching items the count left out. The filters apply to the matching mode, jd mode included; `--tier N` means tier N or lower. `--due` queues only the items due for a retest (the same set as `readiness --due`; with no `--mode` and no `--jd` it covers cards, leadership questions and stories, oldest first, stored with the mode `retest`, and a filter such as `--tier` limits only the kind it belongs to; with a `--mode` it queues only that mode's due items; says so and creates nothing when none is due; cannot be combined with `--only-open`). The solid-card aging in the default queue follows the stored retest window. |
| `sessions list` | none | List sessions. |
| `sessions resume` | `ID` | What was covered, the last answers and the next item. A queued item whose card, question or story was removed is reported as unavailable and skipped. |
| `sessions log` | `ID ITEM --question Q --answer A\|- [--grade G] [--confidence 0\|1\|2] [--quiz]` | Record one answered item. `--answer -` reads the full answer from stdin. `--quiz` (tutor mode) says a quiz was answered correctly and needs `--grade` and `--confidence 2`. An item that does not exist, including a queued item that was removed, is refused until it exists again. |
| `sessions close` | `ID` | Close a session. |
| `sessions reopen` | `ID` | Continue a closed session. |

Teaching caps a card's confidence at 1; a passed quiz allows 2.

### `readiness`

`readiness [--jd FILE] [--days N] [--due [--json] [-o FILE]]`: coverage and evidence per area across cards, leadership questions and stories. Read-only. `--jd` limits it to what a job description touches (architecture and stories). `--days` is how old a solid answer may be before it reads as aging; the default is the stored retest window (`profile set reassess_days N`, 30 when none is set). `--due` prints, instead of the report, the items due for a retest (the ones the report labels `aging` or `done-aging`): id, name, the date of the last good answer and its age in days, oldest first, or `none due`; `--json` and `-o FILE` give it as JSON or write it to a file; it cannot be combined with `--jd`.

Labels: `untested`, `some gaps`, `solid-unlogged`, `solid-once`, `solid-repeated`, `aging` (also when every solid answer is older than `--days`). Stories: `empty`, `draft`, `done`, `done-rehearsed` (answer logged within `--days`), `done-aging`; a story label says attempted, not graded. A tutor lesson does not refresh the last-drilled date. There is deliberately no single score.
