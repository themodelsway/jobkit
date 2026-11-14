# interview-prep

The interview-prep skill runs a mock interview. It asks a question, waits for the answer, gives no hints, then grades the answer and saves it. This page explains how the skill is used, then lists the commands it runs. The [tutor](tutor.md) skill provides teaching before practice.

## How to use it

Requests use plain language and fall into these categories:

- Mock interview.
- Leadership question practice.
- Story rehearsal.
- Continuation of an earlier practice session.
- Preparation for a supplied job posting.

**The first time.** The skill asks what the preparation is for: the kind of role and the technologies it uses. It then sets up drill cards for each technology named, leadership questions, and a set of stories drawn from the resumes added with [resume-workflows](resume-workflows.md). Resumes must be added first.

**Every time.** The skill lists earlier sessions and asks whether to start a new one or resume one. It never chooses on the user's behalf.

- **Retests.** When well-answered items are older than the retest window (30 days unless another number is set), the skill says how many and asks whether to re-check those first. A retest never starts without confirmation.
- **Order.** For technical and leadership questions, the skill asks whether to start with the weakest topics or mix them randomly.
- **One question at a time.** The skill asks, the user answers, and the skill grades. The complete answer is saved, and a session can be stopped and resumed. Later practice adds entries and never edits old ones.

**Practice areas**

- **Technical questions.** Cards for services, decision pairs (comparisons of alternatives and the conditions for choosing each) and scenarios, for the technologies named. Facts used for grading come from the vendor's own documentation, not from memory.
- **Leadership questions.** Roadmapping, mentoring, conflict, prioritisation and more. Each is tied to examples from the most recent employers.
- **Stories.** The skill walks through each story one question at a time (situation, the user's part, the actions, the result with a number, what would change) and saves the answers as it goes. It asks before saving anything that is not already on a resume. Answers can be structured as STAR, SOAR or CARL; see [Answer styles](#answer-styles).
- **A job posting.** Given a posting, the skill ranks the stories for it, reports which are unfinished and which requirements have no story, then rehearses the questions typically asked.

At the end, the skill closes the session. Overall readiness is covered on the [tutor](tutor.md#readiness-report) page.

## Commands it uses

The skill runs these commands. The full options are below, and the shared commands `jobkit` and `profile` are in the [manual](../manual.md#commands-every-skill-uses). The tutor skill uses the same commands, and `readiness` is described on its [page](tutor.md#readiness).

### `prep`

STAR stories and engagements, stored in the database.

**Stories**

| Subcommand | Arguments and options | What it does |
|---|---|---|
| `prep init` (same as `prep skeleton`) | none | Create or extend stories and themes from the resume data. Never overwrites answers already filled in. |
| `prep status` | none | Stories per employer, and how many are filled. |
| `prep list` | `[--company ID]` | Every story: id, status, headline. |
| `prep next` | `[--company ID]` | Print the next empty story to work on. |
| `prep show` | `STORY_ID [--style S]` | Print one story, grouped as the parts of the style. Nothing stored changes. |
| `prep set` | `STORY_ID FIELD VALUE [--style S] [--merge]` | Set a field. `FIELD`: `situation task action result metric lessons notes status`, `spoken.60s`, `spoken.2min`, a list field (`follow_ups likely_questions never_say also_themes`, items separated by ` \| `), or a part name of a style (`obstacle`, `challenge`, `learning`). `status` is `empty`, `draft` or `done`; `done` needs every part of the style in force and is blocked while `validate` reports errors. A part is saved to the stored field it maps to, and the message names that field. A part that does not belong to the style is an error that lists the parts that do. `--merge` is explained under [Answer styles](#answer-styles). |
| `prep styles` | none | List the three answer styles with their parts and a use for each, and the style in force. |
| `prep new` | `STORY_ID --company ID --theme T [--headline H] [--engagement E]` | Add a story beyond the generated ones. |
| `prep for-jd` | `JD [--top N]` | Rank stories for a job description (default 8), with typical questions. |
| `prep search` | `TEXT` | Search stories and engagements. |
| `prep validate` | `[ID] [--style S]` | Check one story or all. Errors block `done` and exit 1; warnings are advice. A story already `done` is valid while it is complete in any style; a part missing in the style in force is a warning. |
| `prep export` | `[--story S \| --engagement E] [--format json\|md] [--style S] [-o FILE]` | Export to JSON (default) or Markdown. The Markdown cheat sheet uses the headings of the style. |
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
| `prep followup resolve` | `STORY INDEX_OR_TEXT [--answer A]` | Mark one answered, with the answer given. |

#### Answer styles

A story is stored once, and a style is a labelled view of it. No story is rewritten per style, and showing a story in any style leaves the stored text unchanged.

| Style | Parts in order | Use |
|---|---|---|
| `star` | Situation, Task, Action, Result | A clear sequence for most behavioural questions. The style when none is chosen. |
| `soar` | Situation, Obstacle, Action, Result | When overcoming something is the point of the story. |
| `carl` | Challenge, Action, Result, Learning | When what was learned matters as much as what happened. |

How the parts map onto the stored story:

| Part | Stored field |
|---|---|
| Obstacle (`soar`) | `task` |
| Challenge (`carl`) | `situation` followed by `task` |
| Learning (`carl`) | `lessons` |
| Situation, Action, Result | themselves, in every style |

- **Style in force.** The `--style` option, then the answer style saved in the profile (`profile set answer_style`), then `star`.
- **Saving a challenge never repeats text.** A challenge is saved as the `situation`. When the `task` already has text, the save is refused, and the message offers two ways forward: set the `situation` and `task` separately, or save again with `--merge`. A merge stores the new text as the `situation`, empties the `task` and says so. A challenge that was shown, edited and saved with `--merge` reads back as exactly the edited text.
- **Done.** Marking a story `done` needs every part of the style in force. A story already `done` stays valid while it is complete in at least one of the three styles, so changing the default style never turns a valid story into an error; the gaps in the style in force are warnings.
- **Unchanged in every style.** Fact and metric rules, the hedging rule for estimated numbers, the warning when "we" outnumbers "I" in the action, and the word limits of the spoken versions. Spoken versions are shown as written, with a note, and are not rearranged to the style.
- **Stored field names.** `situation`, `task`, `action` and `result` keep working in `prep set` when no `--style` is given.

### `arch`

Architecture drill cards for one or more technologies (tracks), stored in the database. A card is a service, a decision pair or a scenario. AWS is bundled; any other technology is added from a JSON seed with no code.

| Subcommand | Arguments and options | What it does |
|---|---|---|
| `arch tracks` | none | List the tracks available to drill and which are enabled. |
| `arch track add` | `NAME --seed FILE\|-` | Validate and register a technology from a JSON seed. `NAME` is 2-31 lower-case letters, digits or `-`, and not `aws`. Seed shape: [data-structures.md](../references/data-structures.md#track-seed-track-export-kind-arch-tracks). |
| `arch init` | `[--track NAME ...]` | Create or extend the catalog and progress. Default: the enabled tracks, else `aws`. Tier 1 is derived from the resumes (or `profile tier1`). |
| `arch status` | none | Cards by confidence, per area (per track and area when several tracks are enabled). |
| `arch next` | `[--track T] [--area A] [--tier N] [--kind K] [--order O]` | The next card to drill. `K`: `service pair scenario`. `O`: `default` or `random`. |
| `arch list` | `[--track T] [--area A] [--tier N] [--kind K]` | List cards. |
| `arch show` | `ID` | Print a card with its track, lifecycle facts and notes. |
| `arch set` | `ID confidence\|notes VALUE` | Confidence is `0` none, `1` some gaps, `2` solid. |
| `arch for-jd` | `JD` | Cards the job description mentions, weakest first (across all tracks). |
| `arch stale` | `[--months N]` | Cards whose facts are unverified or older than N months (default 6). |
| `arch refresh` | `ID --status S --source URL [--date D] [--note T] [--change "DATE\|SUMMARY"]...` | Record researched facts. `S`: `active maintenance sunset unverified`. `--source` is required and must be an https page on one of the card's track hosts. |

`--tier N` keeps cards of tier N or lower (`--tier 2` = tiers 1 and 2). `--area` matches part of the area name.

Lifecycle words: maintenance means closed to new customers with no new features; sunset means it has an end date.

### `lead`

Leadership questions, stored in the database. Each question holds the user's principle plus one STAR example per recent employer (the top three).

| Subcommand | Arguments and options | What it does |
|---|---|---|
| `lead init` | none | Create or extend the questions and progress (never overwrites answers). |
| `lead status` | none | Confidence per category, and employers whose scope facts (reports, team, budget) are still missing. |
| `lead next` | `[--category C] [--order default\|random]` | The next question. |
| `lead list` | `[--category C]` | List questions. |
| `lead show` | `ID` | The question, profile facts, candidate stories and saved answers. |
| `lead set` | `ID principle\|notes\|confidence VALUE` | `principle` is the candidate's approach to the leadership topic, in the user's words. |
| `lead example` | `ID COMPANY FIELD VALUE` | `FIELD`: `situation task action result metric`. `COMPANY` is any employer in the resume data. Blank values are not counted; the target is up to three examples per question, fewer with fewer employers. |
| `lead skip` / `lead unskip` | `ID COMPANY [REASON]` | Mark an employer as not applicable for a question (never had that responsibility, no real example yet), in the user's own words; it counts as covered and shows as `N not applicable`. A real example replaces the mark; `skip` is refused when an example exists. |
| `lead profile` | `show` or `set COMPANY FIELD VALUE` | Factual scope per employer. `FIELD`: `title direct_reports indirect_team team_composition budget stakeholders reporting_to cadence notes`. Values come from the user, never guessed. |

### `sessions`

Resumable practice sessions, stored in the database. A session keeps the complete answers; later drills add entries and never edit old ones.

| Subcommand | Arguments and options | What it does |
|---|---|---|
| `sessions new` | `TITLE [--mode M] [--topic T] [--order O] [--category C] [--jd FILE] [--track T] [--area A] [--tier N] [--kind K] [--company C] [--count N] [--only-open] [--due]` | Start a session with a queue of items. Unfinished stories and cards, leadership questions and cards that are not solid come first; finished stories and solid items follow (solid items not drilled for 30 days before recently solid ones), so strong material is still rehearsed and nothing saved changes. `--only-open` queues only the unfinished and weak ones. `--mode`: `architecture`, `stories`, `jd`, `leadership`, `tutor` (default: `jd` when `--jd` is given, else `architecture`; `--jd` with another mode is an error). `--topic` (tutor mode only): `architecture`, `leadership` or `stories`. `--count` is the queue length (default 10). A jd session takes a card and a story in turn, so the count cannot leave one kind out; when one kind runs out the other fills the rest. The start message gives the number of each kind queued and how many matching items the count left out. The filters apply to the matching mode, jd mode included; `--tier N` means tier N or lower. `--due` queues only the items due for a retest (the same set as `readiness --due`; with no `--mode` and no `--jd` it covers cards, leadership questions and stories, oldest first, stored with the mode `retest`, and a filter such as `--tier` limits only the kind it belongs to; with a `--mode` it queues only that mode's due items; says so and creates nothing when none is due; cannot be combined with `--only-open`). The solid-card aging in the default queue follows the stored retest window. |
| `sessions list` | none | List sessions. |
| `sessions resume` | `ID` | What was covered, the last answers and the next item. A queued item whose card, question or story was removed is reported as unavailable and skipped. |
| `sessions log` | `ID ITEM --question Q --answer A\|- [--grade G] [--confidence 0\|1\|2] [--quiz]` | Record one answered item. `--answer -` reads the full answer from stdin. `--quiz` (tutor mode) says a quiz was answered correctly and needs `--grade` and `--confidence 2`. An item that does not exist, including a queued item that was removed, is refused until it exists again. |
| `sessions close` | `ID` | Close a session. |
| `sessions reopen` | `ID` | Continue a closed session. |

Teaching caps a card's confidence at 1; a passed quiz allows 2.
