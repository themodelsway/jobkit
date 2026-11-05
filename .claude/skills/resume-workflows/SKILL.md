---
name: resume-workflows
description: Use when building a tailored resume for a job description (build-resume) or adding a new resume file (pdf, docx, md, txt) to the resume data (survey, process, tag themes, verify).
---

# Resume workflows

Run tools as commands from `.venv/bin/` (installed by `uv sync`) in the project folder. Flags: `build-resume --help`, `process-resumes --help`, `query-resume --help`.

## Creating a resume for a JD
1. Save the JD to a text file, run `build-resume` on it.
2. It picks: best-fit opening summary, top non-duplicate bullets per company (same scoring as `match`), JD-matched skills by group, certifications, education.
3. Read the output and report: the summary id used, JD skills with no supporting bullet (gaps), and any `needs_review` bullets left out. Don't invent bullets; suggest edits to the user instead.
4. If a company shows the wrong job title, rerun with `--title`. `profile/header.md` holds name/contact (never copy it into `resume-data/`).

## Adding a new resume
1. `.venv/bin/process-resumes --survey`, then `.venv/bin/process-resumes`.
2. Check `resume-data/json/_unparsed.json` (certificate PDFs there are expected; an unreadable or unsupported file is listed with its reason) and any `problems` printed.
3. Tag new content in `themes.json`: themes for each new bullet, angles for each new summary (angles: the words `curate themes` lists).
4. Resolve new skill spellings/groups in `curated.json`; flag conflicting metrics as `needs_review`.
5. New employers are found by the scan and added to `profile/companies.json` (edit it to merge or rename). A new resume layout -> adjust the parser.
6. Verify: `.venv/bin/query-resume stats` and `review`; re-run `process-resumes` and expect 0 new/changed; run the PII grep above.
