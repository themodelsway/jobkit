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
- **WHEN** `search --skill Python` is run
- **THEN** only bullets tagged with that skill are listed

#### Scenario: Search limit cuts the list
- **WHEN** more bullets match than `--limit` allows
- **THEN** each company is named once above its bullets, and the last line gives the total and, per company, the number of matches not shown

### Requirement: Build a tailored resume
The system SHALL write a markdown resume to `output/resumes/<jd name>.md` under the home folder (or `-o`) with the best summary, top bullets per company (default 4, at most 2 for old companies), the skills that matter for the posting, certifications and education, with the header taken from the name and contact line saved with `profile header set`; when none is saved, from the older `profile/header.md` file in the home folder; when neither exists, the placeholder header, which the build report flags.

The skills section SHALL list, by group, the skills the posting names first and then stored skills that share a meaningful word with the posting, at most 10 per group, the skill found in most resume files first, and the group with the most posting skills first. It SHALL NOT list a skill the posting neither names nor echoes.

#### Scenario: Skills follow the posting
- **WHEN** a posting names PostgreSQL and asks for stakeholders and stream processing
- **THEN** the skills section lists PostgreSQL, then Stakeholder management and Stream Processing Systems, and leaves out unrelated stored skills

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
The build SHALL print each experience line within 200 characters when it can: the user's approved shorter wording, else the stored line when it fits, else the longest stored wording of the same line that fits. A line that still exceeds the limit SHALL be printed as stored, never cut or rewritten, and listed in the build report with its id, marked FAR OVER when it is more than 250 characters. The summary SHALL be one summary with no job title in front of it: the best-fitting one of at most 400 characters; when none of the stored summaries fits, the best-fitting one is used anyway and listed in the build report as over the limit. It SHALL show the user's `years_experience` setting as "N+ years" in place of the career-length phrase only: where a summary has several durations, the longest one that is not a specific skill's ("5 years of Kubernetes experience") is changed and the others are left as they are, and a summary with no such phrase is unchanged. The summary length SHALL be measured, and reported, after that substitution. Approved wording SHALL be used only while it still passes the checks against the stored line, and an entry whose line no longer exists SHALL be reported as unmatched curation.

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
The command SHALL report JD skills with no supporting bullet separately from skills that have evidence but are not shown in this draft, and SHALL judge which skills are shown from the wording the resume prints (approved or stored shorter wording included), not from the stored line or its tags alone, for the report, for coverage repair and for ranking the lines of each employer (`query-resume for-jd` still ranks the stored lines), so a shortened line that no longer shows a requirement is not counted as showing it. It SHALL say the result is a draft to review (titles and dates, claims, contact lines, qualifications, appearance).

#### Scenario: Skill without evidence
- **WHEN** a JD skill has no supporting bullet in the stored data
- **THEN** the report lists it apart from skills that have evidence but are not shown

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
The `resume-lines` tool SHALL list stored lines over the limit, show one line, and validate a proposed wording; a wording SHALL be accepted only when it is within 200 characters and keeps every figure of the stored line without adding one; a figure includes its sign, so "-5%" and "5%" are different figures. Approved wording SHALL be saved with `process-resumes curate add short-wording ID TEXT`, which applies the same checks and never changes the stored line. The skill SHALL propose wording only when the user asks and SHALL save it only after the user accepts it.

#### Scenario: Figure changed
- **WHEN** a proposed wording drops "70%" or adds "80%"
- **THEN** `validate` exits 1 and the save is refused
