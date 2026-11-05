---
name: resume-workflows
description: Use when building a tailored resume for a job posting or adding a new resume file (pdf, docx, md, txt) to the user's resume data (scan, tag, check).
---

# Resume help

<!-- shared:preflight -->
## Before you start (every time, before anything else)
Do the technical steps yourself and quietly. The user only sees the lines that start with `>`.
1. Run `sh "${CLAUDE_PLUGIN_ROOT}/setup/install" --check`. It prints one line:
   - `ok:FOLDER`: the helper is ready. Remember FOLDER.
   - `missing` or `older:FOLDER`: the helper must be set up or updated. Ask this and wait for the answer:
     > I need to set up a small helper on your computer so I can keep your resumes and practice notes. It takes about a minute, downloads one standard tool from astral.sh, and everything stays on your computer. Is that OK?
     - Yes: run `sh "${CLAUDE_PLUGIN_ROOT}/setup/install"`. It prints `ok:FOLDER` when it worked. If it fails, say the next line and stop:
       > Setup did not finish. Please check that you are online and ask me to try again. Nothing was changed on your computer.
     - No: install nothing, say the next line and stop:
       > No problem. I can't help with your resumes or practice without that helper, so I'll stop here. Ask me again whenever you're ready.
   - `unsupported`: say the next line and stop:
     > Sorry, this isn't available on Windows yet.
2. Run every jobkit command with FOLDER first on the path, for example `PATH="FOLDER:$PATH" arch next` (macOS has its own `arch` program; this makes sure the right one runs). The commands in this skill are shown without that prefix.
3. Run `jobkit status`. If it says there is no database, run `jobkit init`. Do not mention either.
4. Run `profile status`. If there is no resume data yet, set up the resumes, one question at a time:
   1. Ask:
      > Where do you keep your resumes? You can drag the folder here or tell me its name.
   2. Look inside that folder. Only if it also holds files that do not look like resumes, ask:
      > I see some files that don't look like resumes. Should I skip any part of that folder?
   3. Run `profile init --resume-root FOLDER [--resume-dir SUBFOLDER ...]`, then `process-resumes --survey`, then `process-resumes`.
   4. Report what was found and ask:
      > I found N resumes from M employers: A, B, C. Does that look right?
   5. If one employer shows up under two names, ask for each pair:
      > I found "X" and "Y". Are they the same company?
      On yes, run `profile companies merge FROM INTO`, then `process-resumes --force`.
<!-- /shared:preflight -->

<!-- shared:talking -->
## Talking to the user
Everything the user reads is in everyday words. Lines that start with `>` in this skill are what to say: reword them lightly if you like, but keep the meaning and the plain wording. Never show the user commands, file names or folder paths (except the resume folder they named), error text, or the words database, JSON, id, hash, track, seed, tier, confidence, curation, needs review or JD. Run technical steps yourself; never ask the user to run a command or edit a file. Ask one question at a time, and say what will happen before anything is saved or changed. When something fails, say in plain words what went wrong and what to do next.

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

Flags: `build-resume --help`, `process-resumes --help`, `query-resume --help`. The resume data model (layouts, how lines are matched across resumes, curation) is in `${CLAUDE_SKILL_DIR}/data-model.md`; read it before changing how resumes are read or tagged.

## Building a resume for a job posting
1. Ask:
   > Please paste the job posting here.
2. Run `build-resume -` with the posting on stdin. It picks the best-fitting opening summary, the best non-duplicate lines per company (same scoring as `query-resume for-jd`), the skills the posting asks for grouped, certifications and education, and writes a Markdown file under the jobkit home folder's `output/resumes/`.
3. Read the result and tell the user, in plain words: that the resume is ready and where it is (this is the one place a folder name is shown), which skills the posting asks for that nothing on their resumes backs up, and, if lines were left out because they carry numbers that may be off, say so and offer to go through them:
   > A few lines were left out because their numbers may be off. Want to go through them now?
   Never invent resume lines; suggest wording and let the user decide.
4. If a company shows the wrong job title, rerun with `--title COMPANY-ID="Title"`.
5. The name and contact lines at the top come from `header.md` in the jobkit home folder (`~/.jobkit/profile/header.md`). `build-resume` creates a template on first run and reports when it is missing. If it is a template, ask:
   > What name and contact line should go at the top of your resumes?
   Write the answer to `header.md` yourself. Never copy it into the stored resume data.
6. Years of experience: use the figure the user gave in their open items (`profile open`). If the stored summaries disagree, ask which number is right before using one:
   > Your resumes say different numbers of years of experience. Which one should I use?

## Adding a resume
1. Run `process-resumes --survey`, then `process-resumes`.
2. Check the unparsed report (`jobkit export --only resume-unparsed`; certificate PDFs there are expected; an unreadable or unsupported file is listed with its reason) and any `problems` printed. Tell the user in plain words which files could not be read and why.
3. Tag new content with `process-resumes curate add theme BULLET_ID THEME...` for each new line and `curate add summary-angle SUMMARY_ID ANGLE...` for each new summary (angles: the words `curate themes` lists). Do this yourself.
4. Resolve new skill spellings and groups with `curate add skill-merge`, `skill-group` or `skill-drop` (one name at a time); mark conflicting figures with `curate add wrong-metric FIGURE` after the user confirms the figure is wrong. Then run `process-resumes` to apply.
5. New employers are found by the scan (`profile companies`). If one employer appears under two names, ask whether they are the same company and, on yes, `profile companies merge FROM INTO`; to change a name, `profile companies rename ID NAME`; then `process-resumes --force`. A new resume layout needs a parser change, which is a developer task: tell the user the file could not be read.
6. Verify: `query-resume stats` and `review`; run `process-resumes` again and expect 0 new or changed; check that no phone, email or LinkedIn is stored: `jobkit export --only resume-companies | grep -Ei '@|[0-9]{3}[ -][0-9]{3,4}'` shows any hit to review.
7. Tell the user, in plain words, how many resumes were added and anything that needs their decision.

## Extra rules for this skill
- Resume numbers are only accurate where the user confirms them.

<!-- shared:rules -->
## Rules
- The stored data is opened only through the commands in this skill, never directly. To show the user their data, read it with `jobkit export` and summarise it in plain words.
- The folder that holds the user's resumes is read-only: never create, edit or delete anything in it.
- Never invent resume lines or details about the user's experience. Suggest wording and let the user decide.
- Never store a phone number, email address or LinkedIn link in the data. Raw text taken from resumes stays under the jobkit home folder (`~/.jobkit/output`).
<!-- /shared:rules -->
