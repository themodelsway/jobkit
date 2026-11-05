# resumes/parsing Specification

## Purpose
Parse the text of one resume into structured pieces (companies with roles and bullets, summaries, skills, certifications, education). Implemented in `src/jobkit/resumes/parse_resume.py` as pure functions.

## Requirements

### Requirement: Parser contract
The system SHALL expose `parse_resume(text, layout_text)` that takes extracted text and returns structured pieces, with no file or network access.

#### Scenario: Same input twice
- **WHEN** the same text is parsed twice
- **THEN** the results are identical

### Requirement: Two layout families
The system SHALL recognise layout A (`WORK EXPERIENCE`, company with dates, title below, `•` bullets, `Present`) and layout B (`Work History`, `Company – Title`, optional `Role:`/`Client:`, `●` bullets, `§` profile points, `Current`).

#### Scenario: Layout B resume
- **WHEN** a resume uses `Work History` and `●` bullets
- **THEN** each company's bullets and dates are parsed

### Requirement: Work history comes from layout text
The system SHALL read work history from `layout_text`, and other sections from the default reading-order `text`.

#### Scenario: Right-aligned dates
- **WHEN** a heading line ends with two or more spaces then `MM/YYYY - MM/YYYY`, `Present` or `Current`
- **THEN** the dates are split from the heading

### Requirement: Employers come from the profile
The system SHALL match employers using the registry installed from `profile/companies.json` and SHALL NOT contain employer names in committed code.

#### Scenario: No registry
- **WHEN** no employers are installed
- **THEN** work history is not attributed to any company

### Requirement: Unparseable resumes are reported
The system SHALL report a file that yields no work history as unparsed with a reason, instead of dropping it silently.

#### Scenario: Plain essay text
- **WHEN** a text file has no recognisable work history
- **THEN** it appears in the unparsed list
