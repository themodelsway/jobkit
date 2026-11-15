---
name: interview-prep
description: Mock-interview practice: asks first, no hints, then grades. Use to be quizzed or practise answers (architecture, leadership questions, STAR stories), continue an earlier session, or see what to rehearse for a posting. Not for being taught or a readiness report (use tutor).
---

# Interview practice

<!-- shared:preflight -->
## Before you start (every time, before anything else)
Do the technical steps yourself and quietly. The user only sees the lines that start with `>`. If this conversation already completed this whole section (for example in another of these skills), do not run it again: keep JOBKIT_COMMANDS_DIR and carry on.
1. Find the plugin's own files. Resolve every file this skill names from the folder of this loaded skill file, never from the working folder. A guide marked "(in this skill's folder)" sits next to this skill file; one marked "(a path from this skill's folder)" is in a sibling skill. JOBKIT_PLUGIN_DIR below is the folder two levels above this skill file (where the plugin's setup and skill files are). JOBKIT_PLUGIN_DIR and JOBKIT_COMMANDS_DIR are folders you work out, not environment variables; only JOBKIT_HOME (the data folder) is one. Put these paths in quotes, since they may contain spaces. Read every file this skill names (the setup guides, the guides next to this skill, and another skill's file) by printing it with `cat "PATH"`, so the user is not asked for permission to read it.
2. Read and follow `JOBKIT_PLUGIN_DIR/setup/preflight.md` now. It holds this skill's prerequisites (uv and the jobkit helper, and how to install them with the user's consent) and what to do when a save is not allowed (that applies to every command in this conversation), and it gives you JOBKIT_COMMANDS_DIR, the folder where uv keeps the jobkit commands this skill runs. Without JOBKIT_COMMANDS_DIR none of this skill's commands can run: if JOBKIT_COMMANDS_DIR is not known, finish this step before anything else.
3. Run every jobkit command by its full path inside JOBKIT_COMMANDS_DIR, in quotes, for example `"JOBKIT_COMMANDS_DIR/arch" next` (this also makes sure the right `arch` runs on a Mac, which has its own). The commands in this skill are shown by name only. Put any folder or file name you pass in quotes too, since it may contain spaces. If JOBKIT_COMMANDS_DIR is no longer known (for example after a long conversation was summarised), run the helper check from step 1 of `JOBKIT_PLUGIN_DIR/setup/preflight.md` again (it only reads); never guess the folder.
4. Run `jobkit status --setup`. It prints one word, for you only: never say it to the user, or tell them setup is unfinished.
   - `no-database`: run `jobkit init`, then `jobkit status --setup` again.
   - `no-resumes`: read and follow `JOBKIT_PLUGIN_DIR/setup/first-run.md`, which imports the resumes, then run `jobkit status --setup` again. If it still prints `no-resumes`, do not start the import again in this conversation; say the next line and stop:
     > I couldn't import any resumes from that folder. Please check that it holds your resumes, then ask me again.
   - `no-target` or `ready`: carry on. `no-target` means "what they are preparing for" has not been finished (it may have stopped part way before); a skill with that section does it, from the start, before its first lesson or practice.
   - `blocked`, `busy`, `too-new`, `failed`, any other output, or no output: the check could not tell. Never guess the stage and never import the resumes on a guess. Read and follow `JOBKIT_PLUGIN_DIR/setup/troubleshoot.md`, and carry on with this skill only if it says so.
5. Run `profile status` and keep its output; later steps of this skill read it. Do not mention any of this.
6. If the resumes were just imported, or this is the start of the conversation and the request names no task, read and follow `JOBKIT_PLUGIN_DIR/setup/welcome.md`.
<!-- /shared:preflight -->

<!-- shared:talking -->
## Talking to the user
Everything the user reads is in everyday words. Lines that start with `>` in this skill are what to say: reword them lightly if you like, but keep the meaning and the plain wording. Never show the user commands, file names or folder paths (except the resume folder they named, and the data folder when a save was blocked), error text, or the words database, JSON, id, hash, track, seed, tier, confidence, curation, needs review or JD. Run technical steps yourself; never ask the user to run a command or edit a file. Ask one question at a time, and say what will happen before anything is saved or changed. When something fails, say in plain words what went wrong and what to do next.

| Internal term | Say instead |
|---|---|
| JD | the job posting |
| confidence 0, 1, 2 | how comfortable you feel: not yet, a little, solid |
| needs review, wrong figure | a few lines with numbers that may be off |
| track | a topic to practise (AWS, Acme Data, ...) |
| tier-1 service | a key service |
| bullet | a line on your resume |
| readiness | how prepared you are |
| theme, summary angle, curation | (do not name them; say "I'll label it" or just do it) |
<!-- /shared:talking -->

## What they are preparing for (when the setup check printed `no-target`)
Treat this as the opening of the task the user chose, not as a setup step: never tell the user about a setup check, a status word or unfinished setup.
1. Ask, one question at a time:
   > Before we start, what kind of role are you preparing for?
   Then:
   > Is there a technology you'd like to focus on, such as AWS, Azure, Google Cloud or large language models? If you're not sure, I can suggest some from your resumes.
   If the user wants a suggestion, name the two or three technologies the resumes show most and ask which to use.
2. Run `lead init` and `prep init` (leadership questions and stories come from the resumes whatever the target). Then set up each topic the user named (see "Tracks" in `architecture.md` (in this skill's folder)): `arch init --track aws` for the bundled AWS example; for any other technology build a seed, show it to the user in plain words, register it with `arch track add NAME --seed -`, then run `arch init --track NAME`. Key services are the ones the resumes mention (the user may pin their own list with `profile tier1 ...`). `arch tracks` shows what exists; another topic can be added later the same way.
3. Last, when every command above has worked, save what they are preparing for, in a few of their own words: `profile set preparing_for "TEXT"`. This marks the section as done. Until it is saved the setup check keeps printing `no-target`, so a setup that stopped part way is done again from the start next time; every command above is safe to run again. Then carry on with the task the user chose, without asking for it again.

Stories, answers and progress are personal data kept on the user's computer. Read and write them only through the commands below.

## Commands
- `prep status`: filled vs empty stories per company
- `prep next [--company COMPANY-ID]`: next unfinished story (prints the resume line, figures and current answers)
- `prep show STORY_ID [--style star|soar|carl]`
- `prep set STORY_ID FIELD "VALUE" [--style S]`: FIELD is situation, task, action, result, metric, lessons, notes, follow_ups, likely_questions, never_say, also_themes (lists: use ` | ` between items), spoken.60s, spoken.2min (the spoken versions, kept as written) or status (empty, draft, done). A style also names its own parts: obstacle (soar), challenge and learning (carl).
- `prep styles`: the three answer styles (star, soar, carl) and the one in force: `--style`, then the saved `profile set answer_style`, then star. `status done` is accepted only when the story is complete in that style; if it is refused, the message names the missing part, so ask for that part.
- `prep new STORY_ID --company C --theme T`: an extra story beyond the ones `prep init` makes. `prep list [--company C]` lists every story. `prep evidence STORY` shows the dates it was practised.
- `prep for-jd -`: stories ranked for a job posting (posting on stdin), with typical questions and the unfinished ones
- `prep for-target COMPANY`: stories ranked for a researched company, every company value with its state, and whether each story is complete in the company's suggested style
- `target show NAME`, `target list`, `target save NAME --seed -`, `target none-found NAME`, `target stale`, `target recheck NAME FACT [--remove]`, `target remove NAME`: researched companies (see "Preparing for a specific company")
- `prep init`: add stories for new resume lines or themes (never overwrites answers)

## Sessions (always first)
Every practice run belongs to a session, so the user can start fresh or go back to an old one.
1. Run `sessions list`. Ask whether to start a new session or continue one. Never guess which:
   > Do you want to start a new practice session, or pick up one you did before?
2. Before a new session, use the `profile status` output from the preflight (run it again only if a setting just changed). If the retest window says it is the default (not set), ask once, and save the answer with `profile set reassess_days N` (a whole number of days, 1 to 365; if the user has no preference, keep the default and do not ask again):
   > How many days should pass before I offer to re-check an answer you did well on? Most people pick 30.
   Then run `readiness --due`. If it lists items, say how many and how old the oldest is, and ask:
   > N of your good answers are older than D days. Do you want to re-check those first?
   On yes, start the session with `--due` added to the command below. On no, start as usual and do not ask again in this conversation. Never start a retest without a yes.
   For a story or leadership session, ask which answer structure to use unless the user already said, offering the three by their shape (see "Filling in stories"):
   > How would you like to structure your answers?
   New: `sessions new "title" [--mode architecture|stories|jd|leadership] [--order default|random] [--jd FILE] [--track T] [--area A] [--tier N] [--kind service|pair|scenario] [--company C] [--category C] [--count N] [--only-open] [--due] [--target COMPANY] [--style star|soar|carl]`. `--company` is one of the user's own past employers; `--target` is a researched company they are preparing for. Pass `--target` only when the user named that company for this session (a saved default company in `profile status` is a suggestion to confirm, never applied by itself). Finished stories and solid cards follow the unfinished and weak ones in the queue, so strong material is still rehearsed; `--only-open` leaves them out. With `--jd` the queue takes a card and a story in turn, so both kinds are asked. The start message gives the number of each kind and how many matching items `--count` left out; when some were left out, tell the user once, and start a longer session only if they ask:
   > This session has N questions. M more fit this job, so say so if you want a longer one.
   (`--mode tutor --topic ...` belongs to the tutor skill.) Pick a short plain title yourself. A closed session continues with `sessions reopen ID`.
3. Continue: `sessions resume ID` prints what was covered, the last answers and the next item; for a company session also what the company's interviewers look for and the values still to cover. If the user wants another structure from now on, `sessions resume ID --style S`.
4. After each answer: `sessions log ID ITEM --question "..." --answer - --grade "..." --confidence N` (answer on stdin; keep the user's FULL answer). If the user answered one question in another structure, add `--style S` for that answer only (never for an architecture card). When you run `prep show` or `prep set` for a story during a session, pass the session's style (shown by `sessions resume`) with `--style`. End with `sessions close ID` when the user says they are done. The command rejects unknown items, empty answers, closed sessions and `--confidence` on stories; fix the command rather than working around it.
Commands: `sessions list|new|resume|log|close`.

## Order
For architecture and leadership sessions ask, unless they already said:
> Should I start with what you know least, or mix the questions up randomly?
(default order = weakest first; random = `--order random`).

## Architecture fundamentals (mode: architecture, or the architecture items in a job-posting session)
Service, decision-pair and scenario questions for each topic the user chose. Read `architecture.md` (in this skill's folder) for the rubric, how to add a topic, and the rule that facts come from checked sources, never from memory. Commands (`arch`): `tracks`, `track add NAME --seed FILE|-`, `status`, `next [--track --area --tier --kind]`, `show ID`, `list`, `set ID confidence|notes VALUE`, `for-jd -`, `stale`, `refresh ID --status ... --source URL`, `init`.
Flow: the session's next item, then `arch show ID`, ask one question, wait for the answer, grade and correct with checked facts, log it.

## Leadership questions (mode: leadership)
People-leadership questions (roadmapping, prioritization, mentoring, conflict, team size, execution, influence), each tied to STAR examples from the three most recent companies. Read `leadership.md` (in this skill's folder) first. Commands (`lead`): `status`, `next [--category C] [--order default|random]`, `show ID`, `list`, `set ID principle|notes|confidence VALUE`, `example ID COMPANY FIELD VALUE`, `profile show|set`, `init`. Start with `sessions new "title" --mode leadership [--category C] [--order random]`.

## Filling in stories
1. Run `prep status`, then `prep next` (use `--company` if the user names one; start with the most recent job).
2. Show the story's resume line and figures in two lines, then ask **one question at a time**, in this order. Put each in plain words, for example:
   > What was the situation? What was going on when this started?
   > What was your part in it?
   > What did you personally do, as opposed to the team?
   > What was the result? A number helps.
   > What went wrong, or what would you do differently?
   Then the tough follow-up questions an interviewer would ask.
   If `profile status` shows the answer style as "not set", ask once and save the choice with `profile set answer_style star|soar|carl` (run `prep styles` for the parts of each):
   > Stories can be shaped three ways. Situation, task, action, result is a clear sequence that suits most questions. Situation, obstacle, action, result suits a story about overcoming something. Challenge, action, result, learning suits a story where what you learned matters as much as what happened. Which do you want to use? Most people start with the first.
   Ask for the parts of the style in force, with the same plain-words questions (an obstacle is what stood in the way, a learning is what they took from it). In `soar` or `carl` the story is done when its own parts are filled, not necessarily situation and task.
3. Do not make up details. If an answer is vague, ask one follow-up ("how was that measured?", "what did you do versus the team?"). Never copy facts from other stories or from your own assumptions.
4. After each answer, save it with `prep set`. When every part of the style in force is filled, tighten them into one or two sentences each, read the finished story back, and on the user's okay set status to `done`.
5. Offer the next story only after the current one is done. Stop when the user says to.
6. If the user's answer differs from the resume line (for example a different number), ask which is right before saving:
   > Your resume says X but you just said Y. Which one is right?

## Preparing for a specific company
1. When the user names a company they are interviewing with, or a job posting names one, run `target show NAME`. If it is not researched or is stale, research it first by following `research.md` (in this skill's folder): only if you can read web pages, with only the company name and role title, leaving out anything written by individual users. Say what you are doing first:
   > I'll look up what this company has published about how it interviews. I'll only use what the company or a proper article says, not reviews or forum posts.
   Steps 2 to 5 need stored facts. When `target show NAME` reports `none found`, or you could not read pages and nothing is stored for the company, skip them: practise as usual in the answer structure the user chose, and run no `prep for-target`, `readiness --target` or `--target` for that company (each of them refuses a company without facts).
2. Run `prep for-target NAME` and report in plain words: which stories fit which of the company's values, which values have no story yet, and which values need the user's own judgment. Explain a value in the company's own words, and say beside every fact where it came from:
   > This comes from the company's own site.
   > This comes from another site, not the company itself.
3. If the company suggests an answer structure, say so and whether it was the company's own words or your suggestion, then ask which structure the user wants; their choice wins.
4. In practice, grade each answer against what the company's interviewers look for, as listed by `sessions resume`, without adding anything the stored facts do not say. Practise the values that need the user's judgment from their stored typical questions, as open questions.
5. Before saving a challenge over a story that already has a task, tell the user the two parts will be joined into one and ask; use `--merge` only on a yes.

## Preparing for a specific job posting
1. Ask the user to paste the posting, then run `prep for-jd -` with it on stdin. If the posting names the company, also follow "Preparing for a specific company".
2. Report in plain words: the best-matching stories and the questions typically asked about them, which of those are not finished yet (offer to finish those first), and anything the posting asks for that has no story at all.
3. For rehearsal, ask the typical questions one at a time and give short feedback on the answer against the saved story (structure, a number, ownership, length). Do not rewrite their story unless asked.

## Extra rules for this skill
- Contact details and company-confidential specifics (client names, internal figures beyond the resume) are the user's call: ask before saving anything not already on a resume.

<!-- shared:rules -->
## Rules
- The stored data is opened only through the commands in this skill, never directly. To show the user their data, read one kind at a time with `jobkit export --only KIND` and summarise it in plain words. Never run `jobkit export` without `--only` (it dumps everything, hundreds of kilobytes), and for an overview use `query-resume stats`, `prep status` or `readiness` instead.
- The folder that holds the user's resumes is read-only: never create, edit or delete anything in it.
- Never invent resume lines or details about the user's experience. Suggest wording and let the user decide.
- Never store a phone number, email address or LinkedIn link in the resume data (lines, summaries, skills). The name and contact line for the top of built resumes is the one exception, and it is saved only with `profile header set`. Raw text taken from resumes stays under the jobkit home folder (`~/.jobkit` unless `JOBKIT_HOME` names another), in its `output` folder.
- Never run a jobkit command, and never answer as if resumes are set up, until `JOBKIT_PLUGIN_DIR/setup/preflight.md` has given you JOBKIT_COMMANDS_DIR in this conversation.
- When a jobkit command fails and its message does not say what to fix, or its last line points to the troubleshooting guide, read and follow `JOBKIT_PLUGIN_DIR/setup/troubleshoot.md`. Never repair, delete or recreate the stored data yourself.
- Jobkit does not post issues on GitHub. Never create issues, comments or anything else there; when something should be reported, write it for the user to post.
<!-- /shared:rules -->
