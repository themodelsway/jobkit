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
A solid answer last drilled more than `--days` ago SHALL be labelled aging; when `--days` is not given the window SHALL be the stored retest window (30 when none is stored). An item whose solid answers are all older than the window SHALL also be aging, whatever later lessons logged.

#### Scenario: Old solid answer
- **WHEN** the last solid answer is 45 days old
- **THEN** the label is aging

#### Scenario: Stored window
- **WHEN** the stored retest window is 60 and the last solid answer is 45 days old
- **THEN** the label is not aging, and `--days 30` makes it aging for that run

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

### Requirement: List answers due for a retest
`readiness --due` SHALL list, instead of the report, the items labelled aging or done-aging, each with its id, name, the date of its last good answer and its age in days. It SHALL be read-only, use the same window rules as the report, and print "none due" when the list is empty.

#### Scenario: Two items due
- **WHEN** two items have good answers older than the window and one has a recent one
- **THEN** only the two older items are listed with their ages

#### Scenario: Nothing due
- **WHEN** no item is aging
- **THEN** the output says none are due and the exit status is 0

### Requirement: Limit to a target company
With `--target COMPANY` the report SHALL show evidence per company value: the value's state as defined for target companies, and the stories and leadership questions that match it, each with its existing label and how it matched. The system SHALL NOT compute a single percentage or rank companies.

#### Scenario: Value with a solid story
- **WHEN** a story that matches a value by theme is done-rehearsed
- **THEN** the value reads covered and lists that story with the label done-rehearsed

#### Scenario: Value matched only by word
- **WHEN** the only matches for a value are by word
- **THEN** the value reads possible and each item is marked matched by word

#### Scenario: Value with nothing
- **WHEN** a value has themes or hint words and no story or question matches
- **THEN** the value reads no story

#### Scenario: Value that cannot be matched
- **WHEN** a value lists no themes and no hint words
- **THEN** the value reads needs your judgment, never untested and never covered

#### Scenario: No score
- **WHEN** the company report is shown
- **THEN** it contains no overall percentage

#### Scenario: Company is always named
- **WHEN** `readiness` is run without `--target` while the profile has a default company
- **THEN** the report is the same as before this change

### Requirement: Company with a job description
`--target` MAY be combined with `--jd`, and the report SHALL then cover only what both select. Both SHALL narrow the same report, not produce two.

#### Scenario: Both filters
- **WHEN** `--target COMPANY --jd jd.txt` is given
- **THEN** every company value is still listed with its state, and under each only the items the job description also selects

### Requirement: Company report is read-only
The company report SHALL NOT change any stored data, and `--due` SHALL accept `--target` to list only due items that match a company value by theme or by word.

#### Scenario: Due for a company
- **WHEN** `--due --target COMPANY` is run and three items are due, one matching
- **THEN** only the matching item is listed

#### Scenario: Due, nothing matching
- **WHEN** `--due --target COMPANY` is run and no due item matches
- **THEN** the command says how many items are due in all and that none match this company
