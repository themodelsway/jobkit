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
A solid answer last drilled more than `--days` ago (default 30) SHALL be labelled aging. An item whose solid answers are all older than `--days` SHALL also be aging, whatever later lessons logged.

#### Scenario: Old solid answer
- **WHEN** the last solid answer is 45 days old
- **THEN** the label is aging

### Requirement: Story and leadership status
Stories SHALL be labelled empty, draft, done, done-rehearsed (done, with an answer logged within `--days`) or done-aging (done, but every logged answer is older). The label says attempted, not graded. Leadership questions SHALL show how many examples with content are filled against the target (up to three employers).

#### Scenario: Rehearsed story
- **WHEN** a done story is logged in a session
- **THEN** it is labelled done-rehearsed

#### Scenario: Old rehearsal
- **WHEN** the only logged answer for a done story is 45 days old
- **THEN** it is labelled done-aging

### Requirement: Limit to a job description
With `--jd` the report SHALL cover only architecture cards and stories that the job description touches.

#### Scenario: JD filter
- **WHEN** `--jd jd.txt` is given
- **THEN** unrelated cards are omitted

### Requirement: Read-only
The report SHALL NOT change any stored data.

#### Scenario: Run twice
- **WHEN** the report is run
- **THEN** the database is unchanged, including its modification time
