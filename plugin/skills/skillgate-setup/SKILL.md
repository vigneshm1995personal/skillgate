---
name: skillgate-setup
description: Use when setting up Skill Gate in a project — check MCP health with doctor, validate SKILL.md packs, or scaffold a new skill or starter eval cases. Requires pip install "skillgate-ai[mcp]".
license: Apache-2.0
metadata:
  author: skillgate-ai
  version: "1.0"
---

# Skill Gate setup (MCP)

Install the MCP extra once per machine:

```bash
pip install "skillgate-ai[mcp]"
```

The **skillgate** MCP server runs `skillgate mcp --root .` against the **workspace root** (where `skills/` lives). Override with client env `SKILLGATE_ROOT` if needed.

## Primary tools

### `doctor`

Call first when checks fail to start or harness auth is unclear. Returns agent availability and **boolean** key presence (never secret values).

### `validate_skill`

Arguments: `skill` — pack folder name, path, or `SKILL.md`. Strict validation of frontmatter and cases. Use before `check_start`.

### `dataset_scaffold`

Arguments: `skill` (existing) or `name` (new skill under `skills/`), optional `force`. Creates starter cases or a new skill directory.

## Workflow

1. `doctor` — confirm MCP and agents can run checks.
2. `validate_skill` on the target pack.
3. `dataset_scaffold` when adding a new skill or empty dataset.

## All thirteen MCP tools

| Tool | Purpose |
| --- | --- |
| `doctor` | Agents, keys (booleans), version |
| `validate_skill` | Strict SKILL.md + cases |
| `dataset_scaffold` | New skill or starter cases |
| `dataset_get` | Eval dataset view (see skillgate-dataset) |
| `case_add` | Add one check |
| `case_edit` | Edit a check |
| `case_remove` | Remove a check |
| `case_import` | Bulk CSV / JSONL / YAML |
| `check_start` | Start a check (see skillgate-check) |
| `check_poll` | Poll run status |
| `check_cancel` | Kill or skip a running check |
| `report_latest` | Latest saved run for a skill |
| `report_get` | One history run by id |

Headless Claude Code: `claude -p "..." --allowedTools mcp__skillgate` (or per-tool `mcp__skillgate__doctor`).