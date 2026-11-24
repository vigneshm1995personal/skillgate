# Skill Gate MCP server

Skill Gate ships a **local Model Context Protocol (MCP) server** over **stdio**. It exposes the same project-root operations agents use from the CLI—validate packs, edit checks, start eval runs, read reports—without a Skill Gate account. The server never returns API key values.

Use **`skillgate mcp`** when an IDE or headless agent needs programmatic access (Cursor, Claude Code, Codex, custom MCP clients). Use the **CLI** for scripts and CI (`skillgate check`, `skillgate deploy`). Use **`skillgate ui`** when you want the browser UI.

Fifteen tools are registered (see [Tools](#tools)). Checks need `skillgate login` or a configured provider key.

## Install

```bash
pip install "skillgate-ai[mcp]"
```

| Extra | Adds | Needed for |
| --- | --- | --- |
| `pip install "skillgate-ai[mcp]"` | `mcp` | `skillgate mcp` |
| `pip install "skillgate-ai[ui]"` | FastAPI, uvicorn | `skillgate ui` |
| `pip install "skillgate-ai[mcp,ui]"` | mcp + ui | MCP and local UI together |
| `pip install "skillgate-ai[all]"` | ui, docs, mcp | everything |

Without the `mcp` extra, `skillgate mcp` prints an install hint for `skillgate-ai[mcp]` and exits with code 2 (message on stderr).

**pipx / uvx** (no global venv):

```bash
pipx install "skillgate-ai[mcp]"
# or:
uvx --from "skillgate-ai[mcp]" skillgate mcp --root /path/to/project
```

The [plugin](../plugin/) launcher `bin/skillgate-mcp` falls back to `uvx --from "skillgate-ai[mcp]" skillgate mcp` when no local `skillgate` binary supports `mcp`.

## Start the server

From your **project root** (the directory that contains `skills/` or a skill pack):

```bash
skillgate mcp --root .
```

**Root resolution** (first match wins):

1. `--root` on the command line
2. `SKILLGATE_ROOT` in the environment (also bound to `--root` via Typer)
3. Auto-detected project root (`project_root()` from the current working directory)

Paths are expanded (`~`) and resolved. If the root is not a directory, stderr shows `Root <path> is not a folder.` and the process exits **2**.

At startup the server calls `load_env(workspace)` so `.env` and keys under that root are visible to checks.

**Transport:** stdio only. JSON-RPC uses the dedicated protocol fds. By default a **stdio guard** redirects stray harness writes away from stdout (debug only: `SKILLGATE_MCP_NO_STDIO_GUARD=1`).

**Skill argument:** tools accept a pack directory, catalog name/slug, absolute path under the root, or a path ending in `SKILL.md` (its parent pack is used). Resolution errors include `A skill name is required.`, `Skill '…' was not found.` (hint: connect an agent or paste a SKILL.md), and `That path is outside this project.`

## Client configuration

### Cursor (`.cursor/mcp.json`)

In your **project** (the folder you open in Cursor), create or edit `.cursor/mcp.json`:

Prefer an **absolute** project root so the server does not depend on the client's cwd:

```json
{
  "mcpServers": {
    "skillgate": {
      "command": "skillgate",
      "args": ["mcp", "--root", "/absolute/path/to/your/project"]
    }
  }
}
```

Alternatively, set only `SKILLGATE_ROOT` and omit `--root`:

```json
{
  "mcpServers": {
    "skillgate": {
      "command": "skillgate",
      "args": ["mcp"],
      "env": {
        "SKILLGATE_ROOT": "/absolute/path/to/your/project"
      }
    }
  }
}
```

If both are set, **`--root` wins** over `SKILLGATE_ROOT`.

**Cursor plugin:** install the repo plugin (see [plugin.md](plugin.md)). The plugin ships [`plugin/mcp.json`](../plugin/mcp.json) with `"command": "${CURSOR_PLUGIN_ROOT}/bin/skillgate-mcp"` and `"args": ["--root", "."]` (workspace root = project with `skills/`). The wrapper [`plugin/bin/skillgate-mcp`](../plugin/bin/skillgate-mcp) resolves `skillgate` on PATH, optional `SKILLGATE_BIN`, repo `../.venv/bin`, or `uvx --from "skillgate-ai[mcp]"`. Override the binary with `SKILLGATE_BIN` if needed.

### Claude Code

```bash
claude mcp add skillgate -- skillgate mcp --root /absolute/path/to/your/project
```

**Marketplace / plugin** (from a clone of this repo, matching [plugin.md](plugin.md)):

```bash
claude plugin marketplace add /path/to/skillgate
claude plugin install skillgate@skillgate
```

That loads [`plugin/.mcp.json`](../plugin/.mcp.json) (`${CLAUDE_PLUGIN_ROOT}/bin/skillgate-mcp`, `args: ["--root", "."]`).

#### Headless (`claude -p`)

Non-interactive runs cannot answer permission prompts, so allow tools up front:

```bash
claude -p "Run skillgate check_start on skills/pdf, poll until done, summarize" \
  --allowedTools "mcp__skillgate"
```

`mcp__skillgate` allows every tool from the server named `skillgate`. Allow a single tool with names like `mcp__skillgate__check_start`. With an installed **plugin**, tool names may be prefixed differently (for example `mcp__plugin_skillgate_skillgate__*`); run `/mcp` after install and match the listed prefix. Use `--mcp-config <file>` (and `--strict-mcp-config` to ignore other servers) when the server is not registered via `claude mcp add`. The CLI also accepts `--allowed-tools` as an alias for `--allowedTools`.

### Claude Desktop

Add a stdio server in Claude Desktop's config file (`claude_desktop_config.json` on macOS, typically under `~/Library/Application Support/Claude/`). Use an **absolute** project root; do not put API keys in `env`:

```json
{
  "mcpServers": {
    "skillgate": {
      "command": "skillgate",
      "args": ["mcp", "--root", "/absolute/path/to/your/project"]
    }
  }
}
```

### Codex

Point Codex at the same command and args as Cursor: `skillgate mcp --root <project>`.

### Generic MCP client

Spawn:

```text
skillgate mcp --root /absolute/path/to/project
```

Transport: stdio. Initialize the session, then `tools/list` and `tools/call`. Tool errors return MCP `isError` content: `message` plus optional `Hint: …` line.

## Typical flow

1. `doctor` — confirm `can_check` and agent login status.
2. `validate_skill` — strict SKILL.md + cases.
3. `dataset_get` (compact) or `case_get` for one check in full.
4. `case_add` / `case_edit` / `case_import` (`dry_run` first) / `pack_tool_checks_set` as needed.
5. `check_start` → `check_poll` until `status` is not `running` (use `include_report` when finished).
6. `report_get` for the full saved report shape, or `report_latest` for the newest run on a pack.

## Tools

Summary:

| Tool | Purpose |
| --- | --- |
| `validate_skill` | Strict SKILL.md + cases validation |
| `dataset_scaffold` | Create a new skill or starter cases |
| `dataset_get` | Read the eval dataset view |
| `case_get` | One check in full (prompt, fixtures, golden, tool_checks) |
| `case_add` | Add one check |
| `case_edit` | Edit a check |
| `case_remove` | Remove a check |
| `case_import` | Bulk import CSV / JSONL / YAML |
| `pack_tool_checks_set` | Replace pack-level tool_checks |
| `check_start` | Start a check (one at a time) |
| `check_poll` | Poll run status |
| `check_cancel` | Kill or skip a running check |
| `report_latest` | Latest saved run for a skill |
| `report_get` | One history run (`history show --json` shape) |
| `doctor` | Agents, key presence (booleans), version |

Pack-editing tools return a compact `dataset` (`include_files=false`) unless noted. For `tool_checks` schema details see [writing-a-dataset.md#tool-call-checks](writing-a-dataset.md#tool-call-checks) and [pack.md](pack.md).

### Pack and dataset

#### `validate_skill`

Validates a skill pack (strict ingest).

| Parameter | Type | Default | Notes |
| --- | --- | --- | --- |
| `skill` | string | (required) | Pack name, path, or `SKILL.md` path |

**Returns:** On success `{ok: true, name, description, warning, path}`. On validation failure `{ok: false, path, error: {message, hint?}}` (normal return, not an MCP tool error). Skill resolution failures raise a tool error.

#### `dataset_scaffold`

Creates starter cases for an existing skill or scaffolds a new skill under `skills/`.

| Parameter | Type | Default | Notes |
| --- | --- | --- | --- |
| `skill` | string \| null | null | Existing pack |
| `name` | string \| null | null | New skill folder name |
| `force` | boolean | false | Replace existing cases when scaffolding `skill` |

Pass **exactly one** of `skill` or `name`. Errors: `Pass skill or name, not both.`, `Pass one of skill or name.`, `This skill already has cases.` (hint: `force=true`).

**Returns:** `{ok, path, created, dataset}`.

#### `dataset_get`

| Parameter | Type | Default | Notes |
| --- | --- | --- | --- |
| `skill` | string | (required) | |
| `include_files` | boolean | false | When true, embed fixture file bodies |

**Returns:** `{path, include_files, dataset}`. Error: `Not a skill folder.`

#### `case_get`

| Parameter | Type | Default | Notes |
| --- | --- | --- | --- |
| `skill` | string | (required) | |
| `case_id` | string | (required) | Slugged before lookup |

**Returns:** `{path, …}` with full case view. Error: `No check named <slug>.`

### Editing cases

#### `case_add`

| Parameter | Type | Default | Notes |
| --- | --- | --- | --- |
| `skill` | string | (required) | |
| `prompt` | string | (required) | |
| `case_id` | string \| null | null | Auto-generated if omitted |
| `expected` | string \| null | null | Golden text |
| `output_path` | string \| null | null | |
| `should_trigger` | boolean | true | Required for `must_call` tool_checks |
| `inputs` | string[] \| null | null | Fixture paths |
| `output_optional` | boolean | false | |
| `force` | boolean | false | Overwrite existing id |
| `tool_checks` | object \| null | null | Per-case block |

**Returns:** `{ok: true, case_id, dataset}`.

#### `case_edit`

| Parameter | Type | Default | Notes |
| --- | --- | --- | --- |
| `skill` | string | (required) | |
| `case_id` | string | (required) | |
| `prompt` | string \| null | null | Unchanged if null |
| `expected` | string \| null | null | |
| `output_path` | string \| null | null | |
| `output_optional` | boolean \| null | null | |
| `tool_checks` | object \| null | null | null = unchanged, `{}` = clear, object = replace |

Error if every optional field is null: `Nothing to change.`

**Returns:** `{ok: true, case_id, dataset}`.

#### `case_remove`

| Parameter | Type | Default |
| --- | --- | --- |
| `skill` | string | (required) |
| `case_id` | string | (required) |

**Returns:** `{ok: true, removed, dataset}`.

#### `case_import`

| Parameter | Type | Default | Notes |
| --- | --- | --- | --- |
| `skill` | string | (required) | |
| `content` | string | (required) | Max 2 MiB UTF-8 |
| `format` | `csv` \| `jsonl` \| `yaml` \| null | null | Inferred from `filename` when null |
| `filename` | string \| null | null | Hint for format |
| `on_conflict` | `fail` \| `skip` \| `replace` | `fail` | |
| `dry_run` | boolean | false | Plan only, no writes |

**Returns:** `{ok, dry_run, format, rows, warnings, applied, dataset}`.

#### `pack_tool_checks_set`

| Parameter | Type | Default | Notes |
| --- | --- | --- | --- |
| `skill` | string | (required) | |
| `tool_checks` | object \| null | (required) | null or `{}` clears pack-level block |

**Returns:** `{ok: true, tool_checks, dataset}`.

### Running checks

#### `check_start`

Starts one eval run. Only **one check at a time** per MCP server process and per project (cross-process lock).

| Parameter | Type | Default | Notes |
| --- | --- | --- | --- |
| `skill` | string | (required) | |
| `harness` | `auto` \| `cursor-agent` \| `codex` \| `claude` | `auto` | |
| `case_ids` | string[] \| null | null | Subset forces tryout (see below) |
| `tryout` | boolean | false | Explicit tryout |
| `no_judge` | boolean | false | |
| `model` | string \| null | null | Override |
| `timeout_sec` | integer \| null | null | |

Errors: missing API key (from `missing_key_error()`), busy when another run holds the lock, unknown `case_ids`, `This skill has no checks yet.`

**Returns:** `{id, status, skill, tryout, tryout_reason, case_ids, run_gate}` where `run_gate` summarizes deploy impact (see [Official runs vs tryouts](#official-runs-vs-tryouts)).

#### `check_poll`

| Parameter | Type | Default | Notes |
| --- | --- | --- | --- |
| `run_id` | string | (required) | `[A-Za-z0-9_-]{1,128}` |
| `include_report` | boolean | false | Full report when run finished |

Resolves a run in order: in-memory registry → pack **history** (`evals/history/*.jsonl`) → on-disk **run status** at `<pack>/evals/history/runs/<run_id>.json`. Errors: `Invalid run id.`, `Unknown run …`

When the run is finished and `include_report` is false, response includes `report: null` and `report_omitted: true`. Finished rows include top-level **`gate`** (`green` / `red` / `needs review` — eval outcome), **`gate_decision`** (`pending` / `blocked` / `cleared` — whether this run changes Deploy), plus **`run_gate`** and **`tryout_reason`** when known (see [Gate fields](#gate-fields-run_gate-vs-gate)).

#### `check_cancel`

| Parameter | Type | Default | Notes |
| --- | --- | --- | --- |
| `run_id` | string | (required) | |
| `mode` | `kill` \| `skip` | `kill` | `skip` skips current case |

Async: returns `{ok: true, id, mode, status: "running"}`; keep polling. Error: `Run … is not running.`

### Reports

#### `report_latest`

| Parameter | Type | Default |
| --- | --- | --- |
| `skill` | string | (required) |

**Returns:** `{run, path}` where `run` may be `null` if the pack was never checked.

#### `report_get`

| Parameter | Type | Default | Notes |
| --- | --- | --- | --- |
| `run_id` | string | (required) | |
| `skill` | string \| null | null | Narrow search to one pack |

Same JSON shape as `skillgate history show --json` (history rows only — **no** on-disk run-status fallback). A run that is still in flight after an MCP server restart is **not** visible here until it is appended to history; use **`check_poll`** for in-flight or disk-backed status. Error: `No run named <id>.`

### Diagnostics

#### `doctor`

No parameters.

**Returns:** `{root, can_check, agents, keys, version}` — each `keys` entry is booleans only (never secret values).

## Official runs vs tryouts

Deploy gate semantics match the CLI and UI.

### Gate fields: `run_gate` vs `gate`

Poll and report payloads carry **two layers**:

| Layer | Fields | Meaning |
| --- | --- | --- |
| **Eval outcome** | `gate`, `gate_decision`, `gate_reason` | Per-run scoring: `gate` is `green`, `red`, or `needs review` from the check/judge. `gate_decision` is `pending`, `blocked`, or `cleared` — whether **this run** may unlock or block Deploy. |
| **Tryout / deploy summary** | `tryout`, `tryout_reason`, **`run_gate`** | Whether the run counts as official or tryout and a uniform deploy summary: `run_gate.kind`, `run_gate.moves_gate`, `run_gate.decision`, `run_gate.reason`, and optional `run_gate.tryout_reason`. |

`run_gate.decision` reuses the same `pending` / `blocked` / `cleared` vocabulary but is computed for agents via `run_gate_summary` (includes running-state `pending`, tryout rules, and `moves_gate`). Use **`gate`** / **`gate_decision`** for pass-fail and deploy copy; use **`run_gate`** + **`tryout`** when deciding if a run may move the pack gate.

Every poll/report on a saved or resolved run includes **`run_gate`**:

| Field | Meaning |
| --- | --- |
| `kind` | `official` or `tryout` |
| `moves_gate` | Whether this run can advance or block deploy |
| `decision` | `pending`, `blocked`, or `cleared` |
| `reason` | Human-readable gate explanation |
| `tryout_reason` | Set for tryouts: `explicit`, `subset`, or `includes_drafts` |

**Official run:** full pinned check set (default `check_start`).

**Tryout** (never moves the deploy gate):

- `tryout: true` on `check_start` → `tryout_reason: "explicit"`
- `case_ids` listing a strict subset of pinned checks → tryout (`subset` or `includes_drafts` if drafts are included)
- Any `case_ids` filter that is not exactly the pinned set forces tryout

Partial `case_ids` runs are always tryouts and never move the deploy gate.

## Errors

- Most failures raise an MCP **tool error** (`isError: true`) with text `message` and optional second line `Hint: …`.
- `validate_skill` returns `ok: false` in the JSON body instead of raising, for SKILL validation failures.

## Concurrency and disk-backed status

- One active check per MCP server and per project root (registry + `project_run_lock`).
- **Live run status on disk** is written under each pack at  
  **`<pack>/evals/history/runs/<run_id>.json`** (`history_dir` → `evals/history`, then `runs/`; see `run_status.status_path`). This is **not** under `.skillgate/`.
- After an MCP **server restart**, **`check_poll`** can still resolve an in-flight run via that file (and then history if the run finished). **`report_get`** and **`report_latest`** read **history only** — they do **not** read `evals/history/runs/*.json`. For a restarted server watching a still-running check, keep calling **`check_poll`**, not `report_get`.
- **Orphan detection:** while status is `running` or `started`, a disk snapshot is treated as **orphaned** when, on the **same host** as the recorded owner, the owner **pid is dead**, **or** `heartbeat_at` is older than **60 seconds** (`ORPHAN_HEARTBEAT_SEC`). The owning process refreshes the heartbeat every **10 seconds** (`HEARTBEAT_INTERVAL_SEC`). Orphaned runs get `status: "orphaned"` and an error message that the Skill Gate process exited without saving a result.
- `run_id` must match `^[A-Za-z0-9_-]{1,128}$`.

## Security

Do not commit API keys into MCP `env` blocks. The server and `doctor` report key **presence** only as booleans. Harness auth diagnostics in poll responses are sanitized (no raw secrets).

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Server missing in client | Command on PATH; install `skillgate-ai[mcp]`; restart client after config change |
| Immediate exit 2, stderr mentions `[mcp]` | Reinstall with the mcp extra |
| `Root … is not a folder` | Fix `--root` / `SKILLGATE_ROOT` |
| `can_check: false` in `doctor` | `skillgate login` or set provider keys under the project root |
| Harness errors / logged out | `doctor.agents`; sign in to Cursor, Claude, or Codex as needed |
| Tool calls denied in `claude -p` | `--allowedTools` / plugin-specific tool prefix |
| Broken MCP stream / garbled JSON | Harness wrote to stdout; ensure stdio guard is on (default); do not wrap server with tools that print to stdout |
| `check_start` busy | Another run in this project; `check_poll` or `check_cancel` |
| Long runs | Poll `check_poll`; increase `timeout_sec` on `check_start` |

## See also

- [Plugin install (Cursor & Claude Code)](plugin.md)
- [Local UI](ui.md) — requires `skillgate-ai[ui]` or `[all]`
- [10-minute quickstart](quickstart.md)