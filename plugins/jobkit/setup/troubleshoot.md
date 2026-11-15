# When something goes wrong

Read by the jobkit skills when the setup check (`jobkit status --setup`) prints `blocked`, `busy`, `too-new`, `failed`, anything else that is not one of its four stage words, or nothing; and whenever a jobkit command fails and its message does not say what to fix, or its last line is "For help, read setup/troubleshoot.md in the plugin folder." The skill that is running explained JOBKIT_PLUGIN_DIR and JOBKIT_COMMANDS_DIR and how to run commands. Do the checks yourself and quietly: the user only sees the lines that start with `>`. When a check here says to carry on, go back to the skill.

A mistake in how a command was run (a wrong option, a missing or misspelt name) is not a reason to read this guide: its message says what to fix, so fix it and run the command again.

## Never
- Never guess the setup stage, and never import the resumes on a guess.
- Never try to repair the stored data yourself: do not delete, move, recreate or restore anything, and never open the database directly.
- Never run a failed command again more than once, and only where this guide says so.
- Never turn your own protections off, and never ask the user to.

## 1. The setup check could not tell the stage
- `blocked`: saving is not allowed, and jobkit cannot work without it. Handle it as step 2 of `preflight.md` (in this folder) says for a save that was not allowed, and stop if it stays blocked. This is not something to report.
- `busy`: another command is using the stored data. Wait a few seconds and run `jobkit status --setup` once more. If it now prints a stage word, carry on; if it prints `busy` again, handle it as `failed`.
- `too-new`: the stored data was written by a newer version. Say the next line and stop:
  > Your saved data comes from a newer version of this helper than the one installed here. Please update the plugin, then ask me again.
- `failed`, any other output, or no output: the command printed one error line (its type and message). Go to section 3.

## 2. A command failed later in the conversation
Read the error the command printed.
- It says the database is busy: wait a few seconds and run the same command once more (a failed command saved nothing, so this is safe). If it fails again, go to section 3.
- It says a save was not allowed: handle it as step 2 of `preflight.md` says.
- It says the stored data comes from a newer version: say the `too-new` line from section 1 and stop.
- It says a command or option does not exist: the helper may be older than this plugin. Run the helper check from step 1 of `preflight.md`; if it prints `older:JOBKIT_COMMANDS_DIR`, follow that step's answer for `older` (it asks the user before updating anything). Otherwise go to section 3.
- Anything else: run `jobkit status --setup`. If it prints a word other than `no-target` or `ready`, handle that word as section 1 says. If it prints `no-target` or `ready`, setup is fine and the problem is in that one command: go to section 3.

## 3. Report it
Explain the error in plain words in one sentence (no error text, commands or file names), then say the next line and stop what you were doing:
> Something went wrong, so I've stopped here. Please report it at https://github.com/themodelsway/jobkit/issues. If you like, I can write the report for you to paste there.

If the user says yes, write a short report: what was being done, the name of the command that failed (without what was passed to it), the error line or the last lines of the error, the three folder lines of `jobkit status --summary` (`JOBKIT_HOME`, `JOBKIT_COMMANDS_DIR` and `JOBKIT_PROGRAM_DIR`, which carry the jobkit and Python versions and already show the home folder as `~` (`%USERPROFILE%` on Windows); if the summary cannot run, give the version from `jobkit --version` instead), the operating system and the agent. Leave out names, resume content, company names, file and folder names, and anything personal; show the home folder as `~` (`%USERPROFILE%` on Windows). Show it to the user to post themselves. Jobkit does not post issues on GitHub: never create issues, comments or anything else there.
