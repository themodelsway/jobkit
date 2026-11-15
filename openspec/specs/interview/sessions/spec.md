# interview/sessions Specification

## Purpose
Keep resumable practice and tutor sessions stored in the database, with the user's full answers. Implemented in `sessions`.

## Requirements

### Requirement: Session is one file with a queue and a log
A session SHALL hold a queue of items (architecture cards, stories or leadership questions) and an append-only log that keeps the user's full answers.

#### Scenario: Re-drill a topic
- **WHEN** a topic is drilled in a later session
- **THEN** the new session logs it and the old session is not edited

#### Scenario: Log entry for an unknown item
- **WHEN** an answer is logged for an item that does not exist
- **THEN** the command fails and the log is unchanged

### Requirement: Resume and close
The system SHALL show what was covered, the last answers and the next item to ask on `resume ID`, and SHALL allow `close` and `reopen`.

#### Scenario: Reopen
- **WHEN** a closed session is reopened
- **THEN** it continues from its next unasked item

### Requirement: Modes
A session SHALL have a mode of architecture, stories, jd, leadership or tutor, and SHALL be narrowable by track, area, tier, kind, company, category and count. Without `--mode`, the mode is jd when `--jd` is given and architecture otherwise; `--jd` with any other explicit mode is an error.

#### Scenario: JD mode
- **WHEN** a session starts with `--jd`
- **THEN** its queue holds the items that job description touches, and the saved mode is jd with the JD recorded

#### Scenario: Count cuts a JD queue
- **WHEN** a jd session matches more cards and stories than `--count` allows
- **THEN** the queue takes a card and a story in turn until one kind runs out, and the start message gives the number of each kind queued and the number of matching items left out

#### Scenario: JD with filters
- **WHEN** a jd session is started with `--track`, `--area`, `--tier` or `--kind`
- **THEN** only the matched cards that pass every filter are queued

#### Scenario: JD with another mode
- **WHEN** `--jd` is given with `--mode stories`
- **THEN** the command fails and says to drop one of them

### Requirement: Teaching caps confidence
In tutor sessions a logged confidence SHALL be capped at 1, and a passed quiz (`--quiz`, which needs `--grade` and confidence 2) SHALL allow 2. `--quiz` SHALL be rejected outside tutor sessions.

#### Scenario: Taught but not quizzed
- **WHEN** a tutor log has confidence 2 without `--quiz`
- **THEN** it is stored as 1

### Requirement: A lesson does not refresh a drill date
A tutor lesson that does not raise confidence SHALL NOT change the item's last-drilled date, so old solid answers still read as aging.

#### Scenario: Lesson on an old solid card
- **WHEN** a tutor lesson without a passed quiz is logged for a card at confidence 2
- **THEN** its last-drilled date is unchanged

### Requirement: Confidence is shared
Confidence per architecture card SHALL be stored once, outside any session, and SHALL be shared across sessions.

#### Scenario: Two sessions
- **WHEN** a card is graded in session B after session A
- **THEN** the card shows the latest confidence in both

### Requirement: Queue uses the retest window
The age after which a solid card is queued before recently solid ones SHALL be the stored retest window (30 when none is stored). `sessions new --due` SHALL queue only the items that `readiness --due` lists.

#### Scenario: Stored window changes the order
- **WHEN** the stored window is 60 and a solid card was last drilled 45 days ago
- **THEN** the card is queued with the recently solid ones, not before them

#### Scenario: Due-only queue
- **WHEN** a session is created with `--due` and two items are due
- **THEN** its queue holds exactly those two items

### Requirement: A due-only session with no mode covers every kind of item
`sessions new --due` with no `--mode` and no `--jd` SHALL queue the items `readiness --due` lists, across architecture cards, leadership questions and stories, oldest first. Each kind SHALL apply the filters that belong to it. The session SHALL be stored with the mode `retest`. With a `--mode` or `--jd`, the session SHALL queue only the due items of that mode.

#### Scenario: Only a leadership question is due
- **WHEN** only a leadership question is due and `sessions new "title" --due` is run
- **THEN** a session is created with that question in its queue

#### Scenario: Items of different kinds are due
- **WHEN** a card and a story are due and the card is older, and `sessions new "title" --due` is run
- **THEN** the queue holds exactly those two items, the card first, and the session's mode is `retest`

#### Scenario: A mode narrows the queue
- **WHEN** a card and a story are due and `sessions new "title" --due --mode stories` is run
- **THEN** the queue holds only the story

#### Scenario: Nothing is due
- **WHEN** no item is due and `sessions new "title" --due` is run
- **THEN** the command says nothing is due and no session is created

### Requirement: A queued item whose target was removed
A queued item whose card, question or story no longer exists SHALL stay in the session and be shown as unavailable. The session SHALL move on to the next item. An answer to that item SHALL be refused with a message until the item exists again.

#### Scenario: Next item is unavailable
- **WHEN** the next queued item's card has been removed and a session is resumed
- **THEN** the item is reported as unavailable, the following item is shown and the command succeeds

#### Scenario: Answering an unavailable item
- **WHEN** an answer is logged for a queued item whose target has been removed
- **THEN** the command exits with status 1 and nothing is stored

#### Scenario: Target restored
- **WHEN** the removed item exists again
- **THEN** an answer to it is accepted

### Requirement: Session records a company and a style
`new` SHALL accept `--target COMPANY` and `--style STYLE`, store both on the session, and show them in `list` and `resume`. With no `--style` the session SHALL record the profile's default style; with no `--target` it SHALL record no company, whatever the profile's default company is.

#### Scenario: Company and style recorded
- **WHEN** `new "title" --target COMPANY --style soar --mode stories` is run
- **THEN** `list` and `resume` show that company and soar

#### Scenario: Unknown company or style
- **WHEN** a company without a profile or a style other than star, soar or carl is given
- **THEN** the command fails with status 1 and no session is created

#### Scenario: No company
- **WHEN** a session starts without `--target` while the profile has a default company
- **THEN** it behaves as before this change and stores no company

### Requirement: A company orders the queue and never empties it
With `--target`, the queue SHALL hold the same items as without it, with stories and leadership questions that match the company by theme first, then those that match by word, then the rest. Each queued story or question SHALL show the company values it matches and how.

#### Scenario: Matching items first
- **WHEN** `new "title" --target COMPANY --mode stories` is run and two of five stories match by theme
- **THEN** the queue holds all five, those two first, each marked with the values it matches

#### Scenario: More values first
- **WHEN** two stories match by theme, one matching three values and the other one
- **THEN** the story matching three values comes first, and stories matching the same number keep their usual order

#### Scenario: Random order
- **WHEN** `--target` is given with `--order random`
- **THEN** items are shuffled within each group, and every theme match still comes before every word match, and every word match before the rest

#### Scenario: Count keeps the best matches
- **WHEN** `--target` is given with `--count 3` and five stories are queued
- **THEN** the three kept are the first three after ordering by the company

#### Scenario: Nothing matches
- **WHEN** no story matches any value of the company
- **THEN** the session is created with the usual queue, and the output says no story matches this company yet

#### Scenario: Architecture cards
- **WHEN** `--target` is given for a session whose queue holds only architecture cards
- **THEN** the session is created, the cards keep their usual order, and the output says a company does not change card order

#### Scenario: With a job description
- **WHEN** `--target` is given with `--jd`
- **THEN** the items the job description selects are queued, the stories among them ordered by the company

### Requirement: Company session shows what is left to cover
`resume ID` for a session with a company SHALL show, beside the next story or question, what that company's graders look for, and SHALL list the company values that are `no story` or `needs your judgment` with their stored typical questions. Each fact SHALL show its label and the site it came from.

#### Scenario: Resume a company session
- **WHEN** a session with a company is resumed
- **THEN** the output shows the grading emphasis, the style in force, and the values still to cover with their typical questions

#### Scenario: Every value is unmapped
- **WHEN** every value of the company is needs your judgment
- **THEN** all of them are listed with their typical questions, so the session can still be run

#### Scenario: Next item is a card
- **WHEN** the next item of a company session is an architecture card
- **THEN** no grading emphasis is shown beside it

### Requirement: The session's style can be changed
`resume ID --style STYLE` SHALL change the session's current style from then on and say so. Entries logged earlier SHALL NOT change.

#### Scenario: Change on resume
- **WHEN** a carl session is resumed with `--style star`
- **THEN** the session's current style is star in `list` and in later `resume` output

#### Scenario: Next story shown in the session's style
- **WHEN** the next item of a session is a story and the session's style differs from the profile's default
- **THEN** the story is shown grouped as the session's style, after `new`, `resume` (with or without `--style`) and `reopen`

### Requirement: Logged answers keep the style and company
Each entry logged for a story or leadership question SHALL keep the session's current style and company at the time it was logged, and `log` SHALL accept `--style` to record a different style for that one entry. An entry for an architecture card SHALL record no style.

#### Scenario: After a change of style
- **WHEN** a carl session is resumed with `--style star` and an answer is then logged
- **THEN** the new entry records star and earlier entries still record carl

#### Scenario: One answer in another style
- **WHEN** an answer is logged with `--style soar` in a star session
- **THEN** that entry records soar and the session's current style stays star

#### Scenario: Entry logged before this change
- **WHEN** an entry logged before this change is shown
- **THEN** it shows no style and no company, and is otherwise unchanged

### Requirement: Company sessions work with the retest window
`new --due` SHALL accept `--target` and queue the same due items as without it, those matching the company first.

#### Scenario: Due and company
- **WHEN** `new "title" --due --target COMPANY` is run and three items are due, one matching
- **THEN** all three are queued, the matching one first

#### Scenario: Due, company and count
- **WHEN** `new "title" --due --target COMPANY --count 2` is run and four items are due, two matching
- **THEN** the two matching items are kept, the one due longest first

#### Scenario: Due items in the same group
- **WHEN** several due items fall in the same group
- **THEN** the one due longest comes first within that group

#### Scenario: Nothing due
- **WHEN** `new "title" --due --target COMPANY` is run and nothing is due
- **THEN** the command says nothing is due and creates no session, as it does without a company

### Requirement: A session whose company profile was removed
A session that names a company whose profile no longer exists SHALL still be listed, resumed and logged to. `resume` SHALL say the profile is gone and show no grading emphasis, and the queue SHALL keep its stored order.

#### Scenario: Resume after removal
- **WHEN** a session's company profile was removed and the session is resumed
- **THEN** the next item is shown, with a line saying the company's profile no longer exists

#### Scenario: Log after removal
- **WHEN** an answer is logged in that session
- **THEN** it is stored, and the entry still records the company's name
