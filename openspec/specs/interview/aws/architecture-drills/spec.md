# aws/architecture-drills Specification

## Purpose
Keep AWS architecture drill cards (services, decision pairs, scenarios) and the user's confidence in `prep/arch/`. Implemented in `src/jobkit/interview/arch.py`; seed data lives in `src/jobkit/interview/aws/arch_seed.py`.

## Requirements

### Requirement: Catalog and progress are separate
The system SHALL keep facts (catalog) and the user's confidence and notes (progress) in separate files so refreshing facts never touches progress.

#### Scenario: Refresh a card
- **WHEN** `refresh` updates a card's facts
- **THEN** its confidence and notes are unchanged

### Requirement: Confidence scale
Confidence SHALL be 0 (none), 1 (some gaps) or 2 (solid), set by the user or by graded drills.

#### Scenario: Invalid value
- **WHEN** confidence 3 is set
- **THEN** the system rejects it

### Requirement: AWS facts need a source
Lifecycle facts SHALL NOT be seeded; they SHALL be recorded only by `refresh` with a source URL on an aws.amazon.com or docs.aws.amazon.com page. Lifecycle values SHALL be `active`, `maintenance`, `sunset` or `unverified`.

#### Scenario: Refresh without source
- **WHEN** `refresh` is run without `--source`
- **THEN** the system rejects it

### Requirement: Choosing cards
The system SHALL pick cards by area, tier and kind (service, pair, scenario) in default or random order, list cards that a job description mentions weakest first, and list stale cards (unverified or older than a number of months).

#### Scenario: Stale list
- **WHEN** `stale --months 6` is run
- **THEN** unverified cards and cards verified more than six months ago are listed

### Requirement: Seed is idempotent
`init` SHALL create or extend the catalog from the seed and never overwrite existing progress.

#### Scenario: Second init
- **WHEN** `init` runs twice
- **THEN** progress is unchanged
