---
name: resume-workflows
description: Use when building a tailored resume for a job posting, rating how well the resume matches a posting (a match or ATS-style score), adding a resume file (pdf, docx, md, txt) to the user's resume data, or, when asked, shortening long lines. Not for interview practice or being taught.
---

# Resume help

<!-- shared:preflight -->
## Before you start (every time, before anything else)
Do the technical steps yourself and quietly. The user only sees the lines that start with `>`. If this conversation already completed this whole section (for example in another of these skills), do not run it again: keep JOBKIT_COMMANDS_DIR and carry on.
1. Find the plugin's own files. Resolve every file this skill names from the folder of this loaded skill file, never from the working folder. A guide marked "(in this skill's folder)" sits next to this skill file; one marked "(a path from this skill's folder)" is in a sibling skill. JOBKIT_PLUGIN_DIR below is the folder two levels above this skill file (where the plugin's setup and skill files are). JOBKIT_PLUGIN_DIR and JOBKIT_COMMANDS_DIR are folders you work out, not environment variables; only JOBKIT_HOME (the data folder) is one. Put these paths in quotes, since they may contain spaces. Read every file this skill names (the setup guides, the guides next to this skill, and another skill's file) by printing it with `cat "PATH"`, so the user is not asked for permission to read it.
2. Read and follow `JOBKIT_PLUGIN_DIR/setup/preflight.md` now. It holds this skill's prerequisites (uv and the jobkit helper, and how to install them with the user's consent) and what to do when a save is not allowed (that applies to every command in this conversation), and it gives you JOBKIT_COMMANDS_DIR, the folder where uv keeps the jobkit commands this skill runs. Without JOBKIT_COMMANDS_DIR none of this skill's commands can run: if JOBKIT_COMMANDS_DIR is not known, finish this step before anything else.
3. Run every jobkit command by its full path inside JOBKIT_COMMANDS_DIR, in quotes, for example `"JOBKIT_COMMANDS_DIR/cards" next` (this also makes sure that no other command with the same name runs instead). The commands in this skill are shown by name only. Put any folder or file name you pass in quotes too, since it may contain spaces. If JOBKIT_COMMANDS_DIR is no longer known (for example after a long conversation was summarized), run the helper check from step 1 of `JOBKIT_PLUGIN_DIR/setup/preflight.md` again (it only reads); never guess the folder.
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
Everything the user reads is in everyday words. Lines that start with `>` in this skill are what to say: reword them lightly if you like, but keep the meaning and the plain wording. Never show the user commands, file names or folder paths (except the resume folder they named, the data folder when a save was blocked, and where a built resume draft was saved), error text, or the words database, JSON, id, hash, track, seed, tier, confidence, curation, needs review or JD. Run technical steps yourself; never ask the user to run a command or edit a file. Ask one question at a time, and say what will happen before anything is saved or changed. When something fails, say in plain words what went wrong and what to do next.

| Internal term | Say instead |
|---|---|
| JD | the job posting |
| confidence 0, 1, 2 | how comfortable you feel: not yet, a little, solid |
| needs review, flagged number | a few lines with numbers that may be off |
| track | a field or technology to practice (people operations, product design, a cloud platform, ...) |
| key topic | a topic your resumes show you know |
| bullet | a line on your resume |
| readiness | how prepared you are |
| theme, summary positioning, curation | (do not name them; say "I'll label it" or just do it) |
<!-- /shared:talking -->

Flags: `build-resume --help`, `process-resumes --help`, `query-resume --help`. The resume data model (layouts, how lines are matched across resumes, curation) is in `data-model.md` (in this skill's folder); read it before changing how resumes are read or tagged.

## Building a resume for a job posting (beta)
1. Ask:
   > Please paste the job posting here.
2. Read the posting and list every skill, tool or duty it asks for. Run `build-resume -` with the posting on stdin and one `--requirement "NAME"` for each item in that list, including ones the user may not have (a missing one is reported as a gap; leaving the flag out means such skills are not checked). If the output lists possible matches (a skill name that is also an ordinary word, with its sentence), read each sentence and, for the ones that really mean the skill, run the command again with `--requirement NAME`. It picks the best-fitting opening summary, the best non-duplicate lines per company, grouped under each role with its own title and dates (same scoring as `query-resume for-jd`), the skills the posting asks for grouped, certifications and education, and writes a Markdown file under the jobkit home folder's `output/resumes/`.
3. Read the result and tell the user, in plain words: that the resume is a draft and where it is, which skills the posting asks for that nothing on their resumes backs up (including ones outside their stored skills), which skills they have evidence for that this draft does not show (the command prints both), and, if lines were left out because they carry numbers that may be off, say so and offer to go through them:
   > A few lines were left out because their numbers may be off. Want to go through them now?
   If the report lists lines over the limit, say how many are long in one sentence; do not offer to rewrite them.
   Also say, the first time in a conversation:
   > This feature is in beta, so please look the draft over before you use it.
   Never invent resume lines; suggest wording and let the user decide.
   If the output lists lines it set aside or capped, say in plain words which skill each concerns. For a line that reads like training, ask one at a time:
   > Your line "TEXT" sounds like training. Did you also use this skill at work?
   If yes, suggest wording and let the user decide; never change a stored line. For a line that says the skill was not used at work, say it is not shown in your profile and leave it out.
4. If a company shows the wrong job title, rerun with `--title COMPANY-ID="Title"`.
5. The name and contact lines at the top are saved in the profile (`profile header` shows them). `build-resume` reports when none is saved, and the draft then carries a placeholder. If none is saved, ask:
   > What name and contact line should go at the top of your resumes?
   Save the answer yourself with `profile header set NAME CONTACT_LINE`. Never copy it into the stored resume data (lines, summaries, skills). Then run `build-resume -` again with the same posting, so the draft carries the real header.
   When the user has looked it over (job titles and dates, every line is theirs and still true, the name and contact lines, how it looks when opened) and says it is ready, run `build-resume --approve FILE`. Never approve on your own; `build-resume --status FILE` shows draft, approved, or changed (edited after approval).
6. Years of experience: the build shows the figure saved in the profile (`profile status` shows it). If none is saved, take the figure the user gave in their open items (`profile open`) and save it with `profile set years_experience N`; if there is none, and the stored summaries disagree in a way the resumes' dates do not explain (an older resume states fewer years), ask which number is right before using one; when the dates explain it, use the figure from the newest resume:
   > Your resumes say different numbers of years of experience. Which one should I use?

## Rating how well the resume matches a job posting (beta)
Use this when the user asks how well their resume matches a posting or wants a score. The result is a match estimate, never an employer's applicant tracking score, and the user must not be told otherwise. Do every technical step yourself, and never ask the user anything from the first step to the end of the report: settle every doubt with the rules in `match-rubric.md` (in this skill's folder) (read it before step 3; it also gives the request format) and report what you assumed. Flags: `match-score --help`.
1. If the posting is not already in the conversation, say:
   > Please paste the job posting here.
   Write no file for it: the next step takes it on standard input.
2. Run `match-score extract --jd -` with the posting on standard input. It saves the posting and prints `posting`, the KEY for the next steps. If the answer says `cached: true`, give the user that stored report in plain words (step 6) and stop: neither the posting, the resume lines nor the date changed. Otherwise note the requirements it returned that code already rated, and the `evidence` it prints (skill names by group, education in order, certifications): that is all the skills, education and certifications there are to cite.
3. Pass 1, following the rubric: choose the level of the role, split the posting into requirements, rate each against the user's lines, cite the lines, and compose the request JSON. Never invent a line.
   Hand pass 1 to the helper named `jd-matcher` if your tool has one (give it the posting text, the `extract` answer, KEY, the folder that holds the commands and the path of `match-rubric.md`), otherwise to a separate helper with its own working context if your tool can run one, otherwise do it yourself. A fresh helper cannot pick up what the user said earlier, so the rating rests on the stored lines alone. What it returns is the request JSON; you still run steps 4 and 5. The rules for the helper:
   <!-- shared:match-pass-one -->
   Do only pass 1 of a match score. You are given the posting text, the output of `match-score extract` (its `code_items` and `evidence`), the posting KEY, the folder that holds the jobkit commands, and the path of `match-rubric.md`. Read the rubric first and follow it exactly, including its request format. Rate only from the stored data: use `query-resume for-jd` and `query-resume search` (by their full path in that folder) to find lines, cite only lines, skills, education and certifications that those commands or the `evidence` show, and never invent one. Ask no question: settle every doubt with the rubric. Write no file and run no other command that changes anything. Run `match-score check - --key KEY` with your request on standard input and fix every problem it lists. Return only the request JSON, with nothing before or after it.
   <!-- /shared:match-pass-one -->
4. Run `match-score check - --key KEY` with the request JSON on standard input (write no file). If it lists problems, fix the request and run it again; do not ask the user. Note its assumptions.
5. Run `match-score run - --key KEY` with the same request on standard input.
6. Tell the user in plain words, in this order: what their profile does not show yet (must-haves first), what it shows well, then the range:
   > Your profile matches this posting about LOW to HIGH out of 100. The lower number counts only what your lines clearly show; the higher number is what it would be if every close call went your way.
   Then each thing you assumed, one short line each (lines the report lists as reading like training, or as not shown in the profile, are among them: say them the same way and ask nothing); if the report says the posting was vague, say it was hard to judge in places. End with:
   > This is only an estimate of how well your lines match this posting. It is not the score any employer's tracking software gives, and it does not tell you whether you will be hired.
   > This feature is in beta, so the numbers and the way they are worked out may still change.
   Say "level of the role" for the band, and never show file names, commands, ids or the words band, preset, fallback or flag. Say "not shown in your profile yet", never that the user lacks a skill.
7. If the report lists a people-leadership item as not or only partly shown, run `lead profile show` and add one statement, never a question. If it holds a team size or number of reports for an employer, offer one line of wording built only from those facts, say it is only a suggestion and that nothing was changed. If it holds none, say:
   > If you tell me how many people you led and for how long, I can suggest a line for your resume.
   Only if the user later accepts wording, save it with `profile open add TEXT` so they can put it in their resume file themselves. Never change the resume folder or a stored line.
Earlier results: `match-score list`, then `match-score show KEY`.

## Shortening long lines (only when asked)
Use this only when the user asks to shorten, tighten or polish long lines. Never start it, offer it or rewrite a line on your own. When a build report lists lines over the limit, say in one sentence how many lines are long and stop there. Flags: `resume-lines --help`. A line is at most 200 characters; the script counts, never you.
1. Take the lines from the build report, or run `resume-lines list` for every stored line over the limit. Go through them one at a time, longest first, and stop when the user says so.
2. For one line run `resume-lines show ID`. Write one rephrasing of at most 200 characters that says exactly the same thing: the same meaning and the same scope (never a stronger verb such as "led" for "contributed to"), every figure and every tool, company or product name, no new claim. Run `resume-lines validate ID "TEXT"`. If it is not acceptable, fix the wording and run it again; do not ask the user. If it lists names that are no longer present, mention in plain words which ones and let the user judge.
3. Show the user the original and your version, and ask:
   > Here is your line: "ORIGINAL". A shorter version: "SHORTER". Do you want to use the shorter version, change it, or keep your original?
4. Use: save it with `process-resumes curate add short-wording ID "TEXT"`. Change: take the user's own words, validate them the same way, then save. Keep: save nothing and do not raise that line again in this conversation. The save refuses wording that fails the checks; say plainly why and offer to adjust.
5. At the end say:
   > Your original lines and your resume files are untouched. The shorter wording is used only in the resumes I build for you from now on. Want me to build the resume again so it uses them?
   If yes, run the build again with the same posting.

## Adding a resume
1. Run `process-resumes --survey`, then `process-resumes`.
2. Check the unparsed report (`jobkit export --only resume-unparsed`; certificate PDFs there are expected; an unreadable or unsupported file is listed with its reason) and any `problems` printed. Tell the user in plain words which files could not be read and why.
2a. Visual reading, only for a PDF the output marks "needs visual reading" (`process-resumes visual list` shows each one; a Word, text or Markdown file, or a PDF that read fine but is not a resume, never qualifies). Show the user the reason in plain words and ask:
   > I could not read the text of FILE (REASON IN PLAIN WORDS). I can look at its pages as pictures and type out what I see, but I can misread a date or a figure. Do you want me to try?
   On no, stop for that file. On yes, first get the pages: if your tool can open a PDF's pages as images, use the PDF itself; otherwise run `process-resumes visual render FILE` (FILE as `visual list` shows it) and use the image paths it prints (they are removed when the transcript is confirmed). Paths in command output show the home folder as `~` (`%USERPROFILE%` on Windows); expand it when a tool needs a full path. Then have the pages read by the helper named `resume-visual-scanner` if your tool has one (give it the PDF path or the image paths, and ask for a transcript), otherwise by a separate helper that has its own working context if your tool can run one (the page images then stay out of this conversation), otherwise do it yourself. The rules of a transcript:
   <!-- shared:visual-transcript -->
   Read every page as an image: the PDF's own pages, or the page image files you were given. Type out the text as it appears: same order, one line per line, headings and bullets kept, nothing added or guessed. Write `[unclear]` for anything you cannot read. Return only the text.
   <!-- /shared:visual-transcript -->
   Then save it to the path `visual list` gives, never in the resume folder. Show the user the key facts you read (employers, titles, dates) and ask them to confirm or correct; fix the transcript, and only once they agree run `process-resumes visual confirm FILE` (FILE as `visual list` shows it), then `process-resumes` again. A transcript that is not confirmed is never used, and one confirmed for an earlier version of the PDF needs a new reading. Say in plain words that this file was read from its pictures.
2b. Check a PDF's parse against its pages, only when the user asks, for a PDF that read as text; never start or offer it on your own. The page reading is for structure (which employer, which dates, which section); the wording of the resume file stays the reference.
   1. Run `process-resumes visual schema`. Get the pages as in step 2a (the PDF itself, or `process-resumes visual render FILE`). Have them read by the helper named `resume-visual-scanner` if your tool has one (give it the PDF path or the image paths, the printed shape and a request for a JSON reading), otherwise by a separate helper that has its own working context if your tool can run one (the page images then stay out of this conversation), otherwise do it yourself. The rules of a JSON reading:
      <!-- shared:visual-json -->
      Read every page as an image: the PDF's own pages, or the page image files you were given. Return only JSON in exactly the shape printed by `process-resumes visual schema`, with no comments. One string per bullet, copied as printed and without the bullet mark. Dates as YYYY-MM, or YYYY when only a year is printed, and null for a current job. Leave out phone numbers, email addresses and links. Write `[unclear]` inside a string for anything you cannot read. Add nothing that is not printed.
      <!-- /shared:visual-json -->
   2. Run `process-resumes visual compare FILE --reading -` with that JSON on standard input. If it reports an error in the reading, fix the JSON and run it again.
   3. If it reports no differences, say so in plain words and stop. Otherwise go through the differences one at a time, in the order printed, and ask:
      > In your resume file this reads: "PARSER VERSION". In the pages it looks like: "PAGE VERSION". Which one is right?
      For a missing or extra employer, date or bullet, ask whether the pages or the resume file are right in the same way. Never blend two versions and never write wording nobody read in one of them; a line marked `[unclear]` is never chosen.
   4. If every answer is "the resume file is right", say so and stop. Otherwise get the current text with `process-resumes visual text FILE`, apply only the agreed changes, save the whole corrected text as the report says, show the user the changed lines and ask them to agree, and only then run `process-resumes visual confirm FILE` and `process-resumes`. If `visual confirm` refuses and lists roles or work bullets the transcript drops: for each one the user agreed to remove in step 3, confirm again with `--remove "TEXT"` (TEXT exactly as listed, one `--remove` per item); for any other, the text lost it by mistake, so take the work history lines from `process-resumes visual text FILE --layout`, keep the other sections from `visual text FILE`, save again and confirm again. Never pass `--remove` for an item the user did not agree to remove. Say in plain words that this file is now read from the corrected text and that the original file was not changed. If the PDF is replaced later, the corrected text stops being used.
3. Tag new content with `process-resumes curate add theme BULLET_ID THEME...` for each new line and `curate add summary-positioning SUMMARY_ID POSITIONING...` for each new summary. For several at once give `-` as the only value and one entry per line on standard input (`BULLET_ID THEME THEME`), which saves them in one call. Use only the words `process-resumes curate themes` lists: other themes are kept but drive no questions or matching, and any other summary positioning is refused. Do this yourself.
   jobkit includes general leadership and delivery themes. Every other theme, and every summary positioning word, comes from the user's own resumes. When `curate themes` lists no positioning words, or new lines are about something no listed theme covers, propose a few words from the user's own resumes: themes for the subjects their lines keep returning to, positioning words for the professional focus of each summary, each with two or three phrases a job description would use for it, taken from the user's own wording; avoid employer names and employer-specific product names, and use transferable subjects and skills. Show them in plain words and ask:
   > I'd like to add a few labels that describe your work, so I can match it to job postings: LABELS. Is that OK?
   Once the user responds with yes, save them with `curate add theme-word WORD HINT...` and `curate add positioning-word WORD HINT...` (several at once with `-`), then tag as above. For a theme of the user's own, `curate add theme-question THEME QUESTION...` can hold the typical interview questions for it.
4. Resolve new skill spellings and groups with `curate add skill-merge`, `skill-group` or `skill-drop` (several at once the same way, one per line on standard input). Then run `process-resumes` to apply.
5. New employers are found by the scan (`profile companies`). If two names appear to refer to the same employer, resolve them in step 6. To change a name, `profile companies rename ID NAME`, then `process-resumes --force`. A new resume layout needs a parser change, which is a developer task: tell the user the file could not be read.
6. Inconsistencies: compare what the resumes say about the same facts and settle each real difference with the user.
   1. Carefully review the data and look for any potential inconsistency, not only in a fixed list of fields: for example employer names and spellings, job titles, start and end dates, locations, numbers and results, years of experience, education and certifications.
   2. Find where each value comes from. `jobkit export --only resume-companies` gives each role's titles and end dates with the files that state them, and each line's wording per file; `jobkit export --only resume-profile` gives the summaries, education and certifications in use. For anything else, such as locations, read each resume's raw text in the `output` folder of the jobkit home folder (`~/.jobkit/output` unless `JOBKIT_HOME` names another).
   3. Leave out what is not an inconsistency. Compare by meaning, not spelling: "70 percent" and "70%" are the same value. A difference need not be an inconsistency: say nothing when the time a resume was written explains it (a job still current then, fewer years of experience in an older resume, a later title after a promotion) or when it was worded for one posting (a tailored title or summary).
   4. Ask about the rest one at a time, showing both values and the files they come from:
      > Your resumes do not agree on WHAT: FILE says A, but FILE says B. Which one is right, or should I keep both?
      When the user keeps both, they stay as variants: save nothing and do not raise that difference again in this conversation.
   5. Save the agreed change with the jobkit command for that kind of data, then run `process-resumes`: `curate add flagged-number NUMBER` for a wrong number; `profile companies merge FROM INTO` for one employer under two names (then `process-resumes --force`); `profile set years_experience N` for years of experience. For education or a certification, a curated list with any entry replaces the whole list read from the resumes: take the entries in use from `jobkit export --only resume-profile` and `curate list education` (or `certification`), save every entry the user keeps together with the corrected one, and remove a rejected curated entry with `curate rm`. When no command can correct that kind of data, such as a date, a title or a location, tell the user which resume file needs changing (the resume folder is read-only) and offer to record it with `profile open add TEXT`.
   6. Contact details: compare only the newest resume added (by file date) with the saved header (`profile header`), and skip this while the header is still the template. Compare by meaning: a phone number with brackets and dashes and the same digits with dots are the same number, and email case and a trailing slash in a link do not matter. When one really differs, ask:
      > Your newest resume shows VALUE, but your saved contact details show OTHER VALUE. Which should I use?
      For the resume's value, save it with `profile header set NAME CONTACT_LINE`, changing only that detail and never copying it into the stored resume data. For the saved value, change nothing and do not ask about that detail again in this conversation.
7. Verify: `query-resume stats` and `review`; run `process-resumes` again and expect 0 new or changed; check that no phone, email or LinkedIn is stored: `jobkit export --only resume-companies | grep -Ei '@|[0-9]{3}[ -][0-9]{3,4}'` shows any hit to review.
8. Tell the user, in plain words, how many resumes were added and anything that needs their decision.

## Extra rules for this skill
- Resume numbers are only accurate where the user confirms them.

<!-- shared:rules -->
## Rules
- The stored data is opened only through the commands in this skill, never directly. To show the user their data, read one kind at a time with `jobkit export --only KIND` and summarize it in plain words. Never run `jobkit export` without `--only` (it dumps everything, hundreds of kilobytes), and for an overview use `query-resume stats`, `prep status` or `readiness` instead.
- The folder that holds the user's resumes is read-only: never create, edit or delete anything in it.
- Never invent resume lines or details about the user's experience. Suggest wording and let the user decide.
- Never store a phone number, email address or LinkedIn link in the resume data (lines, summaries, skills). The name and contact line for the top of built resumes is the one exception, and it is saved only with `profile header set`. Raw text taken from resumes stays under the jobkit home folder (`~/.jobkit` unless `JOBKIT_HOME` names another), in its `output` folder.
- Never run a jobkit command, and never answer as if resumes are set up, until `JOBKIT_PLUGIN_DIR/setup/preflight.md` has given you JOBKIT_COMMANDS_DIR in this conversation.
- When a jobkit command fails and its message does not say what to fix, or its last line points to the troubleshooting guide, read and follow `JOBKIT_PLUGIN_DIR/setup/troubleshoot.md`. Never repair, delete or recreate the stored data yourself.
- Jobkit does not post issues on GitHub. Never create issues, comments or anything else there; when something should be reported, write it for the user to post.
<!-- /shared:rules -->
