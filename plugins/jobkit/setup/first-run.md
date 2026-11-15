# First run: import the resumes

Read by a jobkit skill when `jobkit status --setup` printed `no-resumes`. Run every command by its full path inside JOBKIT_COMMANDS_DIR, as the skill says. Ask one question at a time; the user only sees the lines that start with `>`. RESUME_FOLDER is the folder the user names for their resumes. When this is done, go back to the skill.

1. Ask:
   > Where do you keep your resumes? You can drag the folder here or tell me its name.
2. Look inside that folder. Only if it also holds files that do not look like resumes, ask:
   > I see some files that don't look like resumes. Should I skip any part of that folder?
3. Run `profile init --resume-root "RESUME_FOLDER" [--resume-dir SUBFOLDER ...]`, then `process-resumes --survey`, then `process-resumes`.
4. Report what was found and ask:
   > I found N resumes from M employers: A, B, C. Does that look right?
   If the user says no, ask what is wrong. When it is another folder, or other parts of the folder to skip, save the corrected answer with `profile init --replace --resume-root "RESUME_FOLDER" [--resume-dir SUBFOLDER ...]` (plain `profile init` keeps the first answer), then run `process-resumes --survey` and `process-resumes` again (resumes no longer in the chosen folder are dropped) and ask this step's question again.
5. If one employer shows up under two names, ask for each pair:
   > I found "X" and "Y". Are they the same company?
   On yes, run `profile companies merge FROM INTO`, then `process-resumes --force`.
