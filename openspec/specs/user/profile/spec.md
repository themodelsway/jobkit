# user/profile Specification

## Purpose
Hold per-user settings in the database under the home folder so committed files stay free of personal data. Implemented in `plugins/jobkit/src/jk/user/profile.py`.

## Requirements

### Requirement: Profile files
The system SHALL keep the settings (resume root, resume folders, optional name and key topics) and the employers found by the first scan (name and regex) in the database, and the header (name and contact line for generated resumes, saved with `profile header set NAME CONTACT_LINE`) in the database; an older `profile/header.md` file is still read when no header is saved.

#### Scenario: Init
- **WHEN** `init --resume-root PATH` is run
- **THEN** the settings are stored and an existing answer is not overwritten

#### Scenario: Init again with other answers
- **WHEN** `init` is run again with a different resume root, name or folders
- **THEN** the stored values are kept, a line says so, and `set` is the way to change name or resume root

### Requirement: Employers are editable
The system SHALL list the scanned employers with `companies` and let the user rename them and merge them with commands, without editing any file.

#### Scenario: Renamed employer
- **WHEN** `companies rename ID NAME` is run
- **THEN** the next run uses the new name

#### Scenario: Merged employers
- **WHEN** `companies merge FROM INTO` is run
- **THEN** the next run treats both names as the one employer

### Requirement: Employer spellings are reconciled
The resume scan SHALL store spellings of one employer name that differ only in letter case, accents, punctuation, spacing, "&" for "and", a leading "The" or a legal ending (such as Inc, LLC, Ltd, Corp or GmbH) as one employer, named by the spelling in the most resumes, with the other spellings kept as aliases that also match. A scan SHALL never rename or remove a stored employer.

#### Scenario: Spellings of one employer
- **WHEN** the resumes name "Acme Corp", "ACME CORP." and "The Acme Corp, Inc."
- **THEN** one employer named "Acme Corp" is stored, and header lines in any of the three spellings match it

#### Scenario: A new spelling of a stored employer
- **WHEN** a later scan finds "Acme-Labs, LLC" and "Acme Labs" is stored
- **THEN** the spelling is added to "Acme Labs" and no new employer is stored

#### Scenario: A stored employer with a custom pattern
- **WHEN** a scan finds a new spelling of a stored employer whose pattern was edited
- **THEN** that employer is not changed, and the scan names any spelling it could not store

### Requirement: Look-alike employer names are confirmed by the user
Employer names that only look alike (one is the start of the other, one is the initials of the other, or they differ by a letter or two) SHALL NOT be merged by a scan. `companies` SHALL list them as pairs that may be one employer, and the scan SHALL report only the pairs that involve an employer it just added or changed.

#### Scenario: Names that look alike
- **WHEN** the resumes name "Acme Research Group" and "ARG"
- **THEN** both are stored, and `companies` lists them as a pair that may be one employer

#### Scenario: A pair is not reported twice
- **WHEN** a later scan adds an unrelated employer
- **THEN** the scan does not report pairs between employers stored before

### Requirement: Open items
The system SHALL keep personal open items and data notes in the database, listed with `open`, added with `open add TEXT` and closed with `open done ID`.

#### Scenario: Add item
- **WHEN** `open add "check figure"` is run
- **THEN** the item appears in `open`

### Requirement: Personal terms
The system SHALL keep the words that must never be committed (products, clients, patterns, and the derived terms the user ignores) in the database, and SHALL read the user's name, header contact details, resume folder, employer names and the company folder of each resume file from where they are stored instead of copying them.

#### Scenario: Derived term found
- **WHEN** a staged file contains an employer name from the resume scan
- **THEN** `profile terms check --staged` prints the file and line and exits 1

#### Scenario: Ignored term
- **WHEN** a term is ignored with `profile terms ignore TEXT`
- **THEN** `check` no longer reports it and `list` marks it ignored

#### Scenario: Ignored text is checked like an added term
- **WHEN** `profile terms ignore` is given text shorter than three characters or a pattern that is not valid
- **THEN** it is refused, as `profile terms add` refuses it, and nothing is stored

#### Scenario: Company folder below a chosen resume folder
- **WHEN** a chosen resume folder has more than one level, such as `2026/tech`, and a resume is in `2026/tech/Acme Air/`
- **THEN** the company folder term is "Acme Air", not "tech"

### Requirement: Personal terms check
`profile terms check` SHALL report each hit as file and line and exit 1, scanning the staged files as staged (`--staged`), every committable file (`--all`) or given paths, and SHALL skip with a message when there is no database.

#### Scenario: Common words on request
- **WHEN** `profile terms check --all --exhaustive` is run
- **THEN** the ignored terms are checked as well and reported as one block per word with the files that contain it, while the pre-commit hook does not use the option

#### Scenario: Short name
- **WHEN** a short employer name such as ACME is checked
- **THEN** it matches only as a whole word

#### Scenario: No database
- **WHEN** `profile terms check` is run on a machine with no database
- **THEN** it prints a message that the check was skipped and exits 0

### Requirement: Key topics
The user SHALL be able to pin their own key topics (tier 1), for any track and matched by name, with `key-topics`, and running it with no arguments SHALL show the current list.

#### Scenario: Pin topics
- **WHEN** `key-topics TOPIC ...` is run
- **THEN** those topics replace the pinned list and are used instead of the ones derived from the resume scan

#### Scenario: Show list
- **WHEN** `key-topics` is run with no arguments
- **THEN** the current list is printed

### Requirement: Retest window
The profile SHALL hold a retest window, `reassess_days`, as a whole number of days from 1 to 365. `profile set reassess_days N` SHALL store it and reject any other value without changing the stored one. When none is stored the window SHALL be 30, and `profile status` SHALL show which applies.

#### Scenario: Set the window
- **WHEN** `profile set reassess_days 45` is run
- **THEN** the stored window is 45 and `profile status` shows 45

#### Scenario: Invalid value
- **WHEN** `profile set reassess_days 0` or `profile set reassess_days soon` is run
- **THEN** the command fails and the stored window is unchanged

#### Scenario: Nothing stored
- **WHEN** no window has been set
- **THEN** the window is 30 and `profile status` says it is the default

### Requirement: Default answer style
The profile SHALL hold an optional default answer style (star, soar or carl), set with `set` and shown by `status`. It SHALL apply wherever a style is needed and none is given, and a command option SHALL override it for that run only.

#### Scenario: Set the style
- **WHEN** `set answer_style carl` is run
- **THEN** `status` shows carl as the default style

#### Scenario: Invalid value
- **WHEN** `set answer_style bogus` is run
- **THEN** the command fails with status 1, names the valid styles, and the stored value is unchanged

#### Scenario: Override
- **WHEN** a command is given a style different from the default
- **THEN** that run uses it and the stored default is unchanged

### Requirement: Research window
The profile SHALL hold a research window in days, 30 when not set, set with `set research_days N` and shown by `status`. It SHALL decide when a researched company is stale.

#### Scenario: Default
- **WHEN** `research_days` has never been set
- **THEN** `status` shows 30

#### Scenario: Set the window
- **WHEN** `set research_days 60` is run
- **THEN** `status` shows 60 and a fact read 45 days ago is not stale

#### Scenario: Invalid value
- **WHEN** `set research_days 0` or `set research_days soon` is run
- **THEN** the command fails with status 1, says a whole number of days of 1 or more is needed, and the stored value is unchanged

### Requirement: Default target company
The profile SHALL hold an optional default target company, set with `set` and shown by `status`. It SHALL be used only by the commands whose single purpose is to view a company (showing a profile and ranking stories for a company) when no company is given; every other command SHALL apply a company only when one is named.

#### Scenario: Set the company
- **WHEN** `set target_company NAME` is run for a profile that exists
- **THEN** `status` shows it as the default company

#### Scenario: Unknown company
- **WHEN** `set target_company NAME` is run for a company with no profile
- **THEN** the command fails with status 1, lists the profiles that exist, and the stored value is unchanged

#### Scenario: Company with nothing found
- **WHEN** `set target_company NAME` is run for a company recorded as none found
- **THEN** the command fails with status 1, says research found no qualifying page for it, and the stored value is unchanged

#### Scenario: Default used
- **WHEN** a default company is set and stories are ranked for a company with none given
- **THEN** the default is used and the output says so

#### Scenario: Default not applied elsewhere
- **WHEN** a default company is set and a session, a readiness report or a leadership list is run with no company named
- **THEN** the result is the same as with no default set

#### Scenario: Default company removed
- **WHEN** the default company's profile no longer exists and a company view is run with no company
- **THEN** the command fails with status 1, says the default no longer exists, and lists the profiles that do

#### Scenario: Clear the default
- **WHEN** `set target_company ""` is run
- **THEN** `status` shows no default company

### Requirement: Role-question research preference

The profile SHALL accept `question_research` as `yes`, `no` or `unset` and show the saved choice or that the user has not been asked.

#### Scenario: Changing the answer

- **WHEN** the user sets the choice to `no` and later clears it with `unset`
- **THEN** the saved preference first reads `no` and then reads as unanswered
