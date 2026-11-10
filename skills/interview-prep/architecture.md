# Architecture fundamentals: grading rubric

Used by the `interview-prep` skill in architecture mode. Cards come from `arch` (catalog and progress live in the local database). Each card belongs to a *track*, one technology the user is preparing for (AWS, Acme Data, GCP, ...); AWS is bundled, the others are added with `arch track add`.

## Card kinds
- **service**: one service, product or feature area of the track's technology.
- **pair**: a "which one and why" comparison (the most common interview form).
- **scenario**: an open design question.

## Dimensions to grade a service answer against
1. What it is and the problem it solves
2. When to choose it, and the alternatives (why not those)
3. Key limits and gotchas
4. Security (identity, encryption, network exposure)
5. Cost drivers
6. Scaling and failure behaviour (multi-AZ, regional limits, quotas)
7. Where the user has used it (the card shows resume bullets that mention it)
8. What changed in the last 3 years, and anything deprecated

For a **pair**, grade on the decision criteria (latency, protocol, scale, cost, operational burden, security) and a clear recommendation, not on a description of each service. For a **scenario**, grade on clarifying questions, the component choices with reasons, failure modes, security, cost, and what they would measure.

## Facts: never from memory
- Run `arch show ID` first. The card stores only lifecycle and recent changes. If `lifecycle/changes verified on` is a date within about 6 months, you may use those. A card marked "seeded lead ... NOT verified" is not verified. Limits, prices and feature details are never on the card: look them up each time.
- If it says NEVER or is older, or the user's answer touches a limit, price, version or newer feature, search and read the vendor's official documentation (on the hosts `arch tracks` lists for the card's track) before correcting. If you cannot check, say "unverified" rather than state a number.
- After checking, record the result with `arch refresh ID --status active|maintenance|sunset --source URL [--date D] [--note T] [--change "DATE|SUMMARY"]`. A source must be a specific page on one of the track's documentation hosts (the tool rejects other hosts); dates must be YYYY-MM-DD and not in the future (put scheduled end dates in `--note`). Third-party blogs are leads only; confirm on a vendor page before storing.
- Lifecycle words: **maintenance** = existing customers keep it, new customers cannot onboard, no new features. **Sunset** = has an end date (usually about 12 months). Say which one applies, with the date.

## Tracks (more than one technology)
The user may prepare for several technologies at once, for example AWS, Acme Data and GCP. Ask which, then for each:
- **AWS**: `arch init --track aws` (bundled seed).
- **Anything else**: build a seed, show it to the user for approval, then `arch track add NAME --seed -` (JSON on stdin) and `arch init --track NAME`. NAME is lower-case letters, digits and `-`. `arch init` with no `--track` extends the tracks already enabled; `arch tracks` lists them.

A seed is topic names only, never facts. Search and read the vendor's official documentation index for the topic list; never take it from memory:
```json
{"label": "Acme Data",
 "source_hosts": ["docs.example.com"],
 "services": [{"area": "Governance", "name": "Data Catalog", "tier": 2, "aliases": ["UC"]}],
 "pairs": [{"topic": "Table formats", "name": "Format A vs Format B", "members": ["Format A", "Format B"]}],
 "scenarios": ["Design a lakehouse for streaming and BI"]}
```
`tier` is 2 (core) or 3 (optional); tier 1 is set from the user's resumes. `source_hosts` are the only hosts `arch refresh` will accept as a source, so list the vendor's docs hosts (for GCP: `cloud.google.com`; for Azure: `learn.microsoft.com`). Aim for 30 to 60 services in areas the vendor itself uses, 6 to 10 decision pairs the vendor's own docs compare, and 6 to 8 scenarios. Re-running `arch track add` with the same name replaces the seed; `arch init --track NAME` then adds the new cards and keeps progress. Card ids of non-AWS tracks start with the track name (`acmedata-turbo`).

Use `--track T` on `arch next|list` and `sessions new` to drill one technology; without it, cards from all enabled tracks are mixed.

## Flow per question
1. Ask one question. Do not give hints or the answer.
2. After the user answers, grade against the dimensions in a few lines: what was right, what was missing, what was wrong. Correct only with checked facts.
3. Log the full answer: `sessions log SESSION ITEM --question "..." --answer - --grade "..." --confidence N` (answer on stdin; confidence 0 not drilled, 1 some gaps, 2 solid).
4. Ask whether to go deeper on this card or move on. Never skip ahead without asking.
