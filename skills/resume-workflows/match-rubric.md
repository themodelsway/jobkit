# Match rubric

Rubric version: 1

This file is for Claude, not the user. It is how to do pass 1 of a match score: split a job posting into requirements and rate each one against the user's stored resume lines. The `match-score` command checks your output and does only arithmetic, so your job is to judge carefully and consistently, and to write the judgment down in the request format below. Never ask the user anything while scoring; settle every doubt with the rules here and say what you assumed.

## The request you write

A JSON file with this shape (the fields are checked; anything invalid is rejected with its path and you fix the file):

```json
{
  "schema_version": 1,
  "band": "mid-manager",
  "band_reason": "One sentence on why this level, from the duties.",
  "band_alternatives": [],
  "label": "Role at Company",
  "requirements": [
    {
      "id": "r1", "label": "short name", "quote": "the posting sentence",
      "section": "the heading it sat under", "category": "people_leadership",
      "priority": "required", "importance": 1.0, "level": "substantial", "confidence": 0.8,
      "reason": "one sentence", "evidence": ["bullet:BULLET_ID"], "related": "",
      "flag": {"kind": "level", "readings": ["partial", "substantial"]}
    }
  ]
}
```

`importance`, `confidence`, `related`, `flag`, `contest` and `band_alternatives` are optional. `confidence` (0 to 1) is only shown to the user and never changes a number.

## Splitting the posting

- One requirement per skill, duty or qualification (atomic). Split "Python and Go" into two; keep "lead a team of 10 or more" as one.
- `quote` is the posting sentence it came from; `section` is the heading above it ("Qualifications", "Responsibilities", "Nice to have").
- Run `match-score extract` first. It returns requirements code can already rate (ids starting `code:`). Copy those into your request with the same id and give each its category, priority, quote and section; the command replaces your level and evidence with the code's. Add only what code did not return: years tied to one skill, "or related field" degrees, certifications the user does not hold, and every duty, result and domain requirement.
- A skill the posting names that is not in the stored skills is a `profile_miss` requirement; add it.
- Code counts a skill line only when it is not flagged `needs_review`, not ignored, and does not explicitly say that skill was not used professionally ("no production use", "never used it"): such a line earns nothing and is not demonstrated in the profile. A line that reads like training ("completed a bootcamp") counts but never above partial. The report lists both kinds as assumptions: never ask the user about them during a rating. A line with a measured result counts twice. If that is wrong for a code-rated item, give `"contest": {"level": "...", "reason": "..."}` on it. The report then shows the code's level, yours and your reason.

## Levels

- `full`: a stored line or entry shows the same responsibility, at a similar scale, with the result or detail the posting asks for.
- `substantial`: the same responsibility at a similar scale, with one detail unstated (for example the team size is close but not equal, or the result is implied).
- `partial`: the same responsibility at a clearly smaller scale or with less ownership, or an activity with no stated result when the posting asks for a result, or a skill that appears only in the skills list with no line showing it.
- `profile_miss`: nothing stored shows it. The user will see this as "not shown in your profile yet". It is not a judgment of the person.
- `unknown`: the posting is too unclear to say what is being asked. Use it rarely; most unclear wording is settled with the default rules instead.

A level of `full`, `substantial` or `partial` must cite at least one stored line or entry. A `profile_miss` or `unknown` cites none.

### Adjacent work earns no credit

If the stored work is related but a different responsibility, rate `profile_miss` and put the related work in `related`. It is shown to the user and earns nothing. Mentoring four engineers is not leading a team: mentoring is `profile_miss` against "lead a team", with `related` saying so. "Managed" and "led" both count as leading. The same responsibility at a smaller scale is `partial`, not `profile_miss`.

## Categories

- `core_skills`: tools, languages, platforms, methods the person uses.
- `impact`: results and outcomes (money, time, scale, quality, growth).
- `functional_leadership`: technical or functional leadership: setting methods, standards and direction for a discipline (architecture and design standards in engineering, policy and frameworks in HR or finance, the craft bar in design) and mentoring others in it. Mentoring counts here when the posting asks to mentor.
- `people_leadership`: managing reports, hiring, performance, building or reshaping an organisation, organisation size.
- `strategy`: business strategy, budget or P&L, executive and cross-department influence, vendors and partners.
- `domain`: industry, market, regulation, customer segment. At the Executive and Senior Executive bands, a technology area named as an area of expertise rather than a tool ("deep understanding of cloud and AI") is `domain`.
- `education`: degrees and certifications.

## Priority

- `critical`: only with explicit must-have wording (must have, mandatory, non-negotiable, essential).
- `required`: "required", "you will", "responsible for", "X+ years".
- `preferred`: "nice to have", "a plus", "preferred", "bonus".
- If the posting treats one requirement as both preferred and required, it is required. If both required and critical, it is critical only with explicit must-have wording, otherwise required. (The command applies these two rules itself; you may set a priority flag for them.)

## Choosing the band

Read the responsibilities and who the role reports to, not just the title (a "Director" can run one team of eight). Bands: `junior-ic` (early career, learns under guidance), `mid-senior-ic` (owns work independently; includes staff, principal and architect roles), `mid-manager` (manages a team, up to senior manager), `executive` (director or senior director: manages managers, owns a budget), `senior-executive` (VP and above: sets direction for a large organisation). If it could fit two bands, set `band` to either and list the other in `band_alternatives`; the command uses the lower one and says so.

## Flags (use sparingly)

Flag a requirement only for one of these conflicts, and name both readings:

- `level`: two defensible levels. `readings`: the two levels.
- `category`: two defensible categories. `readings`: the two categories.
- `priority`: wording about priority that the fixed rules do not settle. `readings`: the two priorities.

Merely vague wording is not a flag: decide it with the rules above. Set the requirement's own fields to the reading you find more likely; the command takes the cautious one (the lower level, the category of the posting section, the lower priority) and counts the other in the upper score.

## Finding evidence

Run `query-resume for-jd` once on the whole posting to see the best lines per company (line ids are printed under the company name), and `query-resume search` for specific words. Read skills, education and certifications with `jobkit export --only resume-skills` and `--only resume-profile`. Cite with:

- `bullet:BULLET_ID` (a line; use `bullet:COMPANY_ID:BULLET_ID` only if the command says two companies share an id),
- `skill:NAME`, `education:N` (1 is the first education entry), `certification:NAME`, `role:COMPANY_ID`.

Cite only lines that really support the requirement. Never invent a line or a detail the stored data does not show.

## Examples

### Example 1: people leadership

Posting: "Manage a team of 10 or more engineers." Line: "Led a team of 6 engineers building the payments platform." Same responsibility, similar scale, size short of ten: `substantial`, reason "Led six engineers; the posting asks for ten or more." Line: "Mentored 4 junior engineers." Mentoring is a different responsibility: `profile_miss`, `related`: "Mentored four junior engineers (not managing a team)."

### Example 2: impact

Posting: "placeholder" Line: "placeholder" An outcome with scale: `full`. Line: "placeholder" An activity with no stated result: `partial`, reason "Page speed work is shown but no result is stated."

### Example 3: domain

Posting: "Experience in regulated financial services." Line: "Built reporting for a retail bank under audit rules." Same domain: `full`. Line: "Built reporting for a hospital group under health rules." An adjacent regulated industry, not the one asked: `profile_miss`, `related`: "Regulated healthcare work."

### Example 4: a skill only in a list

Posting: "Experience with Kubernetes." Stored skills include Kubernetes but no line mentions it: `partial`, evidence `skill:Kubernetes`, reason "Listed as a skill but no line shows it in use." (The code pass rates named skills this way; copy its id.)

### Example 5: a field other than engineering

HR posting: "Set compensation standards and coach the HR team on them." Line: "Designed the pay framework and levelling guide used by 400 staff." Category `functional_leadership`, `full` for the framework; coaching the team is a second requirement rated on its own evidence.
