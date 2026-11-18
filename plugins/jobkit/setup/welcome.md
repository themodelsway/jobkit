# Welcome: what the user can do

Read by a jobkit skill right after the first resume import, or at the start of a conversation whose request names no task. The user only sees the lines that start with `>`.

First run `jobkit status --summary` (by its full path inside JOBKIT_COMMANDS_DIR). Its `suggested next` line is the next step the stored data points to. When it is not `none` and the request that started this named no task, go for it: say the matching line below, then start that step straight away, without showing the list or asking what to do first. That line is the user's go-ahead for the step; if the user asks for something else instead, do that.
- `continue-session ID`: with TITLE taken from the `latest open session` line, say:
  > Let's pick up your unfinished practice session, "TITLE", where you left off. If you'd rather do something else, just say so.
  Continue it with `sessions resume ID`: a session whose mode is `tutor` continues in the tutor skill, any other in the interview-prep skill (its "Sessions" section, from step 3).
- `retest N`: say:
  > A few things you practiced a while ago are due for a quick refresh, so let's start with those. If you'd rather do something else, just say so.
  Start the refresh in the interview-prep skill (its "Sessions" section): a new session with `--due`.
- `prepare-for COMPANY`: say:
  > Let's keep preparing for COMPANY, starting with a practice round on what its interviewers look for. If you'd rather do something else, just say so.
  Continue in the "Preparing for a specific company" section of the interview-prep skill, with COMPANY as the company the user named for this session.

Otherwise (it is `none`, or the request named a task), show the list:

> Your resumes are ready. Here is what we can do with them:
> 1. **Learn a topic.** I explain a topic from your field, a choice between two approaches, or one of your own stories, then check with a short quiz.
> 2. **Practice an interview.** I ask, give no hints, then grade your answer: questions about your field, leadership questions, and your stories told the way you prefer (STAR, SOAR or CARL).
> 3. **Prepare for a company.** Name a company and I look up how it hires (its values, interview rounds, typical questions) from what the company and proper articles publish, then focus your practice on it.
> 4. **See how prepared you are.** A report of what is solid, what needs work and what you haven't tried yet, for one job posting if you give me one.
> 5. **Check how well you match a job (early preview).** Give me a job posting and I rate how well your resumes cover it, and list what it asks for that they don't show yet.
>
> What would you like to do first?

If the request that started this already named a task (possible right after the first import), show the list and carry on with that task without asking what to do first; the rest of the running skill's steps still apply. Otherwise wait for the choice. Items 1 and 4 belong to the tutor skill (`JOBKIT_PLUGIN_DIR/skills/tutor/SKILL.md`); item 2 to the interview-prep skill (`JOBKIT_PLUGIN_DIR/skills/interview-prep/SKILL.md`); item 3 to the "Preparing for a specific company" section of the interview-prep skill; item 5 to the "Rating how well the resume matches a job posting (early preview)" section of the resume-workflows skill (`JOBKIT_PLUGIN_DIR/skills/resume-workflows/SKILL.md`). When the choice belongs to a skill other than the one that is running, read that skill file and continue with it.
