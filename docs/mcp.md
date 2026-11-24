# Skill Gate MCP server

Install the optional extra:

```bash
pip install 'skillgate-ai[mcp]'
```

`[mcp]` installs only the MCP server. `skillgate ui` (the local web UI) needs the `ui` extra: install `pip install 'skillgate-ai[mcp,ui]'` or `pip install 'skillgate-ai[all]'` to use both. With `[mcp]` alone, `skillgate ui` exits with a missing-extra message.

Start the stdio server from your project root (where `skills/` lives):

```bash
skillgate mcp --root .
```

`--root` overrides `SKILLGATE_ROOT`, which overrides the auto-detected project root.

## Client configuration

### Cursor (`mcp.json`)

```json
{
  "mcpServers": {
    "skillgate": {
      "command": "skillgate",
      "args": ["mcp", "--root", "."],
      "env": {
        "SKILLGATE_ROOT": "/absolute/path/to/your/project"
      }
    }
  }
}
```

### Claude Code

```bash
claude mcp add skillgate -- skillgate mcp --root .
```

**Headless (`claude -p`)**: non-interactive runs cannot answer permission prompts, so allow the Skill Gate tools up front:

```bash
claude -p "Run skillgate check_start on skills/pdf, poll until done, summarize" \
  --allowedTools "mcp__skillgate"
```

`mcp__skillgate` allows every tool from the server named `skillgate`. Allow single tools with names like `mcp__skillgate__check_start`. Use `--mcp-config <file>` (plus `--strict-mcp-config` to ignore other configured servers) when the server is not registered via `claude mcp add`. The CLI also accepts `--allowed-tools` as an alias for `--allowedTools`.

### Codex

Point Codex at the same command and args as Cursor (`skillgate mcp --root <project>`).

## Tools

| Tool | Purpose |
|------|---------|
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

## Official runs vs tryouts

`check_start` with no `case_ids`, or with `case_ids` listing every pinned case, is an official run: it can unlock or block Deploy. A partial list, any draft case, or `tryout: true` runs as a tryout and never moves the gate. `check_poll`, `report_get`, and `report_latest` return `run_gate` with `kind` (`official` | `tryout`), `moves_gate`, `decision`, `reason`, and `tryout_reason` (`explicit` | `subset` | `includes_drafts`, or null).

Checks need `skillgate login` or a configured API key. The server never returns secret values.