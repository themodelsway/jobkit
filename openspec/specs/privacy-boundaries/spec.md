# privacy-boundaries Specification

## Purpose
Keep everything personal out of the repository and out of the resume data, and keep the user's resume files untouched. Enforced partly by `tests/meta/test_no_personal.py`.

## Requirements

### Requirement: Committed files hold nothing personal
Committed files SHALL NOT contain the user's name, employers, folder paths or figures. Personal data SHALL live only under the home folder (`JOBKIT_HOME`, default `~/.jobkit`), outside the repository.

#### Scenario: Personal data in a tracked file
- **WHEN** a tracked file contains a configured personal term or a phone-like number
- **THEN** the no-personal test fails

#### Scenario: Data location
- **WHEN** any command writes personal data
- **THEN** it is written under the home folder and nothing is added inside the repository

### Requirement: No contact info in resume data
The system SHALL NOT store phone, email or LinkedIn details in the resume data. Name and contact lines for generated resumes SHALL come from the saved header (`profile header set`), kept apart from the resume data; an older `profile/header.md` file is still read when no header is saved.

#### Scenario: Contact check
- **WHEN** the stored resume data is searched for `@` or phone patterns
- **THEN** no hit is a real contact detail

### Requirement: Raw extracted text stays in output
The system SHALL write raw extracted text only under `output/`.

#### Scenario: Extraction run
- **WHEN** resumes are processed
- **THEN** raw text files exist only in `output/`

### Requirement: Resume folder is read-only
The system SHALL NOT edit or write inside the folder named by `resume_root`.

#### Scenario: Any tool run
- **WHEN** any tool runs
- **THEN** the resume folder is unchanged

### Requirement: Resume bullets are never invented
Generated resumes and suggestions SHALL use only bullets stored in the resume data; proposed edits SHALL be suggestions to the user, not stored as bullets.

#### Scenario: Build for a job description
- **WHEN** a resume is built
- **THEN** every bullet in it exists in the resume data

### Requirement: Contact check on resume data is automated
The test suite SHALL fail when any stored resume text contains an email address or a phone-like number, and SHALL report a skip, not a pass, when there is no resume data to check.

#### Scenario: Email in generated data
- **WHEN** a stored bullet, summary or skill contains an email address
- **THEN** the test fails and names the record

#### Scenario: Fresh clone
- **WHEN** no resume data exists
- **THEN** the check is reported as skipped

### Requirement: Missing profile is visible
The personal-term check SHALL report a skip with the reason when the profile provides no terms, so a run without a profile never reads as a full pass.

#### Scenario: No profile
- **WHEN** the profile is absent
- **THEN** the test output shows the personal-term check as skipped and says why

### Requirement: The staged check reads every added or moved file
`profile terms check --staged` SHALL read the staged content of every added, copied, modified, renamed (under its new name) or type-changed file, so a renamed file that gains a personal term is not skipped.

#### Scenario: Renamed file with a new term
- **WHEN** a file is renamed, a personal term is added to it, and it is staged
- **THEN** the check reports the term, even when the working copy has since been cleaned

### Requirement: Text from stored data is caught
`profile terms check` SHALL compare every line it reads with the contributor's stored data (resume lines and all their wordings, profile text, titles, certifications, education, stories, practice notes, own vocabulary and extracted resume text), leaving out jobkit's own seeded text, and SHALL report a shared five-word phrase, a near-copy, a stored title, certification or degree, two stored figures, or three distinctive terms in one line as a hit.

#### Scenario: A resume line copied with small edits
- **WHEN** a staged test file holds a lightly edited copy of one of the contributor's resume lines
- **THEN** the check reports the line as a phrase or near-copy hit and exits 1

#### Scenario: Seeded text is not a hit
- **WHEN** a staged file quotes a built-in practice question or card name
- **THEN** the check does not report it

#### Scenario: A false alarm
- **WHEN** the contributor ignores the matched text with `profile terms ignore TEXT`
- **THEN** the next check no longer reports that line

### Requirement: Stored-data hits never show the stored text
A stored-data hit SHALL print only its location, its kind and the kind and id of the record it matches, never the stored text.

#### Scenario: A phrase hit
- **WHEN** a line matches a stored story
- **THEN** the output names the file, the line, `phrase` and the story's id, and no words of the story

### Requirement: The comparison is rebuilt on every run
The check SHALL build its comparison from the database and the output folder in memory on each run and SHALL NOT write it to disk.

#### Scenario: New data
- **WHEN** a new resume is processed and the next commit stages one of its lines
- **THEN** the hook reports the line

### Requirement: Removed lines are warned about
With `--staged`, the check SHALL warn without failing when the staged changes remove lines that match stored data, saying that removed text stays in earlier commits.

#### Scenario: Cleaning a file
- **WHEN** the staged changes only remove a line copied from a resume
- **THEN** the check passes and prints the warning

### Requirement: The history can be checked
`profile terms check --history` SHALL apply the term and stored-data checks to every version of every file in the history of all branches, naming each hit by path and object id.

#### Scenario: An old version
- **WHEN** an earlier commit held a resume line that the current files no longer hold
- **THEN** `--history` reports it while `--all` does not

### Requirement: Fictional employers in test resumes are Acme names
Every employer in the test resume samples SHALL have a name starting with "Acme".

#### Scenario: A sample with another name
- **WHEN** a test resume sample names an employer that does not start with "Acme"
- **THEN** the no-personal test fails

### Requirement: Tests never change the real database
A test that checks the real home SHALL run against a consistent copy of the database, never against the original, because every command upgrades the database it opens. The original SHALL keep its schema version and bytes.

#### Scenario: Older database
- **WHEN** the real-home personal-term test runs against a database from the previous schema version
- **THEN** that database is still at the previous version afterwards and its own release can still open it

### Requirement: Resume folder immutability is tested
The test suite SHALL show that a full rebuild, including pruning, leaves every file in the resume folder unchanged in content, name and modification time, and adds no file there.

#### Scenario: Rebuild with a deleted source
- **WHEN** a rebuild runs against a temporary resume folder
- **THEN** a snapshot of that folder before and after is identical

### Requirement: Commits are scanned for secrets
The pre-commit hook SHALL run gitleaks on the staged changes and SHALL block the commit when it reports a leak or when gitleaks is not installed.

#### Scenario: Key in a staged file
- **WHEN** a staged file contains an access key or secret
- **THEN** the commit is blocked
