---
name: gate-skill
description: Run Skill Gate check_skill on the open SKILL.md
---

# Gate the open skill

Use the `skillgate` MCP server. Call `check_skill` on the skill pack for the currently open `SKILL.md`.

1. Identify the open file. If it is `SKILL.md`, that file's parent folder is the pack. If it is not, walk up from the open file to the nearest `SKILL.md`. If none is open, ask which pack to check.
2. Call the `skillgate` MCP tool `check_skill` with that pack path. Do not substitute a local CLI run unless the MCP server is unavailable.
3. Report pass, fail, or not ready, plus the tool's findings. Do not invent scores.
