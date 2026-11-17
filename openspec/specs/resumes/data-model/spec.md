# resumes/data-model Specification

## Purpose
Define how parsed resumes are merged into the generated resume data (stored in the database), and how the user's curation survives rebuilds. Implemented in `plugins/jobkit/src/jk/resumes/process_resumes.py` and `resume_data.py`.

## Requirements

### Requirement: Bullet identity
The system SHALL give a new bullet an id that is a short hash of its normalized text. A bullet SHALL keep that id on every later run, including a full rebuild, while it continues: while the bullet built on this run shares a wording with the stored bullet, or is at least 0.92 similar to it and states the same numbers. The id SHALL NOT change because of the order the files are read in or because the file that first stated the bullet is gone.

#### Scenario: Same bullet in two resumes
- **WHEN** identical text appears in two resumes
- **THEN** one bullet exists and both resumes are listed in its `sources`

#### Scenario: A resume that sorts earlier words the bullet differently
- **WHEN** a new resume that is read first states a stored bullet in slightly different words, and the data is fully rebuilt
- **THEN** the bullet keeps its id and its themes

#### Scenario: The file that first stated the bullet is deleted
- **WHEN** that file is deleted, another file still states the bullet in slightly different words, and the data is fully rebuilt
- **THEN** the bullet keeps its id and its themes

#### Scenario: A claim that really changed
- **WHEN** a resume is edited so that a bullet states different numbers or is no longer similar
- **THEN** it is a new bullet with a new id, and curation on the old id is reported as orphaned

### Requirement: Near-duplicates become variants
The system SHALL treat bullets with a similarity ratio of at least 0.92 as variants of one bullet, and SHALL keep materially different claims as separate bullets. Two bullets that state different numbers are different claims, however similar the wording.

#### Scenario: Slight rewording
- **WHEN** two bullets differ by one word
- **THEN** the second is stored as a variant of the first

#### Scenario: Same sentence, different figure
- **WHEN** two bullets are identical except for one number (40% and 90%)
- **THEN** they are two bullets, each with its own sources

### Requirement: Every wording of a line counts as evidence
A line's text, its variants and the wording each resume file uses SHALL all count when the system decides which skills and posting requirements the line shows and which skills it is tagged with; a wording that denies professional use of a skill SHALL make the line not show that skill.

#### Scenario: Requirement shown only by an older wording
- **WHEN** a posting asks for structured interviews, the newest wording of a line says "Improved hiring for 12 teams" and an older resume's wording of the same line says "Ran structured interviews for 12 teams"
- **THEN** the line counts as showing structured interviews, the requirement is not reported as missing, and the line is tagged with that skill

#### Scenario: A denial in one wording
- **WHEN** one wording of a line names a skill and another says it was not used at work
- **THEN** the line does not count as showing that skill

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

### Requirement: A parser change rebuilds the data once
The system SHALL record the parser version the stored resume data was built with. When that version differs from the running one (or none was recorded and data or a ledger exists, so files that all failed are retried too), the next `process-resumes` run SHALL first save a copy of the database to `backup/` and then rebuild the data from the resume files once, keeping curation, and say so. Survey SHALL NOT do this.

#### Scenario: Parser upgraded
- **WHEN** the plugin is updated to a parser with a new version and `process-resumes` runs
- **THEN** a copy of the database is saved, every resume is read again, and the next run finds 0 new or changed files

### Requirement: Survey writes nothing
The system SHALL show what each resume parses into with `--survey` and SHALL NOT change any stored data or write any file in that mode. For a PDF it SHALL name the pages that were read as columns.

#### Scenario: Survey run
- **WHEN** `--survey` is used
- **THEN** the database and `output/` are unchanged

### Requirement: Dates may be a year
A role's start and end SHALL be stored as `YYYY-MM`, or as `YYYY` when the resume gives only a year. Roles with their own dates SHALL stay separate.

#### Scenario: Year-only dates
- **WHEN** a resume supplies only the years for a role
- **THEN** the dates are displayed without months and are treated as June for month arithmetic

### Requirement: One job is one role
The system SHALL keep one role per job. Roles of one employer with the same start date and the same end date are one role, and so are two with the same start date where one resume says `Present` and another gives an end date. Roles with the same start date and different real end dates stay separate.

#### Scenario: Older resume still says Present
- **WHEN** one resume lists a job as `03/2021 - Present` and another lists it as `03/2021 - 06/2022`
- **THEN** one role exists, ending 2022-06, and it is not shown as current

#### Scenario: The resume with the end date is deleted
- **WHEN** that second resume is deleted
- **THEN** the role has no end date again

#### Scenario: Different real end dates
- **WHEN** two resumes list the same start date with different real end dates
- **THEN** two roles exist

### Requirement: Hand curation survives rebuilds
The system SHALL keep curation in the database, apply it after every rebuild, and never overwrite it. Curation (certifications, education, skill merge/drop/group, tag-only skills, extra skills, flagged numbers, bullet themes, ignored fragments and summary positioning) SHALL be changed only with commands that list, add and remove its entries.

#### Scenario: Flagged number
- **WHEN** a bullet contains a number listed with `curate add flagged-number`
- **THEN** the bullet is flagged `needs_review`

#### Scenario: Flagged plain count
- **WHEN** `12` is flagged and one line says "a team of 12" and another "a team of 120"
- **THEN** only the first line is flagged

#### Scenario: Add and remove curation
- **WHEN** a curation entry is added and then removed with the curation commands
- **THEN** it is applied on the next rebuild while present and has no effect after removal, without `--force`

#### Scenario: Curation changed since the last build
- **WHEN** the curation differs from the one the stored data was built with
- **THEN** the next run rebuilds the data from the resume files, with the curation applied, and says so; a run with unchanged curation does not rebuild

#### Scenario: Curated list replaces the parsed list
- **WHEN** resumes state two certifications and one certification is added with `curate add`
- **THEN** the command says the curated list replaces the parsed one, and after a rebuild only the curated certification is stored

#### Scenario: Last curated entry removed
- **WHEN** the only curated education entry is removed and the data is rebuilt
- **THEN** the education parsed from the resumes is back

### Requirement: Themes and summary positioning come from one list
The commands SHALL share role-neutral leadership and delivery themes and ship no positioning words. Additional vocabulary SHALL come from the user's curation. `process-resumes curate themes` SHALL show both the built-in and curated lists.

#### Scenario: Adding vocabulary
- **WHEN** a user curates a theme word, positioning word or theme question
- **THEN** the relevant commands use it without changing the built-in list
- **AND** a word uses its supplied posting hints or the word itself when no hints are supplied

#### Scenario: Unknown theme
- **WHEN** a bullet is tagged with a theme that is not on the list
- **THEN** the tag is stored and the command warns that no tool uses it, and names `curate add theme-word`

#### Scenario: Own theme in a job description
- **WHEN** the user's own theme word has hints and a job description contains one of them
- **THEN** the job description is read as asking for that theme

#### Scenario: No positioning words yet
- **WHEN** a summary is given a positioning before the user has any positioning words
- **THEN** the command refuses it and says how to add one

#### Scenario: Unknown summary positioning
- **WHEN** a summary is given a positioning that is not one of the user's positioning words
- **THEN** the command refuses it and names the ones that exist

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
On each rebuild the system SHALL remove a resume file's contribution from the resume data when that file no longer exists or has changed, and SHALL then merge it again if it still exists. Skills whose source is `curated` SHALL be kept.

#### Scenario: Deleted resume
- **WHEN** a resume file is deleted and the data is rebuilt
- **THEN** bullets that only that file supplied are gone and bullets shared with other resumes stay with one source fewer

#### Scenario: Renamed resume
- **WHEN** a resume file is renamed and the data is rebuilt
- **THEN** its bullets appear once, under the new name only

#### Scenario: Edited resume drops a bullet
- **WHEN** a resume is edited to remove a bullet and the data is rebuilt
- **THEN** that bullet no longer appears if no other resume has it

#### Scenario: Everything left without a source is removed
- **WHEN** a rebuild leaves bullets, roles, role titles, subtitles, clients, summaries, headlines, profile points, education, certifications, projects or skills with no source
- **THEN** they are removed, together with the file's ledger, unparsed and raw-text entries

#### Scenario: Alternative spellings
- **WHEN** a file that gave a skill an alternative spelling is removed
- **THEN** the spelling stays, because skill alternative spellings are not tracked per file

### Requirement: Pruning reports what it removed
The system SHALL print the files whose contribution was removed and how many bullets were dropped. The system SHALL NOT prune when the scan finds no resume files, or when any configured resume folder is unavailable. A folder is unavailable when it does not exist, or when it has no resume files although the ledger lists files from it; `--force` SHALL accept the second case as a deliberate removal.

#### Scenario: Resume folder unavailable
- **WHEN** the resume folder is empty or unmounted
- **THEN** the system reports an error and the existing data is unchanged

#### Scenario: One of several folders is missing
- **WHEN** two resume folders are configured and one does not exist
- **THEN** the system names that folder in an error, exits with status 1, and the existing data is unchanged

#### Scenario: One of several folders has emptied
- **WHEN** a configured folder has no resume files and the ledger lists files from it, and `--force` is not given
- **THEN** the system names that folder in an error, exits with status 1, and the existing data is unchanged

#### Scenario: Files were moved out on purpose
- **WHEN** a configured folder has no resume files, the ledger lists files from it, and `--force` is given
- **THEN** the data is rebuilt from the remaining files

### Requirement: Orphaned curation is reported
The system SHALL list curation entries (themes, ignored fragments, summary positioning) whose id matches no current bullet or summary, in `review` output and as a warning at the end of a rebuild. Reporting SHALL NOT modify any curation entry.

#### Scenario: Bullet text changed
- **WHEN** a bullet's text changes so that its id changes
- **THEN** its old id is listed as orphaned and the curation entry is unchanged

#### Scenario: No orphans
- **WHEN** every curation id matches a current bullet or summary
- **THEN** the report says none were found

### Requirement: A role ends on the latest real end date
The end date of a role SHALL be the latest real end date any resume gives, and `Present` (no end date) only when none gives one. Removing a resume SHALL restore the end date the remaining resumes give.

#### Scenario: Latest end date wins
- **WHEN** two resumes give the same role end dates 05/2022 and 06/2022
- **THEN** the role ends 2022-06

### Requirement: A curated list replaces the parsed list
A curated education or certifications list that has entries SHALL replace the list parsed from the resumes, and `curate add` SHALL say so. A curated list with no entries SHALL count as no curation.

#### Scenario: Empty curated list
- **WHEN** a curated education list has no entries
- **THEN** it counts as no curation and the parsed list is used

### Requirement: Data from before source tracking is rebuilt once
Data stored before sources were tracked SHALL be rebuilt once from the resume files.

#### Scenario: Old data
- **WHEN** a command runs on data stored before sources were tracked
- **THEN** the data is rebuilt from the resume files once and not again on later runs

### Requirement: Inconsistencies between resumes are raised with the user
After import, the skill SHALL tell the agent to compare what resumes state about the same facts and ask about each real difference one at a time, showing both values. The agent SHALL save answers only through jobkit commands.

#### Scenario: Both versions are intentional
- **WHEN** the user keeps both as variants or a difference reflects tailoring for a posting
- **THEN** the agent saves no correction

#### Scenario: A correction needs a resume edit
- **WHEN** no jobkit command can correct the value
- **THEN** the skill tells the agent to leave the edit to the user because the resume folder is read-only

#### Scenario: Two resumes give different start dates
- **WHEN** two resumes give different start dates for the same job
- **THEN** the agent asks which is right, saves nothing, names the file that holds the wrong date, and offers to note it as an open item

#### Scenario: An older resume shows a job as current
- **WHEN** an older resume shows a job as current and a newer one gives its end date
- **THEN** the difference is not raised
