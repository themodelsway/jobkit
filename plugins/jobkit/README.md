# jobkit plugin

Resume tooling and interview-preparation skills for Claude Code and Codex. This folder is the installable
plugin; the full documentation is in the [repository](https://github.com/themodelsway/jobkit).

## What is here

- `skills/`: the three skills (interview-prep, tutor, resume-workflows) and the guides they read.
- `agents/`: two helpers the skills hand work to where the agent supports them: `resume-visual-scanner` (reads PDF
  pages as pictures, once the user responds with yes to a visual reading) and `jd-matcher` (the first rating pass of a match score).
- `setup/`: the installers the skills offer; the skills tell the agent to run them once the user responds with yes. `install` is for macOS and Linux,
  `install.ps1` for Windows.
- `src/`, `pyproject.toml`, `.python-version`: the `jobkit` commands the skills run.

## Installing

In Claude Code: `/plugin marketplace add themodelsway/jobkit`, then `/plugin install jobkit@themodelsway`.
In Codex: `codex plugin marketplace add themodelsway/jobkit`, then `codex plugin add jobkit@themodelsway`.

## Privacy

Text extracted from users' resumes, practice answers and match results are stored on their own computer, in `~/.jobkit` on macOS and Linux and in `%USERPROFILE%\.jobkit` (the `.jobkit` folder in the user home folder) on Windows. The original resume files stay where users keep them; the jobkit commands only read them, and the skills tell the agent never to change them.
Content sent to a model is handled under the policies and privacy settings of the provider serving it.
The [repository README](https://github.com/themodelsway/jobkit#privacy) has the details.

## License

Apache License 2.0. See `LICENSE`.
