# interview-prep

The interview-prep skill runs a mock interview. It asks a question, waits for the answer, gives no hints, then grades the answer and saves it. This page explains how the skill is used, then lists the commands it runs. The [tutor](tutor.md) skill provides teaching before practice.

## How to use it

Requests use plain language and fall into these categories:

- Mock interview.
- Leadership question practice.
- Story rehearsal.
- Continuation of an earlier practice session.
- Preparation for a supplied job posting.
- Preparation for a named company.

**The first time.** Before the first task, the skill tells the agent to ask what kind of role the preparation is for, then what to focus on: a field such as HR, product design, strategy, finance or project delivery, or a technology the role uses (it can suggest some from the resumes). The skill tells the agent to choose the role family itself from the role and to ask only when the role could fit more than one. For each field or technology (other than AWS, which is bundled as an example), the agent builds a topic list with a rubric and shows it in plain words; it is saved once the user responds with yes. The skill then sets up drill cards for each topic, leadership questions, and a set of stories drawn from the resumes added with [resume-workflows](resume-workflows.md). Resumes must be added first.

**Every time.** The skill lists earlier sessions and asks whether to start a new one or resume one. It never chooses on the user's behalf.

- **Retests.** When well-answered items are older than the retest window (30 days unless another number is set), the skill says how many and asks whether to re-check those first. A retest never starts without confirmation.
- **Order.** For knowledge and leadership questions, the skill asks whether to start with the weakest topics or mix them randomly.
- **One question at a time.** The skill asks, the user answers, and the skill grades. The complete answer is saved, and a session can be stopped and resumed. Later practice adds entries and never edits old ones.

**Practice areas**

- **Role knowledge.** Cards for the technologies or fields named: topics, comparisons (of alternatives and the conditions for choosing each) and scenarios, for any role. Each card is graded against the rubric of its role family (engineering, product, delivery, people or operations), or a rubric adapted for the role. Facts used for grading come from official sources (the vendor's documentation, a regulator, a standards body), for the track's country where one is set, not from memory.
- **Cases.** A question developed over several turns, as in product, consulting or operations interviews. The skill tells the agent to reveal information only when asked, to say when a figure is made up for practice, to push back at least once, and to grade the whole exchange.
- **Role-plays.** The agent plays a part, for example a sales director who wants a feature now or an employee receiving hard news, and the user pursues a goal. The skill tells the agent to stay in the part until the user is done, then step out and grade.
- **Leadership questions.** Roadmapping, mentoring, conflict, prioritization and more. Each is tied to examples from the most recent employers. The skill tells the agent to offer them when the role or resumes involve leading people, and otherwise only when asked.
- **Not covered.** Coding exercises, tests with one right answer, and written work samples such as a plan or a document.
- **Stories.** The skill walks through each story one question at a time (situation, the user's part, the actions, the result with a number, what would change) and saves the answers as it goes. It asks before saving anything that is not already on a resume. Answers can be structured as STAR, SOAR or CARL; see [Answer styles](#answer-styles).
- **A job posting.** Given a posting, the skill ranks the stories for it, reports which are unfinished and which requirements have no story, then rehearses the questions typically asked.

- **A named company.** When a company is named, the skill tells the agent to look up how that company hires, where the agent can read web pages: its published values, interview rounds, what interviewers look for and typical questions. See [Company research](#company-research). Stories are then ranked against the company's values, and a session puts the matching stories and leadership questions first.

At the end, the skill closes the session.

### Company research

Nothing about any company is shipped with jobkit. The facts are looked up when a company is named and stored in the data folder, each with the link to its page and the date it was read.

- **What the skill tells the agent to do.** Search with only the company name and the role title, never the user's name, employers or resume text. Read pages the company publishes first (careers, culture, engineering, the job posting), then articles other sites publish about its hiring. Leave out anything written by individual users on any site: reviews, interview reports, salary posts, comments, forum threads. For each fact, copy a short quote word for word from the page and state only what it says; confirm the page was read, the quote is on it and it is not user-written content; then save it.
- **What the commands check.** A fact without a link, a quote, a label, a date or the agent's confirmation is refused, and so is a quote over 40 words or a link on a known user-content site (forums, question-and-answer sites, and the review, interview-report and salary pages of job sites). A save is all or nothing. The commands never read the pages, so they cannot check that a quote is on its page; every fact keeps its link so the user can open it.
- **Where a fact came from.** Each fact is labeled `company-references` (a site the company publishes) or `othersite-references` (any other site), and the label and the site's name are shown beside it.
- **Suggested answer style.** A company may get a suggested style: `stated` when a stored fact says it, or `inferred` (the agent's suggestion, shown as such, with the facts it rests on). It never overrides the style in force.
- **Nothing found, or no web access.** When no page qualifies, the skill tells the agent to record that, say so in plain words and use the default answer style; nothing is invented. When the agent cannot read web pages (Codex in its default sandbox, for example), the skill tells the agent to skip research, say so once and use the default style; nothing is recorded, and there is no paste-the-page fallback. In both cases practice continues without the company: `prep for-target`, `readiness --target` and `sessions new --target` refuse a company recorded as none found or never researched, whether it is named or is the default company.
- **Aging.** Facts older than the research window (30 days unless `profile set research_days` changes it) make a company stale. The skill tells the agent to read it again when next needed: a quote still on its page gets today's date; a changed page is shown to the user, old and new wording side by side, and the fact is replaced or removed only once the user responds with yes.
- **Matching.** A company value lists story themes and hint words, which are the mapping to the user's stories and not claims about the company. A value reads `covered` (a story with content matches its theme), `possible` (stories match only by a hint word), `no story`, or `needs your judgment` (no themes or hint words; its typical questions are still practiced). Overall readiness is covered on the [tutor](tutor.md#readiness-report) page.

### Questions for the role

The skill tells the agent to ask about web research once and remember the answer. Before browsing, the agent states the search terms, limited to the posting's title, level and skills, recent role titles, and general skills. The skill excludes the user's name, contact details, employers, clients, employer-specific products, figures, and resume sentences. Published questions carry their source and the date read. General practice questions carry a general-knowledge label. Personal questions are generated locally from resume claims or posting requirements without matching resume evidence.

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
| `prep for-target` | `[COMPANY]` | Rank stories for a researched company: theme matches, then hint-word matches, then the rest, empty stories last; each story with the values it matches and, when the company has a suggested style, whether it is complete in it. Every value is listed with its state and its stored typical questions. Without `COMPANY`, the profile's `target_company` is used and named. Read-only. |
| `prep search` | `TEXT` | Search stories and engagements. |
| `prep validate` | `[ID] [--style S]` | Check one story or all. Errors block `done` and exit 1; warnings are advice. A story already `done` is valid while it is complete in any style; a part missing in the style in force is a warning. |
| `prep export` | `[--story S \| --engagement E] [--format json\|md] [--style S] [-o FILE]` | Export to JSON (default) or Markdown. The Markdown cheat sheet uses the headings of the style. |
| `prep evidence` | `STORY` | Dates the story was practiced in sessions (read-only). |

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

A story is stored once, and a style is a labeled view of it. No story is rewritten per style, and showing a story in any style leaves the stored text unchanged.

| Style | Parts in order | Use |
|---|---|---|
| `star` | Situation, Task, Action, Result | A clear sequence for most behavioral questions. The style when none is chosen. |
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

### `cards`

Role-knowledge cards for one or more fields or technologies (tracks), stored in the database. A card is a topic, a decision pair, a scenario, a case or a role-play. Each track belongs to a role family (`cards families` lists them), and each card is graded against its own track's rubric. Any field or technology is added from a JSON seed with no code; AWS is bundled as one example of the engineering family.

| Subcommand | Arguments and options | What it does |
|---|---|---|
| `cards families` | none | List the role families (people, design, strategy, product, delivery, finance, sales and marketing, operations, engineering): who each fits, example focus areas, where its facts come from, and the rubric each uses by default. Read-only; needs no database. |
| `cards tracks` | none | List the tracks available to drill, which are enabled, and each one's family. |
| `cards track add` | `NAME --seed FILE\|-` | Validate and register a technology or field from a JSON seed. `NAME` is 2-31 lower-case letters, digits or `-`, and not `aws`. Seed shape: [data-structures.md](../references/data-structures.md#track-seed-track-export-kind-cards-tracks). |
| `cards init` | `[--track NAME ...]` | Create or extend the catalog and progress. Default: the enabled tracks; with none enabled, the command fails and names how to choose a track (no track is loaded by default). Tier 1 is derived from the resumes (or `profile key-topics`). |
| `cards status` | none | Cards by confidence, per area (per track and area when several tracks are enabled). |
| `cards next` | `[--track T] [--area A] [--tier N] [--kind K] [--order O]` | The next card to drill. `K`: `topic pair scenario case role-play`. `O`: `default` or `random`. |
| `cards list` | `[--track T] [--area A] [--tier N] [--kind K]` | List cards. |
| `cards show` | `ID` | Print a card with its track and notes, a case's situation or a role-play's part and goal, the track's country, and the rubric to grade against; topic, pair and scenario cards also show their lifecycle facts. |
| `cards set` | `ID confidence\|notes VALUE` | Confidence is `0` none, `1` some gaps, `2` solid. |
| `cards for-jd` | `JD` | Cards the job description mentions, weakest first (across all tracks). |
| `cards stale` | `[--months N]` | Cards whose facts are unverified or older than N months (default 6). |
| `cards refresh` | `ID --status S --source URL [--date D] [--note T] [--change "DATE\|SUMMARY"]...` | Record researched facts. `S`: `active maintenance sunset unverified`. `--source` is required and must be an https page on one of the card's track hosts. |

`--tier N` keeps cards of tier N or lower (`--tier 2` = tiers 1 and 2). `--area` matches part of the area name.

Lifecycle words: maintenance means closed to new customers with no new features; sunset means it has an end date.

### `lead`

Leadership questions, stored in the database. Each question holds the user's principle plus one STAR example per recent employer (the top three).

| Subcommand | Arguments and options | What it does |
|---|---|---|
| `lead init` | none | Create or extend the questions and progress (never overwrites answers). |
| `lead status` | none | Confidence per category, and employers whose scope facts (reports, team, budget) are still missing. |
| `lead next` | `[--category C] [--audience everyone] [--order default\|random]` | The next question. `--audience everyone` leaves out the questions only people leaders are asked. |
| `lead list` | `[--category C] [--audience everyone] [--target COMPANY]` | List questions (`--audience` as for `lead next`). With `--target`, each question shows the company values it matches and how; questions that match none are listed separately, and values that need judgment come last with their typical questions. Read-only. |
| `lead show` | `ID [--target COMPANY]` | The question, profile facts, candidate stories and saved answers; with `--target`, the company values it matches and their typical questions. |
| `lead set` | `ID principle\|notes\|confidence VALUE` | `principle` is the candidate's approach to the leadership topic, in the user's words. |
| `lead example` | `ID COMPANY FIELD VALUE` | `FIELD`: `situation task action result metric`. `COMPANY` is any employer in the resume data. Blank values are not counted; the target is up to three examples per question, fewer with fewer employers. |
| `lead skip` / `lead unskip` | `ID COMPANY [REASON]` | Mark an employer as not applicable for a question (never had that responsibility, no real example yet), in the user's own words; it counts as covered and shows as `N not applicable`. A real example replaces the mark; `skip` is refused when an example exists. |
| `lead profile` | `show` or `set COMPANY FIELD VALUE` | Factual scope per employer. `FIELD`: `title direct_reports indirect_team team_composition budget stakeholders reporting_to cadence notes`. Values come from the user, never guessed. |

### `questions`

| Command | Arguments | Purpose |
| --- | --- | --- |
| `questions list` | `[ROLE]` | List saved questions with their labels and each role's research status. |
| `questions show` | `ID` | Show the wording, source, evidence and confidence. |
| `questions save` | `ROLE --seed FILE` | Read a JSON object with a `questions` list from a file or standard input (`-`). Each entry needs `question` and `source`. An optional local `id` can identify an entry for updates. The command saves the whole batch together. |
| `questions none-found` | `ROLE` | Date a completed search that found no qualifying sources. |
| `questions stale` | `[ROLE]` | List citations and unsuccessful searches older than the research window. |
| `questions remove` | `ID` | Remove a question and its current progress. Existing sessions retain their logs. |
| `questions personal` | `ROLE [--jd FILE] [--requirement NAME] [--count N]` | Save up to 10 prompts by default, based on resume claims and gaps. With a posting file or standard input, repeat `--requirement` for requirements to check beyond stored skills. |
| `questions set` | `ID --confidence 0\|1\|2` | Record practice confidence and the date. |

Cited entries use `research` or `company` and require `link`, `quote`, `pulled` and `vetted: true`. Local entries use `general` or `personal`. A personal entry references one resume `bullet` ID or posting `requirement`. The `rq:` prefix is reserved for role-question IDs.

### `sessions`

Resumable practice sessions, stored in the database. A session keeps the complete answers; later drills add entries and never edit old ones.

| Subcommand | Arguments and options | What it does |
|---|---|---|
| `sessions new` | `TITLE [--mode M] [--topic T] [--role ROLE] [--order O] [--category C] [--audience everyone] [--jd FILE] [--track T] [--area A] [--tier N] [--kind K] [--company C] [--count N] [--only-open] [--due]` | Start a session with a queue of items. Unfinished stories and cards, leadership questions and cards that are not solid come first; finished stories and solid items follow (solid items not drilled for 30 days before recently solid ones), so strong material is still rehearsed and nothing saved changes. `--only-open` queues only the unfinished and weak ones. `--mode`: `knowledge`, `stories`, `jd`, `leadership`, `questions`, `tutor` (default: `jd` when `--jd` is given, else `knowledge`; `--jd` with another mode is an error). `--topic` (tutor mode only): `knowledge`, `leadership`, `stories` or `questions`. Both question modes require `--role ROLE`. `--count` is the queue length (default 10). A jd session takes a card and a story in turn, so the count cannot leave one kind out; when one kind runs out the other fills the rest. The start message gives the number of each kind queued and how many matching items the count left out. The filters apply to the matching mode, jd mode included; a job posting matches topic cards only, so `--jd` accepts no `--kind` other than `topic`. `--tier N` means tier N or lower. `--due` queues only the items due for a retest (the same set as `readiness --due`; with no `--mode` and no `--jd` it covers cards, leadership questions, role questions and stories, oldest first, stored with the mode `retest`, and a filter such as `--tier` limits only the kind it belongs to; with a `--mode` it queues only that mode's due items; says so and creates nothing when none is due; cannot be combined with `--only-open`). The solid-card aging in the default queue follows the stored retest window. `--target COMPANY` names a researched company (`--company` is one of the user's own employers): the queue holds the same items, with stories and leadership questions that match a company value by theme first, then by hint word, then the rest (more matching values first; with `--order random`, shuffled inside each group); role-knowledge cards keep their places; `--count` cuts after this ordering, and with `--due` the item due longest comes first inside a group. An unknown company creates no session. `--style S` records the session's answer style (default: the profile's `answer_style`, then `star`); a saved default company is never applied here. |
| `sessions list` | none | List sessions, with each one's style and company. |
| `sessions resume` | `ID [--style S]` | What was covered, the last answers and the next item. A queued item whose card, question or story was removed is reported as unavailable and skipped. For a company session it also shows the style in force, what the company's graders look for beside the next story or question, and the values still to cover with their typical questions; when the company's profile was removed it says so. `--style` changes the session's style from then on. |
| `sessions log` | `ID ITEM --question Q --answer A\|- [--grade G] [--confidence 0\|1\|2] [--quiz] [--style S]` | Record one answered item. `--answer -` reads the full answer from stdin. `--quiz` (tutor mode) says a quiz was answered correctly and needs `--grade` and `--confidence 2`. An item that does not exist, including a queued item that was removed, is refused until it exists again. A story or leadership answer records the session's style (or `--style` for this one answer) and its company; a card answer records neither. |
| `sessions close` | `ID` | Close a session. |
| `sessions reopen` | `ID` | Continue a closed session. |

Teaching caps a card's confidence at 1; a passed quiz allows 2.

### `target`

Researched target companies, stored in the database (see [Company research](#company-research)). The command never reads a page; the skill tells the agent to research and vet, and the command checks what it can see.

| Subcommand | Arguments and options | What it does |
|---|---|---|
| `target list` | none | Every researched company with its state: `fresh`, `stale`, `none found` or `not researched`. |
| `target show` | `[NAME]` | Values (with themes, hint words and typical questions), rounds, what graders look for, questioning style, the suggested style and the state, each fact with its link, label, site and date read. Without `NAME`, the profile's `target_company`. Names match in any letter case. |
| `target save` | `NAME --seed FILE\|-` | Add facts, or replace them by id; the other facts stay. All or nothing: one refused fact stores nothing and is named. Warns about themes no story or question uses. The JSON format is in `target --help` and [data-structures.md](../references/data-structures.md#researched-companies-target_company-target_fact-export-kind-research). |
| `target none-found` | `NAME` | Record, with today's date, that no qualifying page was found; the company is not researched again within the research window. |
| `target stale` | none | Companies older than the research window, with the facts to read again. |
| `target recheck` | `NAME FACT [--remove]` | The page still says the fact: its date read becomes today. `--remove`: the page no longer says it and the user responded with yes; the fact (and questions under a removed value) is removed. Removing the company's last fact is refused; `target remove` drops the company. |
| `target remove` | `NAME` | Remove a company and its facts. Says how many sessions name it; they keep working. |
