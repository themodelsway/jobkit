# First run: import the resumes

Read by a jobkit skill when `jobkit status --setup` printed `no-resumes`. Run every command by its full path inside JOBKIT_COMMANDS_DIR, as the skill says. Ask one question at a time; the user only sees the lines that start with `>`. RESUME_FOLDER is the folder the user names for their resumes. When this is done, go back to the skill.

1. Ask:
   > Where do you keep your resumes? You can drag the folder here or tell me its name.
2. Look inside that folder. Only if it also holds files that do not look like resumes, ask:
   > I see some files that don't look like resumes. Should I skip any part of that folder?
3. Run `profile init --resume-root "RESUME_FOLDER" [--resume-dir SUBFOLDER ...]`, then `process-resumes --survey`, then `process-resumes`.
4. The import already treats the spellings of one employer that differ only in capitals, punctuation, "&" for "and", a leading "The" or an ending such as Inc, Corp or Ltd as one employer; never ask about those. Run `profile companies`. Only if it lists names that look alike and may be one employer, ask once, naming every listed pair in the one question:
   > A few employer names look alike: "X" and "Y"; "P" and "Q". Which of these are the same company? If they are all different, just say so.
   For each pair the user says is one company, run `profile companies merge FROM INTO` (INTO is the name the user prefers; otherwise the one listed first). After the merges, run `process-resumes --force` once. Do not ask about the pairs the user called different again.
5. Report what was found and ask:
   > I found N resumes from M employers: A, B, C. Does that look right?
   If the user says no, ask what is wrong. When it is another folder, or other parts of the folder to skip, save the corrected answer with `profile init --replace --resume-root "RESUME_FOLDER" [--resume-dir SUBFOLDER ...]` (plain `profile init` keeps the first answer), then run `process-resumes --survey` and `process-resumes` again (resumes no longer in the chosen folder are dropped) and ask this step's question again. When two employers they name are one company, merge them as in step 4.
