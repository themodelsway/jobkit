# interview/stories Specification

## Purpose
Hold STAR stories and the real engagements behind them in the database, with every fact and number carrying a basis. Implemented in `plugins/jobkit/src/jk/interview/prep.py` and `story_model.py` (pure rules).

## Requirements

### Requirement: Facts carry a basis
Every engagement fact SHALL have a basis of `stated`, `estimate`, `unsure`, `verified-doc` or `proposed`; only `stated`, `estimate` and `verified-doc` SHALL back interview text.

#### Scenario: Unsure fact in a story
- **WHEN** a story relies on a fact marked `unsure`
- **THEN** validation reports an error

### Requirement: Metrics carry a basis
Every story metric SHALL have a basis of `measured`, `estimated`, `stated` or `unknown`.

#### Scenario: Hedged metric
- **WHEN** a spoken version states an `estimated` number without hedging
- **THEN** validation warns

### Requirement: Status gates on validation
A story SHALL move between `empty`, `draft` and `done`, and validation errors SHALL block `done` while warnings are advice only.

#### Scenario: Linked engagement missing
- **WHEN** a story links an engagement that does not exist
- **THEN** validation reports an error

### Requirement: Stories link to engagements
The system SHALL link a story to an engagement and to the specific facts it relies on, and SHALL allow one engagement to serve several stories.

#### Scenario: Unlink facts
- **WHEN** `unlink STORY --facts f1` is run
- **THEN** only that fact is detached

### Requirement: Rank for a job description
The system SHALL rank stories for a job description and include typical questions.

#### Scenario: JD run
- **WHEN** `for-jd jd.txt` is run
- **THEN** stories are listed best match first

### Requirement: Safe storage
The system SHALL store stories, engagements and their facts, decisions, people and metrics in the database, change them atomically, and let concurrent writers proceed without losing data.

#### Scenario: Concurrent writers
- **WHEN** two writes start together
- **THEN** both are stored and no data is lost

#### Scenario: Failure part way
- **WHEN** a command fails after changing a story and its engagement
- **THEN** neither change is stored
