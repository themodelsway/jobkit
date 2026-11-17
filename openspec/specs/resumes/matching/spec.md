# resumes/matching Specification

## Purpose
Suggest the best stored bullets, summaries and skills for a job description, and build a tailored markdown resume from them. Implemented in `query-resume` and `build-resume`.

## Requirements

### Requirement: Rank for a job description
The system SHALL rank bullets per company, newest company first, from keyword and tag matches, with a recency nudge (default weight 2.0), and SHALL also suggest opening summaries, JD skills with no matching bullet, and skills grouped for featuring.

#### Scenario: Match run
- **WHEN** `for-jd jd.txt` is run
- **THEN** output lists summaries, bullets per company, uncovered JD skills and skill groups

### Requirement: Flagged bullets are hidden by default
Bullets flagged `needs_review` SHALL be excluded from ranking and building unless `--include-review` is given.

#### Scenario: Default build
- **WHEN** a resume is built without the flag
- **THEN** no flagged bullet appears

### Requirement: Search and review
The system SHALL support filtering bullets by skill, company, text and theme, and a `review` view of flagged bullets, one-source skills and untagged themes.

#### Scenario: Skill search
- **WHEN** `search --skill NAME` is run
- **THEN** only bullets tagged with that skill are listed

#### Scenario: Search limit cuts the list
- **WHEN** more bullets match than `--limit` allows
- **THEN** each company is named once above its bullets, and the last line gives the total and, per company, the number of matches not shown

### Requirement: Build a tailored resume
The system SHALL write a Markdown resume to `output/resumes/<jd name>.md` under the home folder by default, or use the path given with `-o`. It SHALL use the best summary, relevant skills, certifications, education and the top bullets per employer.

#### Scenario: Header and initial picks
- **WHEN** a draft is built
- **THEN** the header comes from `profile header set`, the older `profile/header.md` when no header was saved, or a placeholder flagged in the report
- **AND** by default the draft uses up to four bullets per employer and at most two for older employers

#### Scenario: Skill ordering and limits
- **WHEN** the skills section is assembled
- **THEN** it lists the groups with the most posting skills first, with up to ten skills in each group
- **AND** named skills precede skills that echo a meaningful posting word, with the skills found in the most resumes ranked first within each group of matches
- **AND** unrelated skills are excluded

#### Scenario: Skills follow the posting
- **WHEN** a posting names one stored skill and asks for stakeholder work and a topic that another stored skill shares a word with
- **THEN** the skills section lists the named skill first, then the stored skills that echo the posting's words (such as a stakeholder management skill), and leaves out unrelated stored skills

#### Scenario: Skill missing from the first picks
- **WHEN** a JD skill has a matching bullet that the per-employer picks left out
- **THEN** the resume includes a bullet that shows it

#### Scenario: Approval goes stale
- **WHEN** an approved resume file is edited
- **THEN** `--status` reports changed

#### Scenario: Title override
- **WHEN** `--title COMPANY=TITLE` is given
- **THEN** that title is shown for the company

#### Scenario: Same figure, different results
- **WHEN** two selected bullets state different achievements that both say 20%
- **THEN** both are in the resume

### Requirement: Line and summary length
The build SHALL use an approved short wording while it passes validation and report orphaned approvals. It SHALL use a stored wording that fits within 200 characters when available. The build SHALL prefer the best-fitting summary within 400 characters and print it without a job title.

#### Scenario: Text exceeds the target length
- **WHEN** no stored wording fits or the best available summary is over 400 characters
- **THEN** the build keeps the wording or summary and reports the overage

#### Scenario: A career-length setting
- **WHEN** a summary contains a career-length phrase and `years_experience` is set
- **THEN** the build replaces the longest career-level duration with "N+ years" and leaves skill-specific durations alone
- **AND** the summary length is measured after that change

#### Scenario: No wording fits
- **WHEN** a chosen line and all its stored wordings are over 200 characters and no wording is approved
- **THEN** the line is printed as stored and listed in the report

#### Scenario: Line far over the limit
- **WHEN** a printed line is more than 250 characters
- **THEN** the report and `resume-lines list` mark it FAR OVER

#### Scenario: Same line reworded
- **WHEN** two selected lines share five or more content words and at least half of the shorter line's words (hyphens and dashes ignored), with or without a figure
- **THEN** only the better-ranked one is in the resume

#### Scenario: Same result told twice
- **WHEN** two selected bullets share a figure ("70 percent" and "70%" count as the same) and four or more content words
- **THEN** only the better-ranked one is in the resume

#### Scenario: Second build for another posting from stdin
- **WHEN** `build-resume -` is run twice
- **THEN** the second resume is `resume-2.md` and the first is unchanged

### Requirement: An employer with no usable bullet keeps its role line
When the build has no bullet to show for an employer, the resume SHALL still show that employer with its latest role's title and dates, and the build SHALL name the employer in its report. The resume SHALL NOT have an employer heading with nothing under it.

#### Scenario: The employer's only bullet is flagged
- **WHEN** every stored bullet of an employer is flagged and left out
- **THEN** the resume shows the employer and its latest role with title and dates, and the build report names that employer

#### Scenario: Title override on an employer with no bullet
- **WHEN** `--title COMPANY=TITLE` is given for an employer with no usable bullet
- **THEN** that title is shown on its role line

### Requirement: Old companies and repeated claims
Old companies SHALL be those that ended more than eight years ago. A claim SHALL NOT be repeated across companies, and two different results that share one figure (for example two 20% results) SHALL both be kept; only wording that overlaps as well as the figure counts as the same claim. The resume SHALL NOT print an opening headline; job titles appear only in the experience section.

#### Scenario: Old company
- **WHEN** a company ended more than eight years ago
- **THEN** at most 2 of its bullets are chosen

### Requirement: Bullet limit
`--max-bullets N` SHALL limit the total number of bullets. Because each employer keeps at least one bullet, an N below the number of employers with bullets SHALL be rejected with an error that names the minimum. Coverage repair SHALL keep the same per-employer limit as the first selection (two for an old employer).

#### Scenario: Limit below the number of employers
- **WHEN** `--max-bullets` is lower than the number of employers with bullets
- **THEN** the command exits with an error that names the minimum

### Requirement: A build never overwrites an earlier build
The default file name SHALL get `-2`, `-3` and so on when the file exists; an explicit `-o` path SHALL be written as given. Next to each resume the build SHALL write `<name>.build.json` with the job description's fingerprint, the settings, the chosen bullet ids, and the gaps.

#### Scenario: Explicit path
- **WHEN** `-o PATH` names a file that exists
- **THEN** the file is written as given

### Requirement: The build reports its gaps and says it is a draft
The command SHALL report separately the skills with no supporting bullet and the skills with evidence missing from the draft. It SHALL label the result a draft for review.

#### Scenario: Printed wording drives the build
- **WHEN** a chosen line is printed in a shorter wording
- **THEN** reporting, coverage repair and line ranking use what that wording shows
- **AND** `query-resume for-jd` continues to rank stored lines

#### Scenario: Draft review
- **WHEN** the command reports a draft
- **THEN** it calls for review of titles and dates, claims, contact lines, qualifications and appearance

#### Scenario: Skill without evidence
- **WHEN** a JD skill has no supporting bullet in the stored data
- **THEN** the report lists it apart from skills that have evidence but are not shown

### Requirement: The printed wording is chosen for the posting
When no approved wording applies, the build SHALL print, among the stored wordings of a line that fit the line limit, the one that names the most skills and requirements of the posting when it names more than the line's usual wording, and SHALL list the lines printed that way in its report.

#### Scenario: An older wording shows the requirement
- **WHEN** only an older stored wording of a chosen line names a requirement of the posting
- **THEN** the draft prints that wording, the requirement counts as shown, and the report names the line

### Requirement: The build covers the posting
The build SHALL make the whole resume cover the posting: a JD skill that the stored data backs up but the first picks do not show SHALL be covered by bringing in the best-ranked bullet that shows it (added to its employer when there is room, or in place of that employer's last bullet when that bullet shows no needed skill nothing else shows), unless the bullet repeats a chosen claim. The command SHALL report how many JD skills the draft shows.

#### Scenario: Skills shown
- **WHEN** a draft is built
- **THEN** the command reports how many JD skills the draft shows

### Requirement: A built resume is approved explicitly
A built resume SHALL start as a draft. `build-resume --approve FILE` SHALL record approval with a fingerprint of the file and SHALL be refused while the file has the placeholder header. `--status FILE` SHALL report draft, approved, or changed (the file was edited after approval).

#### Scenario: Fresh build
- **WHEN** a resume has just been built
- **THEN** `--status` reports draft

#### Scenario: Placeholder header
- **WHEN** `--approve` is given a file that has the placeholder header
- **THEN** the approval is refused

### Requirement: Shorter wording on request
`resume-lines` SHALL list long lines, show a line and validate proposed wording. Approved wording SHALL be stored with `process-resumes curate add short-wording ID TEXT`, using the same checks and preserving the stored line.

#### Scenario: User requests a rewrite
- **WHEN** the user asks for shorter wording
- **THEN** the skill proposes it and saves it only after acceptance
- **AND** validation requires at most 200 characters and the same figures, including their signs

#### Scenario: Figure changed
- **WHEN** a proposed wording drops "70%" or adds "80%"
- **THEN** `validate` exits 1 and the save is refused
