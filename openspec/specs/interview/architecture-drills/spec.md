# aws/architecture-drills Specification

## Purpose
Keep architecture drill cards (services, decision pairs, scenarios) for one or more technologies and the user's confidence, stored in the database. Implemented in `plugins/jobkit/src/jk/interview/arch.py` and `tracks.py`; AWS is the bundled example (`plugins/jobkit/src/jk/interview/aws/arch_seed.py`); other technologies are track seeds stored in the database.

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
The system SHALL pick cards by track, area, tier and kind (service, pair, scenario, case, role-play) in default or random order, list cards that a job description mentions weakest first, and list stale service cards (unverified or older than a number of months). `status` SHALL count the unverified cards among the same service cards that `stale` lists.

#### Scenario: Stale list
- **WHEN** `stale --months 6` is run
- **THEN** unverified cards and cards verified more than six months ago are listed

#### Scenario: Filter by a new kind
- **WHEN** `next --kind role-play` is run and a track holds role-play cards
- **THEN** only role-play cards are offered

#### Scenario: Existing tracks keep their order
- **WHEN** a track holds only service, pair and scenario cards
- **THEN** `next` and a new architecture session offer the same cards in the same order as before this change

### Requirement: Seed is idempotent
`init` SHALL create or extend the catalog from the seed and never overwrite existing progress.

#### Scenario: Second init
- **WHEN** `init` runs twice
- **THEN** progress is unchanged

### Requirement: Several technologies without code
The system SHALL let the user prepare for several technologies or fields at once. AWS SHALL be bundled; any other track SHALL be added as a validated JSON seed (`arch track add NAME --seed FILE|-`) holding topic names, source hosts and optionally a role family, a rubric and a country, but no facts, stored in the database. Each card SHALL belong to one track; ids of non-AWS tracks SHALL start with the track name, and cards made before tracks existed SHALL count as AWS.

#### Scenario: Two tracks
- **WHEN** `init --track aws --track acmedata` runs
- **THEN** both sets of cards exist, a service named alike in both has two cards, and `list --track acmedata` shows only the Acme Data ones

#### Scenario: Bad seed
- **WHEN** a seed has no source hosts, a URL instead of a host, a tier outside 2-3 or not a whole number, a blank service or pair name, the reserved name `aws`, an unknown family, an empty rubric line, a rubric of more than 12 lines, or no cards of any kind
- **THEN** `track add` rejects it and says which part is wrong

#### Scenario: Seed stored by an earlier version
- **WHEN** a track stored by an earlier version breaks a check added since (such as the rubric of at most 12 lines)
- **THEN** its cards are still created, listed and shown with that track's own rubric

#### Scenario: Stored seed that cannot be read
- **WHEN** a stored seed fails a check that every version made, and `show` is run for one of its cards
- **THEN** the command fails and names the problem, rather than showing another track's rubric

#### Scenario: Seed without services
- **WHEN** a seed holds only scenario, case and role-play cards
- **THEN** `track add` accepts it

#### Scenario: Init without a track
- **WHEN** `init` runs with no `--track`
- **THEN** it extends the tracks already enabled, or AWS when none is

### Requirement: Card ids never clash
A card's id SHALL be made from its track, its kind (none for services, `pair-`, `scn-`, `case-` or `role-`) and the slug of its name. `track add` and `init` SHALL refuse a seed in which two cards get the same id, or in which a card gets the id of a stored card of another kind or another track, and SHALL name both cards, so that no card replaces another or takes over its progress.

#### Scenario: Two cards of one seed
- **WHEN** a seed holds the service "Role conflict" and the role-play "Conflict" (both `<track>-role-conflict`)
- **THEN** `track add` rejects it and names both

#### Scenario: A new card and a stored one
- **WHEN** a track's service card has progress and the seed is changed so that a role-play gets that card's id
- **THEN** `track add` and `init` refuse it, and the stored card and its progress are unchanged

### Requirement: Case and role-play cards
A seed SHALL be able to hold case cards (a title and the situation the interviewer opens with) and role-play cards (a title, the part the agent plays and the goal the user pursues), each stored as a card of its own kind in the seed's track.

#### Scenario: Role-play card shown
- **WHEN** `show` is run for a role-play card
- **THEN** it prints the part the agent plays and the user's goal

#### Scenario: Role-play without a part
- **WHEN** a seed's role-play card has no part
- **THEN** `track add` rejects it and names the card

### Requirement: Each card shows its own track's rubric
`show` SHALL print the rubric of the card's own track, so cards of different tracks are graded against different rubrics.

#### Scenario: Two tracks with different rubrics
- **WHEN** AWS and a product track are both enabled and `show` is run for a product card
- **THEN** it prints the product track's rubric, not AWS's

#### Scenario: AWS unchanged
- **WHEN** `show` is run for an AWS card
- **THEN** it prints the same rubric lines AWS used before this change

### Requirement: Country of a track
A seed SHALL be able to name a country, and `show` SHALL print it for every card of that track.

#### Scenario: Country printed
- **WHEN** a track's seed names the United Kingdom and `show` is run for one of its cards
- **THEN** the output names the United Kingdom
