# resumes/match-score Specification

## Purpose
Rate how well the stored resume lines cover a job posting, as a lower and an upper score with the gaps and assumptions behind them, counting only admissible evidence. Implemented in `match-score`.

## Requirements

### Requirement: Denied use is not credit
A stored line SHALL be `not_demonstrated` for a skill only when a clause naming that skill, or in a line tagged with that one skill a clause naming none, explicitly says the skill was not used professionally (for example "no production use", "never used"). Such a line SHALL earn no credit for that skill. A denial about one skill SHALL NOT remove credit for another skill in the same line.

#### Scenario: Explicit denial
- **WHEN** the only line that mentions Python says "No production use of Python"
- **THEN** the skill earns no credit from that line and the report lists the line as not demonstrated in the profile

#### Scenario: Denial about another skill
- **WHEN** a line says "Did not use Java in production; built Python services" and is tagged with both skills
- **THEN** Java earns no credit from it and Python is rated from it normally

### Requirement: Training wording is capped, not dropped
A line that reads like training only (completed a course, tutorial, bootcamp or introduction; beginner-level, introductory course or coursework-only wording) and does not deny use SHALL be `confirm_use`. It SHALL count, but a skill backed only by such lines SHALL be rated at most partial; an ordinary line SHALL be rated as before. The same rules SHALL apply to ranking and building.

#### Scenario: Training wording only
- **WHEN** the only line for a skill says "Completed a Kubernetes bootcamp"
- **THEN** the skill is rated partial and the report lists the line as reading like training

#### Scenario: Wording that is not a denial
- **WHEN** a line says "Led a beginner-friendly Python workshop for ten engineers"
- **THEN** it is neither a denial nor training wording, and the skill is rated from it normally

#### Scenario: Training plus an ordinary line
- **WHEN** a skill has one bootcamp line and one ordinary line that shows it
- **THEN** the skill is rated from the ordinary line and the bootcamp line is only listed

### Requirement: Set-aside lines are always listed
Every line in either state SHALL be listed with its reason in the match-score report and the build-resume output, never dropped silently. The match-score command SHALL NOT ask the user anything; a resume build MAY ask whether a `confirm_use` skill was also used at work.

#### Scenario: Match-score never asks
- **WHEN** a posting is scored and a line is `confirm_use`
- **THEN** the report states it as an assumption and asks nothing
