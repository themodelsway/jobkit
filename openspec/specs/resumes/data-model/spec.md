# resumes/data-model Specification

## Purpose
Define how parsed resumes are merged into the generated resume data in `resume-data/json/`, and how hand curation survives rebuilds. Implemented in `src/jobkit/resumes/process_resumes.py` and `resume_data.py`.

## Requirements

### Requirement: Bullet identity
The system SHALL give each bullet an id that is a short hash of its normalized text.

#### Scenario: Same bullet in two resumes
- **WHEN** identical text appears in two resumes
- **THEN** one bullet exists and both resumes are listed in its `sources`

### Requirement: Near-duplicates become variants
The system SHALL treat bullets with a similarity ratio of at least 0.92 as variants of one bullet, and SHALL keep materially different claims as separate bullets.

#### Scenario: Slight rewording
- **WHEN** two bullets differ by one word
- **THEN** the second is stored as a variant of the first

### Requirement: Rebuilds are incremental
The system SHALL re-process only new or changed resume files, using the ledger, unless `--force` is given.

#### Scenario: Unchanged file
- **WHEN** the tool runs again with no file changes
- **THEN** no resume is re-parsed

### Requirement: Survey writes nothing
The system SHALL show what each resume parses into with `--survey` and SHALL NOT write any file in that mode.

#### Scenario: Survey run
- **WHEN** `--survey` is used
- **THEN** `resume-data/` is unchanged

### Requirement: Hand curation survives rebuilds
The system SHALL apply `resume-data/curated.json` (certifications, skill merge/drop/group, tag-only skills, extra skills, known-wrong metrics) and `resume-data/themes.json` after every rebuild without overwriting them.

#### Scenario: Known-wrong metric
- **WHEN** a bullet contains a figure listed in `review_if_metric_matches`
- **THEN** the bullet is flagged `needs_review`

### Requirement: Quality words are tags, not skills
The system SHALL treat Security, Performance, Scalability, High Availability and Cost Efficiency as bullet tags only.

#### Scenario: Skills list
- **WHEN** the skills file is built
- **THEN** none of those words appears as a skill

### Requirement: Resume folders are read-only
The system SHALL NOT write into the resume folders; it SHALL write only under `resume-data/json/` and `output/`.

#### Scenario: Full run
- **WHEN** processing completes
- **THEN** no file under the resume folders has changed

### Requirement: Rebuild removes what a missing or changed file contributed
On each rebuild the system SHALL remove a resume file's contribution from the resume data when that file no longer exists or has changed, and SHALL then merge it again if it still exists. Bullets, roles, summaries and skills left with no source SHALL be removed, together with the file's ledger, unparsed and raw-text entries. Skills whose source is `curated` SHALL be kept.

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
The system SHALL list curation entries (themes, ignored fragments, summary angles) whose id matches no current bullet or summary, in `review` output and as a warning at the end of a rebuild. Reporting SHALL NOT modify any curation file.

#### Scenario: Bullet text changed
- **WHEN** a bullet's text changes so that its id changes
- **THEN** its old id is listed as orphaned and the curation file is unchanged

#### Scenario: No orphans
- **WHEN** every curation id matches a current bullet or summary
- **THEN** the report says none were found
