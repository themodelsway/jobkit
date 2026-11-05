# user/profile Specification

## Purpose
Hold per-user settings in the git-ignored `profile/` folder so committed files stay free of personal data. Implemented in `src/jobkit/user/profile.py`.

## Requirements

### Requirement: Profile files
The system SHALL keep `profile.json` (resume root, resume folders, optional name and tier-1 services), `companies.json` (employers found by the first scan, with name and regex) and `header.md` (name and contact line for generated resumes) under `profile/`.

#### Scenario: Init
- **WHEN** `init --resume-root PATH` is run
- **THEN** `profile/profile.json` is created and an existing answer is not overwritten

### Requirement: Employers are editable
The system SHALL list the scanned employers with `companies` and let the user merge or rename them by editing `companies.json`.

#### Scenario: Renamed employer
- **WHEN** a company name is edited
- **THEN** the next run uses the new name

### Requirement: Open items
The system SHALL keep personal open items and data notes in `profile/open_items.json`, listed with `open`, added with `open add TEXT` and closed with `open done ID`.

#### Scenario: Add item
- **WHEN** `open add "check figure"` is run
- **THEN** the item appears in `open`

### Requirement: Tier-1 services
The user SHALL be able to pin their own tier-1 AWS services with `tier1`, and running it with no arguments SHALL show the current list.

#### Scenario: Show list
- **WHEN** `tier1` is run with no arguments
- **THEN** the current list is printed
