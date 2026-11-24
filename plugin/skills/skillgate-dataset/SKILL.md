---
name: skillgate-dataset
description: Use when reading or editing Skill Gate eval datasets — list cases, add or edit checks, remove rows, or bulk import CSV, JSONL, or YAML into a skill pack. Requires the skillgate MCP server.
license: Apache-2.0
metadata:
  author: skillgate-ai
  version: "1.0"
---

# Skill Gate datasets (MCP)

Work against skill packs under the workspace `skills/` tree (or `SKILLGATE_ROOT`). Prefer MCP tools over hand-editing `evals/` when an agent is driving changes.

## Primary tools

### `dataset_get`

Arguments: `skill`, optional `include_files` (default `false`). Compact view lists paths, sizes, and `tool_checks`; pass `include_files: true` for file text bodies.

### `case_get`

One case in full: `skill`, `case_id`. Use after compact `dataset_get` when editing a specific check.

### `case_add`

Add one check: `skill`, `prompt`, optional `case_id`, `expected`, `output_path`, `should_trigger`, `inputs`, `output_optional`, `force`, `tool_checks`.

### `case_edit`

Edit fields on an existing case: `skill`, `case_id`, and any of `prompt`, `expected`, `output_path`, `output_optional`, `tool_checks` (omit/null = unchanged, `{}` = clear, object = replace whole block).

### `pack_tool_checks_set`

Replace pack-level `tool_checks`: `skill`, `tool_checks` (`null` or `{}` clears).

### `case_remove`

Remove a case: `skill`, `case_id`.

### `case_import`

Bulk import: `skill`, `content`, optional `format` (`csv` | `jsonl` | `yaml`), `filename`, `on_conflict` (`fail` | `skip` | `replace`), `dry_run`.

## Workflow

1. `dataset_get` (compact) → `case_get` for the case you will edit.
2. Use `case_add` / `case_edit` / `case_remove` for incremental edits.
3. Use `case_import` for spreadsheets or generated fixtures; run with `dry_run: true` first when unsure.

Validate after large edits with `validate_skill` (skillgate-setup skill).

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