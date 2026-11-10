# privacy-boundaries Specification

## Purpose
Keep everything personal out of the repository and out of the resume data, and keep the user's resume files untouched. Enforced partly by `tests/test_no_personal.py`.

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
