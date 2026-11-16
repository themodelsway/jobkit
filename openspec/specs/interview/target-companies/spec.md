# interview/target-companies Specification

## Purpose
Hold researched facts about how a company hires, each with a reference link and the date it was read, so the user can rank stories and practice against a company's emphasis. The `interview-prep` skill tells the agent to research and vet; the commands check what they can see, and store, date and age the facts. Requirements that describe the agent's part say what the skill SHALL tell the agent to do, because the commands cannot check it. Nothing is shipped in the package.

## Requirements

### Requirement: Company profile content
A company profile SHALL hold the company's name and its facts, each of one kind: value (a name and a short description), round, grading note, typical question or questioning style, plus an optional suggested answer style. Nothing personal SHALL be stored in it.

#### Scenario: Show a profile
- **WHEN** a company's profile is shown
- **THEN** its values, rounds, grading notes, typical questions, suggested style, state and each fact's link, label and date of pull are listed

#### Scenario: Unknown company
- **WHEN** a company that has no profile is requested
- **THEN** the command fails with status 1 and lists the profiles that exist

#### Scenario: Name in another case
- **WHEN** a profile saved as Acme is requested as acme
- **THEN** the same profile is found

### Requirement: Every stored fact has a reference link
Every fact SHALL have an id unique in its profile, a reference link (http or https), a quote of at most 40 words, a label and a date of pull. A fact missing any of these SHALL be refused. The skill SHALL tell the agent to copy the quote word for word from the linked page; the command cannot check that it is on the page.

#### Scenario: No link
- **WHEN** a fact is saved with no reference link
- **THEN** it is refused, nothing is stored, and the message says every fact needs a link

#### Scenario: No quote or too long
- **WHEN** a fact is saved with no quote, or a quote of 41 words
- **THEN** it is refused and the message says what is wrong

### Requirement: Two reference labels
A fact's label SHALL be `company-references` when its link is on a site the company publishes, or `othersite-references` for any other site, and no other label SHALL be accepted. The label and the site's name SHALL be shown beside every fact.

#### Scenario: Invalid label
- **WHEN** a fact is saved with a label other than the two
- **THEN** it is refused and the message names the two labels

#### Scenario: Labels shown
- **WHEN** a profile is shown
- **THEN** each fact shows its label and the name of the site it came from

### Requirement: No user-written content
The skill SHALL tell the agent not to take a fact from reviews, interview reports, salary posts, comments or other content written by individual users, on any site. The command SHALL refuse a link on a known user-content site or page pattern (a fixed list in code); it cannot recognize other user-written pages.

#### Scenario: Forum link
- **WHEN** a fact is saved with a link on a forum or question-and-answer site
- **THEN** it is refused and the message says user-written content is not accepted

#### Scenario: Review page on a job site
- **WHEN** a fact is saved with a link to a company's review or interview-report page on a job site
- **THEN** it is refused

#### Scenario: Editorial article
- **WHEN** a fact is saved with a link to an article the site itself published about a company's hiring process
- **THEN** it is accepted with the label othersite-references

### Requirement: Each saved fact carries the agent's vetting confirmation
The skill SHALL tell the agent to read the page, check that the quote is on it and that the content is not written by individual users, and confirm this for each fact in the save. A save without the confirmation SHALL be refused, and the confirmation SHALL be stored with the fact. The command checks that the confirmation is present, not that the agent did what it confirms.

#### Scenario: Not vetted
- **WHEN** a fact is saved without the confirmation
- **THEN** it is refused and nothing is stored

#### Scenario: Vetted fact shown
- **WHEN** a vetted fact is shown
- **THEN** it shows that it was vetted and the date of pull

### Requirement: Date of pull
Each fact SHALL carry the date the page was read. A date in the future SHALL be refused.

#### Scenario: Future date
- **WHEN** a fact is saved with a date of pull after today
- **THEN** it is refused

### Requirement: A save is all or nothing
A save SHALL be given as a file or on standard input. If any fact is refused, nothing SHALL be stored. Saving a fact whose id already exists SHALL replace it and leave the other facts in place.

#### Scenario: One bad fact
- **WHEN** a save holds ten facts and one has no link
- **THEN** the command fails with status 1, names that fact, and nothing is stored

#### Scenario: Save again
- **WHEN** a fact with an existing id is saved again with new wording
- **THEN** the fact shows the new wording and the other facts are unchanged

#### Scenario: Wrong shape
- **WHEN** a save gives an id, a question's value or a suggestion's fact that is not text, or a link that cannot be parsed
- **THEN** nothing is stored and the command exits with status 1, naming the fact and the problem, without a traceback

#### Scenario: Theme the user does not have
- **WHEN** a value names a theme that none of the user's stories or questions use
- **THEN** the value is stored and the command warns that this theme matches nothing yet

### Requirement: Company state
A company SHALL be shown in exactly one state: `fresh` (every fact read within the research window), `stale` (any fact read before the window), `none found` (researched, nothing qualified, with its date) or `not researched`. The window SHALL be the profile's research days, 30 by default.

#### Scenario: Fresh
- **WHEN** every fact was read 10 days ago and the window is 30
- **THEN** the company is fresh

#### Scenario: Stale
- **WHEN** one fact was read 31 days ago and the window is 30
- **THEN** the company is stale and that fact's id is listed

#### Scenario: Never researched
- **WHEN** a company has no profile and no none-found record
- **THEN** its state is not researched

### Requirement: Nothing found
When no page qualifies, the skill SHALL tell the agent to record `none found` (the command stores it with the date), to tell the user in plain words that no official or hiring-process page was found, to carry on in the style in force without a company emphasis, and to invent no fact.

#### Scenario: Small company
- **WHEN** research finds no qualifying page
- **THEN** a none-found record with today's date is stored, the user is told, and a practice session uses the style in force

#### Scenario: Not repeated while fresh
- **WHEN** a none-found record is younger than the window
- **THEN** the company is not researched again

#### Scenario: Practice without the company
- **WHEN** `prep for-target`, `readiness --target` or `sessions new --target` names a company recorded as none found, or the command falls back to a default company recorded as none found
- **THEN** the command exits with status 1, says that research found nothing to prepare against, and the skill tells the agent to practice without the company

### Requirement: No web access
When the agent cannot read pages (for example Codex in its default sandbox), the skill SHALL tell the agent not to research, to say so once in plain words, to use the style in force, and to record nothing. The skill SHALL NOT offer a fallback that asks the user to paste page text.

#### Scenario: Cannot read pages
- **WHEN** a company is named and the agent cannot read pages
- **THEN** the user is told once, the style in force is used, and no company record or fact is created

### Requirement: Research uses only the company and role
The skill SHALL tell the agent to search with only the company's name and the role title, and to put none of the user's name, employers, contact details or resume text in a search or a fact.

#### Scenario: Search terms
- **WHEN** a company is researched for a role
- **THEN** the searches contain only the company name and the role title

### Requirement: Stale facts are re-read
The skill SHALL tell the agent to re-read a stale company when it is next needed. Where the quote is still on the page, the agent records that (`recheck`) and the command sets the date of pull to today. Where the page no longer has it or says something different, the skill SHALL tell the agent to show the user the old and new wording and to replace or remove the fact only after the user responds with yes. Where the page cannot be read, the fact stays and the command lists it as stale.

#### Scenario: Unchanged page
- **WHEN** a stale fact's quote is still on its page
- **THEN** its date of pull is today and its wording is unchanged

#### Scenario: Changed page
- **WHEN** the page now says something different
- **THEN** the user sees the old and new wording and nothing changes until the user responds with yes

#### Scenario: Page cannot be read
- **WHEN** a stale fact's page cannot be read
- **THEN** the fact is kept, listed as stale, and its date is unchanged

#### Scenario: Last fact
- **WHEN** removing a fact, with the typical questions of a removed value, would leave the company with no facts
- **THEN** the command fails with status 1, removes nothing, and names `target remove` for dropping the company's research

### Requirement: Suggested answer style
A profile MAY hold a suggested answer style with a basis. `stated` SHALL point to a stored fact that says it. `inferred` SHALL list the ids of the facts it rests on and be shown as a suggestion, never as the company's word. It SHALL NOT change the style in force.

#### Scenario: Stated
- **WHEN** a stored fact says the company asks for STAR answers
- **THEN** the suggestion shows star with that fact

#### Scenario: Inferred
- **WHEN** the agent suggests carl from two stored facts
- **THEN** it is shown as our suggestion with those two fact ids

#### Scenario: Style in force
- **WHEN** a suggested style exists and a session is started with no style
- **THEN** the style in force is still decided by the command option, the session, the profile default, then star

### Requirement: Values match stories by theme and by word
Each company value MAY list story themes and hint words, which are the user's mapping and not claims about the company. A story SHALL match a value by theme when its theme or extra themes are listed, and by word when a hint word appears as a whole word, in any letter case, in its text.

#### Scenario: Matching theme
- **WHEN** a story's theme is listed under a value
- **THEN** the story matches that value by theme

#### Scenario: Matching hint word
- **WHEN** a value lists the hint word "deadline" and a story's action text contains that word
- **THEN** the story matches that value by word, and the output says so

#### Scenario: Word inside another word
- **WHEN** a value lists the hint word "lead" and a story contains only "misleading"
- **THEN** the story does not match

### Requirement: Each value has one of four states
For a company, each value SHALL be shown as exactly one of: `covered` (a story with content matches by theme), `possible` (stories match only by word), `no story` (the value has themes or hint words and nothing matches), or `needs your judgment` (the value lists neither themes nor hint words).

#### Scenario: Theme match
- **WHEN** a story with content matches a value by theme
- **THEN** the value is covered

#### Scenario: Word match only
- **WHEN** the only matches for a value are by word
- **THEN** the value is possible, never covered, and its stories are listed as matched by word

#### Scenario: Empty story
- **WHEN** the only story matching a value by theme has no content
- **THEN** the value is no story

#### Scenario: Value with no mapping
- **WHEN** a value lists no themes and no hint words
- **THEN** it is needs your judgment, not no story and not covered

### Requirement: Rank stories for a company
The system SHALL rank the user's stories for a company, theme matches before word matches before the rest, show the state of every company value, and show the suggested style when there is one. Stories that are empty SHALL be listed after those with content.

#### Scenario: Ranking
- **WHEN** stories are ranked for a company
- **THEN** each story is listed best match first with the values it matches and how

#### Scenario: All values listed
- **WHEN** stories are ranked for a company
- **THEN** every value of the company appears once with its state

#### Scenario: Read-only
- **WHEN** stories are ranked for a company
- **THEN** nothing stored is changed

### Requirement: Typical questions per value
Typical questions SHALL be shown with their value, whatever its state, when the research found them. Each is a fact with its own link and label. None SHALL be invented when the research found none.

#### Scenario: Questions for a covered value
- **WHEN** a ranked story covers a value that has stored typical questions
- **THEN** those questions are listed with it

#### Scenario: Questions for a value that needs judgment
- **WHEN** a value is needs your judgment and has stored questions
- **THEN** its questions are still listed, so it can be practiced

#### Scenario: No questions found
- **WHEN** a value has no stored typical question
- **THEN** it is listed without questions and none are made up

### Requirement: No invented story content
Profiles and ranking SHALL NOT write or rewrite any story text. Suggested wording SHALL be offered to the user, who decides.

#### Scenario: Gap found
- **WHEN** a value is no story
- **THEN** the output suggests which engagement to build one from and does not create story text

### Requirement: Removing a profile that is in use
Removing a profile SHALL succeed even when sessions or the profile default name it, and the command SHALL say how many sessions name it.

#### Scenario: Profile used by a session
- **WHEN** a profile named by two sessions is removed
- **THEN** it is removed, the message says two sessions name it, and those sessions are unchanged
