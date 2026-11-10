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
Each command SHALL commit all of its changes together or none of them. A write that fails inside a larger command SHALL leave none of its own changes behind, even when the command handles the failure and carries on.

#### Scenario: Failure part way
- **WHEN** a command fails after changing some records
- **THEN** none of its changes are stored

#### Scenario: Handled failure
- **WHEN** a session save is refused inside a larger change and the error is handled
- **THEN** the session's title, queue and log are unchanged, and the rest of the larger change is stored

### Requirement: Safe concurrent use
Several commands running at the same time SHALL NOT lose each other's changes. A writer that has to wait SHALL wait for a bounded time and then fail with a clear message.

#### Scenario: Two writers
- **WHEN** two commands write at the same time
- **THEN** both changes are stored

#### Scenario: Reader during a write
- **WHEN** a read-only command runs while another command is writing
- **THEN** the reader sees the data as it was before or after that write, never half of it

### Requirement: References stay valid
The database SHALL refuse a record that refers to a missing record (for example a logged answer for an unknown item, or a fact for a missing engagement), and SHALL report this as a user-readable error. A new queue entry or logged answer SHALL name an item that exists now. Entries already stored SHALL stay readable after their item is removed. Curation entries that name a bullet id are exempt, because a rebuild can legitimately change that id; they are reported as orphaned instead.

#### Scenario: Unknown item
- **WHEN** an answer is logged for an item that does not exist
- **THEN** the command fails with a message and nothing is stored

#### Scenario: Unknown queue entry
- **WHEN** a session is saved with a new queue entry naming an item that does not exist
- **THEN** the save is refused with a message and nothing is stored

#### Scenario: Item removed later
- **WHEN** an item with logged answers is removed from the catalog
- **THEN** the session and its answers can still be read and exported

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

### Requirement: One value per field
The system SHALL store each field of a record in one place, so that every command that shows a field shows the same value. A log of answers MAY repeat fields of an entry, because a logged entry can never be changed.

#### Scenario: Listing and detail agree
- **WHEN** a session is changed and then both listed and shown in detail
- **THEN** its title, mode, status and dates are the same in both

### Requirement: A session's creation time is fixed
The system SHALL refuse a change to the creation time of an existing session, and SHALL leave the session unchanged.

#### Scenario: Changed creation time
- **WHEN** a session is saved with a creation time different from the stored one
- **THEN** the change is refused with a message and the session's title, queue and log are unchanged

### Requirement: Confidence values are checked
The system SHALL store a confidence of 0, 1 or 2 only, and SHALL refuse any other value with a message, leaving the stored progress unchanged.

#### Scenario: Confidence out of range
- **WHEN** progress is written with a confidence of 3
- **THEN** the write is refused and the stored progress is unchanged

### Requirement: Upgrades keep the data
An upgrade SHALL keep every record and field, so that a JSON export has the same records and values before and after. It SHALL check the data before changing it, and SHALL stop with a message and change nothing when a key field's stored copies disagree. The one exception is a session's creation time: the value shown in the session listing SHALL be kept and the difference reported.

#### Scenario: Export after upgrade
- **WHEN** a database at the previous version is upgraded
- **THEN** a JSON export has the same records and values as before

#### Scenario: Copies disagree
- **WHEN** a story's link to its engagement differs between its copies during the upgrade
- **THEN** the upgrade stops with a message naming the table, the database stays at its old version and nothing is changed

#### Scenario: Session creation time differs
- **WHEN** a session's two stored creation times differ during the upgrade
- **THEN** the upgrade keeps the value the listing showed and reports the session

#### Scenario: Answers stay protected
- **WHEN** the upgrade has finished
- **THEN** logged answers still cannot be edited or removed
