# resume-workflows

The resume-workflows skill imports resumes into one store, creates tailored drafts for job postings and estimates how well stored resume evidence covers a posting. The interview skills use the imported data. This page explains how the skill is used, then lists the commands it runs.

## How to use it

Requests use plain language and fall into these categories:

- Resume import, from a named folder.
- Addition of a new resume file.
- Tailoring for a supplied job posting.
- Match assessment for a supplied job posting.

**Adding resumes.** The skill takes the folder that holds the resumes. It finds every PDF, Word, Markdown and text file in that folder and its subfolders, previews what each parses into, and then reads them. The jobkit commands only read your resume folder, and the skill tells the agent never to change it. Every resume is split by employer and merged into one store. Wording that appears in several resumes is kept once, with its sources. Files that have not changed are skipped on later runs, new files are added and removed files are dropped. Older Word formats (`.doc`, `.rtf`, `.odt`) require conversion to `.docx` before import. Resumes can be laid out in many ways: skills or highlights in a side column (PDF columns, Word text boxes or tables), headings such as `Experience` or `Career Highlights`, dates written `09/2021`, `Sep 2021` or `2012`, a job written `Company | Title | dates` or with the title first, and several titles at one employer. After a plugin update that changes how resumes are read, the next run saves a copy of your data and re-reads every resume once (your curation is kept). The preview names anything that looks wrong, such as an unknown heading that ended the work history. A PDF that cannot be read as text (a scan, or a damaged file) is reported with its reason, and the skill tells the agent to ask before reading its pages visually. Where the app can run it, the skill has the pages read by the `resume-visual-scanner` helper, to keep the page images out of the main conversation.

For a PDF with a text layer, the parser output can be compared with a reading of the page images; the skill tells the agent to do this only when the user asks. The agent goes through the differences one at a time. Confirmed corrections are stored in the data folder and used until the PDF changes; the jobkit commands do not write to the original resume file.

**Checking the result.** The skill reports what it found: employers, lines and skills, and anything that needs a human look, such as conflicting figures. A figure known to be wrong can be flagged, so lines that use it are marked and left out of matching.

## Tailoring a resume (early preview)

For a supplied job posting, the skill:

1. lists every skill or duty the posting asks for and builds a draft Markdown resume from the stored lines: the best opening summary, the best lines per employer under each role, the skills the posting asks for, certifications and education;
2. reports the draft location, requirements with no evidence in the stored resumes, and skills evidenced in the stored resumes but missing from the draft;
3. asks about lines it left out because their numbers may be off, and about lines that read like training ("was this skill also used at work?");
4. asks for your name and contact line the first time, and saves them in your profile (`profile header`), not in the resume data.

The draft requires user review and explicit approval; the skill never approves one on its own. Suggested wording remains subject to user acceptance. Rankings use keywords and tags; final bullet selection requires user review.

## Match score (early preview)

Rates how well the resume lines cover a posting: a lower and an upper score, the requirements the resumes do not show yet, and the assumptions made. It is an estimate of coverage. It is not any employer's applicant-tracking score, and it does not predict whether the user will be hired. The model in the running app rates each requirement against the lines; the command checks and adds up. Where the app can run it, the skill has the first rating pass done by the `jd-matcher` helper. A stored score is reused when the posting, the resume data, the scoring settings and the assessment date all match; otherwise the posting is assessed again.

## Shortening long lines (only on request)

The target length is 200 characters for a line on a built resume and 400 for the opening summary. When a line has a shorter wording in one of the user's own resume files, the build uses it. Otherwise the build keeps the stored wording and reports how many lines are long.

Shortening is offered only on request. The skill goes through the long lines one at a time and proposes a rephrasing of at most 200 characters with the same meaning, figures and names. A script checks the count and the figures, and the user accepts, changes or keeps the original.

Accepted wording is saved as the approved wording and used in resumes it builds from then on, for as long as it still keeps the figures of its line. If a line changes so that its approved wording no longer fits, the build ignores that wording and says so, and `query-resume review` lists wording whose line is gone. Stored lines and resume files are never changed.

## Commands it uses

The skill runs these commands. The full options are below, and the shared commands `jobkit` and `profile` are in the [manual](../manual.md#commands-every-skill-uses).

### `process-resumes`

Builds the resume data from every `.pdf`, `.docx`, `.md` and `.txt` resume under the folders in the profile. Read-only on the resume folders; raw extracted text goes to `output/` under the home folder. Incremental: unchanged files are skipped, deleted or renamed files are pruned. Nothing is pruned when a configured folder is unavailable: a folder that does not exist, or one with no resume files although earlier runs read files from it, stops the run with an error naming the folder (exit status 1) and leaves the data unchanged. `--force` accepts an emptied folder as a deliberate removal.

| Option | What it does |
|---|---|
| (none) | Parse new or changed resumes and merge them in. |
| `--survey` | Show what each resume parses into; write nothing. |
| `--force` | Ignore the ledger and rebuild everything; also accepts a folder emptied on purpose. |
| `process-resumes curate themes` | List the themes and summary angles the tools act on. `curate add theme` warns about any other theme; `curate add summary-angle` refuses it. |
| `process-resumes curate list` `[KIND]` | List the curation entries (all kinds, or one). |
| `process-resumes curate add` `KIND VALUE...` | Add or replace one curation entry. With `-` as the only value, adds one entry per line of standard input (quotes group words, `#` starts a comment) in one save: a bad line saves nothing. `--issued YYYY-MM` and `--expires YYYY-MM` apply to `certification`. |
| `process-resumes curate rm` `KIND VALUE...` | Remove one entry. For `extra-skill`, a second value removes one skill instead of the whole group. |
| `process-resumes visual list` | List PDFs the parser cannot read (no text layer, or not readable as a PDF): the file to look at, and where to save the text a visual reading produced. The command reads nothing visually; the skill tells the agent to ask the user before a visual reading. A confirmed transcript replaces the PDF text on the next `process-resumes` run. |
| `process-resumes visual render` `FILE` | Writes the pages of that PDF as images under `output/visual/pages/` in the home folder and prints their paths, for an agent that cannot open a PDF's pages itself. Uses poppler's `pdftoppm` when installed; otherwise copies the page images out only of a plain scan (each page draws one JPEG over the whole page and nothing else: no text, tiles, clip, painting over the image, annotations or rotation), and says how to install poppler when that is not the case. A PDF of more than 30 pages is refused, not cut short. The images are removed when the transcript is confirmed. |
| `process-resumes visual confirm` `FILE` | After the user has checked the typed-out text of that PDF, tie the saved transcript to the PDF as it is now. For a PDF that reads as text it refuses a transcript that drops a role or work bullet of the PDF's own text, and lists each one; `--remove TEXT` (repeatable, TEXT as listed) confirms a removal the user agreed to and records it beside the transcript. The page images of that PDF are removed. Until then (and after the PDF is replaced) the transcript is not used. |
| `process-resumes visual text` `FILE` | Print the text the parser works from for a PDF (the confirmed transcript when there is one), as the start of a corrected text. `--layout` prints the layout reading the work history is parsed from. |
| `process-resumes visual schema` | Print the JSON a visual reading of a PDF must return: employers with title, dates and bullets, skills, certifications, education and summary. |
| `process-resumes visual compare` `FILE` `--reading JSON` | Compare a visual reading of a PDF (a file, or `-` for standard input) with what the parser reads from it, and list what only one side has and what differs, with both versions. Numbers, decimal points, qualification levels and technical punctuation (`C++`) count as differences; only case, spacing, typographic quotes and dashes and a trailing full stop are ignored. The reading is checked before use and a wrong shape is named by field (`employers[0].bullets`). Wording is never merged. After a corrected transcript is confirmed for the PDF, the parser side is that transcript. |

Curation (`process-resumes curate`) records the user's decisions about the data; it survives every rebuild and is applied after each one (run `process-resumes` to apply a change; a changed curation rebuilds the data from the resume files once). It is changed only with `curate`, never by editing files. The kinds and their arguments:

| Kind | `add` arguments | Effect |
|---|---|---|
| `certification` | `NAME [--issued] [--expires]` | Certifications shown on built resumes. Once there is any entry, the curated list replaces the certifications parsed from the resumes (`add` says so); with no entries the parsed ones are used. |
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
| `short-wording` | `BULLET_ID TEXT` | The approved shorter wording of one line, used instead of the stored line in built resumes (the stored line is never changed). Refused when it is over 200 characters, drops or adds a figure, or the id is unknown. |

A bullet keeps its id through rebuilds while its claim continues, so only a real change (different numbers, or a bullet no longer similar) can leave a `theme` or `ignore` entry pointing at nothing; `query-resume review` and the end of a rebuild list such entries and never remove them.

### `query-resume`

Reads the resume data. Read-only.

| Subcommand | Arguments and options | What it does |
|---|---|---|
| `query-resume for-jd` (same as `query-resume match`) | `JD`; `--top N` (3), `--recency X` (2.0), `--summaries N` (2), `--include-review`, `--theme T...`, `--requirement NAME...` | Rank bullets per employer for a job description, suggest opening summaries, list JD skills with no supporting bullet, group skills to feature. `JD` is a text file or `-`. `--top` is bullets per employer. `--recency` is the maximum score bonus for bullets from recent roles, judged by the role's own start date and not by when a resume file was saved (`0` turns it off). A bullet shown in more resume files gains at most a small capped bonus; the file count is shown as provenance. A bullet that shows one skill the posting asks for is listed. `--include-review` also shows bullets flagged `needs_review`. `--theme` favours an extra theme (repeatable). `--requirement` names a skill or duty the posting asks for that may not be one of the stored skills (repeatable): it is searched for in the bullets and listed as a gap when nothing shows it. Without it the output says that such requirements were not checked. One- and two-letter skills (R, Go, HR) match as whole words with the same capitalisation; longer names ignore capitalisation. Skill names that are also ordinary words (Go, Make, Rust, Ruby, Dart, Ant, Pig, Chef, Swift, Spring, Puppet, Julia) match only with their own capitalisation and not at the start of a sentence ("Go to market"); such a use is listed as a possible match with its sentence to confirm, and `--requirement` counts it. |
| `query-resume search` | `--skill S`, `--company C`, `--text T`, `--theme T`, `--limit N` (20) | Filter bullets. Filters combine (all must match). Bullets are listed under their company, newest company first. `--limit` caps the total printed; when it cuts the list, the last line says how many matches each company has that were not shown (use `--company` or a higher `--limit` to see them). |
| `query-resume review` | none | Items needing a human look: bullets flagged `needs_review`, single-source skills, untagged themes, orphaned curation ids. |
| `query-resume stats` | none | Counts per employer and skill group. |

Rankings use keywords and tags; final bullet selection requires user review.

### `build-resume`

`build-resume JD [-o FILE] [--top N] [--max-bullets N] [--title ID="Title"]... [--recency X] [--include-review] [--requirement NAME]...`
`build-resume --approve RESUME` and `build-resume --status RESUME`

Writes a draft Markdown resume from stored resume evidence. The draft contains an opening summary, the best bullets grouped by employer and role, relevant skills, certifications, education and relevant stored projects. Each employer appears once, with every role under it showing its own title and dates. Gaps between roles remain visible; `--title` overrides only the latest role of an employer.

An employer with no usable bullet (for example, every bullet is flagged) still appears with its latest role's title and dates, and the build report names it. No employer is printed with nothing under it. Every bullet comes from the resume data. No claim is repeated across employers or within one: "70 percent" and "70%" are the same figure, two lines on the same topic with the same figure count as one claim, and two different results that share a figure are both kept.

The build report lists the posting's skills with no supporting bullet and, separately, skills with evidence that the draft does not show. It also lists, with the line text, every line that is not demonstrated for a requested skill (the line says the skill was not used at work) or that reads like training (the line still counts and may appear in the draft, but whether the skill was also used at work needs confirmation). These lines require review before the draft is approved.

The saved header (`profile header set`) supplies the name and contact lines; the build is repeated after saving it. Each build is a draft and ends with a review checklist. Next to the resume, `<name>.build.json` records the job description fingerprint, settings, chosen bullet ids and gaps.

Selection details:

- Skills: the ones the posting names first, then stored skills that share a meaningful word with it (such as Stakeholder management for a posting about stakeholders), at most 10 per group.
- Education: every entry appears as its own line.
- Projects: a section for stored projects that mention a skill the posting asks for.
- Upgrade: after upgrading, `process-resumes --force` is run once so older bullets are tagged with short skill names too.

| Argument or option | What it does |
|---|---|
| `JD` | Job description text file, or `-` for stdin. |
| `-o`, `--output FILE` | Output path (default `output/resumes/<jd file name>.md`; `-2`, `-3` ... is added when that file exists, so an earlier build is never overwritten). An explicit path is overwritten. |
| `--max-bullets N` | Limit the total number of bullets (the longest lists shrink first; each employer keeps one, so a limit below the number of employers is an error). |
| `--top N` | Bullets per employer (default 4; old employers get at most 2). |
| `--title ID="Title"` | Override the job title shown for one employer id (repeatable). |
| `--recency X` | Recency weight, as in `query-resume for-jd` (default 2.0). |
| `--include-review` | Allow bullets flagged `needs_review`. |
| `--requirement NAME` | A skill or duty the posting asks for, even if it is not a stored skill (repeatable), as in `query-resume for-jd`. A requirement with no supporting bullet is reported as a gap; without any, the output says requirements outside the stored skills were not checked. |
| `--approve RESUME` | After a built resume has been reviewed, record it as approved (with a fingerprint of the file). Refused while it still has the placeholder header. |
| `--status RESUME` | `draft`, `approved`, or `changed` (edited after approval). |

The build covers the whole posting: a JD skill that the data backs up, but the first picks leave out, is covered by bringing in the best bullet that shows it. The output says how many JD skills the draft shows. A new build is always a draft.

### `resume-lines`

Finds stored lines over 200 characters and checks a proposed shorter wording. It never changes a line; accepted wording is saved with `process-resumes curate add short-wording`, which applies the same checks.

| Subcommand | Arguments and options | What it does |
|---|---|---|
| `resume-lines list` | `--all` | Stored lines over the limit with their length, longest first (every line with `--all`). Marks lines that already have approved wording. |
| `resume-lines show` | `ID` | One line: its length, its other stored wordings with their lengths, and any approved wording. |
| `resume-lines validate` | `ID TEXT` | Checks a proposed wording: at most 200 characters and every figure kept, none added ("70 percent" and "70%" are the same). Names that are no longer present are listed for the user to judge. Exits 1 when it is not acceptable. |

### `match-score`

> **Early preview.** The levels, weights and wording are first versions and may change; treat the numbers as a rough guide.

Rates how well the stored resume lines cover a job posting, as a lower and an upper match score with the gaps. It is a match estimate: **not** any employer's applicant tracking system score and not a prediction of a hiring decision (every report says so). It is not `query-resume match` (an alias of `for-jd`), which ranks lines and gives no score. The agent rates the requirements (the `resume-workflows` skill, in whichever app runs it); this command checks and adds up. The request and result are described in [data-structures.md](../references/data-structures.md#match-scores-match-score). In the formula every credit, weight and threshold is a placeholder default. A skill line earns credit only when it is not flagged for review, not ignored and does not explicitly say that skill was not used professionally (a line that only reads like training counts for at most partial; both kinds are listed in the report's assumptions); a reviewer can contest a code-rated level with a reason (`contest`), and the report shows both levels.

| Subcommand | Arguments and options | What it does |
|---|---|---|
| `match-score extract` | `--jd FILE` (`-` for standard input), `-o`/`--output FILE` | Saves the posting under `output/match/postings/` in the home folder and prints its `posting` KEY. Prints `cached: true` with the stored report when this posting was scored before the same day with the same resume lines (flagged, ignored and tagged lines count); otherwise prints the requirements code can rate (named skills, degree level, certifications, total years) and an `evidence` block: skill names by group (no sources), education in order and certifications, which is all pass 1 may cite besides lines. Renews the stored result's last-used date. |
| `match-score check` | `REQUESTS`, `--jd FILE` or `--key KEY` (the posting `extract` saved), `--band NAME`, `-o`/`--output FILE` | Validates the requirements (every problem with its path, nothing repaired), applies the fixed priority rules and the code pass, and shows which close calls take their fallback with how far each moves the score. Writes nothing. |
| `match-score run` | `REQUESTS`, `--jd FILE` or `--key KEY`, `--band NAME`, `--json`, `-o`/`--output FILE` | Scores, stores the result, removes entries not used for 90 days (and saved postings not used for 30) and prints the report (gaps first, then the lower and upper scores, the assumptions and the caveat); `--json` prints the whole result. |
| `match-score list` | `--json`, `-o`/`--output FILE` | Stored results, newest first. |
| `match-score show` | `KEY`, `--json`, `-o`/`--output FILE` | Prints a stored result again (the first letters of the key are enough). |

`REQUESTS` and the posting file may each be `-` (stdin), but not both. `--band` replaces the band named in the request (a built-in one or one from `profile/match-bands.json`). Formula in short: category score = sum(weight x credit) / sum(weight) with credits full 1.00, substantial 0.75, partial 0.40, `profile_miss` 0, unknown 0 (lower) or 1 (upper); weights critical 3, required 2, preferred 1 times importance; the overall score combines populated categories by the band's weights rescaled to total 1; the upper score credits unresolved close calls at their higher reading.
