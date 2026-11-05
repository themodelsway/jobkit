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

### Requirement: Build a tailored resume
The system SHALL write a markdown resume to `output/resumes/<jd name>.md` (or `-o`) with the best summary, top bullets per company (default 4, at most 2 for old companies), matching skills, certifications and education, with the header taken from `profile/header.md`.

#### Scenario: Title override
- **WHEN** `--title COMPANY=TITLE` is given
- **THEN** that title is shown for the company
