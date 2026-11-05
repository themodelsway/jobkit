# aws/architecture-drills Specification

## Purpose
Keep architecture drill cards (services, decision pairs, scenarios) for one or more technologies and the user's confidence, stored in the database. Implemented in `src/jobkit/interview/arch.py` and `tracks.py`; AWS is the bundled example (`src/jobkit/interview/aws/arch_seed.py`); other technologies are track seeds stored in the database.

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

### Requirement: Facts need a source
Lifecycle facts SHALL NOT be seeded; they SHALL be recorded only by `refresh` with a source URL on a documentation host listed by the card's track (for AWS: aws.amazon.com, docs.aws.amazon.com). Lifecycle values SHALL be `active`, `maintenance`, `sunset` or `unverified`.

#### Scenario: Refresh without source
- **WHEN** `refresh` is run without `--source`
- **THEN** the system rejects it

#### Scenario: Source from another track
- **WHEN** a Acme Data card is refreshed with an AWS documentation URL
- **THEN** the system rejects it and names the hosts that track accepts

### Requirement: Choosing cards
The system SHALL pick cards by track, area, tier and kind (service, pair, scenario) in default or random order, list cards that a job description mentions weakest first, and list stale cards (unverified or older than a number of months).

#### Scenario: Stale list
- **WHEN** `stale --months 6` is run
- **THEN** unverified cards and cards verified more than six months ago are listed

### Requirement: Seed is idempotent
`init` SHALL create or extend the catalog from the seed and never overwrite existing progress.

#### Scenario: Second init
- **WHEN** `init` runs twice
- **THEN** progress is unchanged

### Requirement: Several technologies without code
The system SHALL let the user prepare for several technologies at once. AWS SHALL be bundled; any other technology SHALL be added as a validated JSON seed (`arch track add NAME --seed FILE|-`) holding topic names and documentation hosts but no facts, stored in the database. Each card SHALL belong to one track; ids of non-AWS tracks SHALL start with the track name so names never collide, and cards made before tracks existed SHALL count as AWS.

#### Scenario: Two tracks
- **WHEN** `init --track aws --track acmedata` runs
- **THEN** both sets of cards exist, a service named alike in both has two cards, and `list --track acmedata` shows only the Acme Data ones

#### Scenario: Bad seed
- **WHEN** a seed has no documentation hosts, a URL instead of a host, a tier outside 2-3, or the reserved name `aws`
- **THEN** `track add` rejects it and says which part is wrong

#### Scenario: Init without a track
- **WHEN** `init` runs with no `--track`
- **THEN** it extends the tracks already enabled, or AWS when none is
