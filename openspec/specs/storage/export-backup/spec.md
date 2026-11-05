# storage/export-backup Specification

## Purpose
Let the user see and keep their data without opening the database: a readable export for viewing, and a database backup and restore.

## Requirements

### Requirement: Export for viewing
`jobkit export` SHALL write the stored data as readable JSON (default) or Markdown (`--format md`) to stdout or, with `-o`, to a folder, and SHALL NOT change the database.

#### Scenario: Export to a folder
- **WHEN** `jobkit export -o out/` is run
- **THEN** `out/` holds one file per kind of data and the database is unchanged

#### Scenario: Export to stdout
- **WHEN** `jobkit export --only stories` is run
- **THEN** only the stories are printed

### Requirement: Export is complete
An export in JSON SHALL contain every stored record with all of its fields, so that the data can be read without any other tool.

#### Scenario: Round trip of counts
- **WHEN** a JSON export is made
- **THEN** the number of records per kind equals the counts shown by `jobkit status`

### Requirement: Export keeps contact details out
`jobkit export` SHALL NOT add contact details that are not stored in the database, and the generated Markdown SHALL be written only where the user names.

#### Scenario: Default output
- **WHEN** no `-o` is given
- **THEN** nothing is written to disk

### Requirement: Database backup
`jobkit backup` SHALL write a consistent copy of the database to `backup/` under the home folder (or to `-o PATH`) while other commands may be running, and SHALL report the file and its size.

#### Scenario: Backup during use
- **WHEN** `jobkit backup` is run while another command writes
- **THEN** the copy opens cleanly and holds a state from before or after that write

### Requirement: Restore
`jobkit backup --restore FILE` SHALL replace the database with a backup after first saving the current database, and SHALL refuse a file that is not a database of a known schema version.

#### Scenario: Restore
- **WHEN** a valid backup is restored
- **THEN** the data matches the backup and the previous database is kept as a backup

#### Scenario: Wrong file
- **WHEN** the file is not a jobkit database
- **THEN** the command exits with status 1 and the current database is unchanged
