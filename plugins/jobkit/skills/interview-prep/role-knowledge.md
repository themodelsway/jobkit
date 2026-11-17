# Role knowledge: cards, rubrics and tracks

Used by the `interview-prep` skill in knowledge mode (and by the tutor skill) for any role. Cards come from `cards` (catalog and progress live in the local database). Each card belongs to a *track*: one field or technology the user is preparing for, for example people operations, product design, UK payroll or AWS. Each track belongs to a *role family* (`cards families` lists them, with who each fits and its default rubric). AWS is bundled as one example of the engineering family; every other track is added with `cards track add`.

## Card kinds
- **topic**: one topic of the track: a method, concept, regulation, product or service.
- **pair**: a "which one and why" comparison (the most common interview form).
- **scenario**: an open design or situational question ("what would you do if...").
- **case**: a question the interviewer develops over several turns. `cards show` prints the situation to open with.
- **role-play**: you play a part and the user pursues a goal. `cards show` prints the part and the goal.

## Grading: always the rubric the card prints
`cards show ID` prints the rubric of the card's own track ("rubric (grade the answer against these)"). Grade every answer against those lines and no others: never against another track's rubric or one from memory. For a **pair**, also judge the decision criteria and whether there is a clear recommendation, not a description of each side. For a **scenario**, also judge the clarifying questions, the choices with reasons, what could go wrong and what they would measure.

## Running a case
1. Open with the card's situation in your own words, as an interviewer would. Do not list what you expect.
2. Reveal more only when the user asks for it. When they ask for a figure the situation does not give, give a plausible one and say it is made up for practice. Never store it.
3. Push back at least once, for example with a new constraint or a doubt about their reasoning.
4. When the user gives a recommendation or says they are done, grade the whole exchange against the rubric: how they structured it, the questions they asked, their reasoning, and the recommendation.

## Running a role-play
1. Say, in one line, who you are playing and what the user is trying to achieve:
   > I'll play a sales director who wants a new feature this quarter. Your goal is to agree a plan without promising a date. Start whenever you're ready.
2. Stay in the part until the user reaches the goal or says they are done. React the way that person would, including pushing back. Give no hints while in the part.
3. Step out of the part and say so, then grade the exchange against the rubric: what worked, what to try differently, with the moment it happened.

## Facts: never from memory
- Run `cards show ID` first. A topic, pair or scenario card stores only lifecycle and recent changes. If `lifecycle/changes verified on` is a date within about 6 months, you may use those. A card marked "seeded lead ... NOT verified" is not verified. Limits, prices, rules and feature details are never on the card: look them up each time.
- Before stating or correcting a fact (a limit, price, version, newer feature, legal rule or threshold), search and read the official sources on the hosts `cards tracks` lists for the card's track. If `cards show` prints a country, check the fact for that country. If you cannot check, say "unverified" rather than state a number.
- The official sources for each family are listed by `cards families`: for a vendor's product, the vendor's own documentation; for a field such as HR, payroll or finance, the regulator, the government or the standards body. Third-party blogs are leads only; confirm on an official page before relying on them.
- Lifecycle facts apply only to products and services. After checking one, record it with `cards refresh ID --status active|maintenance|sunset --source URL [--date D] [--note T] [--change "DATE|SUMMARY"]`. A source must be a specific page on one of the track's hosts (the tool rejects other hosts); dates must be YYYY-MM-DD and not in the future (put scheduled end dates in `--note`).
- Lifecycle words: **maintenance** = existing customers keep it, new customers cannot onboard, no new features. **Sunset** = has an end date (usually about 12 months). Say which one applies, with the date.

## Tracks (more than one technology or field)
The user may prepare for several at once, for example people operations and payroll, or product management and AWS. For each:
- **AWS** (the bundled example): `cards init --track aws` (engineering family, its own rubric).
- **Any other field or technology**:
  1. Choose the role family yourself from what the user said about their role (`cards families` shows who each fits, example focus areas and where its facts come from). Every seed names its family; none is assumed. Ask one question only when the role could fit more than one, naming the choices in everyday words.
  2. Build a seed. Start from the family's default rubric and adapt it to the role where it does not fit.
  3. Show the topics and the rubric to the user in plain words, and save only once they respond with yes: `cards track add NAME --seed -` (JSON on stdin), then `cards init --track NAME`. NAME is lower-case letters, digits and `-`.

`cards init` with no `--track` extends the tracks already enabled; `cards tracks` lists them with their family.

A seed is topic names only, never facts. Search and read an official index of the field (the vendor's documentation, a regulator's guidance, a standards body) for the topic list; never take it from memory:
```json
{"label": "Product management",
 "family": "product",
 "source_hosts": ["www.gov.uk"],
 "country": "United Kingdom",
 "topics": [{"area": "Metrics", "name": "North-star metric", "tier": 2}],
 "pairs": [{"topic": "Planning", "name": "Outcome roadmap vs feature roadmap", "members": ["Outcome roadmap", "Feature roadmap"]}],
 "scenarios": ["Grow weekly active users of a mature app"],
 "cases": [{"title": "Sign-ups fell", "situation": "Sign-ups fell 20% last month. Find out why."}],
 "role_plays": [{"title": "Push back on a feature", "part": "a sales director who wants a feature now", "goal": "agree a plan without promising a date"}]}
```
- Every list is optional, but a seed needs at least one card. If `track add` says two cards would get the same id, rename one of them and add the seed again. Add `"dimensions": [...]` (at most 12 lines) only when you adapted the family's rubric; without it the family's default is used. Give `country` when the knowledge differs by country (employment law, payroll, tax).
- `tier` is 2 (core) or 3 (optional); tier 1 is set from the user's resumes.
- `source_hosts` are the only hosts `cards refresh` accepts, so list the official hosts for the field (for UK employment law: `www.gov.uk`; for a vendor's product: the vendor's documentation host).
- Aim for 20 to 60 topics in areas the field itself uses, 6 to 10 comparisons, and 6 to 8 scenarios, cases or role-plays, whichever fit how the role is interviewed.
- Re-running `cards track add` with the same name replaces the seed; `cards init --track NAME` then adds the new cards and keeps progress. Card ids of non-AWS tracks start with the track name (`people-ops-leave-policy`).

Use `--track T` on `cards next|list` and `sessions new` to drill one track; without it, cards from all enabled tracks are mixed. Use `--kind case` or `--kind role-play` to practice only those (not with a job posting, which matches topic cards only).

## Flow per question
1. Ask one question (or open the case, or step into the role-play). Do not give hints or the answer.
2. After the user answers, grade against the rubric in a few lines: what was right, what was missing, what was wrong. Correct only with checked facts.
3. Log the full answer: `sessions log SESSION ITEM --question "..." --answer - --grade "..." --confidence N` (answer on stdin; for a case or role-play, the whole exchange; confidence 0 not drilled, 1 some gaps, 2 solid).
4. Ask whether to go deeper on this card or move on. Never skip ahead without asking.
