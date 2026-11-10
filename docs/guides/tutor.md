# tutor

The tutor skill teaches a topic before checking understanding with a quiz. It also provides readiness reports. The [interview-prep](interview-prep.md) skill provides practice without a preceding lesson. This page explains how the tutor is used, then lists the commands it runs.

## How to use it

Requests use plain language and fall into these categories:

- Topic instruction.
- Guidance on answering a leadership question.
- Story development for a completed project.
- General readiness.
- Readiness for a supplied job posting.

**Teaching.** The skill covers three kinds of topic: technical questions, leadership questions and personal stories. It first asks what the user already knows, then teaches in short pieces and pauses for questions. For a technical card it covers what the technology is, when to choose it, limits, security, cost and recent changes. For a leadership question it explains what an interviewer is testing for and what a strong answer looks like, then helps the user find personal examples. For a story it teaches the purpose of each part of the STAR format, starting from the resume line, and helps fill in what is missing in the user's own words. It never makes up facts about the user's experience.

**Quiz.** After each lesson the skill asks one short question, corrects the answer, and asks a variation after a wrong answer. A lesson alone counts as "some gaps"; only a correct quiz answer lets a topic count as solid. The skill then asks whether to go deeper, move on, try a practice question or check readiness. It never skips ahead without asking.

**Facts.** For technical cards the skill checks the card first. If the lifecycle and recent-change records have never been verified or are about six months old, it checks the vendor's own documentation and records the source. Limits, prices and features are not stored, so they are looked up in the vendor's documentation every time.

## Readiness report

A readiness request produces the readiness report. It shows coverage and evidence for each area (technical cards, leadership questions and stories), optionally limited to one job posting. Each item carries one of these labels:

- **untested**: no real answer yet.
- **some gaps**: tried, with gaps.
- **solid-once** or **solid-repeated**: answered well once, or on more than one day.
- **aging**: answered well, but not practised for longer than the retest window.
- **solid-unlogged**: confidence recorded by hand, with no logged answer.

Stories carry their own labels: empty, draft, done, done-rehearsed or done-aging. These record attempts, not answer quality.

The report deliberately has no single score. It comes from practice answers the skill graded, so it shows what has been covered and how well it has been tested, not how a real interviewer would score the answers. One good result is weak evidence, so repeating it on another day is worthwhile. A lesson on its own does not count as practice.

The skill names the three to five most valuable gaps and offers to teach or practise the first one. When well-answered items are older than the retest window, it offers to re-check some of them, handing over to interview-prep. A retest never starts without confirmation.

## Commands it uses

The tutor uses the same commands as interview-prep (`prep`, `arch`, `lead`, `sessions`), described on the [interview-prep page](interview-prep.md#commands-it-uses), plus `readiness`. The shared commands `jobkit` and `profile` are in the [manual](../manual.md#commands-every-skill-uses). A tutor session is a session started with `sessions new --mode tutor --topic architecture|leadership|stories`. Teaching alone cannot raise a card's confidence above 1 and never lowers confidence already earned in practice; a passed quiz allows 2.

### `readiness`

`readiness [--jd FILE] [--days N] [--due [--json] [-o FILE]]`: coverage and evidence per area across cards, leadership questions and stories. Read-only. `--jd` limits it to what a job description touches (architecture and stories). `--days` is how old a solid answer may be before it reads as aging; the default is the stored retest window (`profile set reassess_days N`, 30 when none is set). `--due` prints, instead of the report, the items due for a retest (the ones the report labels `aging` or `done-aging`): id, name, the date of the last good answer and its age in days, oldest first, or `none due`; `--json` and `-o FILE` give it as JSON or write it to a file; it cannot be combined with `--jd`.

Labels: `untested`, `some gaps`, `solid-unlogged`, `solid-once`, `solid-repeated`, `aging` (also when every solid answer is older than `--days`). Stories: `empty`, `draft`, `done`, `done-rehearsed` (answer logged within `--days`), `done-aging`; a story label says attempted, not graded. A tutor lesson does not refresh the last-drilled date. There is deliberately no single score.
