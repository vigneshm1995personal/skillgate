# Skill Gate plugin

Dual **Cursor** and **Claude Code** plugin that bundles three agent skills plus the **skillgate** MCP server.

## Prerequisites

```bash
pip install "skillgate-ai[mcp]"
```

Ensure `skillgate` is on your `PATH`. The MCP server runs:

```bash
skillgate mcp --root .
```

with `.` as the **workspace project root** (the folder that contains your `skills/` directory). Set `SKILLGATE_ROOT` in the client MCP environment to override.

## Components

| Path | Role |
| --- | --- |
| `skills/skillgate-setup` | `doctor`, `validate_skill`, `dataset_scaffold` |
| `skills/skillgate-dataset` | `dataset_get`, case tools, `case_import` |
| `skills/skillgate-check` | `check_*`, `report_*` |
| `mcp.json` / `.mcp.json` | stdio MCP `skillgate` server |

Full install instructions: [docs/plugin.md](../docs/plugin.md) in the repository root.

```text
/plugin install skillgate --marketplace vigneshm1995personal/skillgate
```