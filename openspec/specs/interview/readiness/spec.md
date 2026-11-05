# interview/readiness Specification

## Purpose
Report evidence of readiness per area from the user's logged drills, read-only. Implemented in `readiness`.

## Requirements

### Requirement: Evidence labels, no single score
Each architecture card and leadership question SHALL get one label: untested, some gaps, solid-unlogged, solid-once, solid-repeated or aging. The system SHALL NOT compute a single percentage.

#### Scenario: Two good days
- **WHEN** a card is graded 2 on two different days
- **THEN** its label is solid-repeated

### Requirement: Only real answers count
Only log entries with a non-empty answer SHALL count, and tutor-lesson entries SHALL count only when the quiz was passed.

#### Scenario: Empty answer
- **WHEN** a log entry has no answer
- **THEN** it is ignored

### Requirement: Aging
A solid answer last drilled more than `--days` ago (default 30) SHALL be labelled aging.

#### Scenario: Old solid answer
- **WHEN** the last solid answer is 45 days old
- **THEN** the label is aging

### Requirement: Story and leadership status
Stories SHALL be labelled empty, draft, done or done-rehearsed (done and logged in a session at least once), and leadership questions SHALL show how many of the top three company examples are filled.

#### Scenario: Rehearsed story
- **WHEN** a done story is logged in a session
- **THEN** it is labelled done-rehearsed

### Requirement: Limit to a job description
With `--jd` the report SHALL cover only architecture cards and stories that the job description touches.

#### Scenario: JD filter
- **WHEN** `--jd jd.txt` is given
- **THEN** unrelated cards are omitted

### Requirement: Read-only
The report SHALL NOT write any file.

#### Scenario: Run twice
- **WHEN** the report is run
- **THEN** no file under `prep/` changes
