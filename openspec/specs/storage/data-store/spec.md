# storage/data-store Specification

## Purpose
Keep all of the user's data in one local database under a single home folder, so changes are atomic, concurrent use is safe and records cannot point at things that do not exist.

## Requirements

### Requirement: One database under the home folder
The system SHALL keep all user data in one database file, `data/jobkit.db`, under the home folder named by `JOBKIT_HOME` (default `~/.jobkit`), and SHALL NOT resolve any data location from the installed or checked-out source.

#### Scenario: Default location
- **WHEN** `JOBKIT_HOME` is not set
- **THEN** data is read from and written to `~/.jobkit/data/jobkit.db`

#### Scenario: Overridden location
- **WHEN** `JOBKIT_HOME` names another folder
- **THEN** that folder is used for the database, backups, output and `header.md`

### Requirement: Init creates the home
`jobkit init` SHALL create the home folder layout and an empty database at the current schema version, and SHALL leave an existing database and its data unchanged.

#### Scenario: First run
- **WHEN** `jobkit init` is run and no home exists
- **THEN** the folders and an empty database are created

#### Scenario: Repeat run
- **WHEN** `jobkit init` is run again
- **THEN** no data changes and the command reports that the home already exists

### Requirement: Commands need an initialised home
A command that reads or writes data SHALL stop with a message naming `jobkit init` when the database does not exist, and SHALL NOT create one as a side effect.

#### Scenario: No database
- **WHEN** `prep list` is run before `jobkit init`
- **THEN** it exits with status 1 and tells the user to run `jobkit init`

### Requirement: Schema is versioned
The database SHALL record its schema version, and the system SHALL apply any missing numbered upgrade steps, in order and inside a transaction, before a command runs. A database written by a newer version SHALL be refused with a message.

#### Scenario: Older database
- **WHEN** a command opens a database with an older schema version
- **THEN** the upgrade steps are applied and the command then runs

#### Scenario: Newer database
- **WHEN** the database version is newer than the program knows
- **THEN** the command exits with status 1 and makes no change

### Requirement: Changes are atomic
Each command SHALL commit all of its changes together or none of them.

#### Scenario: Failure part way
- **WHEN** a command fails after changing some records
- **THEN** none of its changes are stored

### Requirement: Safe concurrent use
Several commands running at the same time SHALL NOT lose each other's changes. A writer that has to wait SHALL wait for a bounded time and then fail with a clear message.

#### Scenario: Two writers
- **WHEN** two commands write at the same time
- **THEN** both changes are stored

#### Scenario: Reader during a write
- **WHEN** a read-only command runs while another command is writing
- **THEN** the reader sees the data as it was before or after that write, never half of it

### Requirement: References stay valid
The database SHALL refuse a record that refers to a missing record (for example a logged answer for an unknown item, or a fact for a missing engagement), and SHALL report this as a user-readable error. Curation entries that name a bullet id are exempt, because a rebuild can legitimately change that id; they are reported as orphaned instead.

#### Scenario: Unknown item
- **WHEN** an answer is logged for an item that does not exist
- **THEN** the command fails with a message and nothing is stored

### Requirement: Answers are append-only
A session's logged answers SHALL only be added, never edited or removed by any command.

#### Scenario: Later drill
- **WHEN** an item is drilled again
- **THEN** a new log entry is added and the earlier entries are unchanged

### Requirement: Status
`jobkit status` SHALL show the database location, schema version, size and the number of records per kind, without changing anything.

#### Scenario: Status
- **WHEN** `jobkit status` is run
- **THEN** the location, version and per-kind counts are printed
