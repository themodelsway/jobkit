# Resume tooling

Local store of resume content (grouped by company, plus grouped skills) built from resumes (PDF, docx, md, txt). When a job description (JD) is pasted, suggest the best experience bullets per company and opening summaries.

## Hard rules
- The user's resume folder (`resume_root` in `profile/profile.json`) is READ-ONLY. Never edit or write there (add deny rules in `~/.claude/settings.json`; Bash writes are not blocked, so don't do them either).
- Committed files must hold nothing personal (name, employers, folders, figures). Personal settings live only in git-ignored `profile/`, `resume-data/`, `prep/`, `output/`. `tests/test_no_personal.py` enforces it.
- No contact info (phone, email, LinkedIn) in `resume-data/`. Check: `grep -rEi '@|[0-9]{3}[ -][0-9]{3,4}' resume-data/json/` and review any hit.
- Raw extracted text goes only in `output/`.
- Never invent resume bullets; suggest edits to the user instead. For building a resume for a JD or adding a resume file, use the `resume-workflows` skill.
- Don't use the word "bank" in names; say "resume data".
- Prefer Python scripts over `jq` for repeated tasks. If a question is needed, ask one at a time.

## Layout
Tools are grouped by purpose: `src/jobkit/user/` (profile), `src/jobkit/resumes/` (resume files to resume data, matching, building), `src/jobkit/interview/` (stories, architecture, leadership, sessions, readiness); AWS-specific data is in `src/jobkit/interview/aws/`.
| Path | Purpose |
|---|---|
| `src/jobkit/interview/prep.py`, `story_model.py` | Interview-prep stories (STAR, metrics with a basis, spoken versions, follow-ups) and engagements (facts with a basis, decisions, people) in git-ignored `prep/stories.json` and `prep/engagements.json`. `story_model.py` holds the pure rules (fact bases, validation, rendering). Used by the `interview-prep` and `tutor` skills. Tests: `.venv/bin/python -m unittest discover -s tests -t .`. |
| `src/jobkit/interview/arch.py`, `src/jobkit/interview/aws/arch_seed.py` | role knowledge drill cards in git-ignored `prep/arch/`. All AWS-specific seed data (services, decision pairs, scenarios, accepted doc hosts) lives in `src/jobkit/interview/aws/`; lifecycle facts are never seeded, only recorded by `arch refresh` with a source URL. |
| `src/jobkit/resumes/extract.py` | One reader per resume format (pdf, docx, md, txt) behind `extract.extract(path)`, which returns `ExtractedDocument(text, layout_text, format)`; a new format is one `@register` class. Non-PDF text drops contact/address-only lines. Tests: `tests/resumes/test_extract.py`. |
| `resume-data/curated.json` | Hand curation that survives rebuilds: certifications, skill merge/drop/group, tag_only, extra_skills, `review_if_metric_matches`. |
| `resume-data/themes.json` | Bullet id -> themes, `ignore` list, `summary_angles` (summary id -> angles). |
| `resume-data/json/` | Generated: `companies/*.json`, `skills.json`, `profile.json`, `index.json`, `ledger.json`, `_unparsed.json`. |
| `output/*.txt` | Raw extracted text per resume file. |

## Tools
Setup instructions are in `README.md`. First create the git-ignored profile: `.venv/bin/profile init --resume-root <folder>` (see README); command flags are in each tool's `--help`.
Open items and data notes that are personal (figures to correct, certifications to keep, which number to use) live in git-ignored `profile/open_items.json`: read them with `profile open` at the start of resume work, and add with `profile open add TEXT`. `uv sync` installs the tools as commands in `.venv/bin/` (`profile`, `process-resumes`, `query-resume`, `build-resume`, `arch`, `lead`, `prep`, `sessions`, `readiness`; entry points in `pyproject.toml`); run them from the project folder, e.g. `.venv/bin/prep status`. They also run as `.venv/bin/python -m jobkit.interview.prep`.

`match` output: suggested opening summaries, bullets per company (newest first), JD skills with no matching bullet, skills to feature by group. These are keyword/tag-based suggestions; make the final picks yourself.

## Command conventions
Every tool follows the same shape, so one habit works everywhere:
- Verbs: `init` (create/extend, never overwrite answers), `status`, `list`, `show ID`, `next`, `set ID FIELD VALUE`, `for-jd JD` (rank by a job description), `add`/`rm` inside a noun (`fact add`, `metric rm`).
- A job description is a positional file (`-` = stdin) when it is the subject (`for-jd`, `build-resume`) and `--jd` when it only filters (`readiness`, `sessions new`). Output files use `-o/--output`.
- Messages for the user go to stdout; problems go to stderr with exit status 1 (`validate` also exits 1 when it finds errors); bad arguments exit 2 (argparse).
- Older names still work: `query-resume match` = `for-jd`, `prep skeleton` = `init`.

## Code conventions
- Code is the `jobkit` package under `src/jobkit/`; import siblings as `from jobkit.resumes import resume_data`, never by editing `sys.path`. A new tool gets a `[project.scripts]` entry in `pyproject.toml` (the CLI contract test checks the list).
- Python 3.14, every function typed and documented, functions about 20 lines (40 at most), no work at import time. Each tool has `build_parser()` and `main(argv) -> int`; handlers raise `common.ToolError` for user mistakes and `common.run` turns it into an exit status.
- Records are `TypedDict`s (or dataclasses); shared helpers live in `jobkit/common.py` and `resume_data.py`, not copied between tools.
- Checks: `.venv/bin/python -m unittest discover -s tests -t .`, `.venv/bin/pyright` (`[tool.pyright] include` in `pyproject.toml` lists the checked modules) `.venv/bin/ruff check src tests` (`ruff.toml`) and `.venv/bin/pylint src` (`.pylintrc`; for tests add `--disable=missing-function-docstring,missing-class-docstring,protected-access,consider-using-with`); all need `uv sync` (Python pinned in `.python-version`, dependencies in `pyproject.toml` and `uv.lock`; add one with `uv add PKG` or `uv add --dev PKG`). `.githooks/pre-commit` runs ruff, pyright and the tests (not pylint) before each commit; enable it once per clone with `git config core.hooksPath .githooks`.

## Interview prep
Use the `interview-prep` skill (`.claude/skills/interview-prep/`): STAR stories, role knowledge drills, and resumable sessions (each session keeps the user's full answers). The `tutor` skill (`.claude/skills/tutor/`) teaches architecture cards, leadership questions and STAR stories first (explain, then quiz) with the same tools (`sessions new --mode tutor --topic architecture|leadership|stories`); teaching caps confidence at 1, a passed quiz (`--quiz`) allows 2. `readiness [--jd jd.txt]` reports coverage and evidence per area (no single score).
Read/write `prep/` data only through `prep` (stories), `arch` (architecture catalog and confidence), `lead` (leadership), `sessions` (sessions) and `readiness` (read-only report); never open `prep/**/*.json` directly. Writes are atomic (a `.bak` of the previous file is kept) and serialised by a lock (`prep/.lock`). Everything under `prep/` is git-ignored.
AWS facts (limits, features, lifecycle/deprecations) are never stated from memory: check AWS docs, then record with `arch refresh ... --source URL` (an aws.amazon.com / docs.aws.amazon.com page). Cards store only lifecycle and recent changes; seeded values are unverified leads until refreshed. Lifecycle words: maintenance = closed to new customers, no new features; sunset = has an end date.

Leadership data (`prep/leadership/`: questions, progress, profile facts such as team sizes) is also git-ignored; use `lead` only. Team sizes and scope numbers come from the user, never guessed.

## Data model notes
- Bullet id = short hash of normalized text. Bullets seen in several resumes accumulate `sources`; near-identical text (ratio >= 0.92) becomes a `variant`; materially different claims stay separate.
- Two layout families: layout A (`WORK EXPERIENCE`, `Company  dates`, title below, `•`, `Present`) and layout B (`Work History`, `Company – Title`, `Role:`/`Client:`, `●`, `§` profile points, `Current`). Work history is parsed from `pdftotext -layout`; other sections from default reading order.
- Quality words (Security, Performance, Scalability, High Availability, Cost Efficiency) are bullet tags only, not skills.
- Certifications to keep, and expired ones to drop, are set in `resume-data/curated.json` (`certifications`).
- Metrics you know are wrong or conflicting are listed in `resume-data/curated.json` (`review_if_metric_matches`); bullets containing them are flagged `needs_review` and hidden from `match` by default.
- Open item: near-duplicate wordings across resumes are kept separate by design. If your summaries state different years of experience, pick one.
