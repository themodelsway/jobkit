# interview/leadership Specification

## Purpose
Keep leadership interview questions, the user's principle for each, and STAR examples per company stored in the database. Implemented in `lead`.

## Requirements

### Requirement: Question with principle and examples
Each question SHALL hold a principle in the user's own words and a STAR example for any employer in the resume data. The coverage target SHALL be up to three examples, or fewer when there are fewer employers. An example counts only when at least one field has content.

#### Scenario: Add an example
- **WHEN** `example ID COMPANY situation TEXT` is run
- **THEN** that field of the company's example is saved

### Requirement: Not applicable is not a gap
`skip ID COMPANY [REASON]` SHALL mark an employer as not applicable for a question; it SHALL count as covered, be shown separately as not applicable in `list` and the readiness report, and be cleared by `unskip` or by saving a real example. `skip` SHALL be refused when the employer already has an example.

#### Scenario: Never had that role
- **WHEN** `skip ID COMPANY "never managed managers"` is run
- **THEN** `list` shows `not applicable` for that question and readiness does not list it as lacking examples

### Requirement: Profile facts come from the user
Team sizes, reports, budget and cadence SHALL be stored only when the user provides them and SHALL NOT be guessed.

#### Scenario: Missing fact
- **WHEN** a question needs a team size that is not recorded
- **THEN** `status` reports it as a profile gap

#### Scenario: Partly filled profile
- **WHEN** an employer has a title but no team size or budget
- **THEN** `status` still lists that employer with the missing facts (an entered 0 counts as set)

#### Scenario: Blank example
- **WHEN** an example field is set to an empty or whitespace-only value
- **THEN** `list` and the readiness report do not count it


### Requirement: Candidate stories
`show ID` SHALL display the question, profile facts, saved answers and candidate stories from `prep` whose themes match, for the three newest companies.

#### Scenario: Show a question
- **WHEN** `show ID` is run
- **THEN** candidate stories are listed per company

### Requirement: Init keeps answers
`init` SHALL add new questions without overwriting saved answers.

#### Scenario: Re-init
- **WHEN** `init` is run again
- **THEN** existing principles and examples are unchanged
