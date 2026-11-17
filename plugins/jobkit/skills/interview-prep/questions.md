# Questions for the role

Use this guide when the user asks to prepare for interview questions for a role. Choose a short role name from the role they gave or the posting. Run `questions list ROLE` before generating questions or looking for references. Reuse fresh questions or a recent search that found nothing. Keep company interview research in the separate flow in `research.md` (in this skill's folder).

## Ask once before searching

Read question research in `profile status`. If it says the user has not been asked and you can read web pages, ask once:

> Would you like me to look up published interview questions for this kind of role?

Save an explicit answer with `profile set question_research yes` or `profile set question_research no`. If the user defers, keep it unset and use general practice questions. Use the saved preference on subsequent requests.

## Use published sources

- A saved yes allows a search when a role has no recorded research or its research is stale. Search terms may include only the posting's title, level and skills, recent role titles, and general stored skills. Exclude the user's name, contact details, employers, clients, employer-specific products, figures, and resume sentences. If a title or skill includes any excluded detail, omit that detail from the search.
- Before each search, tell the user the exact search terms in one line. Read the original page before treating a question as sourced. Use published hiring guides and editorial material. Exclude user-written reviews, interview reports, forum and question-and-answer posts, comments and social media.
- Save the wording as `question`, the exact page as `link`, a verbatim excerpt of at most 40 words as `quote`, and the date read as `pulled` (YYYY-MM-DD). Set `vetted` to true only after verifying the excerpt and who published it. Use `source` of `company` for a company's own material, or `research` for other publishers. State only what the source supports about hiring or how often a question is asked.
- Save with `questions save ROLE --seed -`, passing a JSON object with `questions` on standard input. To review aging citations, run `questions stale ROLE`. When the same question still has support, save it with its original ID and updated citation. When a citation no longer supports the question, explain the change and remove the old item only once the user responds with yes.
- If the search found no qualifying sources and no cited questions remain, use `questions none-found ROLE`. Save fallback questions as general knowledge. If a page could not be read or searching was unavailable, leave the research record alone and use general practice questions.

## Practice from local material

- If the user declined, searching is unavailable, or useful references were unavailable, write practice questions from general role knowledge. Save them with `source` set to `general`. Present them as general practice questions. Omit links, claims about any company's interviews, and claims about how often the questions are asked.
- Keep personal questions local. Use `questions personal ROLE` to ask about claims on the resume. If there is a posting, add `--jd -` and pass it on standard input. Pass each requirement identified in the posting with `--requirement NAME` to check for gaps even when the requirement is absent from stored skills. A stored wording that shows a requirement counts as evidence. Ask about a possible gap without assuming the user has that experience. Save additional personal prompts with `source` of `personal` and the referenced `bullet` ID or posting `requirement`. Ask for the user's account of the facts.
- Find a relevant story or role-knowledge card using `prep for-jd -` or `cards for-jd -` when a posting is available. In practice, ask the question first and offer the connection during feedback. Let the user supply the details of their own experience.
- Start with `sessions new "title" --mode questions --role ROLE`. Use `questions show ID` to read the source or resume reference, then log the full answer and grade in the session. Use `readiness --role ROLE` to see what to practice again.
