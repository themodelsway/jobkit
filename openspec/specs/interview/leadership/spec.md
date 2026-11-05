# interview/leadership Specification

## Purpose
Keep leadership interview questions, the user's principle for each, and STAR examples per company in `prep/leadership/`. Implemented in `lead`.

## Requirements

### Requirement: Question with principle and examples
Each question SHALL hold a principle in the user's own words and one STAR example per company, for the most recent three companies.

#### Scenario: Add an example
- **WHEN** `example ID COMPANY situation TEXT` is run
- **THEN** that field of the company's example is saved

### Requirement: Profile facts come from the user
Team sizes, reports, budget and cadence SHALL be stored only when the user provides them and SHALL NOT be guessed.

#### Scenario: Missing fact
- **WHEN** a question needs a team size that is not recorded
- **THEN** `status` reports it as a profile gap

### Requirement: Candidate stories
`show ID` SHALL display the question, profile facts, saved answers and candidate stories from `prep` whose themes match, for the top three companies.

#### Scenario: Show a question
- **WHEN** `show ID` is run
- **THEN** candidate stories are listed per company

### Requirement: Init keeps answers
`init` SHALL add new questions without overwriting saved answers.

#### Scenario: Re-init
- **WHEN** `init` is run again
- **THEN** existing principles and examples are unchanged
