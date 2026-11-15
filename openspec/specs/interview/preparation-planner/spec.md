# interview/preparation-planner Specification

## Purpose
Decide what the user should practise next, why, and which of their experience can answer it, keeping knowledge, work experience and performance apart and treating unknown as not yet asked. Rules only: no stored state. Implemented as a rules module that no command uses yet.

## Requirements

### Requirement: Explained actions
The planner SHALL return an ordered list of actions. Each action SHALL carry the competency, one action type (`clarify_fact`, `teach_prerequisite`, `practise_concept`, `rehearse_story`, `reassess`), a reason code, a plain reason, the evidence it uses and the observations it relied on.

#### Scenario: Weak answer with a linked story
- **WHEN** a competency has a graded weak attempt and a confirmed story covers it
- **THEN** the first action is `rehearse_story` naming that story and the weak attempt

### Requirement: Fixed priority order
Actions SHALL be ordered by category: factual blocker, unmet prerequisite, never tested, observed weakness, due reassessment. Within a category the order SHALL be stable (by competency id). A user focus SHALL reorder only within a category.

#### Scenario: Focus does not skip a blocker
- **WHEN** the user focuses a competency that has no blocker while another has an unclear fact
- **THEN** the `clarify_fact` action still comes first

### Requirement: Knowledge, experience and performance stay separate
A passed quiz SHALL raise knowledge only. Experience SHALL come only from confirmed facts and stories. A finished story SHALL NOT count as delivery quality.

#### Scenario: Quiz without work evidence
- **WHEN** a quiz on a competency is passed and no confirmed fact covers it
- **THEN** the plan asks about real use (`clarify_fact`, reason `profile_gap`), and experience stays empty

### Requirement: Unknown is not failed
A competency with no graded attempt SHALL be reported as never tested (reason `untested`, or the more specific `profile_gap` when nothing is recorded for it). Historical self-rated confidence SHALL stay as it was and SHALL NOT be turned into a graded observation.

#### Scenario: Only a coarse confidence
- **WHEN** a competency has only an old confidence of 1
- **THEN** it is in the never-tested group (reason `profile_gap`, since nothing is recorded) and the self-rating is shown separately, not as a grade

### Requirement: Unclear facts become a question
A fact marked proposed or unsure, or a story whose ownership is unclear, SHALL give `clarify_fact` naming the missing fact. The planner SHALL NOT supply an answer.

#### Scenario: Unclear ownership
- **WHEN** a story's ownership is unclear
- **THEN** the action is `clarify_fact` and no experience is counted for it

### Requirement: Reassess old good answers
A good answer older than the reassessment window SHALL give `reassess` showing its age. A completed story SHALL remain eligible for `rehearse_story`.

#### Scenario: Forty-day-old good answer
- **WHEN** the last good answer is 40 days old and the window is 30
- **THEN** a `reassess` action shows an age of 40 days

### Requirement: Prerequisites and aliases
A competency with an unmet prerequisite SHALL get `teach_prerequisite` naming the prerequisite and the target. Aliases SHALL resolve to one competency; related competencies SHALL be reported as transferable, never merged. A prerequisite cycle or an alias with two targets SHALL be rejected when the vocabulary is checked.

#### Scenario: Cycle
- **WHEN** A requires B and B requires A
- **THEN** the vocabulary check fails and names both

#### Scenario: Transferable, not direct
- **WHEN** a story covers ECS and the target is Kubernetes
- **THEN** the evidence is marked transferable

### Requirement: Distinct evidence
Evidence SHALL be counted by distinct fact and engagement, not by document or story version. Several stories on one engagement SHALL be offered as choices of one experience.

#### Scenario: Two stories, one project
- **WHEN** two stories use the same engagement
- **THEN** experience counts one event and both stories are listed as choices

### Requirement: Deterministic and storage-free
The planner SHALL give the same output for the same input and date, and SHALL read no database, file or network.

#### Scenario: Repeat
- **WHEN** the same snapshot and date are planned twice
- **THEN** the results are equal

### Requirement: A missing record is a profile gap, not a verdict
A competency with no confirmed fact or story, no graded drill and no finished story to rehearse SHALL give the reason `profile_gap` with the action `clarify_fact`, asking whether the user has used it at work and for a real example. The reason SHALL NOT depend on a passed quiz, and the planner SHALL NOT state or imply that the user has no experience.


#### Scenario: Passed quiz, nothing recorded
- **WHEN** a quiz on a competency is passed and no confirmed fact or story covers it
- **THEN** the action is `clarify_fact` with reason `profile_gap`, experience stays empty and the wording says nothing is recorded yet

#### Scenario: Nothing at all
- **WHEN** a competency has no attempt and no confirmed fact or story
- **THEN** the reason is the same `profile_gap`, with the same action

### Requirement: Profile gap priority and limits
A `profile_gap` action SHALL be in the "never tested" category and come before plain untested actions inside it. A competency with recorded experience but no graded drill SHALL be reported as untested. A weak latest drill SHALL follow the weak-answer rule, not `profile_gap`.

#### Scenario: Recorded experience, no graded drill
- **WHEN** a confirmed fact covers a competency and no drill is graded
- **THEN** the reason is untested, not `profile_gap`

#### Scenario: Not a blocker
- **WHEN** one competency has a `profile_gap` and another has an unmet prerequisite
- **THEN** the prerequisite action comes first

#### Scenario: Weak answer outranks the gap reason
- **WHEN** a competency has no recorded experience and its latest graded drill is weak
- **THEN** the action follows the weak-answer rule, not `profile_gap`

### Requirement: Resume lines are leads, never experience
When a competency has a `profile_gap`, the planner SHALL include the references of any resume lines supplied for it, so the question can name them. A lead SHALL NOT count as a fact or experience, SHALL NOT change the reason or the category, and SHALL NOT be offered when the line is flagged, ignored or not demonstrated for that skill.

#### Scenario: Resume mentions it
- **WHEN** a competency has no confirmed fact and one resume line is supplied for it
- **THEN** the action is still `clarify_fact` with reason `profile_gap`, carries that line's reference, and experience stays empty

#### Scenario: No lead supplied
- **WHEN** no resume line is supplied
- **THEN** the action is the same and carries no references

### Requirement: Knowledge does not expire
A passed quiz or a good drill answer SHALL count as knowledge whenever it happened. An old good answer SHALL produce a `reassess` offer only and SHALL NOT remove knowledge, so a prerequisite known long ago is not taught again.

#### Scenario: Old quiz pass
- **WHEN** a quiz on a prerequisite was passed a year ago
- **THEN** the prerequisite is not taught again
