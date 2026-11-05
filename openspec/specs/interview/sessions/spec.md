# interview/sessions Specification

## Purpose
Keep resumable practice and tutor sessions in `prep/sessions/`, with the user's full answers. Implemented in `sessions`.

## Requirements

### Requirement: Session is one file with a queue and a log
A session SHALL hold a queue of items (architecture cards, stories or leadership questions) and an append-only log that keeps the user's full answers.

#### Scenario: Re-drill a topic
- **WHEN** a topic is drilled in a later session
- **THEN** the new session logs it and the old session is not edited

### Requirement: Resume and close
The system SHALL show what was covered, the last answers and the next item to ask on `resume ID`, and SHALL allow `close` and `reopen`.

#### Scenario: Reopen
- **WHEN** a closed session is reopened
- **THEN** it continues from its next unasked item

### Requirement: Modes
A session SHALL have a mode of architecture, stories, jd, leadership or tutor, and SHALL be narrowable by area, tier, kind, company, category and count.

#### Scenario: JD mode
- **WHEN** a session starts with `--jd`
- **THEN** its queue holds the items that job description touches

### Requirement: Teaching caps confidence
In tutor sessions a logged confidence SHALL be capped at 1, and a passed quiz (`--quiz`, which needs `--grade` and confidence 2) SHALL allow 2. `--quiz` SHALL be rejected outside tutor sessions.

#### Scenario: Taught but not quizzed
- **WHEN** a tutor log has confidence 2 without `--quiz`
- **THEN** it is stored as 1

### Requirement: Confidence is shared
Confidence per architecture card SHALL be shared across sessions through `prep/arch/progress.json`.

#### Scenario: Two sessions
- **WHEN** a card is graded in session B after session A
- **THEN** the card shows the latest confidence in both
