---
name: tutor
description: Tutor and readiness coach for interview prep. Use to learn or have something explained (services, decision pairs like ALB vs NLB, leadership answers, building a STAR story), or to ask how prepared you are or what to work on next. Not for being quizzed (use interview-prep).
---

# Tutor and readiness

<!-- shared:preflight -->
## Before you start (every time, before anything else)
Do the technical steps yourself and quietly. The user only sees the lines that start with `>`. If this conversation already completed this whole section (for example in another of these skills), do not run it again: keep FOLDER and carry on.
1. Find the plugin's own files. Resolve every file this skill names from the folder of this loaded skill file, never from the working folder. A guide marked "(in this skill's folder)" sits next to this skill file; one marked "(a path from this skill's folder)" is in a sibling skill. PLUGIN below is the folder two levels above this skill file (it holds `setup`). Put these paths in quotes, since they may contain spaces.
2. Check the helper. The session's environment says which kind of computer this is; if it does not, run `uname -s` (`Darwin` is macOS, `Linux` is Linux, a name starting `MINGW`, `MSYS` or `CYGWIN`, or no `uname` at all, is Windows):
   - macOS or Linux: run `sh "PLUGIN/setup/install" --check`.
   - Windows: run `powershell.exe -NoProfile -ExecutionPolicy Bypass -File "PLUGIN/setup/install.ps1" --check`. If that cannot run at all because the shell or `powershell.exe` is missing, say the next line and stop:
     > On Windows I need a free program called Git for Windows. Please install it from git-scm.com (the standard options are fine), then close this window, open it again and ask me again.

   The command prints one line:
   - `ok:FOLDER` or `newer:FOLDER`: the helper is ready. Remember FOLDER. `newer` means the helper is already ahead of this plugin: use it as it is and never offer to install over it.
   - `missing` or `older:FOLDER`: the helper must be set up or updated. Ask this and wait for the answer. Keep this question's wording: say where the data is kept, and never say that it stays on the computer:
     > I need to install the Jobkit engine, which keeps your resumes and interview practice organized. It takes about a minute and downloads one standard tool from astral.sh. Everything is kept in a folder on your own computer. Is that OK?
     - Yes: run the same command again without `--check`. It prints `ok:FOLDER` when it worked. If it fails with a line that starts `failed: uv is too old`, say the next line and stop:
       > Setup did not finish. A tool called uv is already on your computer, but it is too old for me to use, and I won't replace it for you. Please update it, then ask me again.

       If it fails in any other way, say the next line and stop:
       > Setup did not finish. Please check that you are online and that I am allowed to download and install, then ask me to try again. I will carry on from where it stopped.
     - No: install nothing, say the next line and stop:
       > No problem. I can't help with your resumes or practice without that helper, so I'll stop here. Ask me again whenever you're ready.
   - `unsupported`: install nothing, say the next line and stop:
     > Sorry, this isn't available with this app on this kind of computer yet.
3. Run every jobkit command by its full path inside FOLDER, in quotes, for example `"FOLDER/arch" next` (this also makes sure the right `arch` runs on a Mac, which has its own). The commands in this skill are shown by name only. Put any folder or file name you pass in quotes too, since it may contain spaces.
4. If a command fails because it was not allowed to write under the jobkit home folder (the error mentions `Operation not permitted`, `Permission denied`, `unable to open database file` or a read-only database), nothing was saved. Report nothing as saved and never suggest turning the app's protections off. If you can ask the user to approve running that one command again with wider permissions (the app's own one-off approval, for that command only), ask that first and run it again if they agree. If you cannot, or they decline, say the next line with DATA_FOLDER replaced by the jobkit home folder (`~/.jobkit` unless `JOBKIT_HOME` names another), and stop:
   > I wasn't allowed to save that, so nothing was saved. Please allow me to write to this folder, then ask me again: DATA_FOLDER
5. Run `jobkit status && profile status` as one command (each by its full path, as in step 3). If it says there is no database, run `jobkit init` and then `profile status`. Do not mention any of this.
6. From the `profile status` output: if there is no resume data yet, set up the resumes, one question at a time:
   1. Ask:
      > Where do you keep your resumes? You can drag the folder here or tell me its name.
   2. Look inside that folder. Only if it also holds files that do not look like resumes, ask:
      > I see some files that don't look like resumes. Should I skip any part of that folder?
   3. Run `profile init --resume-root "FOLDER" [--resume-dir SUBFOLDER ...]`, then `process-resumes --survey`, then `process-resumes`.
   4. Report what was found and ask:
      > I found N resumes from M employers: A, B, C. Does that look right?
   5. If one employer shows up under two names, ask for each pair:
      > I found "X" and "Y". Are they the same company?
      On yes, run `profile companies merge FROM INTO`, then `process-resumes --force`.
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

## What they are preparing for (once, after the resumes are set up)
1. Ask:
   > What are you preparing for? Tell me the kind of role and the technologies it uses, for example AWS, Acme Data or Google Cloud.
2. Run `lead init` and `prep init` (leadership questions and stories come from the resumes whatever the target). Then set up each topic the user named (see "Tracks" in `../interview-prep/architecture.md` (a path from this skill's folder)): `arch init --track aws` for the bundled AWS example; for any other technology build a seed, show it to the user in plain words, register it with `arch track add NAME --seed -`, then run `arch init --track NAME`. Key services are the ones the resumes mention (the user may pin their own list with `profile tier1 ...`). `arch tracks` shows what exists; another topic can be added later the same way.

Three topics, all backed by the same stored data: architecture, leadership and STAR stories, plus a readiness report. Interview practice (ask first, no hints, grade) belongs to `interview-prep`; this skill explains first.

## Sessions (before any lesson; a readiness report needs none)
1. `sessions list`; ask whether to start a new lesson session or continue one. Never guess:
   > Do you want to start a new lesson, or pick up one you did before?
2. New: `sessions new "title" --mode tutor --topic architecture|leadership|stories [--area A] [--tier N] [--kind service|pair|scenario] [--category C] [--company C] [--order default|random] [--count N] [--only-open] [--target COMPANY] [--style star|soar|carl]`. `--target` only for a researched company with facts that the user named for this session; `--style` records the answer structure they chose (ask "How would you like to structure your answers?" for a stories or leadership lesson unless already said). Solid items follow the weak ones in the queue; `--only-open` leaves them out. Ask whether to begin with what they know least or mix it up, unless already said. Continue: `sessions resume ID`.
3. Log each lesson: `sessions log ID ITEM --question "quiz question" --answer - --grade "..." --confidence N [--quiz]` (answer on stdin, full text). Close with `sessions close ID`.
4. Teaching alone caps confidence at 1 (some gaps) and never lowers a confidence earned in practice. Confidence 2 needs `--quiz --grade "what was right" --confidence 2` after a correct quiz answer. `--quiz` is a claim you make, so use it only when the user's answer really was correct; the log keeps the answer so it can be checked. `sessions reopen ID` continues a closed session.

## Readiness ("how prepared am I?")
Run `readiness` (add `--jd -` with the posting on stdin for a specific job, `--days N` for the aging window) and report in plain words. Rules for honest reporting:
- Report coverage and evidence per area, never one percentage. Labels: untested, some gaps, solid-unlogged (set by hand, no logged answer), solid-once, solid-repeated, aging (solid but not practised for 30+ days). Only real answers count; lessons count only after a passed quiz. Stories: empty, draft, done, done-rehearsed, done-aging. Say these in everyday words, for example "not tried yet", "a few gaps", "solid once", "solid several times", "getting rusty".
- Say what it does and does not show:
  > This comes from practice answers I graded, so it shows what you've covered and how well it has been tested, not how a real interviewer will score you. One good result is weak evidence; it's worth repeating on another day.
- If `profile status` shows the retest window is the default (not set), ask once, and save the answer with `profile set reassess_days N` (a whole number of days, 1 to 365; if the user has no preference, keep the default and do not ask again):
  > How many days should pass before I offer to re-check an answer you did well on? Most people pick 30.
- After the report, run `readiness --due`. If it lists items, say how many and how old the oldest is, and ask:
  > N of your good answers are older than D days. Do you want to re-check some of them now?
  On yes, hand over to practice: the retest is a graded drill, not a lesson, so use the interview-prep skill (`sessions new "title" --due`). On no, say nothing more about it. Never start a retest without a yes.
- Name the 3 to 5 most valuable gaps (key services not tried, leadership questions with no example, stories still empty for the most recent jobs) and offer to teach or practise the first one. Do not decide for the user.
- Use `--jd -` to focus on a role; there is no way to mark items as not relevant, so skip them when the user says so.
- If the user is preparing for a particular company, ask which one unless they already said (a default company in `profile status` is only a suggestion to confirm):
  > Which company are you preparing for?
  Run `target show NAME`. If it has been researched and has facts (not `none found`), add `--target NAME` to `readiness` (it can be combined with `--jd -` and `--due`) and report, per company value, whether a story covers it, may cover it, has no story yet, or needs the user's judgment, saying beside each fact whether it came from the company's own site or another site. This skill never looks a company up: if it is not researched or is stale, say so and offer practice, where it can be looked up:
  > I haven't looked up how this company interviews yet. I can do that when we practise, if you like.

## Facts: never from memory
For architecture cards: `arch show ID` first. If the card says NEVER verified or is older than about 6 months, check the vendor's documentation (the hosts `arch tracks` lists for the card's topic) before teaching limits, features, pricing or lifecycle, then record with `arch refresh ID --status active|maintenance|sunset --source URL [--note T] [--change "DATE|SUMMARY"]` (source = a specific page on one of the topic's documentation hosts; dates YYYY-MM-DD, not in the future). The card stores only lifecycle and recent changes; limits, prices and feature details are looked up every time. A card marked "seeded lead, NOT verified" counts as unverified. If you cannot check, label the point "unverified". Lifecycle: maintenance = closed to new customers, no new features; sunset = has an end date.

## Lesson: architecture (one card at a time)
1. `arch show ID` (lists resume lines that mention the service). Ask in one line what the user already knows; skip what they know:
   > What do you already know about this?
2. Teach in short pieces, pausing for questions: what it is; when to choose it and alternatives (why not those); limits and gotchas; security; cost; scaling and failure; what changed in the last 3 years and anything deprecated. Anchor with their work only where the card links it.
3. Pair: teach decision criteria (protocol, latency, scale, cost, operations, security) and a default recommendation with the conditions that flip it. Scenario: clarifying questions, components with reasons, failure modes, security, cost, what to measure.
4. Overview first, deeper on request. Then quiz (see "Quiz and wrap-up").

## Lesson: leadership (one question at a time)
1. `lead show ID`. Explain what the interviewer is really testing for this question (judgment, scale, self-awareness, influence) and the shape of a strong answer: a short principle, then one concrete STAR example, about 2 minutes spoken.
2. Show a generic skeleton with placeholders, not invented content. Use a different industry example to illustrate, clearly labelled as an illustration, never as the user's experience.
3. Help the user find their own principle and examples: ask what they do in practice, then which of their most recent jobs (`lead profile show` lists them) fits. Save the principle with `lead set ID principle "..."` and examples with `lead example ID COMPANY FIELD VALUE` only in their words and after their confirmation. Scope numbers (team size, budget) come only from them via `lead profile set`.
4. Quiz: they answer the question as in an interview; give brief feedback on structure, "I" vs "we", a result with a number, honesty, length.

## Lesson: stories (one story at a time)
For a researched company the user named, `prep for-target NAME` shows which stories fit its values; teach toward the values that have no story, in the company's own published words, and never present a mapping or a suggested structure as the company's word.
1. `prep next` or `prep show ID`. Run `prep styles` to see the style in force (`profile set answer_style star|soar|carl`; if `profile status` shows it as not set, offer the three in plain words and save the choice). Teach what each part is for, starting from the user's resume line. Star: Situation (context in one or two sentences), Task (what was yours), Action (what you personally did; "I" not "we"), Result (a number, plus what you learned or would change). Soar replaces the task with an obstacle (what stood in the way); carl is Challenge (the situation and task together), Action, Result, Learning (what they took from it).
2. Help them find missing pieces with questions, one at a time (what was at stake, who disagreed, what did you decide, how was it measured). Never fill facts yourself. If something differs from the resume line, ask which is right.
3. Tighten their words into 1-2 sentences per part, read it back, and save with `prep set` after their okay. Status `done` only when every part of the style in force is filled and confirmed (`prep set ... status done` is refused otherwise, with the missing part named). Save the spoken versions with `prep set ID spoken.60s|spoken.2min`, and likely questions or words to avoid with `likely_questions` and `never_say`, only in the user's words.
4. Quiz: they tell the story aloud from the prompt "Tell me about a time you...", then give feedback on length, ownership and result.
5. Record facts, not just prose. When the user describes a project, keep it as an engagement: `prep engagement add ID --company C --title T`, then `prep fact add ENG "text" --basis stated|estimate|unsure` for each thing they said (their words, one fact each), `prep decision add ENG --what W [--why Y] [--ownership mine|team|client|shared|unsure]` for choices they made (`mine` only if they said so), `prep link STORY ENG --facts ...`, `prep metric add STORY --name N --value V --basis measured|estimated|stated|unknown` for numbers. Things you suggested (design options, doc facts) are `--basis proposed` or `verified-doc --source URL`, never `stated`. If the user says "if I remember" or "I believe", the basis is `unsure`. Resolve open questions with `prep followup resolve STORY INDEX_OR_TEXT --answer A` in their words.
6. `prep validate STORY` before marking done: errors (unsure or proposed fact in use, a forbidden term, a missing part) block `done`; warnings (a number without a metric, an estimate not hedged, an action that says "we" a lot, spoken text too long) are advice to pass on in plain words. `prep export --story ID --format md` gives a one-page cheat sheet to show them; `prep search TEXT` finds earlier facts.

## Quiz and wrap-up (all topics)
1. Ask one short question, wait, correct with checked facts, re-teach briefly if wrong and ask a variation. Log it as above (`--quiz` only when answered correctly).
2. Ask whether to go deeper, move on, practise it in `interview-prep`, or see how prepared they are:
   > Want to go deeper on this, move on, try it as a practice question, or see how prepared you are overall?
   Never skip ahead without asking.

## Extra rules for this skill
- Plain language, short messages, one point at a time.
- Use only resume links, saved data, or what the user tells you now when talking about their experience.
- Never use `arch set ID confidence` or `lead set ID confidence` in a lesson (those are the user's own manual overrides); progress changes only through `sessions log`. Notes, principles, examples, profile facts and story fields go through `arch set ID notes`, `lead set|example|profile` and `prep set`. Ask before saving anything not already on a resume (client names, confidential figures).

<!-- shared:rules -->
## Rules
- The stored data is opened only through the commands in this skill, never directly. To show the user their data, read one kind at a time with `jobkit export --only KIND` and summarise it in plain words. Never run `jobkit export` without `--only` (it dumps everything, hundreds of kilobytes), and for an overview use `query-resume stats`, `prep status` or `readiness` instead.
- The folder that holds the user's resumes is read-only: never create, edit or delete anything in it.
- Never invent resume lines or details about the user's experience. Suggest wording and let the user decide.
- Never store a phone number, email address or LinkedIn link in the resume data (lines, summaries, skills). The name and contact line for the top of built resumes is the one exception, and it is saved only with `profile header set`. Raw text taken from resumes stays under the jobkit home folder (`~/.jobkit` unless `JOBKIT_HOME` names another), in its `output` folder.
<!-- /shared:rules -->
