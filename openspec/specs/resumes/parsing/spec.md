# resumes/parsing Specification

## Purpose
Parse the text of one resume into structured pieces (companies with roles and bullets, summaries, skills, certifications, education). Implemented in `plugins/jobkit/src/jk/resumes/parse_resume.py` as pure functions.

## Requirements

### Requirement: Parser contract
The system SHALL expose `parse_resume(text, layout_text)` that takes extracted text and returns structured pieces, with no file or network access.

#### Scenario: Same input twice
- **WHEN** the same text is parsed twice
- **THEN** the results are identical

### Requirement: Layout families
The system SHALL recognize layout A (`WORK EXPERIENCE`, company with dates, title below, `•` bullets, `Present`) and layout B (`Work History`, `Company – Title`, optional `Role:`/`Client:`, `●` bullets, `§` profile points, `Current`), and the other forms in the requirements below.

#### Scenario: Layout B resume
- **WHEN** a resume uses `Work History` and `●` bullets
- **THEN** each company's bullets and dates are parsed

### Requirement: Section headings are recognized by meaning
The system SHALL recognize section heading synonyms regardless of case, a trailing colon, the use of `&` for `and`, or letter spacing. A heading may introduce its content on the same line.

#### Scenario: A heading inside work history
- **WHEN** `Skills:`, `Technical Skills:`, `Leadership Skills:`, `Education:`, `Certifications:` or `Summary:` appears in the work history
- **THEN** it starts the corresponding section
- **AND** a job label such as `Technologies:`, `Tech stack:` or `Leadership:` remains in the job

#### Scenario: End of a section
- **WHEN** a known heading for content that is not stored begins a section
- **THEN** the preceding section ends
- **AND** an unknown all-caps heading that has no nearby date range and is not a job title also ends work history and is reported

#### Scenario: Combined education and certifications
- **WHEN** a combined block contains education and certification lines
- **THEN** the parser separates them by whether each line names a certification

#### Scenario: Work heading without dates
- **WHEN** a work heading has no date range under it
- **THEN** the parser reports the file as not a resume

#### Scenario: Job label above its list
- **WHEN** `Technologies` stands on its own line with `Redis, Go` below it, and another dated employer follows
- **THEN** the work history keeps both employers, and the first job reads as it would with `Technologies: Redis, Go`

#### Scenario: Highlights after the work history
- **WHEN** `Career Highlights` follows the last job
- **THEN** its lines are profile points and no bullet of that job

### Requirement: Date ranges in any common style
The system SHALL read a date range written as `MM/YYYY`, `M/YYYY`, `MM/YY`, `YYYY-MM`, `Mon YYYY`, `Month YYYY` or `YYYY`, separated by a dash, `to`, `until` or `till`, ending in Present, Current, Now, Today, Ongoing, `To date` or `Till date`, and SHALL store `YYYY-MM`, or `YYYY` when only a year is given. A date range inside a sentence SHALL NOT start a job.

#### Scenario: Month names and years
- **WHEN** a job header ends with `Sep 2021 – Present` or `2012 – 2017`
- **THEN** the job starts 2021-09 and is current, or runs 2012 to 2017

### Requirement: Job headers in any common shape
The system SHALL read common job headers, with or without a place line, including title before employer and several dated titles at one employer.

#### Scenario: Alternate formats and dates on the next line
- **WHEN** a header uses `Company | Title | dates`, `Title, Company (dates)` or `Title at Company`
- **THEN** the employer and title are kept separately
- **AND** dates on the next line work as they do on the same line

#### Scenario: A name contains a title word
- **WHEN** the header has a company name that contains a title word and a clearer title in the same header, between the name and dates, or just after the dates
- **THEN** the parser takes the name as the employer without treating a standalone job title or place as an employer

#### Scenario: Several dated titles at one employer
- **WHEN** later titles with dates follow a company, title and dates block
- **THEN** the employer remains the same and each dated title gets a separate role

#### Scenario: Title first
- **WHEN** a job is `Lead Designer   09/2021 - Present` followed by the employer on the next line
- **THEN** the employer is the second line and the title is the first

### Requirement: Summary without a heading
The system SHALL, in a file with no summary heading, skip the name and one more line (contact or title), and SHALL keep that second line as the start of the summary when it is running text (60 characters or more, or ending in a full stop) with no email, phone or LinkedIn in it.

#### Scenario: Name then summary
- **WHEN** the line after the name is a long sentence
- **THEN** it is the summary

### Requirement: Bullets without marks
The system SHALL infer bullets for a job that has no bullet marks and report that it did so.

#### Scenario: Start after terminal punctuation
- **WHEN** a line starts with a capital letter and follows a line ending in a period, semicolon or percent sign
- **THEN** it starts an inferred bullet

### Requirement: Skills in any list style
The system SHALL read skills with or without bullets, one per line or separated by `,`, `;`, `|`, `·`, `•` or table gaps. A `Label:` prefix supplies the group.

#### Scenario: Table gaps and unfamiliar labels
- **WHEN** a line has no other separator
- **THEN** two or more spaces separate skills, including marked entries
- **AND** with other separators present, a gap needs at least three spaces
- **AND** an unknown label is reported and its items go to Unsorted

#### Scenario: Wrapped names and long items
- **WHEN** the prior line ends in a comma, semicolon, `and`, `or`, `/`, `&` or an open bracket
- **THEN** the line continues the prior one
- **AND** otherwise a lowercase skill can stand alone
- **AND** an item longer than 60 characters is reported and excluded

### Requirement: Skill group labels are matched by their words
A skill label SHALL map to a group when it is a known label or contains a word that names a group (such as `leadership`, `cloud`, `data`, `web` or `AI`); a `Label, a, b` line SHALL count as labeled only when its first part also has a list word (such as `skills`, `technologies` or `strategy`). An item that only names a category, such as `Web technologies`, SHALL NOT be stored as a skill.

#### Scenario: Label with a group word
- **WHEN** a skills line reads `Leadership Skills: Topic One, Topic Two`
- **THEN** both items go to the Leadership group

#### Scenario: Unlabeled list
- **WHEN** a skills line reads `Data Modeling, Query Tuning`
- **THEN** both items go to Unsorted, because `Data Modeling` has no list word

### Requirement: Diagnostics for a parse gone wrong
The system SHALL report structural problems that make a resume parse suspect.

#### Scenario: Unexpected structure
- **WHEN** an unknown heading ends work history, a heading is glued into a bullet, a heading has no content, or profile points look like a skills list
- **THEN** the parser reports the issue

### Requirement: Work history comes from layout text
The system SHALL read work history from `layout_text`, and other sections from the default reading-order `text`.

#### Scenario: Right-aligned dates
- **WHEN** a heading line ends with two or more spaces then `MM/YYYY - MM/YYYY`, `Present` or `Current`
- **THEN** the dates are split from the heading

### Requirement: Employers come from the profile
The system SHALL match employers using the registry stored in the profile (the employers found by the first scan, changed with the `companies` commands) and SHALL NOT contain employer names in committed code.

#### Scenario: No registry
- **WHEN** no employers are installed
- **THEN** work history is not attributed to any company

### Requirement: Employer and title are split on a dash
The system SHALL split an employer from a title on an en or em dash, or on a hyphen with a space on each side, and SHALL NOT split inside a hyphenated name.

#### Scenario: Hyphenated employer
- **WHEN** a heading reads `Acme-Labs` or `Acme-Works – Principal Strategist`
- **THEN** the employers are `Acme-Labs` and `Acme-Works`

### Requirement: Unparseable resumes are reported
The system SHALL report a file that yields no work history as unparsed with a reason, instead of dropping it silently. A file with a work-experience heading but no known employer under it SHALL be reported too.

#### Scenario: Work heading, no known employer
- **WHEN** a file has a work-experience heading and none of its employers is known
- **THEN** it appears in the unparsed list with that reason

#### Scenario: Plain essay text
- **WHEN** a text file has no recognizable work history
- **THEN** it appears in the unparsed list

### Requirement: Company, title and dates on separate lines
The system SHALL recognize a work-history entry written as the company on one line, the job title on the next and the date range on the next, and SHALL take the company line as the employer. A line above the dates SHALL be read as a title only when it looks like a job title and the line above it could be a company name. Otherwise the line above the dates stays the employer.

#### Scenario: Three-line entry
- **WHEN** a work history has `Acme Corp`, then `Senior Strategist`, then `01/2020 - Present`
- **THEN** the employer found is `Acme Corp`, not `Senior Strategist`, and the entry's title is `Senior Strategist`

#### Scenario: Line above the dates is the employer
- **WHEN** the line above the dates is a company name and the line above that ends the previous bullet
- **THEN** the company name is the employer, as before

#### Scenario: Employer and title on one line
- **WHEN** the line above the dates reads `Acme Corp – Senior Strategist`
- **THEN** the employer is `Acme Corp`, whatever the line above it says
