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
The system SHALL recognize a section heading from a table of synonyms (for example `Experience`, `Professional Experience`, `Employment History` for work; `Career Highlights`, `Key Achievements`, `Accomplishments` for profile points; `Core Competencies` for skills), ignoring case, a trailing colon, `&` for `and` and letter spacing. `Skills: a, b` SHALL start the skills section with its content; inside the work history only the skills headings (`Skills:`, `Technical Skills:`, `Leadership Skills:`), `Education:`, `Certifications:` and `Summary:` do so, and a job label such as `Technologies:`, `Tech stack:` or `Leadership:` stays in the bullet. A job label on a line of its own (`Technologies` above `Redis, Go`, or `Accomplishments` above bullets) SHALL stay in the job when a dated employer follows before the next heading that is not a job label: its line below is read as `Technologies: Redis, Go` would be, and bullets below it stay bullets of the job. After the last job such a label starts its own section. A known heading whose content is not stored (awards, volunteering, publications, languages, interests, references) SHALL end the section before it. An unknown ALL-CAPS heading inside the work history, with no date range within the next lines and that is not a job title, SHALL end the work history and be reported. A combined `Education and Certifications` block SHALL be split by whether a line names a certification. A file whose work heading has no date range under it SHALL be reported as not a resume.

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
The system SHALL read a job written as `Company | Title | dates`, `Title, Company (dates)`, `Title at Company`, with the title before the employer, with a place line, or with several titles at one employer. An employer SHALL NOT be a job title or a place; a name that holds a title word (`Principal Labs`) is the employer when a clearer title stands in the same header, between it and the dates, or just after the dates, in any order. A header written `Company | Title` with its dates on the next line SHALL read like one with the dates on the same line. A company, title and dates block SHALL set the employer for later titles with their own dates. Several titles with their own dates under one employer SHALL be several roles of that employer.

#### Scenario: Title first
- **WHEN** a job is `Lead Engineer   09/2021 - Present` followed by the employer on the next line
- **THEN** the employer is the second line and the title is the first

### Requirement: Summary without a heading
The system SHALL, in a file with no summary heading, skip the name and one more line (contact or title), and SHALL keep that second line as the start of the summary when it is running text (60 characters or more, or ending in a full stop) with no email, phone or LinkedIn in it.

#### Scenario: Name then summary
- **WHEN** the line after the name is a long sentence
- **THEN** it is the summary

### Requirement: Bullets without marks
The system SHALL, when a job has no bullet marks at all, start a bullet at a line that follows a line ending in `.`, `;` or `%` and starts with a capital letter, and SHALL report that the bullets were inferred.

### Requirement: Skills in any list style
The system SHALL read skills with or without bullet marks, one per line or separated by `,`, `;`, `|`, `·`, `•` or table gaps (two or more spaces in a line with no other separator, three or more otherwise; also in marked entries), with any `Label:` prefix (an unknown label goes to Unsorted and is reported). A line continues the one above only when that line ends in a comma, semicolon, `and`, `or`, `/`, `&` or an open bracket; a lowercase name such as `nginx` is a skill of its own. An item longer than 60 characters SHALL be reported and not stored.

### Requirement: Diagnostics for a parse gone wrong
The system SHALL report an unknown heading that ended the work history, a section heading glued into a bullet, a section with a heading and no content, and profile points that read like a skills list.

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
- **WHEN** a heading reads `Acme-Labs` or `Acme-Works – Principal Engineer`
- **THEN** the employers are `Acme-Labs` and `Acme-Works`

### Requirement: Unparseable resumes are reported
The system SHALL report a file that yields no work history as unparsed with a reason, instead of dropping it silently. A file with a work-experience heading but no known employer under it SHALL be reported too.

#### Scenario: Work heading, no known employer
- **WHEN** a file has a work-experience heading and none of its employers is known
- **THEN** it appears in the unparsed list with that reason

#### Scenario: Plain essay text
- **WHEN** a text file has no recognisable work history
- **THEN** it appears in the unparsed list

### Requirement: Company, title and dates on separate lines
The system SHALL recognize a work-history entry written as the company on one line, the job title on the next and the date range on the next, and SHALL take the company line as the employer. A line above the dates SHALL be read as a title only when it looks like a job title and the line above it could be a company name. Otherwise the line above the dates stays the employer.

#### Scenario: Three-line entry
- **WHEN** a work history has `Acme Corp`, then `Senior Engineer`, then `01/2020 - Present`
- **THEN** the employer found is `Acme Corp`, not `Senior Engineer`, and the entry's title is `Senior Engineer`

#### Scenario: Line above the dates is the employer
- **WHEN** the line above the dates is a company name and the line above that ends the previous bullet
- **THEN** the company name is the employer, as before

#### Scenario: Employer and title on one line
- **WHEN** the line above the dates reads `Acme Corp – Senior Engineer`
- **THEN** the employer is `Acme Corp`, whatever the line above it says
