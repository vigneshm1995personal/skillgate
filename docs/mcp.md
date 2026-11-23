# Skill Gate MCP server

Install the optional extra:

```bash
pip install 'skillgate-ai[mcp]'
```

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
| `dataset_get` | Read the eval dataset view |
| `case_add` | Add one check |
| `case_edit` | Edit a check |
| `case_remove` | Remove a check |
| `case_import` | Bulk import CSV / JSONL / YAML |
| `check_start` | Start a check (one at a time) |
| `check_poll` | Poll run status |
| `check_cancel` | Kill or skip a running check |
| `report_latest` | Latest saved run for a skill |
| `report_get` | One history run (`history show --json` shape) |
| `doctor` | Agents, key presence (booleans), version |

Checks need `skillgate login` or a configured API key. The server never returns secret values.