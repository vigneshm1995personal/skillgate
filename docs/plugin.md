# Skill Gate plugin (Cursor and Claude Code)

The repository ships a [plugin](../plugin/) directory for the [Cursor plugin directory](https://cursor.com/docs/plugins) and [Claude Code plugins](https://code.claude.com/docs/en/plugins).

## Prerequisite

```bash
pip install "skillgate-ai[mcp]"
```

See also [MCP setup](mcp.md) for tool names and headless `--allowedTools` patterns.

## Install from Cursor

1. Open Cursor **Settings → Plugins** (or the marketplace UI on [cursor.directory](https://cursor.directory)).
2. Add or browse the marketplace that lists this repository (manifest at [`.cursor-plugin/marketplace.json`](../.cursor-plugin/marketplace.json)).
3. Install the **skillgate** plugin. Skills load from `plugin/skills/`; MCP loads from `plugin/mcp.json`.

## Install from Claude Code marketplace

From a clone of this repo:

```bash
claude plugin marketplace add /path/to/skillgate
claude plugin install skillgate@skillgate
```

The marketplace name is `skillgate` (see [`.claude-plugin/marketplace.json`](../.claude-plugin/marketplace.json)). Restart Claude Code after install.

## Local install (Claude)

Validate and load from disk:

```bash
claude plugin validate /path/to/skillgate/plugin
claude plugin marketplace add /path/to/skillgate
claude plugin install skillgate@skillgate
```

Confirm with `claude plugin list` and `/mcp` (server **skillgate**).

## Local install (Cursor)

1. Use **Plugins** UI to add the git repo or local folder that contains `.cursor-plugin/marketplace.json`.
2. Enable **skillgate**. Skills and MCP follow `plugin/.cursor-plugin/plugin.json`.

For headless `cursor-agent`, pass `--plugin-dir /path/to/skillgate/plugin` when your build supports it.

## MCP behavior

The plugin launches MCP via `plugin/bin/skillgate-mcp` (resolves `skillgate` on `PATH` or under `~/.local/bin`). Override with env `SKILLGATE_BIN` if needed. Server args: `mcp --root .` where `.` is your workspace root.

Headless Claude (installed plugin) tools are prefixed `mcp__plugin_skillgate_skillgate__*`. Allow with `--allowedTools "mcp__skillgate"` (server-wide) or a specific tool name. The plugin starts MCP via `bin/skillgate-mcp`, which resolves a `skillgate` build with the `mcp` subcommand (`../.venv/bin` when developing from a git checkout, then `~/.local/bin`, optional `SKILLGATE_BIN`).

For scripted runs after connection failures, touch `plugin/.mcp.json` to force a retry and clear stale entries in `~/.claude/mcp-needs-auth-cache.json` if needed.

Do not commit API keys into plugin JSON. `doctor` reports key **presence** only as booleans.