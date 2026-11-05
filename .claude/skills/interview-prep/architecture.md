# Architecture fundamentals: grading rubric

Used by the `interview-prep` skill in architecture mode. Cards come from `src/jobkit/interview/arch.py` (catalog and progress live in git-ignored `prep/arch/`).

## Card kinds
- **service**: one AWS service.
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
- If it says NEVER or is older, or the user's answer touches a limit, price, version or newer feature, look it up on AWS docs (WebSearch or WebFetch, aws.amazon.com / docs.aws.amazon.com) before correcting. If you cannot check, say "unverified" rather than state a number.
- After checking, record the result with `arch refresh ID --status active|maintenance|sunset --source URL [--date D] [--note T] [--change "DATE|SUMMARY"]`. A source must be a specific aws.amazon.com or docs.aws.amazon.com page; dates must be YYYY-MM-DD and not in the future (put scheduled end dates in `--note`). Third-party blogs are leads only; confirm on an AWS page before storing.
- Lifecycle words: **maintenance** = existing customers keep it, new customers cannot onboard, no new features. **Sunset** = has an end date (usually about 12 months). Say which one applies, with the date.

## Flow per question
1. Ask one question. Do not give hints or the answer.
2. After the user answers, grade against the dimensions in a few lines: what was right, what was missing, what was wrong. Correct only with checked facts.
3. Log the full answer: `sessions log SESSION ITEM --question "..." --answer - --grade "..." --confidence N` (answer on stdin; confidence 0 not drilled, 1 some gaps, 2 solid).
4. Ask whether to go deeper on this card or move on. Never skip ahead without asking.
