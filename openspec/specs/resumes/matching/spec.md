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
The system SHALL write a markdown resume to `output/resumes/<jd name>.md` under the home folder (or `-o`) with the best summary, top bullets per company (default 4, at most 2 for old companies), matching skills, certifications and education, with the header taken from `profile/header.md` in the home folder.

Old companies SHALL be those that ended more than eight years ago. A claim SHALL NOT be repeated across companies, and two different results that share one figure (for example two 20% results) SHALL both be kept; only wording that overlaps as well as the figure counts as the same claim. The opening headline SHALL be one that shares words with the job description, and none is shown otherwise. `--max-bullets N` SHALL limit the total number of bullets; because each employer keeps at least one bullet, an N below the number of employers with bullets SHALL be rejected with an error that names the minimum. Coverage repair SHALL keep the same per-employer limit as the first selection (two for an old employer).

The build SHALL NOT overwrite an earlier build: the default file name gets `-2`, `-3` and so on when the file exists (an explicit `-o` path is written as given). Next to each resume it SHALL write `<name>.build.json` with the job description's fingerprint, the settings, the chosen bullet ids, and the gaps. The command SHALL report JD skills with no supporting bullet separately from skills that have evidence but are not shown in this draft, and SHALL say the result is a draft to review (titles and dates, claims, contact lines, qualifications, appearance).

The build SHALL make the whole resume cover the posting: a JD skill that the stored data backs up but the first picks do not show SHALL be covered by bringing in the best-ranked bullet that shows it (added to its employer when there is room, or in place of that employer's last bullet when that bullet shows no needed skill nothing else shows), unless the bullet repeats a chosen claim. The command SHALL report how many JD skills the draft shows.

A built resume SHALL start as a draft. `build-resume --approve FILE` SHALL record approval with a fingerprint of the file, SHALL be refused while the file has the placeholder header, and `--status FILE` SHALL report draft, approved, or changed (the file was edited after approval).

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

#### Scenario: Second build for another posting from stdin
- **WHEN** `build-resume -` is run twice
- **THEN** the second resume is `resume-2.md` and the first is unchanged
