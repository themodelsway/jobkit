# storage/legacy-import Specification

## Purpose
Move the user's existing JSON data into the database without any risk of losing it: back it up first, check the result against the source, and remove nothing until the user decides to.

## Requirements

### Requirement: Backup before import
`jobkit migrate` SHALL copy the complete set of old data files (`profile/`, `prep/`, `resume-data/`) to `backup/json-<timestamp>/` under the home folder before it imports anything, and SHALL stop without importing when the copy is incomplete.

#### Scenario: Backup made
- **WHEN** `jobkit migrate` starts
- **THEN** every old data file exists in the backup folder with identical content before any record is imported

#### Scenario: Backup fails
- **WHEN** the backup cannot be completed
- **THEN** nothing is imported and the command exits with status 1

### Requirement: Originals are left in place
`jobkit migrate` SHALL NOT modify, move or delete the original JSON files.

#### Scenario: After migration
- **WHEN** a migration has finished
- **THEN** every original file is unchanged in content and modification time

### Requirement: Import is verified
After importing, the system SHALL compare, per kind of record, the count and a content checksum of the source against what is stored, and SHALL report each kind as matching or not. When any kind does not match, the import SHALL be rolled back and the command SHALL exit with status 1.

#### Scenario: Everything matches
- **WHEN** all counts and checksums match
- **THEN** the report lists each kind with its count and the import is kept

#### Scenario: A mismatch
- **WHEN** one kind does not match
- **THEN** the report names it, nothing is kept in the database and the exit status is 1

### Requirement: Dry run
With `--dry-run` the system SHALL parse and validate the old files and report what would be imported, and SHALL write nothing, not even a backup or an empty database.

#### Scenario: Dry run
- **WHEN** `jobkit migrate --dry-run` is run
- **THEN** per-kind counts are printed and no file or database is created

### Requirement: Import can be repeated
Running `jobkit migrate` again SHALL NOT duplicate records. If the database already holds imported data the command SHALL say so and SHALL import only with an explicit `--replace`, which first makes a database backup.

#### Scenario: Second run
- **WHEN** `jobkit migrate` is run after a successful import
- **THEN** no record is added and the command reports that the data is already imported

### Requirement: Unreadable files stop the import
A damaged or unrecognised old file SHALL stop the import with a message naming the file, rather than being skipped.

#### Scenario: Broken JSON
- **WHEN** an old data file cannot be parsed
- **THEN** the command exits with status 1 naming the file and the database is unchanged

### Requirement: Old files are removed only on request
The system SHALL remove the old JSON files only when the user runs `jobkit migrate --remove-old`, and only after a verification of the database against the backup passes. The backup SHALL be kept.

#### Scenario: Remove after check
- **WHEN** `jobkit migrate --remove-old` is run and verification passes
- **THEN** the old files are deleted and the backup folder remains

#### Scenario: Verification fails
- **WHEN** verification does not pass
- **THEN** no old file is deleted
