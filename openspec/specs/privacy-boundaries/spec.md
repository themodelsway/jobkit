# privacy-boundaries Specification

## Purpose
Keep everything personal out of the repository and out of the resume data, and keep the user's resume files untouched. Enforced partly by `tests/test_no_personal.py`.

## Requirements

### Requirement: Committed files hold nothing personal
Committed files SHALL NOT contain the user's name, employers, folder paths or figures. Personal settings SHALL live only in git-ignored `profile/`, `resume-data/`, `prep/` and `output/`.

#### Scenario: Personal data in a tracked file
- **WHEN** a tracked file contains a configured personal term or a phone-like number
- **THEN** the no-personal test fails

### Requirement: No contact info in resume data
The system SHALL NOT store phone, email or LinkedIn details in `resume-data/`. Name and contact lines for generated resumes SHALL come from `profile/header.md`.

#### Scenario: Contact check
- **WHEN** `resume-data/json/` is searched for `@` or phone patterns
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
The test suite SHALL fail when any file under `resume-data/json/` contains an email address or a phone-like number, and SHALL report a skip, not a pass, when that folder does not exist.

#### Scenario: Email in generated data
- **WHEN** a generated file contains an email address
- **THEN** the test fails and names the file

#### Scenario: Fresh clone
- **WHEN** `resume-data/json/` does not exist
- **THEN** the check is reported as skipped

### Requirement: Missing profile is visible
The personal-term check SHALL report a skip with the reason when `profile/` provides no terms, so a run without a profile never reads as a full pass.

#### Scenario: No profile
- **WHEN** `profile/` is absent
- **THEN** the test output shows the personal-term check as skipped and says why

### Requirement: Resume folder immutability is tested
The test suite SHALL show that a full rebuild, including pruning, leaves every file in the resume folder unchanged in content, name and modification time, and adds no file there.

#### Scenario: Rebuild with a deleted source
- **WHEN** a rebuild runs against a temporary resume folder
- **THEN** a snapshot of that folder before and after is identical
