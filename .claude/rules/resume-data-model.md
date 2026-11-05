---
paths:
  - "src/jobkit/resumes/**"
  - "tests/resumes/**"
---

# Resume data model

- Bullet id is a short hash of normalised text. A bullet seen in several resumes gains `sources`; near-identical text (ratio >= 0.92) becomes a `variant`; materially different claims stay separate, including near-duplicates across resumes. If summaries state different years of experience, ask the user to pick one.
- Two layouts. A: `WORK EXPERIENCE`, `Company  dates`, title below, `•`, `Present`. B: `Work History`, `Company – Title`, `Role:`/`Client:`, `●`, `§` profile points, `Current`. Work history is parsed from `pdftotext -layout`; other sections from default reading order.
- Curation survives rebuilds and is changed only with `process-resumes curate list|add|rm` (certifications and education to keep, skill merge/drop/group, tag-only and extra skills, `wrong-metric` figures, bullet `theme`s, `ignore`d fragments, `summary-angle`s); bullets with a listed wrong figure are flagged `needs_review` and hidden from `for-jd` by default. Curation entries name bullets by id and are not linked to them: an id can change when a resume is edited, and such entries are reported as orphaned, never removed.
- Quality words (Security, Performance, ...) are bullet tags, not skills.
