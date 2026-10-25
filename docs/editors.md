# Editor MCP

The Skill Gate MCP server is remote streamable HTTP at `https://mcp.skill-gate-ai.app/mcp`. Server name: `skill-gate`. Tools: `check_skill`, `run_eval`, `gate`.

Auth is a Skill Gate token (`sgt_…`) issued at [Connect](https://www.skill-gate-ai.app/connect) after GitHub sign-in. Pass it as `Authorization: Bearer` from the `SKILLGATE_TOKEN` environment variable. Do not put the token in a committed file.

```bash
export SKILLGATE_TOKEN=sgt_YOUR_TOKEN
```

Without a Skill Gate token, use the local CLI as the offline bring-your-own-key path: `pip install skillgate-ai`, then `skillgate keys set` and `skillgate check`.

## Cursor

[Add to Cursor](https://cursor.com/install-mcp?name=skill-gate&config=eyJ1cmwiOiJodHRwczovL21jcC5za2lsbC1nYXRlLWFpLmFwcC9tY3AiLCJoZWFkZXJzIjp7IkF1dGhvcml6YXRpb24iOiJCZWFyZXIgJHtlbnY6U0tJTExHQVRFX1RPS0VOfSJ9fQ==)

Deeplink:

```
cursor://anysphere.cursor-deeplink/mcp/install?name=skill-gate&config=eyJ1cmwiOiJodHRwczovL21jcC5za2lsbC1nYXRlLWFpLmFwcC9tY3AiLCJoZWFkZXJzIjp7IkF1dGhvcml6YXRpb24iOiJCZWFyZXIgJHtlbnY6U0tJTExHQVRFX1RPS0VOfSJ9fQ==
```

Or save this as `.cursor/mcp.json` (project) or `~/.cursor/mcp.json` (every project):

```json
{
  "mcpServers": {
    "skill-gate": {
      "url": "https://mcp.skill-gate-ai.app/mcp",
      "headers": {
        "Authorization": "Bearer ${env:SKILLGATE_TOKEN}"
      }
    }
  }
}
```

`/gate-skill` runs `check_skill` on the open `SKILL.md`. This repo ships that command at `.cursor/commands/gate-skill.md`. Copy that file into another project to get the same `/` command.

## Claude Code

One-line install (token already exported):

```bash
claude mcp add --transport http skill-gate https://mcp.skill-gate-ai.app/mcp --header "Authorization: Bearer ${SKILLGATE_TOKEN}"
```

This repository is a plugin marketplace. The plugin bundles the same MCP server, a `/skillgate` slash command, and an optional pre-commit hook (off until you turn it on):

```bash
claude plugin marketplace add vigneshm1995personal/skillgate
claude plugin install skillgate@skillgate
```

`/skillgate` calls `check_skill` on the nearest `SKILL.md`, or `run_eval` / `gate` when you ask. To enable the pre-commit hook, set the plugin option **Pre-commit gate**, or `SKILLGATE_PRECOMMIT=1`, or link the script:

```bash
ln -s ../../plugins/skillgate/scripts/pre-commit .git/hooks/pre-commit
```

The hook runs `skillgate check` on staged `SKILL.md` packs when the local CLI is installed. It does not read your Skill Gate token.

## Claude Desktop

Save this as Claude Desktop MCP config (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "skill-gate": {
      "type": "http",
      "url": "https://mcp.skill-gate-ai.app/mcp",
      "headers": {
        "Authorization": "Bearer sgt_YOUR_TOKEN"
      }
    }
  }
}
```

Replace `sgt_YOUR_TOKEN` with the token from [Connect](https://www.skill-gate-ai.app/connect). Prefer `SKILLGATE_TOKEN` in Cursor and Claude Code so the value is not stored in a file.

## Offline (local CLI)

No MCP and no Skill Gate token: keep using the public CLI with a key you already have.

```bash
pip install skillgate-ai
skillgate examples install
skillgate keys set
skillgate judge provider set
skillgate check skills/json-response
```

That path does not sign in to Skill Gate. See [Quickstart](quickstart.md).
