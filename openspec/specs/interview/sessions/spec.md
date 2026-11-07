# interview/sessions Specification

## Purpose
Keep resumable practice and tutor sessions stored in the database, with the user's full answers. Implemented in `sessions`.

## Requirements

### Requirement: Session is one file with a queue and a log
A session SHALL hold a queue of items (architecture cards, stories or leadership questions) and an append-only log that keeps the user's full answers.

#### Scenario: Re-drill a topic
- **WHEN** a topic is drilled in a later session
- **THEN** the new session logs it and the old session is not edited

#### Scenario: Log entry for an unknown item
- **WHEN** an answer is logged for an item that does not exist
- **THEN** the command fails and the log is unchanged

### Requirement: Resume and close
The system SHALL show what was covered, the last answers and the next item to ask on `resume ID`, and SHALL allow `close` and `reopen`.

#### Scenario: Reopen
- **WHEN** a closed session is reopened
- **THEN** it continues from its next unasked item

### Requirement: Modes
A session SHALL have a mode of architecture, stories, jd, leadership or tutor, and SHALL be narrowable by track, area, tier, kind, company, category and count. Without `--mode`, the mode is jd when `--jd` is given and architecture otherwise; `--jd` with any other explicit mode is an error.

#### Scenario: JD mode
- **WHEN** a session starts with `--jd`
- **THEN** its queue holds the items that job description touches, and the saved mode is jd with the JD recorded

#### Scenario: JD with filters
- **WHEN** a jd session is started with `--track`, `--area`, `--tier` or `--kind`
- **THEN** only the matched cards that pass every filter are queued

#### Scenario: JD with another mode
- **WHEN** `--jd` is given with `--mode stories`
- **THEN** the command fails and says to drop one of them

### Requirement: Teaching caps confidence
In tutor sessions a logged confidence SHALL be capped at 1, and a passed quiz (`--quiz`, which needs `--grade` and confidence 2) SHALL allow 2. `--quiz` SHALL be rejected outside tutor sessions.

#### Scenario: Taught but not quizzed
- **WHEN** a tutor log has confidence 2 without `--quiz`
- **THEN** it is stored as 1

### Requirement: A lesson does not refresh a drill date
A tutor lesson that does not raise confidence SHALL NOT change the item's last-drilled date, so old solid answers still read as aging.

#### Scenario: Lesson on an old solid card
- **WHEN** a tutor lesson without a passed quiz is logged for a card at confidence 2
- **THEN** its last-drilled date is unchanged

### Requirement: Confidence is shared
Confidence per architecture card SHALL be stored once, outside any session, and SHALL be shared across sessions.

#### Scenario: Two sessions
- **WHEN** a card is graded in session B after session A
- **THEN** the card shows the latest confidence in both
