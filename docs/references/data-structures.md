# jobkit data structures

All of jobkit's data is in one SQLite database under the home folder, which is outside the repository, so nothing personal is committed. This page describes the tables, the shape of each record and which command writes it. Examples use made-up values. The commands are in [manual.md](../manual.md).

Rules that hold for all data:

- Dates are `YYYY-MM-DD`, month values `YYYY-MM`, timestamps ISO 8601.
- The data is changed only by the commands, never by hand. To look at it, run `jobkit export` (JSON or Markdown). Each kind of data below names its export kind.
- A command's changes are stored together or not at all; several commands can run at once.
- Types are the `TypedDict`s in the code. `?` marks an optional field.

| Where | Holds | Written by |
|---|---|---|
| the database (`data/jobkit.db`) | settings, resume data, curation, stories, drill cards, leadership answers, sessions | `profile`, `process-resumes`, `prep`, `arch`, `lead`, `sessions` |
| `header` setting | your name and contact line for built resumes (saved with `profile header set`) | you |
| `output/` | raw extracted text and built resumes | `process-resumes`, `build-resume` |
| `backup/` | database backups | `jobkit backup` |

---

## The database (`~/.jobkit/data/jobkit.db`)

All data lives in one SQLite database under the home folder (`~/.jobkit`, or `.jobkit` in your user folder on Windows, or `JOBKIT_HOME`). It is changed only by the commands, and you look at it with `jobkit export`. Each command's changes are stored together or not at all.

A record table keeps the record as JSON in `body`. A field is a real column only when SQL needs it (a key, a link, a sort or filter, a listing); every other field is in `body` only, and a field that is a column is not repeated in `body`. So each field has one stored value, and every command that shows it shows the same value. The one exception is `session_log`, whose entries can never be changed, so its copies cannot disagree. The shapes below are what `jobkit export` shows, with the column fields and `body` joined. Confidence is checked when written: only 0, 1 or 2 is stored. The schema version is in `PRAGMA user_version`; `jobkit status` shows it. Step 13 added the `target_company` and `target_fact` tables and two log columns. Step 12 added the `term` table. Step 11 moved every field to one place and removed the `bullet_source` table; an upgrade checks that the copies agree first, and stops without changing anything if they do not.

| Table | One row is | Notes |
|---|---|---|
| `meta` | a named setting or document header | The catalog's `tracks` (and a `dimensions` list left by older versions, no longer read), the stories and engagements `schema_version`. |
| `session` | a practice session | Columns: `id`, `title`, `mode`, `status`, `created`, `updated` (the listing reads them). The creation time never changes. `body` holds the rest (`topic`, `jd`). |
| `session_item` | one queued item of a session | `session_id`, `position`, `item`, `kind` (`card`, `story`, `leader`); no `body`. A new entry must name an item that exists. If the item is removed later the entry stays and is shown as unavailable. |
| `match_result` | one finished match score | Added by schema step 10. Columns: `key`, `created`, `last_used`; `body` holds the whole result, including `label`, `band` and the scores, which the listing reads from it (see Match scores). Entries not used for 90 days are removed when `match-score run` finishes. |
| `session_log` | one logged answer | **Append-only**: the database refuses updates and deletes. `answered` is 1 when the answer is not empty; `tutor` and `quiz` mark lessons and passed quizzes. `readiness` is computed from these rows. Step 13 added the nullable `style` and `company` columns, which are empty for entries logged before it and for card entries. |
| `target_company` | a researched company | Added by schema step 13. Columns: `key` (the name in lower case, so names compare without regard to letter case), `name`, `outcome` (`found` or `none found`), `researched` (the date), `style` and `style_basis` (the suggested answer style and whether it is `stated` or `inferred`); `body` has `style_facts`, the ids of the facts the suggestion rests on. Removing a company removes its facts. |
| `target_fact` | one researched fact about a company | `company_key`, `id`, `position`, `kind` (`value`, `round`, `grading`, `question`, `questioning`), `link`, `label` (`company-references` or `othersite-references`), `pulled` (the date the page was read), `vetted` (1 once the agent confirmed it); `body` has `wording`, `quote` and, for a value, `name`, `themes` and `hints`; a typical question may name its value in `value`. |
| `card` | an architecture card (service, decision pair or scenario) | Columns: `id`, `position`; `body` has `track`, `kind`, `area`, `name`, `tier`, `aliases`, `members`, `lifecycle`, `recent_changes`, `verified_on`. |
| `card_progress` | your progress on one card | `card_id` (must be a card); `body` has `confidence` (0 to 2), `last_drilled`, `notes` and `links` to resume bullets. Removing a card removes its progress. |
| `track` | a custom technology track | `name`; `body` is the seed (services, pairs, scenarios, documentation hosts). |
| `engagement` | a real project | Columns: `id`, `position`; `body` has `company`, `title`, `updated`, `my_role`, `period`, `summary`, `notes`, `counters`. |
| `fact` | a fact about an engagement | `engagement_id`, `id` (`f1`, `f2`, ...; an id is never reused), `position`; `body` has `basis`, `text`, `source`, `note`, `added`. |
| `decision` | a decision on an engagement | `engagement_id`, `id` (`d1`, ...), `position`; `body` has `ownership`, `what`, `why`, `alternatives`, `tradeoffs`. |
| `person` | a person on an engagement | `engagement_id`, `position`; `body` has `role`, `note`. |
| `story` | a STAR story | Columns: `id`, `position`, `engagement_id` (the link to its engagement, shown as `engagement`; must be an engagement, checked when the change is committed); `body` is the rest of the story, including `company`, `theme`, `status`, `updated`. |
| `theme` | a story theme | `name`; `body` lists its stories and leadership questions. |
| `lead_question` | a leadership question | `id`, `position`; `body` has `category`, `question` and `themes`. |
| `lead_progress` | your answer to one question | `question_id` (must be a question); `body` has `confidence` (0 to 2), `last_drilled`, `principle`, `notes` and one STAR `examples` entry per company. |
| `lead_company_fact` | factual scope for one employer | `company_id`; `body` has team sizes, budget and similar facts you stated. |
| `setting` | one profile setting | `key` (`resume_root`, `resume_dirs`, `name`, `tier1_services`, `reassess_days`) and its JSON `value`. |
| `employer` | an employer found in the resumes | `id`, `position`; `body` has `name`, the match `regex` and, after a merge, `aliases`. Changed with `profile companies rename` and `merge`. |
| `term` | a personal word that must never be committed | `text` (unique, any letter case), `kind`, `match` (`word`, `phrase`, `regex`), `ignored` (1 hides a derived term of that text). Only what has no other home is stored: products, clients, patterns and ignores. Your name, header contact details, resume folder and employer names are read from the `setting` and `employer` tables when checking. |
| `open_item` | an open item or data note | `id`; `body` has `status` (`open`, `done`) and `text`. |
| `company` | an employer in the resume data | `id`, `position`; `body` has `name`, `aliases`. Removing a company removes its roles and bullets. |
| `role` | one period at a company | `company_id`, `position`; `body` has `start`, `end`, `titles`, `subtitles`, `clients`, `sources`. |
| `bullet` | one experience bullet, deduplicated across resumes | `company_id`, `id` (hash of the text), `position`; `body` has `needs_review`, `text`, `skills`, `themes`, `metrics`, `variants`, `wordings`, `ignored`. |
| `skill` | a skill in a group | `group_name`, `position`; `body` has `name`, `aliases` and `sources`. |
| `resume_item` | one entry of the resume's own sections | `section` (`summaries`, `profile_points`, `education`, `certifications`, `projects`, `headlines`, `item_sources`), `position`; `body` is the entry. `item_sources` entries are `{section, text, sources}`: the resume files that state each item, so a deleted resume takes its items out. No contact details are stored. |
| `ledger` | a resume file that was read | `file`; `body` has `kind` (`resume` or `other`), `mtime`, `size`, `sha256`, `processed_at`. |
| `unparsed` | why a file could not be read | `file`; `body` is the list of problems. |
| `curation` | one curation entry | `file` (`curated` or `themes`), `kind` (the key in that file), `key`, `position`; `body` is the entry. Not linked to bullets: a bullet id changes on a rebuild only when its claim really changes, and such entries are reported as orphaned. Changed only with `process-resumes curate`. |

The sections below describe the record shapes as `jobkit export` shows them (and as `body` holds them).

---

## Settings, employers and open items

### Settings (`setting`; export kind `settings`)
```json
{ "resume_root": "/path/to/resumes", "resume_dirs": ["2026"], "name": "Your Name", "tier1_services": ["Lambda"] }
```
`resume_root` is read-only for all tools. `resume_dirs` limits the scan to subfolders. `tier1_services` pins your own tier-1 drill topics (any track, matched by name). `reassess_days`, `years_experience`, `answer_style`, `research_days` and `target_company` are set with `profile set` (see the manual); `target_company` holds the name of a researched company. Code: `user/profile.py`.

### Employers (`employer`; export kind `employers`)
`{ "<company-id>": { "name": "Acme Corp", "regex": "Acme( Corp)?" } }`. Employers found on the first scan. The regex must match a whole header line. Change employers with `profile companies rename` and `merge`.

### `header` (a setting)
Name and contact line printed at the top of built resumes, saved with `profile header set NAME CONTACT_LINE` and shown with `profile header`. Contact details live only here, never in the resume data. An older `profile/header.md` file is still read when no header is saved.

### Personal terms (`term`; export kind `terms`)
`[ { "text": "acme.ai", "kind": "product", "match": "phrase", "ignored": 0 } ]`. Managed with `profile terms`; see the [manual](../manual.md#for-contributors-keeping-personal-data-out-of-commits).

### Open items (`open_item`; export kind `open-items`)
`[ { "id": 1, "text": "Confirm team size", "status": "open" } ]`. Status is `open` or `done`.

---

## Resume data (generated by `process-resumes`)

How resume text becomes data: each resume is split by employer, bullets are merged across resumes, and every item keeps the resume files it came from (`sources`).

### One employer (`company`, `role`, `bullet`; export kind `resume-companies`)
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
- `roles[].end` is `null` for the current role. When resumes disagree (one says Present, another gives an end date), the latest real end date wins and the role is one role. `titles`, `subtitles` and `clients` collect every spelling seen; `ends` (end date per resume file) and `field_sources` (the files that state each title, subtitle and client) let a deleted resume take only its own out.
- Bullet `id` is a short hash of the normalised text (prefixed by the company) when the bullet is first stored. A bullet keeps its stored id on every later run, including a full rebuild, while it continues: it shares a wording with the stored bullet, or is at least 92% similar to it with the same numbers. So a resume that sorts earlier, or the deletion of the file that first stated the bullet, does not change the id or lose its themes; a bullet whose claim really changed gets a new id and its old curation is reported as orphaned. The same wording in several resumes keeps one bullet with more `sources`. Wording at least 92% similar becomes a `variants` entry, unless the numbers differ: then it is a separate bullet. `wordings` records, per source file, the wording that file used. When a file is deleted or edited, the bullet is rebuilt from the files that remain: its text and figures follow a remaining file's wording, and a bullet no file supports is dropped. Data from before `wordings` existed is rebuilt once automatically when a bullet merged from several files cannot be traced.
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
- Answer styles are views of these fields and are never stored: Obstacle (SOAR) is `task`, Challenge (CARL) is `situation` followed by `task`, and Learning (CARL) is `lessons`. Saving a challenge writes `situation`, and with `--merge` empties `task`. A story marked `done` stays valid while it is complete in any of the three styles. See [Answer styles](../guides/interview-prep.md#answer-styles).
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
- `facts[].basis`: `stated`, `estimate`, `unsure`, `verified-doc` (needs `source`), `proposed` (an agent suggestion, never your claim). Only `stated`, `estimate` and `verified-doc` may back a story.
- `decisions[].ownership`: `mine`, `team`, `client`, `shared`, `unsure`. Claims about your own part need `mine` or `shared`.
- `counters` keep ids unique: the id of a removed fact or decision is never reused.

### Story themes (`theme`; export kind `themes`)
`{ "themes": { "<theme>": { "stories": ["<story-id>"], "questions": ["<leadership-question-id>"] } } }`. Which stories and leadership questions belong to each theme.

---

## Knowledge drill cards

### Catalog (`card`; export kind `arch-catalog`)
```json
{ "scenarios_note": "...", "tracks": ["aws", "acmedata"],
  "cards": [ {
      "id": "acmedata-table-store", "track": "acmedata", "kind": "service", "area": "Storage",
      "name": "Table Store", "tier": 2, "aliases": [], "members": [],
      "lifecycle": { "status": "active", "date": "2026-01-15", "note": "...", "source": "https://docs.example.com/...", "seeded": false },
      "recent_changes": [ { "date": "2026-02-01", "summary": "...", "source": "https://..." } ],
      "verified_on": "2026-11-05" } ] }
```
- `kind`: `service` (any topic: a product, feature, concept or method), `pair` (a "which one and why" comparison; `members` lists the compared names), `scenario` (a design or situational question), `case` (a question developed over several turns; `situation` holds the opening), `role-play` (the agent plays `part` while the user pursues `goal`).
- `tier`: 1 = on your resume or pinned with `profile tier1`; 2 = core; 3 = optional.
- `id`: AWS cards are unprefixed (`vpc`); other tracks use `<track>-<slug>`, `<track>-pair-...`, `<track>-scn-...`, `<track>-case-...`, `<track>-role-...`. A card without `track` counts as AWS, and a catalog without `tracks` counts as AWS enabled, so older files keep working.
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
  "family": "engineering", "dimensions": ["scale", "cost"], "country": "United Kingdom",
  "cases": [ { "title": "Pipeline is late", "situation": "The nightly load now finishes at 9am. Find out why.", "area": "Operations" } ],
  "role_plays": [ { "title": "Explain a cost overrun", "part": "a finance lead who wants the bill cut", "goal": "agree what to change first" } ] }
```
Added with `arch track add NAME --seed FILE|-`, which validates it. The seed holds topic names and the source hosts only, never facts. `source_hosts` are bare host names, not URLs. `tier` is 2 or 3. `name` is 2-31 lower-case letters, digits or `-`, and not `aws`. Every list is optional, but the seed needs at least one card of some kind. `family` is one of the role families `arch families` lists (`engineering` when missing). `dimensions` is the rubric, at most 12 lines (a track stored by an earlier version keeps a longer rubric); without it the family's default rubric is used. Two cards may not get the same id: an id is the track, a kind marker (none for services, `pair-`, `scn-`, `case-`, `role-`) and the slug of the name, so a service "Role conflict" and a role-play "Conflict" clash and the seed is refused. `country` (at most 60 characters) is for knowledge that differs by country. Each case needs `title` and `situation`, each role-play `title`, `part` and `goal`; `area` defaults to `Cases` or `Role-plays`. The AWS seed is built in (`interview/aws/arch_seed.py`), has no file, and keeps its own rubric.

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
  "status": "open", "created": "<timestamp>", "updated": "<timestamp>", "jd": null, "target": null, "style": "star",
  "queue": [ { "id": "lambda", "kind": "card" } ],
  "log": [ { "at": "<timestamp>", "item": "lambda", "kind": "card", "question": "...", "answer": "your full answer",
             "grade": "solid", "confidence_after": 2, "tutor": false, "quiz": false } ] }
```
- `target` is the name of the researched company the session was started for (`sessions new --target`), or `null`; it stays when the company's profile is later removed. `style` is the session's current answer style (`sessions resume --style` changes it). Sessions stored before these fields existed have neither.
- A story or leadership answer also records `style` and `company`: the style in force when it was logged (`sessions log --style` for one answer) and the session's company. Card answers, and entries logged before step 13, have neither.
- `mode`: `architecture`, `stories`, `jd`, `leadership`, `tutor`, `retest` (`sessions new --due` with no mode: due cards, questions and stories). `status`: `open` or `closed`. `topic` is set for tutor sessions.
- `kind` is `card` (architecture), `story` or `leader` (leadership question).
- `queue` is what to ask; `log` is append-only and keeps your complete answers. A later drill adds an entry and never edits an earlier one.
- The database refuses to change or delete a logged entry. `readiness` counts only entries with a non-empty `answer`. A tutor lesson (`tutor: true`) counts only when `quiz: true`.

---

## Researched companies (`target_company`, `target_fact`; export kind `research`)

Written only by `target save`, `target none-found`, `target recheck` and `target remove`; read by `target`, `prep for-target`, `lead --target`, `readiness --target` and `sessions --target`. Nothing about a company is shipped. The export is `{"companies": [...]}`, one entry per company with its facts:

```json
{ "key": "company x", "name": "Company X", "outcome": "found", "researched": "2026-11-14",
  "style": "star", "style_basis": "stated", "style_facts": ["g1"],
  "facts": [
    { "id": "v1", "kind": "value", "name": "Ownership", "wording": "Owns outcomes end to end.",
      "quote": "A short passage copied word for word from the page.", "link": "https://...",
      "label": "company-references", "pulled": "2026-11-14", "vetted": true,
      "themes": ["team-leadership"], "hints": ["deadline"] },
    { "id": "q1", "kind": "question", "value": "v1", "wording": "Tell me about a time you owned a failure.",
      "quote": "...", "link": "https://...", "label": "othersite-references", "pulled": "2026-11-14", "vetted": true },
    { "id": "g1", "kind": "grading", "wording": "Answers are scored as situation, task, action and result.",
      "quote": "...", "link": "https://...", "label": "company-references", "pulled": "2026-11-14", "vetted": true } ] }
```
- `outcome`: `found`, or `none found` (no qualifying page; no facts, dated by `researched`).
- `kind`: `value` (with a `name`), `round`, `grading` (what interviewers look for), `question` (a typical question; `value` names the value it belongs to) or `questioning` (questioning style).
- `label`: `company-references` when the link is on a site the company publishes, `othersite-references` for any other site.
- `vetted`: the agent's confirmation, required on every save, that it read the page, the quote is on it and the page is not written by individual users. The commands cannot check this; they refuse a save without it, a quote over 40 words, a link that is not http or https, a link on a known user-content site, a date read in the future, and a question naming a value the company does not have.
- `themes` and `hints`: the mapping from a value to the user's stories (story themes, and words matched as whole words in any letter case); not claims about the company.
- `style`, `style_basis` and `style_facts`: a suggested answer style, `stated` (a stored fact says it) or `inferred` (the agent's suggestion), with the ids of the facts it rests on. It never changes the style in force.
- State: `fresh` (every fact read within `research_days`), `stale` (a fact older, or a none-found record older), `none found` or `not researched`.
- A save adds facts or replaces them by id and keeps the others; it is all or nothing. `target recheck` sets a fact's `pulled` to today, or removes it with `--remove` (with the questions under a removed value).

---

## Preparation planner (`jk.interview.prep_plan`, not yet used by any command)

A pure function over plain records: `plan(snapshot, today, focus=(), reassess_days=30)` returns ordered, explained actions. It reads no database; the caller builds the `Snapshot`. The date is passed in, so the same input gives the same plan.

- `Competency`: `id`, `name`, `kind` (`technical`, `leadership`, `general`), `aliases`, `requires` (prerequisites), `related`. Aliases resolve to one competency; related competencies (ECS and Kubernetes) are never merged. `check_vocabulary` rejects a prerequisite loop, an alias with two targets and a reference to nothing. `SEED` is a small neutral list.
- `Fact` (engagement, fact id, competencies, `status` confirmed/proposed/unsure, `ownership` own/team/unclear), `Story` (engagement, competencies, done, ownership, facts), `Attempt` (competency, day, `kind` drill/quiz/lesson, `grade` 0 weak, 1 some gaps, 2 good), `Lead` (competency, `ref` of a stored resume line). A lead is a hint for a question, never evidence: it is not a fact and counts as no experience. The caller leaves out lines that are flagged, ignored or not demonstrated for that skill (`evidence.lead_lines`).
- Three kinds of evidence stay apart: experience (confirmed, own facts and stories, counted by distinct engagement), knowledge (a passed quiz or a good drill answer) and performance (graded drill answers). A quiz never creates experience, and a self-rating is never turned into a grade.
- `Action`: `competency`, `type` (`clarify_fact`, `teach_prerequisite`, `practise_concept`, `rehearse_story`, `reassess`), `reason_code`, `reason`, `evidence` and `observations` (`story:ID`, `fact:ENGAGEMENT/ID`, `attempt:ID`), plus `target`, `age_days`, `choices` (other stories on the same engagement), `transferable`, `self_rated` and `leads` (line references, for `profile_gap` only) where they apply. Reason codes: `fact_unconfirmed`, `ownership_unclear` (category 1), `prerequisite_unmet` (2), `profile_gap`, `untested`, `untested_with_story` (3), `weak`, `weak_with_story` (4), `answer_old` (5). `profile_gap` means nothing is recorded yet that shows the person used the competency (no confirmed fact or story, no graded drill, whatever a quiz showed); it asks for an example and never says the person has no experience. `untested` means experience is recorded but no drill is graded yet.
- Order: factual blocker, unmet prerequisite, untested (`profile_gap` before plain `untested`), observed weakness, due reassessment. Within a group, focused competencies first, then by id.
- Knowledge never expires: a quiz passed long ago still counts. An old good answer only gives a `reassess` action.
- `reassess_days` (the window the caller passes as `reassess_days`): a profile setting stored in the `setting` table, a whole number of days from 1 to 365, default 30 when unset. `profile.reassess_days()` returns it; `readiness`, the `sessions` queue and the caller of `plan` all read it, and `--days N` overrides it for one run.

---

## Match scores (`match-score`)

A match score rates how well your stored resume lines cover one job posting. It is **not** any employer's applicant tracking system score and does not predict a hiring decision; every report says so. The agent (Claude Code or Codex, through the model it uses) splits the posting into requirements and rates each against your lines (pass 1); `match-score` checks that input and does only arithmetic. Every number below is a **placeholder default** that will be tuned on real postings; they are versioned (`RUBRIC_VERSION`, `WEIGHTS_VERSION` in `match_engine.py`) and a change retires stored results.

### Request (pass 1 output, a JSON file or `-`)

```json
{
  "schema_version": 1,
  "band": "executive",
  "band_reason": "Leads several teams and owns a budget.",
  "band_alternatives": ["senior-executive"],
  "label": "Director of Engineering at Example Co",
  "requirements": [
    {
      "id": "r4", "label": "Lead a large organisation",
      "quote": "Lead an organisation of 50+ with managers reporting to you.",
      "section": "Responsibilities",
      "category": "people_leadership", "priority": "required", "importance": 1.0,
      "level": "partial", "confidence": 0.7, "reason": "Leads 12 people, no managers of managers.",
      "evidence": ["bullet:3f9a1c0d2e"], "related": "",
      "flag": { "kind": "level", "readings": ["partial", "substantial"] }
    }
  ]
}
```

- `category`: `core_skills`, `impact`, `functional_leadership` (technical or functional leadership), `people_leadership`, `strategy` (strategy, budget and influence), `domain`, `education` (education and certifications).
- `priority`: `critical` (weight 3), `required` (2), `preferred` (1), times the optional `importance` (a number above 0, default 1).
- `level`: `full` (credit 1.00), `substantial` (0.75), `partial` (0.40), `profile_miss` (0.00, shown to you as "not shown in your profile yet") or `unknown` (counts 0 in the lower score and 1 in the upper).
- `evidence`: required for `full`, `substantial` and `partial`; not allowed for `profile_miss` and `unknown` (use `related` for an adjacent experience that earns no credit). A reference is `bullet:BULLET_ID` (or `bullet:COMPANY_ID:BULLET_ID` when two companies have a line with that id), `skill:NAME`, `education:N` (1 is the first education line), `certification:NAME` or `role:COMPANY_ID`.
- `confidence` (0 to 1) is shown and never changes a score.
- `flag` is optional and only for a real conflict: two defensible `level`s, two `category` values, or two `priority` values the fixed rules do not settle. The command picks the fallback (the lower level; the category of the posting section, else the first in the order skills, impact, technical or functional leadership, people leadership, strategy, domain, education; the lower priority) and keeps the other reading for the upper score.
- `band_alternatives` lists higher bands the posting could also fit; the lowest one named (with `band`) is used.
- A degree that names a field is rated on the whole field (full), a related field from a short stored list (substantial), or neither (partial); one shared word such as "Science" is not a match.
- A requirement whose `id` is one `match-score extract` returned (`code:skill:...`, `code:degree:N`, or `code:degree:N:field` for a second field at the same level, `code:cert:...`, `code:years`) takes the code's level and evidence, whatever the agent wrote.
- A skill line is judged per skill: `ok`, `confirm_use` (reads like training: counts, but a skill backed only by such lines is rated at most partial) or `not_demonstrated` (a clause about that skill explicitly denies professional use: no credit; a denial about another skill in the same line does not count; a skill's aliases count as naming it; wording such as "without production downtime" is not a denial, only a denial of use or experience is). A code-rated skill item carries `set_aside`, a plain sentence with the line text for each line in either state; `check` and `run` list them under the assumptions and never ask.
- Invalid input is rejected with every problem and its path (for example `requirements[2] (r3).evidence[0]`); nothing is repaired.

### Level bands and weights

| Band | Skills | Impact | Tech./functional lead. | People lead. | Strategy | Domain | Education |
|---|---|---|---|---|---|---|---|
| `junior-ic` | .50 | .15 | 0 | 0 | 0 | .10 | .25 |
| `mid-senior-ic` | .30 | .25 | .15 | 0 | .05 | .15 | .10 |
| `mid-manager` | .15 | .25 | .10 | .25 | .10 | .10 | .05 |
| `executive` | .05 | .25 | .05 | .20 | .20 | .20 | .05 |
| `senior-executive` | 0 | .25 | 0 | .20 | .30 | .20 | .05 |

A weight of 0 means the category does not apply at that level: its requirements are listed as "noted, not counted at this level", unless the category holds a critical requirement: then the category counts at the smallest positive weight of the band, and the report names the critical requirements the profile does not show right under the score (`unmet_critical`). Weights must not be negative, must total 1 and need at least one above 0. A category with no requirements is left out and the rest are rescaled to total 1; when every category the posting has is a zero-weight one they share equally and an assumption is listed. Staff, Principal and Architect roles fall under `mid-senior-ic`. You can add named bands, or replace a built-in one, in `profile/match-bands.json` in the home folder: `{ "sales": { "core_skills": 0.4, "impact": 0.6, "functional_leadership": 0, "people_leadership": 0, "strategy": 0, "domain": 0, "education": 0 } }` (every category named, validated on every read).

### Formula

For each category in use, the category score is the sum of (weight x credit) over its requirements divided by the sum of their weights, where a requirement's weight is its priority multiplier times `importance`. The **lower score** is the sum of the rescaled band weights times the category scores, x 100, using the fallback reading of every flag and 0 for `unknown`. The **upper score** uses 1 for `unknown` and credits each flag that took a fallback at its higher reading (the reading that gives the higher lower score); it is "the result if every close call went your way", never a prediction. **Coverage** is the same sum with the weight of every requirement that is not `unknown` over the weight of all of them. Arithmetic is exact (`Decimal`); display rounds half up (the report shows whole numbers, the JSON one decimal). A **swing** is how far the lower score moves between the two readings of one flag; more than 3 swings of 2 points or more mark the posting as vague.

Worked example (executive band, one required requirement per category): skills, impact, technical leadership, domain and education are full; people leadership is partial (or substantial); strategy is substantial (or full). Lower = 5 + 25 + 5 + 8 + 15 + 20 + 5 = 83; upper = 5 + 25 + 5 + 15 + 20 + 20 + 5 = 95. This is the example in `tests/resumes/test_match_engine.py`.

### Code pass

Before pass 1, `match-score extract` rates what stored facts decide: named skills (the skills vocabulary and aliases; two or more lines showing the skill is full, one is substantial, a skills-list entry alone is partial), degree level with a keyword check of the field named (not when the posting says "or related field"), certifications you hold (the same certification at a lower level than asked is partial), and total years of experience asked without tying them to a skill (dated roles with overlaps counted once; 100% of the asked years is full, 75% substantial, 40% partial, else `profile_miss`). Years tied to one skill ("5 years of AWS") and certifications you do not hold stay with pass 1.

### Result (`match_result`; export kind `match-results`)

`{ "key", "label", "band", "band_reason", "rubric_version", "weights_version", "score": { "lower", "upper", "coverage", "categories": { name: { "score", "upper", "coverage", "weight" } }, "left_out", "not_counted", "equal_weights", "gaps": { "critical", "required", "preferred", "unassessed" }, "requirements": [...] }, "requirements": [ { the request fields plus "evidence_text", "source": "agent" | "code" | "fallback", final "category", "priority", "level", "credit", "share", "counted" } ], "assumptions": [...], "vague", "priority_rules_applied", "code_pass_notes", "caveat" }`. The key is made from the normalised posting text (Unicode, line endings and whitespace), the resume lines (their text, whether each is ignored or flagged for review, and its skill tags; not ids, so a rebuild that changes no text keeps it), your skills, roles, education and certifications, the rubric and weights versions (and your bands file) and the assessment date, so years in an ongoing role are re-judged on a later day. A short suffix after it identifies the band and requirements used, so scoring the same posting again with another band or other ratings is stored next to the earlier result instead of over it (`match-score list` shows both; `extract` returns the newest). `jobkit export --only match-results` prints the stored results with their versions.

`source` says where a requirement's rating came from: `agent` (judged in pass 1 by the model used by the agent), `code` (rated by the code pass; `code, contested` when the agent gave a different level with a reason) or `fallback` (a flagged requirement settled by the fixed cautious rule). It records no specific agent product or model name. Results stored before version 0.2.0 hold `claude` where new ones hold `agent`; that older value means the same thing, is still read, shown and exported, and is never rewritten.

Stored results are shared by every agent that uses the same jobkit home: `match-score extract` returns a stored result for an identical request whichever agent asks, with the `source` values it was stored with. Because the key includes the assessment date, that reuse happens on the same day only.

---

## Outside the database

| Where | Meaning |
|---|---|
| `header` setting | The name and contact line printed at the top of built resumes. Contact details live only here. |
| `profile/match-bands.json` | Your own level bands for `match-score` (optional; see Match scores). |
| `output/` | Raw extracted resume text (`process-resumes`) and built resumes (`build-resume`). |
| `backup/` | `jobkit backup` copies of the database. |
