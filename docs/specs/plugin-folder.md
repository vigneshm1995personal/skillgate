# Skill Gate plugin folder — build spec

**Base:** `fcab819` (main, MCP server #87) · **Implemented:** PR [#88](https://github.com/vigneshm1995personal/skillgate/pull/88), head `89f032f` · **Status:** shipped; spec matches the merge diff

**Authoring:** Initial spec (web docs + MCP #87). Reconciled with the shipped tree via `claude -p --model opus` on Mini (2026-11-23).

---

## 1. File tree (PR #88)

```
skillgate/                              # repo root — no src/ or workflow edits in PR
├── .cursor-plugin/
│   └── marketplace.json
├── .claude-plugin/
│   └── marketplace.json
├── plugin/
│   ├── .cursor-plugin/
│   │   └── plugin.json
│   ├── .claude-plugin/
│   │   └── plugin.json
│   ├── bin/
│   │   └── skillgate-mcp               # PATH shim for IDE-spawned MCP
│   ├── mcp.json
│   ├── .mcp.json
│   ├── README.md                       # includes marketplace install hints (see §2.7)
│   └── skills/
│       ├── skillgate-setup/SKILL.md
│       ├── skillgate-dataset/SKILL.md
│       └── skillgate-check/SKILL.md
├── docs/
│   ├── plugin.md
│   └── specs/
│       └── plugin-folder.md            # this file
├── README.md                           # § Documentation link only (§5.2)
└── tests/
    └── test_plugin_folder.py
```

---

## 2. Manifest contents

### 2.1 `plugin/.cursor-plugin/plugin.json`

| Field | Value |
| --- | --- |
| `name` | `"skillgate"` |
| `displayName` | `"Skill Gate"` |
| `version` | same as `pyproject.toml` `[project].version` |
| `description` | Evaluate agent skills locally via MCP: validate packs, edit datasets, run checks, read reports. |
| `author.name` | `"Skill Gate AI contributors"` |
| `homepage` | `https://www.skill-gate-ai.app/` |
| `repository` | `https://github.com/vigneshm1995personal/skillgate` |
| `license` | `"Apache-2.0"` |
| `keywords` | `skillgate`, `agent-skills`, `evals`, `mcp`, **`cursor`** |
| `skills` | `"./skills/"` |
| `mcpServers` | `"./mcp.json"` |

### 2.2 `plugin/.claude-plugin/plugin.json`

Same as §2.1 except:

| Field | Claude value |
| --- | --- |
| `displayName` | **omitted** |
| `keywords` | … includes **`claude-code`** instead of `cursor` |
| `mcpServers` | `"./.mcp.json"` (not `./mcp.json`) |

### 2.3 `/.cursor-plugin/marketplace.json`

```json
{
  "name": "skillgate",
  "owner": { "name": "Skill Gate AI contributors" },
  "metadata": {
    "description": "Skill Gate: evaluate agent skills with MCP tools for Cursor and Claude Code."
  },
  "plugins": [
    {
      "name": "skillgate",
      "source": "./plugin",
      "description": "Validate skill packs, manage eval datasets, run checks, and read reports via the skillgate MCP server."
    }
  ]
}
```

### 2.4 `/.claude-plugin/marketplace.json`

```json
{
  "name": "skillgate",
  "description": "Skill Gate plugins for Claude Code",
  "owner": { "name": "Skill Gate AI contributors" },
  "plugins": [
    {
      "name": "skillgate",
      "source": "./plugin",
      "description": "Validate skill packs, manage eval datasets, run checks, and read reports via the skillgate MCP server."
    }
  ]
}
```

### 2.5 `plugin/mcp.json` and `plugin/.mcp.json`

Cursor (`mcp.json`): `"command": "${CURSOR_PLUGIN_ROOT}/bin/skillgate-mcp"`, `"args": ["--root", "."]`.

Claude (`.mcp.json`): `"command": "${CLAUDE_PLUGIN_ROOT}/bin/skillgate-mcp"`, same args.

See §2.5 / `plugin/bin/skillgate-mcp` shim (resolves `skillgate` without hardcoded user paths in JSON).

Rules:

- **No secrets** in any JSON file.
- **No hardcoded user home paths in JSON.** `--root .` is the **client workspace** root. Optional `SKILLGATE_ROOT` / `SKILLGATE_BIN` env (documented only).
- Use `${CURSOR_PLUGIN_ROOT}` / `${CLAUDE_PLUGIN_ROOT}` for plugin-local MCP commands (not `${PLUGIN_ROOT}`).

### 2.6 MCP prerequisite (`plugin/README.md`, `docs/plugin.md`)

```bash
pip install "skillgate-ai[mcp]"
```

`skillgate` on `PATH`. Server name **`skillgate`** (`FastMCP("skillgate")`).

### 2.7 `plugin/README.md` install hint

Document the same flow as `docs/plugin.md`: `claude plugin marketplace add <repo>` then `claude plugin install skillgate@skillgate`. Do **not** rely on a single `/plugin install … --marketplace owner/repo` line (not the documented CLI shape).

---

## 3. Skills (`plugin/skills/*`)

Frontmatter:

```yaml
---
name: <skill-name>   # must match directory name
description: <when to load this skill>
license: Apache-2.0
metadata:
  author: skillgate-ai
  version: "1.0"
---
```

### 3.1–3.3 Primary tools

| Skill dir | Primary MCP tools |
| --- | --- |
| `skillgate-setup` | `doctor`, `validate_skill`, `dataset_scaffold` |
| `skillgate-dataset` | `dataset_get`, `case_add`, `case_edit`, `case_remove`, `case_import` |
| `skillgate-check` | `check_start`, `check_poll`, `check_cancel`, `report_latest`, `report_get` |

Each `SKILL.md` includes a full table of all **13** tools. Headless Claude: `--allowedTools mcp__skillgate` or `mcp__skillgate__doctor`.

---

## 4. Tests — `tests/test_plugin_folder.py`

| Test | Asserts |
| --- | --- |
| `test_plugin_cursor_manifest_name_and_skills` | Cursor manifest: `name == "skillgate"`, `skills == "./skills/"`, `mcpServers == "./mcp.json"` |
| `test_plugin_claude_manifest_name_and_skills` | Claude manifest: `name == "skillgate"`, `skills == "./skills/"`, **`mcpServers == "./.mcp.json"`** |
| `test_plugin_version_matches_pyproject` | Both manifest `version` values equal `pyproject.toml` `[project].version` |
| `test_cursor_marketplace_lists_plugin_source` | One plugin entry; `name == "skillgate"`, `source == "./plugin"` |
| `test_claude_marketplace_lists_plugin_source` | Same |
| `test_mcp_json_skillgate_stdio_no_secrets` | MCP JSON: plugin-root wrapper commands; `args == ["--root", "."]`; no `sk-`, `API_KEY`, `/Users/` in file text; wrapper executable exists |
| `test_skillgate_mcp_wrapper_prefers_path_not_secrets` | `bin/skillgate-mcp` mentions `SKILLGATE_BIN`; no `.skillgate/` or `sk-` |
| `test_skillgate_setup_skill_frontmatter` | `name == skillgate-setup`, non-empty `description` |
| `test_skillgate_dataset_skill_frontmatter` | `name == skillgate-dataset`, non-empty `description` |
| `test_skillgate_check_skill_frontmatter` | `name == skillgate-check`, non-empty `description` |
| `test_plugin_skills_document_all_mcp_tools` | Union of `` `{tool}` `` occurrences across the three `SKILL.md` files equals the 13-tool set |

No `.github/workflows` change required (pytest auto-discovers `tests/test_plugin_folder.py`).

---

## 5. Docs

### 5.1 `docs/plugin.md`

Prerequisite, Cursor directory, Claude marketplace, local Claude/Cursor install, link to `docs/mcp.md`.

### 5.2 `README.md`

Single absolute link under `## Documentation` (avoids `test_readme_points_at_docs` vendor-word ban in Quickstart):

`[Plugin install (skills + MCP)](https://github.com/vigneshm1995personal/skillgate/blob/main/docs/plugin.md)`

---

## 6. Acceptance criteria

### 6.1 CI (automated)

- [x] Tree and manifests match §1–§2.
- [x] `tests/test_plugin_folder.py` — 11 tests green.
- [x] `ruff check`, `ruff format --check`, `mypy src`, `pytest -m "not integration"` green on PR #88.

### 6.2 Claude Code (manual, Mini)

| Step | Pass criterion | Observed (Mini) |
| --- | --- | --- |
| `claude plugin validate ./plugin` | exit 0 | Pass |
| `claude plugin validate` marketplaces | both JSON pass | Pass |
| `claude plugin marketplace add` + `install skillgate@skillgate` | 3 skills + MCP `skillgate` in `claude plugin details` | Pass |
| `claude -p --model opus --allowedTools mcp__skillgate` calls `doctor` | `mcp__plugin_skillgate_skillgate__doctor` invoked; reply `{"can_check": true}` (Mini 2026-11-23; after `plugin/bin/skillgate-mcp` + clear stale `~/.claude/mcp-needs-auth-cache.json` entry) | Pass |

### 6.3 Cursor (manual, Mini)

| Step | Pass criterion | Observed (Mini) |
| --- | --- | --- |
| `cursor-agent -p --trust --plugin-dir <repo>/plugin --workspace <temp>` | Skills `skillgate-setup`, `skillgate-dataset`, `skillgate-check` reported | Pass |
| Same harness + `doctor` | Output `{"can_check": …}` only | Pass (`can_check: true`) |
| MCP config | Loaded from plugin `mcp.json`; `--root .` is workspace (not `${CURSOR_PLUGIN_ROOT}`) | Pass; no workspace `.cursor/mcp.json` in throwaway dir |

---

## 7. DO NOT TOUCH

- `src/skillgate_ai/**` — **no changes** in PR #88.
- `.github/workflows/**` — **no changes** in PR #88.
- Plugin manifest `version` tracks `pyproject.toml`; tests read pyproject dynamically (no manual version bump in this PR).