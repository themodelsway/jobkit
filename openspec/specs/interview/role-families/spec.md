# interview/role-families Specification

## Purpose
Lets knowledge practice fit any role by grouping tracks into role families, all equal, each with a default rubric that a track uses unless its seed gives its own. Engineering is one family among the others, not a default.

## Requirements

### Requirement: Bundled role families
The plugin SHALL ship the role families people, design, strategy, product, delivery, finance, sales-marketing, operations and engineering, each with a label, a short description of the roles it fits, example focus areas, the kind of official source its facts come from, and a default rubric of at least four lines. Nothing personal or company-specific SHALL be in them.

#### Scenario: Every family is usable
- **WHEN** the bundled families are loaded
- **THEN** each has a label, a description, at least three examples, its official sources and at least four non-empty rubric lines

### Requirement: Families can be listed
`cards families` SHALL print each family's name, label, description, examples, official sources and default rubric, and SHALL change nothing.

#### Scenario: Listing
- **WHEN** `cards families` is run
- **THEN** every family is printed with its examples, sources and rubric, and no stored data changes

### Requirement: A track's family and rubric
A track SHALL belong to the family its seed names; a seed SHALL name its family, and no family is used by default. A track SHALL use the rubric its seed gives, or its family's default rubric when the seed gives none; the bundled AWS track SHALL keep its own rubric.

#### Scenario: Seed without a family
- **WHEN** `cards track add` is given a seed that names no family
- **THEN** it is refused, and the message lists the families

#### Scenario: Seed with a family and no rubric
- **WHEN** a seed names the product family and gives no rubric
- **THEN** its cards show the product family's default rubric

#### Scenario: Seed with its own rubric
- **WHEN** a seed names the people family and gives its own rubric
- **THEN** its cards show the seed's rubric

### Requirement: Family shown with the track
`cards tracks` SHALL show each track's family next to its name.

#### Scenario: Tracks listed
- **WHEN** AWS and a product track are enabled and `cards tracks` is run
- **THEN** AWS is shown as engineering and the other as product
