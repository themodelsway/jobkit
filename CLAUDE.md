# jobkit

Contributor guidance for every coding agent is in `AGENTS.md`; edit it there, not here.

@AGENTS.md

## Claude Code only
- Load the plugin's skills in this checkout with `claude --plugin-dir plugins/jobkit` (from the repository root, so these instructions and the OpenSpec skills stay loaded).
- Deny rules in `~/.claude/settings.json` do not block Bash writes, so the read-only rule for the resume folder is yours to keep.
