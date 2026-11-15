# interview/stories Specification

## Purpose
Hold the user's stories, told as STAR, SOAR or CARL, and the real engagements behind them in the database, with every fact and number carrying a basis. Implemented in `prep` and its story rules module.

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

### Requirement: Show a story in a style
`show` SHALL accept a style and display the story with that style's part names, order and mapped text, without changing the stored story. With no style given, the profile default applies.

#### Scenario: Show as soar
- **WHEN** `show STORY --style soar` is run
- **THEN** the story is shown as Situation, Obstacle, Action, Result

#### Scenario: Cheat sheet in a style
- **WHEN** the one-page cheat sheet is produced with a style
- **THEN** it uses that style's headings for the parts, and shows the spoken versions as written

### Requirement: Set a story part by style name
`set` SHALL accept a part name of the chosen style, such as obstacle or learning, and save it to the field that part maps to, telling the user which field was written.

#### Scenario: Set the learning
- **WHEN** `set STORY learning "..." --style carl` is run
- **THEN** the text is saved as the story's lessons

#### Scenario: Part from another style
- **WHEN** a part name that does not belong to the chosen style is given
- **THEN** the command fails with status 1 and lists the parts that do

#### Scenario: Challenge over an existing task
- **WHEN** `set STORY challenge "..." --style carl` is run for a story whose task has text
- **THEN** it is refused unless `--merge` is given, as described for answer styles

### Requirement: Done is checked in the style in force
`set STORY status done` SHALL check completeness in the style given or the profile default, and SHALL leave the stored status unchanged when it refuses.

#### Scenario: Refused done
- **WHEN** a story lacks a part of the chosen style and is marked done
- **THEN** the status stays as it was and the missing parts are named

### Requirement: Validate reports style gaps as warnings
`validate` SHALL accept a style and, for a story already done, SHALL report parts missing in that style as warnings, failing only when the story is complete in none of the three styles.

#### Scenario: Validate everything after changing the default
- **WHEN** the profile default changes from star to carl and `validate` is run
- **THEN** it exits with status 0 and lists, as warnings, the done stories with no lessons

### Requirement: Rank stories for a target company
`for-target [COMPANY]` SHALL rank stories for a target company as described for target companies, and SHALL show for each story whether it is complete in the company's suggested style. With no company given it SHALL use the profile's default company and say so.

#### Scenario: Ranking with completeness
- **WHEN** `for-target COMPANY` is run
- **THEN** each ranked story shows whether it is complete in the suggested style

#### Scenario: No company and no default
- **WHEN** `for-target` is run with no company and no default is set
- **THEN** the command fails with status 1 and lists the profiles that exist
