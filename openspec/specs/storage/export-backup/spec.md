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
`jobkit backup --restore FILE` SHALL replace the database with a backup after first saving the current database, and SHALL refuse a file that is not a complete jobkit database. The file SHALL be checked on a temporary copy before anything is replaced. A refusal SHALL name the table and SHALL NOT print the record's content.

#### Scenario: Checks before replacing
- **WHEN** a file is restored
- **THEN** the copy passes the SQLite integrity check, upgrades to the current schema, has every table, column and trigger of the current schema, has no broken references between tables and holds only readable records

#### Scenario: Restore
- **WHEN** a valid backup is restored
- **THEN** the data matches the backup and the previous database is kept as a backup

#### Scenario: Restore with no usable database
- **WHEN** a valid backup is restored and the current database is missing, damaged or from a newer version
- **THEN** the restore succeeds; a damaged or newer database is first copied file by file to the backup folder, and with no database the output says there was none

#### Scenario: Wrong file
- **WHEN** the file is not a jobkit database
- **THEN** the command exits with status 1 and the current database is unchanged

#### Scenario: Look-alike file
- **WHEN** the file has a `meta` table and a plausible version but lacks the real tables and columns
- **THEN** it is refused and the current database is unchanged

#### Scenario: Unreadable record
- **WHEN** the file holds a stored record that is not valid JSON
- **THEN** it is refused, the table is named, the record's content is not printed and the current database is unchanged

#### Scenario: Broken reference
- **WHEN** the file holds a record that points at a missing record of a linked table
- **THEN** it is refused and the current database is unchanged

#### Scenario: Protection removed
- **WHEN** the file lacks the triggers that protect logged answers
- **THEN** it is refused and the current database is unchanged

### Requirement: Researched companies are exported
`jobkit export` SHALL include the researched company profiles as their own kind, with every field of every fact (id, kind, wording, quote, reference link, label, date of pull, vetting), the none-found records, and the suggested style with its basis, and `jobkit status` SHALL count them.

#### Scenario: Researched company
- **WHEN** one company with three facts is researched and the data is exported
- **THEN** the export contains that company with each fact's link, quote, label and date of pull

#### Scenario: None found
- **WHEN** a company was recorded as none found and the data is exported
- **THEN** the export contains that record with its date

#### Scenario: Fresh database
- **WHEN** a new database is exported
- **THEN** the kind is present and empty

### Requirement: Exported sessions carry style and company
An exported session SHALL include its company and current style, and each exported log entry SHALL include the style and company it recorded, empty for entries logged before they existed.

#### Scenario: Session with a company
- **WHEN** a session started for a company in soar is exported
- **THEN** the session and each of its story entries show that company and soar
