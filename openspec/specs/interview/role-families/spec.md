# interview/role-families Specification

## Purpose
Lets knowledge practice fit any role by grouping tracks into role families, each with a default rubric that a track uses unless its seed gives its own.

## Requirements

### Requirement: Bundled role families
The plugin SHALL ship the role families engineering, product, delivery, people and operations, each with a label, a short description of the roles it fits, and a default rubric of at least four lines. Nothing personal or company-specific SHALL be in them.

#### Scenario: Every family is usable
- **WHEN** the bundled families are loaded
- **THEN** each of the five has a label, a description and at least four non-empty rubric lines

### Requirement: Families can be listed
`arch families` SHALL print each family's name, label, description and default rubric, and SHALL change nothing.

#### Scenario: Listing
- **WHEN** `arch families` is run
- **THEN** the five families are printed with their rubrics and no stored data changes

### Requirement: A track's family and rubric
A track SHALL belong to the family its seed names, or to engineering when it names none. A track SHALL use the rubric its seed gives, or its family's default rubric when the seed gives none; the bundled AWS track SHALL keep its own rubric.

#### Scenario: Seed without a family
- **WHEN** a track stored before this change is shown
- **THEN** it counts as engineering and keeps the rubric it had

#### Scenario: Seed with a family and no rubric
- **WHEN** a seed names the product family and gives no rubric
- **THEN** its cards show the product family's default rubric

#### Scenario: Seed with its own rubric
- **WHEN** a seed names the people family and gives its own rubric
- **THEN** its cards show the seed's rubric

### Requirement: Family shown with the track
`arch tracks` SHALL show each track's family next to its name.

#### Scenario: Tracks listed
- **WHEN** AWS and a product track are enabled and `arch tracks` is run
- **THEN** AWS is shown as engineering and the other as product
