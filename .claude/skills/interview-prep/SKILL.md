---
name: interview-prep
description: Mock-interview drills for the resume project: asks first, no hints, then grades. Use when the user wants to be quizzed or practise answers (architecture for AWS, Acme Data, GCP or another chosen technology, leadership questions, STAR stories), resume an earlier practice session, or see what to rehearse for a job description. To be taught or to check readiness use the tutor skill instead. Asks one question at a time; sessions, stories and progress are saved via the `sessions`, `arch`, `lead` and `prep` commands.
---

# Interview prep

## First run (profile)
Before anything else run `.venv/bin/jobkit status`; if it says there is no database, run `.venv/bin/jobkit init` once. Then run `.venv/bin/profile status`. If there is no profile, or no resume data (`process-resumes` has not run), set up first, asking one question at a time:
1. Ask where the resume files are (pdf, docx, md or txt; any folder; files in its subfolders are found too, no particular layout needed; ask whether to limit the scan to some subfolders only if the folder also holds unrelated files). Optionally ask for the user's name (stored only in your local database).
2. Run `profile init --resume-root <folder> [--resume-dir <subfolder> ...] [--name <name>]`.
3. Run `process-resumes --survey`, then `process-resumes`. The first scan finds the employers in the resumes and stores them; tell the user which employers were found (`profile companies`) and, if one employer shows up twice, fix it with `profile companies merge FROM INTO` or `rename ID NAME` (then `process-resumes --force`).
4. Ask what the user is preparing for: one or several technologies (for example AWS, Acme Data, GCP) and the role. Each is a drill *track*. Run `lead init` and `prep init` (leadership themes and stories come from the resumes whatever the target), then set up every track the user named (see "Tracks" in `.claude/skills/interview-prep/architecture.md`): `arch init --track aws` for the bundled AWS example, and for any other technology build a seed, show it to the user, register it with `arch track add NAME --seed -`, then run `arch init --track NAME`. Tier-1 services are the ones the resumes mention (the user may pin their own list with `profile tier1 ...`). Later the user can add another track the same way; `arch tracks` shows what exists.
Never put the user's name, employers or folders in committed files; they live only in the local database under `~/.jobkit`, outside the repository. To show the user their data, run `jobkit export` (never open the database directly).

Stories live in the local database (personal). Always read and write them through
`.venv/bin/prep` and do not open the JSON files directly, to keep context small.

## Commands
- `prep status` : filled vs empty stories per company
- `prep next [--company <company-id>]` : next unfinished story (prints resume line, metrics, current answers)
- `prep show STORY_ID`
- `prep set STORY_ID FIELD "VALUE"` : FIELD is situation, task, action, result, metric, lessons, notes, follow_ups (use ` | ` between several) or status (empty, draft, done)
- `prep for-jd jd.txt` : stories ranked for a job description, with typical questions and the ones still unfinished
- `prep init` : add stories for new bullets or themes (never overwrites answers)

## Sessions (always first)
Every practice run belongs to a session, so the user can start fresh or go back to an old one.
1. Run `sessions list`. Ask the user whether to start a new session or resume one. Never guess which.
2. New: `sessions new "title" [--mode architecture|stories|jd|leadership] [--order default|random] [--jd jd.txt] [--track T] [--area A] [--tier N] [--kind service|pair|scenario] [--company C] [--category C] [--count N]`. (`--mode tutor --topic ...` belongs to the tutor skill.) A closed session can be continued with `sessions reopen ID`.
3. Resume: `sessions resume ID` prints what was covered, the last answers and the next item.
4. After each answer: `sessions log ID ITEM --question "..." --answer - --grade "..." --confidence N` (answer on stdin; keep the user's FULL answer). End with `sessions close ID` when the user says they are done. The tool rejects unknown item ids, empty answers, closed sessions and `--confidence` on stories; fix the command rather than working around it.
Commands: `sessions list|new|resume|log|close`. Session files hold full answers and are git-ignored; read them only through the tool.

## Architecture fundamentals (mode: architecture, or the architecture items in a jd session)
Service, decision-pair and scenario drills for each track the user chose (AWS, Acme Data, GCP, ...). Read `architecture.md` in this folder for the rubric, how to add a track, and the rule that facts come from checked sources, never from memory. Commands (`.venv/bin/arch`): `tracks`, `track add NAME --seed FILE|-`, `status`, `next [--track --area --tier --kind]`, `show ID`, `list`, `set ID confidence|notes VALUE`, `for-jd jd.txt`, `stale`, `refresh ID --status ... --source URL`, `init`.
Flow: the session's next item -> `arch show ID` -> ask one question -> user answers -> grade and correct with checked facts -> log it.

## Leadership questions (mode: leadership)
People-leadership questions (roadmapping, prioritization, mentoring, conflict, team size, execution, influence), each tied to STAR examples from the three most recent companies. Read `leadership.md` in this folder first. Commands (`.venv/bin/lead`): `status`, `next [--category C] [--order default|random]`, `show ID`, `list`, `set ID principle|notes|confidence VALUE`, `example ID COMPANY FIELD VALUE`, `profile show|set`, `init`. Start a session with `sessions new "title" --mode leadership [--category C] [--order random]`.

## Order choice
For architecture and leadership sessions, ask the user whether they want default order (weakest first) or random, unless they already said.

## Filling stories (interview mode)
1. Run `status`, then `next` (use `--company` if the user names one; default to the most recent role first).
2. Show the story's resume line and metrics in two lines, then ask **one question at a time**, in this order: situation, task, what *you personally* did (action), result with a number, what went wrong or what you would change, then the tough follow-ups an interviewer would ask.
3. Do not make up details. If an answer is vague, ask one probing follow-up ("how was that measured?", "what did you do versus the team?"). Never copy facts from other stories or from your own assumptions.
4. After each answer, save it with `set`. When situation, task, action and result are all filled, tighten them into 1-2 sentences each, read the finished story back, and on the user's okay set status to `done`.
5. Offer the next story only after the current one is done. Stop when the user says to.
6. Flag any mismatch between the user's answer and the resume line (e.g. different number) and ask which is correct before saving; the resume numbers are only accurate where the user confirms them (see `CLAUDE.md` for known figures that need a check).

## Preparing for a specific job description
1. Save the JD to a text file and run `prep for-jd`.
2. Report: the top stories and their typical questions, which of them are not `done` (offer to fill those first), and JD themes with no story at all.
3. For rehearsal, ask the typical questions one at a time and give short feedback on the answer against the saved story (structure, metric, ownership, length). Do not rewrite their story unless asked.

## Rules
- Contact details and company-confidential specifics (client names, internal figures beyond the resume) are the user's call: ask before saving anything not already on a resume.
- Never write to the user's resume folder (the `resume_root` setting).
