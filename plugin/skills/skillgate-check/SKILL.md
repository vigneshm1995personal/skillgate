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

Start a run: `skill`, optional `harness` (`auto` | `cursor-agent` | `codex` | `claude`), `case_ids`, `tryout`, `no_judge`, `model`, `timeout_sec`. Returns `run_id`, `tryout`, `tryout_reason`, and `run_gate`.

No `case_ids`, or `case_ids` listing every pinned case without `tryout: true`, runs officially and can move Deploy. A partial list, any draft case, or `tryout: true` is a tryout that never moves the gate.

Responses include `run_gate`: `kind` (`official` | `tryout`), `moves_gate`, `decision`, `reason`, and `tryout_reason` (`explicit` | `subset` | `includes_drafts`, or null).

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

## All fifteen MCP tools

| Tool | Purpose |
| --- | --- |
| `validate_skill` | Strict SKILL.md + cases validation |
| `dataset_scaffold` | Create a new skill or starter cases |
| `dataset_get` | Compact dataset view (paths, sizes, tool_checks); `include_files: true` for file text |
| `case_get` | One case in full (file text, expected output, tool_checks) |
| `case_add` | Add one check (optional `tool_checks`) |
| `case_edit` | Edit a check; `tool_checks`: omit = unchanged, `{}` = clear, object = replace |
| `case_remove` | Remove a check |
| `case_import` | Bulk import CSV / JSONL / YAML |
| `pack_tool_checks_set` | Replace pack-level `tool_checks` (`{}` clears) |
| `check_start` | Start a check (one at a time) |
| `check_poll` | Poll run status (includes `run_gate`) |
| `check_cancel` | Kill or skip a running check |
| `report_latest` | Latest saved run for a skill |
| `report_get` | One history run (`history show --json` shape) |
| `doctor` | Agents, key presence (booleans), version |