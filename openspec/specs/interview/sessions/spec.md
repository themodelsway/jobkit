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
