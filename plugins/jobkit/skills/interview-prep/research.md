# Researching a target company

Read this before looking up how a company hires. Nothing about any company ships with the plugin: what you find is checked by the `target` command and stored with its link and the date you read it. The command cannot read pages, so it cannot check that a quote is on its page, that you vetted it, or that you searched as described here. Those steps are yours.

## When to research
- Only in this skill, when the user names a company they are preparing for, or a job posting names one. Run `target show NAME` first.
- `fresh` or `none found`: use what is stored; do not research again.
- `not researched` or `stale`: research as below, but only if you can read web pages. If you cannot, say this once, use the answer style in force, practise without the company (no `prep for-target`, no `--target`), and record nothing (no `target none-found`, no partial save). Never ask the user to paste pages instead:
  > I can't look up how this company interviews from here, so I'll use the usual answer structure.

## Searching
- Search with only the company name and the role title. Never put the user's name, employers, resume text or contact details in a search.
- Read, in this order: pages the company publishes (careers, how-we-hire, interview guides, culture or values pages, engineering blog posts about hiring, the job posting when it has a link), then articles that other sites publish themselves about this company's hiring process.
- Leave out anything written by individual users, on any site: reviews, interview reports, salary posts, comments, forum or question-and-answer threads, personal blog posts and social media posts. A job site's own editorial article is fine; its reviews and interview reports are not. The command refuses links on the sites and pages it knows, but it does not know them all.

## Writing facts
For each thing a page says that helps the user prepare, write one fact:
- `kind`: `value` (a value or principle interviewers score against; give it a short `name`), `round` (a stage of the interview), `grading` (what interviewers look for), `question` (a typical question, with `value` naming the value it tests when the page says so) or `questioning` (how they question: follow-ups, depth, format).
- `quote`: a short passage copied word for word from the page, at most 40 words. `wording`: one sentence saying only what the quote says. Add nothing the page does not say.
- `link`: the exact page. `label`: `company-references` when the site is one the company publishes, `othersite-references` for any other site. `pulled`: the date you read it (YYYY-MM-DD).
- `vetted`: `true` only after you have checked that you read this page, the quote is on it word for word, and the page is not written by individual users. Never set it otherwise.
- For a value, `themes` and `hints` are your mapping to the user's stories, not claims about the company: `themes` are story themes from `prep status` that the value is about; `hints` are a few plain words an answer showing the value would use. Leave both empty when no mapping is clear; the value then reads as needing the user's judgment and is practised from its typical questions.
- A suggested answer style is optional: `stated` only when a stored fact says the company wants that structure (list that fact), otherwise `inferred` with the facts it rests on, and it is shown as your suggestion. It never overrides the user's choice.

Save everything for the company in one call, `target save NAME --seed -`, with the JSON on standard input; the exact format is in `target --help`. One refused fact stores nothing: read the message, fix or drop that fact, and save again. If the command warns that a theme matches nothing yet, keep the value; the warning is for you.

## Nothing found
If no page qualifies, run `target none-found NAME`, tell the user, use the answer style in force and practise without the company (no `prep for-target`, no `--target`; they refuse a company recorded as none found). Invent nothing:
> I couldn't find anything the company has published about how it interviews, so I'll use the usual answer structure.

## Re-reading a stale company
`target stale` and `target show NAME` list the facts older than the research window. For each, open its link again:
- The quote is still there: `target recheck NAME FACT`.
- The page now says something different or nothing: show the user the old and new wording side by side and ask whether to change it. Once the user responds with yes, save the new fact under the same id (`target save`) or, when the page no longer says it at all, `target recheck NAME FACT --remove`. On no, leave it as it is.
- The page cannot be read: leave the fact; it stays stale.

## Talking about facts
Whenever you use a stored fact with the user, say where it came from in plain words: "from the company's own site" for `company-references`, "from another site" for `othersite-references`, with the site's name. Quote the company's own words when explaining a value. Never present a suggested style or a mapping as something the company said.
