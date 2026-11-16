# Welcome: what the user can do

Read by a jobkit skill right after the first resume import, or at the start of a conversation whose request names no task. The user only sees the lines that start with `>`.

First run `jobkit status --summary` (by its full path inside JOBKIT_COMMANDS_DIR). If it shows a `latest open session`, say this before the list, with TITLE replaced by that session's title:
> You have an unfinished practice session, "TITLE". Would you like to continue it, or start something below?

If the user wants to continue it: a session whose mode is `tutor` continues in the tutor skill, any other in the interview-prep skill (its "Sessions" section, with `sessions resume ID`). If `due for a retest` is above 0, add after the list:
> A few things you practiced a while ago are due for a quick refresh. Just ask when you want to go over them.

> Your resumes are ready. Here is what we can do with them:
> 1. **Learn a topic.** I explain a technology, a design choice or one of your own stories, then check with a short quiz.
> 2. **Practice an interview.** I ask, give no hints, then grade your answer: technical questions, leadership questions, and your stories told the way you prefer (STAR, SOAR or CARL).
> 3. **Prepare for a company.** Name a company and I look up how it hires (its values, interview rounds, typical questions) from what the company and proper articles publish, then focus your practice on it.
> 4. **See how prepared you are.** A report of what is solid, what needs work and what you haven't tried yet, for one job posting if you give me one.
> 5. **Check how well you match a job (early preview).** Give me a job posting and I rate how well your resumes cover it, and list what it asks for that they don't show yet.
>
> What would you like to do first?

If the request that started this already named a task (possible right after the first import), show the list and carry on with that task without asking what to do first; the rest of the running skill's steps still apply. Otherwise wait for the choice. Items 1 and 4 belong to the tutor skill (`JOBKIT_PLUGIN_DIR/skills/tutor/SKILL.md`); item 2 to the interview-prep skill (`JOBKIT_PLUGIN_DIR/skills/interview-prep/SKILL.md`); item 3 to the "Preparing for a specific company" section of the interview-prep skill; item 5 to the "Rating how well the resume matches a job posting (early preview)" section of the resume-workflows skill (`JOBKIT_PLUGIN_DIR/skills/resume-workflows/SKILL.md`). When the choice belongs to a skill other than the one that is running, read that skill file and continue with it.
