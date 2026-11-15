# Before you start

Read by the jobkit skills at the start of every conversation. The skill that is running explained JOBKIT_PLUGIN_DIR and how to run commands. Do these steps yourself and quietly: the user only sees the lines that start with `>`. When they are done you have JOBKIT_COMMANDS_DIR, the folder where uv keeps the jobkit commands; go back to the skill. Its next step checks how far setup has got (`jobkit status --setup`), which may lead to `first-run.md` (importing the resumes) and `welcome.md` (what the user can do), both in this folder.

1. Check the helper. The session's environment says which operating system this is; if it does not, run `uname -s` (`Darwin` is macOS, `Linux` is Linux, a name starting `MINGW`, `MSYS` or `CYGWIN`, or no `uname` at all, is Windows):
   - macOS or Linux: run `sh "JOBKIT_PLUGIN_DIR/setup/install" --check`.
   - Windows: run `powershell.exe -NoProfile -ExecutionPolicy Bypass -File "JOBKIT_PLUGIN_DIR/setup/install.ps1" --check`. If that cannot run at all because the shell or `powershell.exe` is missing, say the next line and stop:
     > On Windows I need a free program called Git for Windows. Please install it from git-scm.com (the standard options are fine), then close this window, open it again and ask me again.

   The command prints one line:
   - `ok:JOBKIT_COMMANDS_DIR` or `newer:JOBKIT_COMMANDS_DIR`: the helper is ready. Remember JOBKIT_COMMANDS_DIR. `newer` means the helper is already ahead of this plugin: use it as it is and never offer to install over it.
   - `no-uv`: the uv package manager, which the helper needs, is not on this computer. Never install it unasked. Say the next line and wait for the answer:
     > The Jobkit engine requires uv, a Python package manager. Install it by following the instructions at https://github.com/astral-sh/uv, and let me know when it is done; I will continue from here. If you prefer, I can install it for you.
     - The user says uv is installed: run the check again and carry on with its answer. If it still prints `no-uv`, say the next line and wait:
       > I can't find uv yet. If it was installed in another window, please start a new session and ask me again.
     - The user asks you to install uv: ask this and wait for the answer:
       > I will install uv from its official release, then set up the Jobkit engine, which stores your resumes and interview practice. uv will download Python 3.14 and the required Python packages. This takes about a minute. Data is stored in a folder on this computer. Proceed?

       On yes, run the same command without `--check` and with `--with-uv` added at the end, and continue as in the "Yes" case below. On no, install nothing and stop as in the "No" case below.
   - `missing` or `older:JOBKIT_COMMANDS_DIR`: the helper must be set up or updated. Ask this and wait for the answer. Keep this question's wording: say where the data is kept, and never say that it stays on the computer:
     > I need to set up the Jobkit engine, which stores your resumes and interview practice. uv will download Python 3.14 and the required Python packages. This takes about a minute. Data is stored in a folder on this computer. Proceed?
     - Yes: run the same command again without `--check`. It prints `ok:JOBKIT_COMMANDS_DIR` when it worked. If it fails with a line that starts `failed: uv is too old`, say the next line and stop:
       > Setup did not finish. A tool called uv is already on your computer, but it is too old for me to use, and I won't replace it for you. Please update it, then ask me again.

       If it fails in any other way, say the next line and stop:
       > Setup did not finish. Please check that you are online and that I am allowed to download and install, then ask me to try again. I will carry on from where it stopped.
     - No: install nothing, say the next line and stop:
       > No problem. I can't help with your resumes or practice without that helper, so I'll stop here. Ask me again whenever you're ready.
   - `unsupported`: install nothing, say the next line and stop:
     > Sorry, this setup doesn't work on your operating system yet.
2. If a command fails because it was not allowed to write under the jobkit home folder (the error mentions `Operation not permitted`, `Permission denied`, `unable to open database file` or a read-only database), nothing was saved. Report nothing as saved and never suggest turning your own protections off. If you can ask the user to approve running that one command again with wider permissions (your own one-off approval, for that command only), ask that first and run it again if they agree. If you cannot, or they decline, say the next line with JOBKIT_HOME replaced by the data folder, and stop. Take the folder from the `JOBKIT_HOME` line of `jobkit status --summary` (if that cannot run: `~/.jobkit` on macOS and Linux, `%USERPROFILE%\.jobkit` on Windows) and give the user the full path, with the home folder expanded properly: replace `~` or `%USERPROFILE%` with the user's real home folder, so the path can be pasted into the agent's settings. Say the full path only to the user, never in a report.
   > I wasn't allowed to save that, so nothing was saved. Please allow me to write to this folder, then ask me again: JOBKIT_HOME
