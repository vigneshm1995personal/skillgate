---
description: Run Skill Gate check_skill, run_eval, or gate on a skill pack
---

# Skill Gate

Use the `skillgate` MCP server. Auth is the `SKILLGATE_TOKEN` bearer token already configured for that server.

1. Resolve the skill pack. Prefer the nearest `SKILL.md` to the open file or a path the user named. The pack is that file's parent folder.
2. Default: call `check_skill` on that pack.
3. If the user asked to run the dataset, call `run_eval`.
4. If the user asked to gate (pass/fail for merge or commit), call `gate`.
5. Report the tool result. Do not invent scores. If the MCP server is unavailable, say so and point at the local CLI: `skillgate check`.
