# Leadership questionnaire

Used by the `interview-prep` skill in leadership mode. Data lives in git-ignored `prep/leadership/` and is accessed only through `.venv/bin/lead`.

## Shape of an answer
Each question gets two parts:
1. **Principle**: how the user handles this in general, in their own words (2-4 sentences). Saved with `lead set ID principle "..."`.
2. **One STAR example per company** for the three most recent companies (`lead show` or `lead profile show` lists them). Saved with `lead example ID COMPANY situation|task|action|result|metric "..."`.
A strong interview answer is the principle followed by one example, so practise both.

## Profile facts (scope questions)
Questions like "how many people have you led" need exact numbers per role. Ask for them one at a time, never guess, and save with `lead profile set COMPANY FIELD VALUE` (fields: title, direct_reports, indirect_team, team_composition, budget, stakeholders, reporting_to, cadence, notes). Distinguish direct reports, indirect/matrixed team, and contractors or vendors. Do not copy numbers from the resume unless the user confirms them.

## Flow per question
1. `lead show ID` (or `next [--category C] [--order random]`). It prints the question, profile facts, and candidate resume-based stories (from `prep`) for each of the three companies.
2. Ask the question as an interviewer would. One question at a time, no hints.
3. After the user answers, grade briefly: structure (principle then example), ownership ("I" vs "we"), a measurable result, honesty about what went wrong, and length (about 2 minutes spoken).
4. Probe for each of the three companies that `lead show` lists, in turn ("Do you have an example from <company>?"). If a candidate story in `prep` is already `done`, reuse its STAR instead of asking again; if it is empty or draft, finish it through the normal story flow so one story serves both the theme and this question.
5. Never invent details. If the user has no real example for a company, record none and move on. Ask before saving anything that is not on a resume (client names, confidential figures).
6. Log the full answer to the session (`sessions log ... --answer -`) with a confidence of 0, 1 or 2, then ask whether to go deeper or move on.

## Order
Default order is weakest and least recently drilled first. For a surprise mix use `--order random` on `lead next` or `sessions new`. Filter with `--category` (Scope and facts, Roadmapping and strategy, Prioritization, Mentoring and people, Conflict, Execution, Influence and communication, Culture).
