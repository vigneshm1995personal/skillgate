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

Arguments: `skill`. Returns the eval dataset view for that pack (cases, metadata). Call before mutating.

### `case_add`

Add one check: `skill`, `prompt`, optional `case_id`, `expected`, `output_path`, `should_trigger`, `inputs`, `output_optional`, `force`.

### `case_edit`

Edit fields on an existing case: `skill`, `case_id`, and any of `prompt`, `expected`, `output_path`, `output_optional`.

### `case_remove`

Remove a case: `skill`, `case_id`.

### `case_import`

Bulk import: `skill`, `content`, optional `format` (`csv` | `jsonl` | `yaml`), `filename`, `on_conflict` (`fail` | `skip` | `replace`), `dry_run`.

## Workflow

1. `dataset_get` to inspect current cases.
2. Use `case_add` / `case_edit` / `case_remove` for incremental edits.
3. Use `case_import` for spreadsheets or generated fixtures; run with `dry_run: true` first when unsure.

Validate after large edits with `validate_skill` (skillgate-setup skill).

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