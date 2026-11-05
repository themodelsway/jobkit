# jobkit data structures

All of jobkit's data is in one SQLite database under the home folder, which is outside the repository, so nothing personal is committed. This page describes the tables, the shape of each record and which command writes it. Examples use made-up values. The commands are in [cli-manual.md](cli-manual.md).

Rules that hold for all data:

- Dates are `YYYY-MM-DD`, month values `YYYY-MM`, timestamps ISO 8601.
- The data is changed only by the commands, never by hand. To look at it, run `jobkit export` (JSON or Markdown). Each kind of data below names its export kind.
- A command's changes are stored together or not at all; several commands can run at once.
- Types are the `TypedDict`s in the code. `?` marks an optional field.

| Where | Holds | Written by |
|---|---|---|
| the database (`data/jobkit.db`) | settings, resume data, curation, stories, drill cards, leadership answers, sessions | `profile`, `process-resumes`, `prep`, `arch`, `lead`, `sessions` |
| `profile/header.md` | your name and contact line for built resumes (a text file you write) | you |
| `output/` | raw extracted text and built resumes | `process-resumes`, `build-resume` |
| `backup/` | database backups and the copy of the old JSON files | `jobkit backup`, `jobkit migrate` |

---

## The database (`~/.jobkit/data/jobkit.db`)

All data lives in one SQLite database under the home folder (`~/.jobkit`, or `JOBKIT_HOME`). It is changed only by the commands, and you look at it with `jobkit export`. Each command's changes are stored together or not at all.

A record table keeps the whole record as JSON in `body` (the shapes below are what `body` holds) and repeats the fields that are keys, links or queried as real columns, written from the body in one place, so they cannot disagree. The schema version is in `PRAGMA user_version`; `jobkit status` shows it.

| Table | One row is | Notes |
|---|---|---|
| `meta` | a named setting or document header | The catalog's `dimensions` and `tracks`, the stories and engagements `schema_version`. |
| `session` | a practice session | `id`, `title`, `mode`, `status`, `created`, `updated`; `body` holds the rest (`topic`, `jd`). |
| `session_item` | one queued item of a session | `session_id`, `position`, `item`, `kind` (`card`, `story`, `leader`). |
| `session_log` | one logged answer | **Append-only**: the database refuses updates and deletes. `answered` is 1 when the answer is not empty; `tutor` and `quiz` mark lessons and passed quizzes. `readiness` is computed from these rows. |
| `card` | an architecture card (service, decision pair or scenario) | `id`, `track`, `kind`, `area`, `name`, `tier`; `body` has `aliases`, `members`, `lifecycle`, `recent_changes`, `verified_on`. |
| `card_progress` | your progress on one card | `card_id` (must be a card), `confidence` (0 to 2), `last_drilled`; `body` has `notes` and `links` to resume bullets. Removing a card removes its progress. |
| `track` | a custom technology track | `name`; `body` is the seed (services, pairs, scenarios, documentation hosts). |
| `engagement` | a real project | `id`, `company`, `title`, `updated`; `body` has `my_role`, `period`, `summary`, `notes`, `counters`. |
| `fact` | a fact about an engagement | `engagement_id`, `id` (`f1`, `f2`, ...; an id is never reused), `basis`; `body` has `text`, `source`, `note`, `added`. |
| `decision` | a decision on an engagement | `engagement_id`, `id` (`d1`, ...), `ownership`; `body` has `what`, `why`, `alternatives`, `tradeoffs`. |
| `person` | a person on an engagement | `engagement_id`, `position`; `body` has `role`, `note`. |
| `story` | a STAR story | `id`, `company`, `theme`, `status`, `engagement_id` (must be an engagement; checked when the change is committed); `body` is the story. |
| `theme` | a story theme | `name`; `body` lists its stories and leadership questions. |
| `lead_question` | a leadership question | `id`, `position`, `category`; `body` has `question` and `themes`. |
| `lead_progress` | your answer to one question | `question_id` (must be a question), `confidence`, `last_drilled`; `body` has `principle`, `notes` and one STAR `examples` entry per company. |
| `lead_company_fact` | factual scope for one employer | `company_id`; `body` has team sizes, budget and similar facts you stated. |
| `setting` | one profile setting | `key` (`resume_root`, `resume_dirs`, `name`, `tier1_services`) and its JSON `value`. |
| `employer` | an employer found in the resumes | `id`, `position`, `name`; `body` has the match `regex` and, after a merge, `aliases`. Changed with `profile companies rename` and `merge`. |
| `open_item` | an open item or data note | `id`, `status` (`open`, `done`); `body` has `text`. |
| `company` | an employer in the resume data | `id`, `position`, `name`; `body` has `aliases`. Removing a company removes its roles and bullets. |
| `role` | one period at a company | `company_id`, `position`, `start`; `body` has `end`, `titles`, `subtitles`, `clients`, `sources`. |
| `bullet` | one experience bullet, deduplicated across resumes | `company_id`, `id` (hash of the text), `needs_review`; `body` has `text`, `skills`, `themes`, `metrics`, `variants`, `ignored`. |
| `bullet_source` | a resume file a bullet came from | `company_id`, `bullet_id`, `source` (the resume file). Lets a rebuild find what a deleted file contributed. |
| `skill` | a skill in a group | `group_name`, `position`, `name`; `body` has `aliases` and `sources`. |
| `resume_item` | one entry of the resume's own sections | `section` (`summaries`, `profile_points`, `education`, `certifications`, `projects`, `headlines`), `position`; `body` is the entry. No contact details are stored. |
| `ledger` | a resume file that was read | `file`, `kind` (`resume` or `other`), `mtime`; `body` has `size`, `sha256`, `processed_at`. |
| `unparsed` | why a file could not be read | `file`; `body` is the list of problems. |
| `curation` | one curation entry | `file` (`curated` or `themes`), `kind` (the key in that file), `key`, `position`; `body` is the entry. Not linked to bullets: a bullet id can change on a rebuild, and such entries are reported as orphaned. Changed only with `process-resumes curate`. |

The sections below describe the record shapes as `jobkit export` shows them (and as `body` holds them).

---

## Settings, employers and open items

### Settings (`setting`; export kind `settings`)
```json
{ "resume_root": "/path/to/resumes", "resume_dirs": ["2026"], "name": "Your Name", "tier1_services": ["Lambda"] }
```
`resume_root` is read-only for all tools. `resume_dirs` limits the scan to subfolders. `tier1_services` pins your own tier-1 drill topics (any track, matched by name). Code: `user/profile.py`.

### Employers (`employer`; export kind `employers`)
`{ "<company-id>": { "name": "Acme Corp", "regex": "Acme( Corp)?" } }`. Employers found on the first scan. The regex must match a whole header line. Change employers with `profile companies rename` and `merge`.

### `profile/header.md` (a file in the home folder)
Name and contact line printed at the top of built resumes. Plain text, not JSON. Contact details live only here.

### Open items (`open_item`; export kind `open-items`)
`[ { "id": 1, "text": "Confirm team size", "status": "open" } ]`. Status is `open` or `done`.

---

## Resume data (generated by `process-resumes`)

How resume text becomes data: each resume is split by employer, bullets are merged across resumes, and every item keeps the resume files it came from (`sources`).

### One employer (`company`, `role`, `bullet`, `bullet_source`; export kind `resume-companies`)
```json
{
  "id": "acme", "name": "Acme Corp", "aliases": [],
  "roles": [ { "start": "2021-03", "end": null, "titles": ["Architect"], "subtitles": [], "clients": [], "sources": ["2026/a.docx"] } ],
  "bullets": [ {
      "id": "acme-1a2b3c", "text": "Cut deploy time ...", "role_start": "2021-03",
      "skills": ["Terraform"], "skills_manual": [], "themes": ["devops"], "metrics": ["40%"],
      "sources": ["2026/a.docx"], "variants": ["near-identical wording"], "needs_review": false, "ignored": false } ]
}
```
- `roles[].end` is `null` for the current role. `titles`, `subtitles` and `clients` collect every spelling seen.
- Bullet `id` is a short hash of the normalised text (prefixed by the company). The same wording in several resumes keeps one bullet with more `sources`. Wording at least 92% similar becomes a `variants` entry. Materially different claims stay separate bullets.
- `skills_manual` are skills you added by hand; `metrics` are the figures found in the text. `needs_review` is set when a figure matches `review_if_metric_matches` in the curation; those bullets are hidden from `for-jd` unless `--include-review`. `ignored` removes a bullet from matching and from built resumes.
- Quality words (Security, Performance, ...) appear in `themes` or `tag_only`, never as skills.

### Skills (`skill`; export kind `resume-skills`)
```json
{ "groups": { "Cloud": [ { "name": "Terraform", "aliases": ["TF"], "sources": ["2026/a.docx"] } ] },
  "tag_only": ["Security", "Performance"] }
```
Skills by group (Cloud, Languages, Leadership, ...). `tag_only` lists quality words kept as bullet tags.

### The resume's own sections, no contact details (`resume_item`; export kind `resume-profile`)
```json
{ "summaries": [ { "id": "sum-ab12cd", "text": "...", "angles": ["leadership"], "sources": ["..."] } ],
  "headlines": ["placeholder"], "profile_points": ["..."], "education": ["..."],
  "certifications": [ { "name": "...", "issued": "2024-05", "expires": "2027-05" } ], "projects": ["..."] }
```
`angles` say what a summary emphasises, so `for-jd` can pick the best opening.

### Overview (export kind `resume-index`)
`{ "generated": "<timestamp>", "companies": [ { "id", "name", "bullets", "roles" } ], "skill_groups": { "Cloud": 12 }, "themes": ["devops"], "resumes": 8 }`. A summary used by `stats` and by `lead init`, which keeps only themes present here.

### Scan ledger (`ledger`; export kind `resume-ledger`)
`{ "<path relative to resume_root>": { "mtime": 1.7e9, "size": 40213, "sha256": "...", "processed_at": "<timestamp>", "kind": "resume" } }`. `kind` is `resume` or `other` (not a resume). Unchanged files (same size, mtime, hash) are skipped; entries for deleted or renamed files are pruned together with their bullets and sources.

### Unparsed report (`unparsed`; export kind `resume-unparsed`)
`{ "<path>": ["reason it could not be parsed"] }`. Reasons name the cause (for example a scanned PDF with no text layer, or a Word file with text only in text boxes or headers).

---

## Curation (`curation`; changed with `process-resumes curate`)

### Certifications, skill rules and known-wrong figures (export kind `curated`)
```json
{ "certifications": [ { "name": "...", "issued": "2024-05", "expires": "2027-05" } ],
  "review_if_metric_matches": ["40%"], "skill_merge": { "placeholder": "placeholder" },
  "skill_drop": ["Misc"], "tag_only": ["Security"], "skill_group": { "ECS": "Cloud" } }
```
Survives every rebuild. `skill_merge` maps a spelling to its canonical name; `skill_drop` removes a skill; `skill_group` assigns a group; `review_if_metric_matches` lists figures you know are wrong so their bullets are flagged. `query-resume review` reports ids here that no longer exist.

### Bullet themes, ignored fragments and summary angles (export kind `curation-themes`)
`{ "themes": { "<bullet-id>": ["devops"] }, "ignore": ["<bullet-id>"], "summary_angles": { "<summary-id>": ["leadership"] } }`. Which themes tag which bullet and what each summary emphasises.

---

## Stories and engagements

### Stories (`story`; export kind `stories`): `{ "schema_version": 2, "stories": [ Story ] }`
```json
{ "id": "acme-devops", "company": "acme", "company_name": "Acme Corp", "theme": "devops", "headline": "...",
  "status": "draft",
  "situation": null, "task": null, "action": null, "result": null, "metric": null, "lessons": null, "notes": null,
  "follow_ups": [], "likely_questions": [], "never_say": [], "also_themes": [],
  "engagement": "acme-platform", "uses_facts": ["f1", "f3"],
  "metrics": [ { "name": "deploy time", "value": "-40%", "basis": "stated", "note": "..." } ],
  "resolved": [ { "q": "question", "answer": "what you said", "at": "<timestamp>" } ],
  "spoken": { "60s": null, "2min": null },
  "metrics_on_resume": ["40%"], "anchor_bullets": ["acme-1a2b3c"], "updated": "<timestamp>" }
```
- `status`: `empty`, `draft`, `done`. `done` is blocked while `prep validate` reports errors.
- STAR fields are `situation`, `task`, `action`, `result`; `metric` is the headline number as spoken.
- `metrics[].basis`: `measured`, `estimated`, `stated`, `unknown`. Estimated or unknown metrics need hedged wording.
- `spoken` holds the 60-second (about 160 words) and 2-minute (about 330 words) versions.
- `engagement` and `uses_facts` link the story to the real project and the facts it relies on.
- `metrics_on_resume` and `anchor_bullets` are copied from the resume data when the story is generated, so you can see what the resume already claims.

### Engagements (`engagement`, `fact`, `decision`, `person`; export kind `engagements`): `{ "schema_version": 2, "engagements": [ Engagement ] }`
```json
{ "id": "acme-platform", "company": "acme", "title": "Platform migration", "my_role": "Lead", "period": "2022",
  "summary": "...", "notes": null,
  "facts": [ { "id": "f1", "text": "12 engineers", "basis": "stated", "source": "https://...", "note": "...", "added": "<date>" } ],
  "decisions": [ { "id": "d1", "what": "placeholder", "why": "...", "alternatives": ["EKS"], "tradeoffs": "...", "ownership": "mine" } ],
  "people": [ { "role": "Product owner", "note": "..." } ],
  "counters": { "f": 1, "d": 1 }, "updated": "<timestamp>" }
```
- `facts[].basis`: `stated`, `estimate`, `unsure`, `verified-doc` (needs `source`), `proposed` (an assistant suggestion, never your claim). Only `stated`, `estimate` and `verified-doc` may back a story.
- `decisions[].ownership`: `mine`, `team`, `client`, `shared`, `unsure`. Claims about your own part need `mine` or `shared`.
- `counters` keep ids unique: the id of a removed fact or decision is never reused.

### Story themes (`theme`; export kind `themes`)
`{ "themes": { "<theme>": { "stories": ["<story-id>"], "questions": ["<leadership-question-id>"] } } }`. Which stories and leadership questions belong to each theme.

---

## Architecture drill cards

### Catalog (`card`; export kind `arch-catalog`)
```json
{ "dimensions": ["scale", "cost", "security"], "scenarios_note": "...", "tracks": ["aws", "acmedata"],
  "cards": [ {
      "id": "acmedata-table-store", "track": "acmedata", "kind": "service", "area": "Storage",
      "name": "Table Store", "tier": 2, "aliases": [], "members": [],
      "lifecycle": { "status": "active", "date": "2026-01-15", "note": "...", "source": "https://docs.example.com/...", "seeded": false },
      "recent_changes": [ { "date": "2026-02-01", "summary": "...", "source": "https://..." } ],
      "verified_on": "2026-11-05" } ] }
```
- `kind`: `service` (a product or feature), `pair` (a "which one and why" comparison; `members` lists the compared names), `scenario` (a design question).
- `tier`: 1 = on your resume or pinned with `profile tier1`; 2 = core; 3 = optional.
- `id`: AWS cards are unprefixed (`vpc`); other tracks use `<track>-<slug>`, `<track>-pair-...`, `<track>-scn-...`. A card without `track` counts as AWS, and a catalog without `tracks` counts as AWS enabled, so older files keep working.
- `lifecycle.status`: `active`, `maintenance` (closed to new customers, no new features), `sunset` (has an end date), `unverified`. `seeded: true` means an unverified lead, not a checked fact. `verified_on` is set only by `arch refresh`.
- Facts (`lifecycle`, `recent_changes`) are recorded only with a `source` URL on the card's track hosts. The catalog and progress are separate files, so refreshing facts never touches your progress.

### Progress (`card_progress`; export kind `arch-progress`)
`{ "cards": { "<card-id>": { "confidence": 0, "notes": "", "last_drilled": null, "links": { "<company-id>": ["<bullet-id>"] } } } }`. `confidence`: 0 not drilled, 1 some gaps, 2 solid. `links` are the resume bullets that mention the card.

### Track seed (`track`; export kind `arch-tracks`)
```json
{ "name": "acmedata", "label": "Acme Data", "source_hosts": ["docs.example.com"],
  "services": [ { "area": "Storage", "name": "Table Store", "tier": 2, "aliases": ["Store"] } ],
  "pairs": [ { "topic": "Table format", "name": "Format A vs Format B", "members": ["Format A", "Format B"] } ],
  "scenarios": ["Design a lakehouse for 50 TB/day of events"],
  "dimensions": ["scale", "cost"] }
```
Added with `arch track add NAME --seed FILE|-`, which validates it. The seed holds topic names and the documentation hosts only, never facts. `source_hosts` are bare host names, not URLs. `tier` is 2 or 3. `name` is 2-31 lower-case letters, digits or `-`, and not `aws`. The AWS seed is built in (`interview/aws/arch_seed.py`) and has no file.

---

## Leadership

### Questions (`lead_question`; export kind `lead-questions`): `{ "questions": [ { "id": "team-scope", "category": "Scope and facts", "question": "...", "themes": ["team-leadership"] } ] }`
Generic questions every user gets; `lead init` keeps themes that appear in your own resume data.

### Your answers (`lead_progress`; export kind `lead-progress`)
```json
{ "questions": { "team-scope": { "confidence": 1, "principle": "how I handle this", "notes": "", "last_drilled": "2026-11-05",
    "examples": { "<company-id>": { "situation": "...", "task": "...", "action": "...", "result": "...", "metric": "..." } } } } }
```
One STAR example per employer, for the three most recent employers.

### Scope facts (`lead_company_fact`; export kind `lead-scope`)
`{ "companies": { "<company-id>": { "title": null, "direct_reports": null, "indirect_team": null, "team_composition": null, "budget": null, "stakeholders": null, "reporting_to": null, "cadence": null, "notes": null } } }`. Factual scope such as team sizes. Values come from you, never guessed.

---

## Sessions

`sessions list` is a query over the `session` table, with the number of distinct items logged and queued per session.

### One session (`session`, `session_item`, `session_log`; export kind `sessions`; id is `<date>-<slug>`)
```json
{ "id": "2026-11-05-lambda-drill", "title": "Lambda drill", "mode": "architecture", "topic": "architecture",
  "status": "open", "created": "<timestamp>", "updated": "<timestamp>", "jd": null,
  "queue": [ { "id": "lambda", "kind": "card" } ],
  "log": [ { "at": "<timestamp>", "item": "lambda", "kind": "card", "question": "...", "answer": "your full answer",
             "grade": "solid", "confidence_after": 2, "tutor": false, "quiz": false } ] }
```
- `mode`: `architecture`, `stories`, `jd`, `leadership`, `tutor`. `status`: `open` or `closed`. `topic` is set for tutor sessions.
- `kind` is `card` (architecture), `story` or `leader` (leadership question).
- `queue` is what to ask; `log` is append-only and keeps your complete answers. A later drill adds an entry and never edits an earlier one.
- The database refuses to change or delete a logged entry. `readiness` counts only entries with a non-empty `answer`. A tutor lesson (`tutor: true`) counts only when `quiz: true`.

---

## Outside the database

| Where | Meaning |
|---|---|
| `profile/header.md` | The name and contact line printed at the top of built resumes. Contact details live only here. |
| `output/` | Raw extracted resume text (`process-resumes`) and built resumes (`build-resume`). |
| `backup/` | `jobkit backup` copies and the `json-<timestamp>/` copy of the old JSON files that `jobkit migrate` makes. |
