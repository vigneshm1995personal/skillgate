---
name: skillgate-check
description: Use when running Skill Gate live evals — start a check, poll until finished, cancel if needed, and read latest or historical reports via MCP. Requires agent login or API keys for live checks.
license: Apache-2.0
metadata:
  author: skillgate-ai
  version: "1.0"
---

# Skill Gate checks and reports (MCP)

One check run at a time per MCP server process. Call `doctor` first if `check_start` refuses to run.

## Primary tools

### `check_start`

Start a run: `skill`, optional `harness` (`auto` | `cursor-agent` | `codex` | `claude`), `case_ids`, `tryout`, `no_judge`, `model`, `timeout_sec`. Returns `run_id`.

### `check_poll`

Poll status: `run_id`, optional `include_report: true` for the full report when complete.

### `check_cancel`

Cancel or skip: `run_id`, `mode` (`kill` | `skip`).

### `report_latest`

Latest saved eval for `skill` (from history on disk).

### `report_get`

One run: `run_id`, optional `skill` to narrow search. Same shape as `skillgate history show --json`.

## Workflow

1. `validate_skill` on the pack (setup skill).
2. `check_start` → capture `run_id`.
3. Loop `check_poll` until terminal state; use `include_report` on the last poll.
4. On stuck runs, `check_cancel`.
5. Use `report_latest` or `report_get` when reading history without a live run.

## Headless Claude Code

```bash
claude -p "Call doctor and summarize skillgate status" \
  --model opus \
  --allowedTools mcp__skillgate
```

## All thirteen MCP tools

| Tool | Purpose |
| --- | --- |
| `doctor` | Agents, keys (booleans), version |
| `validate_skill` | Strict SKILL.md + cases |
| `dataset_scaffold` | New skill or starter cases |
| `dataset_get` | Eval dataset view |
| `case_add` | Add one check |
| `case_edit` | Edit a check |
| `case_remove` | Remove a check |
| `case_import` | Bulk CSV / JSONL / YAML |
| `check_start` | Start a check |
| `check_poll` | Poll run status |
| `check_cancel` | Kill or skip a running check |
| `report_latest` | Latest saved run for a skill |
| `report_get` | One history run by id |