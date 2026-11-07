# resumes/data-model Specification

## Purpose
Define how parsed resumes are merged into the generated resume data (stored in the database), and how the user's curation survives rebuilds. Implemented in `src/jobkit/resumes/process_resumes.py` and `resume_data.py`.

## Requirements

### Requirement: Bullet identity
The system SHALL give each bullet an id that is a short hash of its normalized text.

#### Scenario: Same bullet in two resumes
- **WHEN** identical text appears in two resumes
- **THEN** one bullet exists and both resumes are listed in its `sources`

### Requirement: Near-duplicates become variants
The system SHALL treat bullets with a similarity ratio of at least 0.92 as variants of one bullet, and SHALL keep materially different claims as separate bullets. Two bullets that state different numbers are different claims, however similar the wording.

#### Scenario: Slight rewording
- **WHEN** two bullets differ by one word
- **THEN** the second is stored as a variant of the first

#### Scenario: Same sentence, different figure
- **WHEN** two bullets are identical except for one number (40% and 90%)
- **THEN** they are two bullets, each with its own sources

### Requirement: Rebuild keeps only what the remaining files say
When a resume file is deleted or changed, each bullet it contributed to SHALL be rebuilt from the wording of the files that remain: its text, figures and variants SHALL NOT keep anything only the removed file said, and a bullet no remaining file supports SHALL be removed. Each bullet SHALL record per source file the wording that file used.

#### Scenario: Canonical file deleted
- **WHEN** a bullet's text came from `a.txt`, `b.txt` words it slightly differently, and `a.txt` is deleted
- **THEN** the bullet's text and figures are those of `b.txt`, and its only source is `b.txt`

#### Scenario: Shared wording
- **WHEN** both files say the same sentence and one is deleted
- **THEN** the text is unchanged and the other file is its source

#### Scenario: Older data
- **WHEN** a stored bullet merged from several files has no per-file wording
- **THEN** the next run rebuilds the data once from the resume files, keeping curation

### Requirement: Rebuilds are incremental
The system SHALL re-process only new or changed resume files, using the ledger, unless `--force` is given.

#### Scenario: Unchanged file
- **WHEN** the tool runs again with no file changes
- **THEN** no resume is re-parsed

### Requirement: Survey writes nothing
The system SHALL show what each resume parses into with `--survey` and SHALL NOT change any stored data or write any file in that mode.

#### Scenario: Survey run
- **WHEN** `--survey` is used
- **THEN** the database and `output/` are unchanged

### Requirement: One job is one role
The system SHALL keep one role per job: roles of one employer with the same start date and the same end date are one role, and so are two with the same start date where one resume says `Present` and another gives an end date. The end date of the role SHALL be the latest real end date any resume gives, and `Present` (no end date) only when none gives one; removing a resume SHALL restore the end date the remaining resumes give. Roles with the same start date and different real end dates stay separate.

#### Scenario: Older resume still says Present
- **WHEN** one resume lists a job as `03/2021 - Present` and another lists it as `03/2021 - 06/2022`
- **THEN** one role exists, ending 2022-06, and it is not shown as current

#### Scenario: The resume with the end date is deleted
- **WHEN** that second resume is deleted
- **THEN** the role has no end date again

### Requirement: Hand curation survives rebuilds
The system SHALL keep curation (certifications, skill merge/drop/group, tag-only skills, extra skills, known-wrong metrics, bullet themes, ignored fragments and summary angles) in the database, apply it after every rebuild, and never overwrite it. Curation SHALL be changed only with commands that list, add and remove its entries.

#### Scenario: Known-wrong metric
- **WHEN** a bullet contains a figure listed as known-wrong
- **THEN** the bullet is flagged `needs_review`

#### Scenario: Add and remove curation
- **WHEN** a curation entry is added and then removed with the curation commands
- **THEN** it is applied on the next rebuild while present and has no effect after removal, without `--force`

#### Scenario: Curation changed since the last build
- **WHEN** the curation differs from the one the stored data was built with
- **THEN** the next run rebuilds the data from the resume files, with the curation applied, and says so; a run with unchanged curation does not rebuild

### Requirement: Quality words are tags, not skills
The system SHALL treat Security, Performance, Scalability, High Availability and Cost Efficiency as bullet tags only.

#### Scenario: Skills list
- **WHEN** the skills file is built
- **THEN** none of those words appears as a skill

### Requirement: Resume folders are read-only
The system SHALL NOT write into the resume folders; it SHALL write only to the database and to `output/` under the home folder.

#### Scenario: Full run
- **WHEN** processing completes
- **THEN** no file under the resume folders has changed

### Requirement: Rebuild removes what a missing or changed file contributed
On each rebuild the system SHALL remove a resume file's contribution from the resume data when that file no longer exists or has changed, and SHALL then merge it again if it still exists. Bullets, roles, role titles, subtitles and clients, summaries, headlines, profile points, education, certifications, projects and skills left with no source SHALL be removed, together with the file's ledger, unparsed and raw-text entries. Skills whose source is `curated` SHALL be kept. Skill alternative spellings are not tracked per file. Data stored before sources were tracked SHALL be rebuilt once from the resume files.

#### Scenario: Deleted resume
- **WHEN** a resume file is deleted and the data is rebuilt
- **THEN** bullets that only that file supplied are gone and bullets shared with other resumes stay with one source fewer

#### Scenario: Renamed resume
- **WHEN** a resume file is renamed and the data is rebuilt
- **THEN** its bullets appear once, under the new name only

#### Scenario: Edited resume drops a bullet
- **WHEN** a resume is edited to remove a bullet and the data is rebuilt
- **THEN** that bullet no longer appears if no other resume has it

### Requirement: Pruning reports what it removed
The system SHALL print the files whose contribution was removed and how many bullets were dropped, and SHALL NOT prune when the scan finds no resume files.

#### Scenario: Resume folder unavailable
- **WHEN** the resume folder is empty or unmounted
- **THEN** the system reports an error and the existing data is unchanged

### Requirement: Orphaned curation is reported
The system SHALL list curation entries (themes, ignored fragments, summary angles) whose id matches no current bullet or summary, in `review` output and as a warning at the end of a rebuild. Reporting SHALL NOT modify any curation entry.

#### Scenario: Bullet text changed
- **WHEN** a bullet's text changes so that its id changes
- **THEN** its old id is listed as orphaned and the curation entry is unchanged

#### Scenario: No orphans
- **WHEN** every curation id matches a current bullet or summary
- **THEN** the report says none were found
