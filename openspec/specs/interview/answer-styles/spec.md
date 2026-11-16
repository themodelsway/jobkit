# interview/answer-styles Specification

## Purpose
Let the user choose how a story is told: STAR, SOAR or CARL. A story is stored once and each style is a labeled view of it, so nothing is rewritten per style.

## Requirements

### Requirement: Three answer styles
The system SHALL offer exactly three answer styles: `star` (Situation, Task, Action, Result), `soar` (Situation, Obstacle, Action, Result) and `carl` (Challenge, Action, Result, Learning). `star` SHALL be the style when none has been chosen.

#### Scenario: List the styles
- **WHEN** the styles are listed
- **THEN** star, soar and carl are shown with their parts in order and a one-line use for each

#### Scenario: Nothing chosen
- **WHEN** no style is set in the profile and none is given on the command
- **THEN** star is used

#### Scenario: Unknown style
- **WHEN** a style other than star, soar or carl is given
- **THEN** the command fails with status 1, names the three valid styles, and changes nothing

### Requirement: A style is a view of one stored story
A story SHALL be stored in one shape whatever the style. Showing a story in a style SHALL NOT change, copy or lose any stored text, and a story written in one style SHALL be viewable in the other two.

#### Scenario: Same story, two styles
- **WHEN** a story filled in as star is shown as carl and then as star
- **THEN** the stored text is identical both times and only the labels and grouping differ

#### Scenario: Showing leaves data alone
- **WHEN** a story is shown in a style
- **THEN** no story, engagement or session is modified

### Requirement: Parts map onto stored fields
In `soar` the Obstacle SHALL be the story's task field. In `carl` the Challenge SHALL be shown as the situation followed by the task, and the Learning SHALL be the lessons field. Action and Result SHALL map to themselves in every style.

#### Scenario: Set an obstacle
- **WHEN** a story part named Obstacle is saved in soar
- **THEN** the text is stored in the task field and shows as Task in star

#### Scenario: Show a challenge
- **WHEN** a story with a situation and a task is shown in carl
- **THEN** its Challenge is the situation followed by the task, and its Learning is the lessons text

### Requirement: Saving a challenge never repeats text
Saving a `carl` Challenge SHALL store the text as the situation. When the task already has text, the save SHALL be refused unless the user asks to merge, and a merge SHALL store the new text as the situation and empty the task, saying so.

#### Scenario: Task is empty
- **WHEN** a Challenge is saved for a story whose task is empty
- **THEN** the text is stored as the situation and the message names that field

#### Scenario: Task has text, no merge asked
- **WHEN** a Challenge is saved for a story whose task has text, without asking to merge
- **THEN** it is refused, nothing is stored, and the message offers the two ways forward: edit situation and task separately, or merge

#### Scenario: Merge
- **WHEN** a Challenge is saved with a merge for a story whose task has text
- **THEN** the new text is the situation, the task is empty, and the message says the task was folded into the challenge

#### Scenario: Read, edit, save, read
- **WHEN** a Challenge is shown, edited, saved with a merge, and shown again
- **THEN** the second view is exactly the edited text, with nothing repeated

### Requirement: Marking done is checked in the style in force
A story SHALL be accepted as `done` only when every part of the style in force for that command has text, and a refusal SHALL name the missing parts and leave the stored status unchanged.

#### Scenario: Done in carl without a task
- **WHEN** a story has situation, action, result and lessons but no task and is marked done in carl
- **THEN** it is accepted

#### Scenario: Done in star without a task
- **WHEN** the same story, not yet done, is marked done in star
- **THEN** it is refused and Task is named as missing

#### Scenario: Missing learning
- **WHEN** a story with no lessons is marked done in carl
- **THEN** it is refused and Learning is named as missing

### Requirement: A done story stays valid in any style
A story already stored as `done` SHALL pass validation when it is complete in at least one of the three styles. Being incomplete in the style in force SHALL be a warning that names the missing parts, never an error.

#### Scenario: Done in carl, default changed to star
- **WHEN** a story marked done in carl has no task and all stories are validated with star in force
- **THEN** validation succeeds and warns that Task is empty in star

#### Scenario: Existing star stories under a carl default
- **WHEN** stories marked done before this change have no lessons and are validated with carl in force
- **THEN** validation succeeds and warns that Learning is empty in carl

#### Scenario: Complete in no style
- **WHEN** a done story has its action emptied
- **THEN** validation fails, as it does today

### Requirement: Existing checks still apply in every style
Facts and metrics SHALL keep their basis rules, hedged numbers SHALL still need hedging words, and the warning about "we" outnumbering "I" in the action SHALL still apply, whatever the style.

#### Scenario: Estimated number in carl
- **WHEN** a carl story states an estimated figure without hedging
- **THEN** validation warns exactly as it does in star

### Requirement: Style prompts for filling a story
When the user is asked for the parts of a story, each prompt SHALL use the chosen style's own part names and order. SOAR SHALL ask what stood in the way, and CARL SHALL ask what the user learned and would do differently.

#### Scenario: Next prompt in soar
- **WHEN** the next missing part of a soar story is the obstacle
- **THEN** the prompt asks what got in the way and does not mention a task

### Requirement: Spoken versions are shown as written
A spoken version SHALL be shown exactly as stored in every style, and its word limits SHALL be the same in every style. When a story is shown in a style, the output SHALL say that the spoken versions are not rearranged to that style.

#### Scenario: Spoken text in another style
- **WHEN** a story with a spoken short version is shown in carl
- **THEN** the spoken text is unchanged and a note says it is shown as written

#### Scenario: Same warning in every style
- **WHEN** a spoken short version is over the word limit
- **THEN** validation gives the same warning whichever style is in force

### Requirement: Style in force
The style for a command SHALL be, in order: the style given on the command, the session's current style when the command acts on a session, the profile default, then star.

#### Scenario: Profile default
- **WHEN** the profile default is carl and a story is shown with no style given
- **THEN** it is shown in carl

#### Scenario: Session before profile
- **WHEN** the profile default is star and an answer is logged in a session whose current style is soar
- **THEN** soar is the style in force
