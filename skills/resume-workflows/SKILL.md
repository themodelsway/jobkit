---
name: resume-workflows
description: Use when building a tailored resume for a job posting, rating how well the resume matches a posting, or adding a new resume file (pdf, docx, md, txt) to the user's resume data (scan, tag, check).
---

# Resume help

<!-- shared:preflight -->
## Before you start (every time, before anything else)
Do the technical steps yourself and quietly. The user only sees the lines that start with `>`.
1. Find the plugin's own files. Resolve every file this skill names from the folder of this loaded skill file, never from the working folder. A guide marked "(in this skill's folder)" sits next to this skill file; one marked "(a path from this skill's folder)" is in a sibling skill. PLUGIN below is the folder two levels above this skill file (it holds `setup`). Put these paths in quotes, since they may contain spaces.
2. Check the helper. The session's environment says which kind of computer this is:
   - macOS or Linux: run `sh "PLUGIN/setup/install" --check`.
   - Windows: run `powershell.exe -NoProfile -ExecutionPolicy Bypass -File "PLUGIN/setup/install.ps1" --check`. If that cannot run at all because the shell or `powershell.exe` is missing, say the next line and stop:
     > On Windows I need a free program called Git for Windows. Please install it from git-scm.com (the standard options are fine), then close this window, open it again and ask me again.

   The command prints one line:
   - `ok:FOLDER` or `newer:FOLDER`: the helper is ready. Remember FOLDER. `newer` means the helper is already ahead of this plugin: use it as it is and never offer to install over it.
   - `missing` or `older:FOLDER`: the helper must be set up or updated. Ask this and wait for the answer. Keep this question's wording: say where the data is kept, and never say that it stays on the computer:
     > I need to set up a small helper on your computer so I can keep your resumes and practice notes. It takes about a minute and downloads one standard tool from astral.sh. Your resumes and notes are kept in a folder on your own computer. Is that OK?
     - Yes: run the same command again without `--check`. It prints `ok:FOLDER` when it worked. If it fails with a line that starts `failed: uv is too old`, say the next line and stop:
       > Setup did not finish. A tool called uv is already on your computer, but it is too old for me to use, and I won't replace it for you. Please update it, then ask me again.

       If it fails in any other way, say the next line and stop:
       > Setup did not finish. Please check that you are online and that I am allowed to download and install, then ask me to try again. I will carry on from where it stopped.
     - No: install nothing, say the next line and stop:
       > No problem. I can't help with your resumes or practice without that helper, so I'll stop here. Ask me again whenever you're ready.
   - `unsupported`: install nothing, say the next line and stop:
     > Sorry, this isn't available with this app on this kind of computer yet.
3. Run every jobkit command by its full path inside FOLDER, in quotes, for example `"FOLDER/arch" next` (this also makes sure the right `arch` runs on a Mac, which has its own). The commands in this skill are shown by name only. Put any folder or file name you pass in quotes too, since it may contain spaces.
4. If a command fails because it was not allowed to write under the jobkit home folder (the error mentions `Operation not permitted`, `Permission denied`, `unable to open database file` or a read-only database), nothing was saved. Report nothing as saved, never suggest turning the app's protections off, say the next line with DATA_FOLDER replaced by the jobkit home folder (`~/.jobkit` unless `JOBKIT_HOME` names another), and stop:
   > I wasn't allowed to save that, so nothing was saved. Please allow me to write to this folder, then ask me again: DATA_FOLDER
5. Run `jobkit status`. If it says there is no database, run `jobkit init`. Do not mention either.
6. Run `profile status`. If there is no resume data yet, set up the resumes, one question at a time:
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

Flags: `build-resume --help`, `process-resumes --help`, `query-resume --help`. The resume data model (layouts, how lines are matched across resumes, curation) is in `data-model.md` (in this skill's folder); read it before changing how resumes are read or tagged.

## Building a resume for a job posting
1. Ask:
   > Please paste the job posting here.
2. Read the posting and list every skill, tool or duty it asks for. Run `build-resume -` with the posting on stdin and one `--requirement "NAME"` for each item in that list, including ones the user may not have (a missing one is reported as a gap; leaving the flag out means such skills are not checked). If the output lists possible matches (a skill name that is also an ordinary word, with its sentence), read each sentence and, for the ones that really mean the skill, run the command again with `--requirement NAME`. It picks the best-fitting opening summary, the best non-duplicate lines per company, grouped under each role with its own title and dates (same scoring as `query-resume for-jd`), the skills the posting asks for grouped, certifications and education, and writes a Markdown file under the jobkit home folder's `output/resumes/`.
3. Read the result and tell the user, in plain words: that the resume is a draft and where it is (this is the one place a folder name is shown), which skills the posting asks for that nothing on their resumes backs up (including ones outside their stored skills), which skills they have evidence for that this draft does not show (the command prints both), and, if lines were left out because they carry numbers that may be off, say so and offer to go through them:
   > A few lines were left out because their numbers may be off. Want to go through them now?
   Never invent resume lines; suggest wording and let the user decide.
   If the output lists lines it set aside or capped, say in plain words which skill each concerns. For a line that reads like training, ask one at a time:
   > Your line "TEXT" sounds like training. Did you also use this skill at work?
   If yes, suggest wording and let the user decide; never change a stored line. For a line that says the skill was not used at work, say it is not shown in your profile and leave it out.
4. If a company shows the wrong job title, rerun with `--title COMPANY-ID="Title"`.
5. The name and contact lines at the top come from `header.md` in the jobkit home folder (`~/.jobkit/profile/header.md`). `build-resume` creates a template on first run and reports when it is missing. If it is a template, ask:
   > What name and contact line should go at the top of your resumes?
   Write the answer to `header.md` yourself. Never copy it into the stored resume data. Then run `build-resume -` again with the same posting, so the draft carries the real header.
   When the user has looked it over (job titles and dates, every line is theirs and still true, the name and contact lines, how it looks when opened) and says it is ready, run `build-resume --approve FILE`. Never approve on your own; `build-resume --status FILE` shows draft, approved, or changed (edited after approval).
6. Years of experience: use the figure the user gave in their open items (`profile open`). If the stored summaries disagree, ask which number is right before using one:
   > Your resumes say different numbers of years of experience. Which one should I use?

## Rating how well the resume matches a job posting (experimental)
Use this when the user asks how well their resume matches a posting or wants a score. The result is a match estimate, never an employer's applicant tracking score, and the user must not be told otherwise. Do every technical step yourself, and never ask the user anything from the first step to the end of the report: settle every doubt with the rules in `match-rubric.md` (in this skill's folder) (read it before step 3; it also gives the request format) and report what you assumed. Flags: `match-score --help`.
1. If the posting is not already in the conversation, say:
   > Please paste the job posting here.
   Write the posting to `output/match/posting.txt` under the jobkit home folder (create the folder if needed).
2. Run `match-score extract --jd FILE`. If the answer says `cached: true`, give the user that stored report in plain words (step 6) and stop: neither the posting, the resume lines nor the date changed. Otherwise note the requirements it returned that code already rated.
3. Pass 1, following the rubric: choose the level of the role, split the posting into requirements, rate each against the user's lines, cite the lines, and write the request file `output/match/requests.json` next to the posting. Never invent a line.
4. Run `match-score check REQUESTS --jd FILE`. If it lists problems, fix the request file and run it again; do not ask the user. Note its assumptions.
5. Run `match-score run REQUESTS --jd FILE`.
6. Tell the user in plain words, in this order: what their profile does not show yet (must-haves first), what it shows well, then the range:
   > Your profile matches this posting about LOW to HIGH out of 100. The lower number counts only what your lines clearly show; the higher number is what it would be if every close call went your way.
   Then each thing you assumed, one short line each (lines the report lists as reading like training, or as not shown in the profile, are among them: say them the same way and ask nothing); if the report says the posting was vague, say it was hard to judge in places. End with:
   > This is only an estimate of how well your lines match this posting. It is not the score any employer's tracking software gives, and it does not tell you whether you will be hired.
   > This feature is experimental, so the numbers and the way they are worked out may still change.
   Say "level of the role" for the band, and never show file names, commands, ids or the words band, preset, fallback or flag. Say "not shown in your profile yet", never that the user lacks a skill.
7. If the report lists a people-leadership item as not or only partly shown, run `lead profile show` and add one statement, never a question. If it holds a team size or number of reports for an employer, offer one line of wording built only from those facts, say it is only a suggestion and that nothing was changed. If it holds none, say:
   > If you tell me how many people you led and for how long, I can suggest a line for your resume.
   Only if the user later accepts wording, save it with `profile open add TEXT` so they can put it in their resume file themselves. Never change the resume folder or a stored line.
Earlier results: `match-score list`, then `match-score show KEY`.

## Adding a resume
1. Run `process-resumes --survey`, then `process-resumes`.
2. Check the unparsed report (`jobkit export --only resume-unparsed`; certificate PDFs there are expected; an unreadable or unsupported file is listed with its reason) and any `problems` printed. Tell the user in plain words which files could not be read and why.
3. Tag new content with `process-resumes curate add theme BULLET_ID THEME...` for each new line and `curate add summary-angle SUMMARY_ID ANGLE...` for each new summary (angles: the words `curate themes` lists). Do this yourself.
4. Resolve new skill spellings and groups with `curate add skill-merge`, `skill-group` or `skill-drop` (one name at a time); mark conflicting figures with `curate add wrong-metric FIGURE` after the user confirms the figure is wrong. Then run `process-resumes` to apply.
5. New employers are found by the scan (`profile companies`). If one employer appears under two names, ask whether they are the same company and, on yes, `profile companies merge FROM INTO`; to change a name, `profile companies rename ID NAME`; then `process-resumes --force`. A new resume layout needs a parser change, which is a developer task: tell the user the file could not be read.
6. Verify: `query-resume stats` and `review`; run `process-resumes` again and expect 0 new or changed; check that no phone, email or LinkedIn is stored: `jobkit export --only resume-companies | grep -Ei '@|[0-9]{3}[ -][0-9]{3,4}'` shows any hit to review.
7. Contact details: only for the newest resume added (by file date), compare the name, phone, email and LinkedIn at the top of its raw text (`~/.jobkit/output`) with `~/.jobkit/profile/header.md`. Compare by meaning, not spelling: a number with brackets and dashes and the same digits with dots are the same number, and email case and a trailing slash in a link do not matter. Say nothing when they match, when the header is still the template, or for older resumes (they keep old details). When one really differs, ask, showing both values:
   > Your new resume shows PHONE, but your saved header has OLD. Should I update the header?
   On yes, change only that line of `header.md` yourself. Never copy contact details into the stored data. On no, leave it and do not ask about that detail again in this conversation.
8. Tell the user, in plain words, how many resumes were added and anything that needs their decision.

## Extra rules for this skill
- Resume numbers are only accurate where the user confirms them.

<!-- shared:rules -->
## Rules
- The stored data is opened only through the commands in this skill, never directly. To show the user their data, read it with `jobkit export` and summarise it in plain words.
- The folder that holds the user's resumes is read-only: never create, edit or delete anything in it.
- Never invent resume lines or details about the user's experience. Suggest wording and let the user decide.
- Never store a phone number, email address or LinkedIn link in the data. Raw text taken from resumes stays under the jobkit home folder (`~/.jobkit/output`).
<!-- /shared:rules -->
