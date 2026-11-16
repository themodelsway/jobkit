# Top commands to explore

These commands display profile settings, interview preparation and study progress from the command line. They leave stored records unchanged, can be run in any order after setup, and do not use AI. The one exception to display-only output is `jobkit export` with `-o`, which writes files and replaces existing exports with the same names.

The three skills run these commands on request, from plain-word questions (see [manual.md](manual.md)). Running a command directly shows the same information the skill uses.

Commands run from a terminal in the repository root, as `uv run` followed by the command. `--help` on any command or subcommand lists its options. Setup comes first: `uv sync`, `uv run jobkit init`, `uv run profile init --resume-root PATH`, `uv run process-resumes` to import the resumes, then `prep init`, `lead init` and `arch init --track NAME` (the bundled technology is `aws`) to create stories, leadership questions and technical cards. Until then, `readiness` and the status commands report which step is missing.

---

## Profile

| Command | What it shows |
|---|---|
| `jobkit status` | Where the data is kept, and how many stories, cards, questions and sessions it holds |
| `profile status` | The saved settings, and any that are still missing |
| `profile open` | The open items and notes saved for later |
| `profile companies` | The employers found in the resumes |
| `jobkit export --only stories --format md` | One kind of data, printed as readable Markdown |
| `jobkit export --format md -o ~/jobkit-export` | All data, written as one Markdown file per kind |

## Interviewing

### Readiness

| Command | What it shows |
|---|---|
| `readiness` | Preparation by area: technical topics, leadership questions and stories, with the next items to work on |

The report deliberately has no single percentage. Technical cards and leadership questions carry an evidence label: untested, some gaps, solid once, solid on more than one day, or aging (good once, but not practiced lately). A separate label marks confidence recorded by hand with no logged answer. Stories show their status and whether they were rehearsed recently.

### Technical topics

| Command | What it shows |
|---|---|
| `arch status` | Technical cards by area: solid, some gaps, or not yet drilled |
| `arch stale` | Cards whose facts have never been checked, or were checked long ago |
| `arch list` | The technical cards in the catalog, with their IDs |
| `arch show ID` | One card, by its ID from `arch list`: confidence, last drill, lifecycle information, notes and the number of linked resume lines for each employer |
| `arch for-jd jd.txt` | Service cards mentioned in a job posting, lowest confidence first |

### Leadership questions

| Command | What it shows |
|---|---|
| `lead status` | Leadership questions by area, and the employers that are missing scope facts such as team size |

### Stories

| Command | What it shows |
|---|---|
| `prep status` | Stories for each employer: done, draft or empty |
| `prep list` | Story IDs, statuses and headlines, for the commands below |
| `prep evidence STORY_ID` | Practice dates for one story, including the dates it was graded solid |
| `prep export --story STORY_ID --format md` | A one-page cheat sheet for one story |
| `prep search "latency"` | Matching text in stories and in engagement facts and decisions |
| `sessions list` | All sessions, newest first, with mode, status and progress |

`prep evidence` shows rehearsal history. `prep show STORY_ID` displays the story, its metrics and its linked facts with their stated basis. `prep validate STORY_ID` reports content problems that need review. `sessions resume ID` shows the recent answers and the next item; a closed session needs `sessions reopen ID` before practice can continue.

## Tutoring

| Command | What it shows |
|---|---|
| `readiness --due` | Cards and leadership questions due for reassessment, plus completed stories due for another rehearsal, oldest first |
| `readiness --jd jd.txt` | Coverage for the service cards and story themes that match a job posting, followed by suggested gaps |
| `arch stale` | Cards whose facts need checking against the vendor's documentation |
| `sessions list` | All sessions, including lesson sessions, with mode and status |

Teaching alone does not establish a solid result. For technical cards and leadership questions, a passed quiz or a graded practice answer does. A story's rehearsal status records attempts, not answer quality.

---

## Plain-language requests

Each skill can run these commands from a plain-language request, read the output and explain it:

| Output | Request type |
|---|---|
| Weak topics in `arch for-jd` or `readiness --jd` | Instruction on a named service or practice, or a quiz for a supplied posting |
| Empty stories in `prep status` | Development of a story about a completed project |
| Items due in `readiness --due` | Readiness assessment and an optional retest |

Every command and option is listed in [manual.md](manual.md) and the [guides](guides/).
