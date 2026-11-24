# Skill Gate plugin

Dual **Cursor** and **Claude Code** plugin that bundles three agent skills plus the **skillgate** MCP server.

## Prerequisites

```bash
pip install "skillgate-ai[mcp]"
```

Install `skillgate-ai[mcp]` so `skillgate` is available (typically `~/.local/bin` via pipx). The plugin starts MCP through `bin/skillgate-mcp` with `--root .` as the **workspace project root** (the folder that contains your `skills/` directory). Set `SKILLGATE_ROOT` in the client MCP environment to override.

## Components

| Path | Role |
| --- | --- |
| `skills/skillgate-setup` | `doctor`, `validate_skill`, `dataset_scaffold` |
| `skills/skillgate-dataset` | `dataset_get`, `case_get`, case tools, `case_import`, `pack_tool_checks_set` |
| `skills/skillgate-check` | `check_*`, `report_*` |
| `mcp.json` / `.mcp.json` | stdio MCP `skillgate` server |

Full install instructions: [docs/plugin.md](../docs/plugin.md) in the repository root.

```bash
claude plugin marketplace add https://github.com/vigneshm1995personal/skillgate
claude plugin install skillgate@skillgate
```