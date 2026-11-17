# Role questions

## Purpose

Save sourced, general and personal interview questions by role and practice them in sessions.

## Requirements

### Requirement: Research uses the saved choice and limited search terms

The interview-prep skill SHALL ask about web research when the choice is unset and save an explicit answer. It SHALL use a saved yes before browsing, state the exact search terms, and limit them to the posting's title, level and skills, recent role titles and general stored skills.

#### Scenario: Web research allowed

- **WHEN** the user has agreed and a role needs research
- **THEN** the skill tells the agent to announce the search terms before browsing
- **AND** personal names, contact details, employers, clients, employer-specific products, figures and resume sentences are excluded

#### Scenario: Web research declined or unavailable

- **WHEN** research was declined or the agent cannot browse
- **THEN** the skill tells the agent to use questions labeled general knowledge
- **AND** those questions carry no links or claims about a company or how often a question is asked

### Requirement: Question provenance and atomic save

`questions save` SHALL save or update a complete batch for one role. Cited questions SHALL have an accepted reference link, a quote of at most 40 words, a valid non-future pull date and a vetting confirmation. Local questions SHALL have a general-knowledge or personal label and no citation.

#### Scenario: One invalid entry

- **WHEN** a batch includes a citation from a known user-content site or a question with inconsistent provenance
- **THEN** the whole save is refused and no questions change

#### Scenario: Same local ID in two roles

- **WHEN** two roles save a question with the same local ID
- **THEN** the resulting IDs are different from one another and from cards, stories and leadership questions
- **AND** re-saving the same full ID under its original role updates the existing entry in place

#### Scenario: ID is already in use by a story

- **WHEN** a new question ID would collide with a legacy story or another practice item
- **THEN** the save is refused and the user can choose another local ID
- **AND** new story IDs beginning with the question prefix are reserved for role questions

### Requirement: Research outcomes and freshness

`questions list` SHALL report research state by role independently of its general and personal questions. `questions stale` SHALL use the saved research window for citations and dated unsuccessful searches.

#### Scenario: Nothing qualifying was found

- **WHEN** a completed search returns no qualifying sources and the role has no cited questions
- **THEN** `questions none-found` saves that outcome and its date
- **AND** any general or personal questions remain available

#### Scenario: A citation ages

- **WHEN** its pull date is older than the research window
- **THEN** the role is listed as stale and the question ID is shown for review

### Requirement: Personal prompts are local and grounded

`questions personal` SHALL generate practice prompts locally from admissible resume claims or posting requirements with no matching evidence. Each prompt SHALL reference a stored bullet ID or the posting requirement.

#### Scenario: Alternate wording shows evidence

- **WHEN** a posting requirement is shown only by another stored wording of a resume line
- **THEN** it is not used as a gap prompt

#### Scenario: A requirement has no evidence

- **WHEN** a named posting requirement lacks supporting resume evidence
- **THEN** the prompt asks what relevant experience the user could discuss without assuming they have it

### Requirement: Shared role-question practice

Questions SHALL support practice and tutor sessions, shared confidence, readiness evidence and retests. Removing a question SHALL remove its active progress and preserve historical session answers.

#### Scenario: Graded practice and readiness

- **WHEN** a saved role question is answered and graded solid in a practice session
- **THEN** readiness shows the evidence under role questions, even without a knowledge-card catalog
- **AND** an aging answer is eligible for a retest

#### Scenario: Removed question in a queue

- **WHEN** a saved question is removed after it was queued
- **THEN** the existing session can be resumed and the unavailable question is skipped
