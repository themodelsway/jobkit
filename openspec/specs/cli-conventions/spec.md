# cli-conventions Specification

## Purpose
Give every tool the same command shape so one habit works everywhere. Checked by `tests/test_cli_contract.py`.

## Requirements

### Requirement: Common verbs
Tools SHALL use the verbs `init`, `status`, `list`, `show ID`, `next`, `set ID FIELD VALUE`, and `for-jd JD`; `add` and `rm` SHALL be used inside a noun.

#### Scenario: Init never overwrites
- **WHEN** `init` is run on existing data
- **THEN** it extends the data and does not overwrite the user's answers

### Requirement: Job description argument
A job description SHALL be a positional file (`-` for stdin) when it is the subject, and `--jd` when it only filters.

#### Scenario: Stdin
- **WHEN** `for-jd -` is run with piped text
- **THEN** the piped text is used as the job description

### Requirement: Output channels and exit status
Messages for the user SHALL go to stdout and problems to stderr with exit status 1; `validate` SHALL also exit 1 when it finds errors; bad arguments SHALL exit 2.

#### Scenario: Unreadable input file
- **WHEN** a JD or other input file is missing, is a folder, cannot be read, or is not UTF-8 text
- **THEN** a one-line message with the path goes to stderr, the exit status is 1, and no traceback is shown

#### Scenario: Missing record
- **WHEN** `show` is given an unknown id
- **THEN** a message goes to stderr and the exit status is 1

### Requirement: Every tool answers help
Every tool SHALL answer `--help`, and output files SHALL use `-o/--output`.

#### Scenario: Help check
- **WHEN** each tool is run with `--help`
- **THEN** it exits 0

### Requirement: Older names stay as aliases
`query-resume match` SHALL work as `for-jd`, and `prep skeleton` as `init`.

#### Scenario: Old command
- **WHEN** `match jd.txt` is run
- **THEN** the output equals `for-jd jd.txt`

### Requirement: Tool structure
Each tool SHALL have `build_parser()` and `main(argv) -> int`, SHALL do no work at import time, and SHALL turn user mistakes (`ToolError`) into an exit status.

#### Scenario: Import
- **WHEN** a tool module is imported
- **THEN** nothing runs and nothing is written

### Requirement: Tools are installed as commands
Each tool SHALL be a module of the `jobkit` package with a console entry point in `pyproject.toml`, so that `uv sync` installs it as a command in `.venv/bin/`; a tool SHALL NOT edit `sys.path` to find its siblings.

#### Scenario: Entry points
- **WHEN** the entry points in `pyproject.toml` are read
- **THEN** each names a `main` function in a tool module, and every tool module has one entry point

#### Scenario: Run as a module
- **WHEN** a tool is run as `python -m jobkit.<group>.<tool> --help`
- **THEN** it exits 0
