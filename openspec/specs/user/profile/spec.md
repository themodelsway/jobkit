# user/profile Specification

## Purpose
Hold per-user settings in the database under the home folder so committed files stay free of personal data. Implemented in `src/jobkit/user/profile.py`.

## Requirements

### Requirement: Profile files
The system SHALL keep the settings (resume root, resume folders, optional name and tier-1 services) and the employers found by the first scan (name and regex) in the database, and `header.md` (name and contact line for generated resumes) as a file under `profile/` in the home folder.

#### Scenario: Init
- **WHEN** `init --resume-root PATH` is run
- **THEN** the settings are stored and an existing answer is not overwritten

#### Scenario: Init again with other answers
- **WHEN** `init` is run again with a different resume root, name or folders
- **THEN** the stored values are kept, a line says so, and `set` is the way to change name or resume root

### Requirement: Employers are editable
The system SHALL list the scanned employers with `companies` and let the user rename them and merge them with commands, without editing any file.

#### Scenario: Renamed employer
- **WHEN** `companies rename ID NAME` is run
- **THEN** the next run uses the new name

#### Scenario: Merged employers
- **WHEN** `companies merge FROM INTO` is run
- **THEN** the next run treats both names as the one employer

### Requirement: Open items
The system SHALL keep personal open items and data notes in the database, listed with `open`, added with `open add TEXT` and closed with `open done ID`.

#### Scenario: Add item
- **WHEN** `open add "check figure"` is run
- **THEN** the item appears in `open`

### Requirement: Tier-1 services
The user SHALL be able to pin their own tier-1 AWS services with `tier1`, and running it with no arguments SHALL show the current list.

#### Scenario: Show list
- **WHEN** `tier1` is run with no arguments
- **THEN** the current list is printed

### Requirement: Retest window
The profile SHALL hold a retest window, `reassess_days`, as a whole number of days from 1 to 365. `profile set reassess_days N` SHALL store it and reject any other value without changing the stored one. When none is stored the window SHALL be 30, and `profile status` SHALL show which applies.

#### Scenario: Set the window
- **WHEN** `profile set reassess_days 45` is run
- **THEN** the stored window is 45 and `profile status` shows 45

#### Scenario: Invalid value
- **WHEN** `profile set reassess_days 0` or `profile set reassess_days soon` is run
- **THEN** the command fails and the stored window is unchanged

#### Scenario: Nothing stored
- **WHEN** no window has been set
- **THEN** the window is 30 and `profile status` says it is the default
