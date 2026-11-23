# Skill Gate plugin folder — build spec

**Base:** `fcab819` (main, MCP server #87) · **Status:** implement literally

**Authoring note:** STEP 1 intended `claude -p --model opus` on Mini; Pro session limit blocked the run. This spec was aligned to [Cursor Plugins reference](https://cursor.com/docs/reference/plugins), [Claude Code plugin manifest](https://code.claude.com/docs/en/plugins/manifest-reference), and `docs/mcp.md`.

---

## 1. File tree

```
skillgate/                          # repo root (unchanged src/, tests/, …)
├── .cursor-plugin/
│   └── marketplace.json            # Cursor directory (multi-plugin root)
├── .claude-plugin/
│   └── marketplace.json            # Claude marketplace from this git repo
├── plugin/                         # dual-format plugin payload (Cursor + Claude)
│   ├── .cursor-plugin/
│   │   └── plugin.json
│   ├── .claude-plugin/
│   │   └── plugin.json
│   ├── mcp.json                    # Cursor MCP (root-level discovery)
│   ├── .mcp.json                   # Claude MCP (root-level discovery)
│   ├── README.md                   # plugin README (install + MCP prerequisite)
│   └── skills/
│       ├── skillgate-setup/
│       │   └── SKILL.md
│       ├── skillgate-dataset/
│       │   └── SKILL.md
│       └── skillgate-check/
│           └── SKILL.md
├── docs/
│   └── plugin.md                   # user-facing install guide (both directories)
└── tests/
    └── test_plugin_folder.py       # manifest + frontmatter validation
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
| `keywords` | `["skillgate", "agent-skills", "evals", "mcp", "cursor"]` |
| `skills` | `"./skills/"` |
| `mcpServers` | `"./mcp.json"` |

### 2.2 `plugin/.claude-plugin/plugin.json`

Same metadata as Cursor manifest except **omit** `displayName` (optional in Claude; keep `name`, `description`, `version`, `author`, `homepage`, `repository`, `license`, `keywords`, `skills`, `mcpServers`).

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

### 2.5 `plugin/mcp.json` and `plugin/.mcp.json` (identical)

```json
{
  "mcpServers": {
    "skillgate": {
      "command": "skillgate",
      "args": ["mcp", "--root", "."]
    }
  }
}
```

Rules:

- **No secrets** in any JSON file.
- **No hardcoded user home paths.** `--root .` is the open workspace project root (where `skills/` lives). Optional override: users set `SKILLGATE_ROOT` in client MCP env (documented; not in committed config).
- Do **not** use `${PLUGIN_ROOT}` / `${PLUGIN_DATA}` (Cursor does not expand Agent-standard vars). Use `${CURSOR_PLUGIN_ROOT}` only if a future plugin script lives under `plugin/` (not required for this release).
- Claude expands `${CLAUDE_PLUGIN_ROOT}` in `.mcp.json` when needed; not required here.

### 2.6 MCP prerequisite (document in `plugin/README.md` and `docs/plugin.md`)

```bash
pip install "skillgate-ai[mcp]"
```

`skillgate` must be on `PATH` (venv, pipx, or `uv tool`). The MCP server name exposed to clients is **`skillgate`** (matches `FastMCP("skillgate")`).

---

## 3. Skills (`plugin/skills/*`)

Each `SKILL.md` uses Agent Skills frontmatter:

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

### 3.1 `skillgate-setup`

Teach: **`doctor`**, **`validate_skill`**, **`dataset_scaffold`**. Workflow: run `doctor` before live checks; `validate_skill` on a pack path/name; `dataset_scaffold` for new skills or starter cases. Link to all 13 tools in a reference table.

### 3.2 `skillgate-dataset`

Teach: **`dataset_get`**, **`case_add`**, **`case_edit`**, **`case_remove`**, **`case_import`**. Workflow: read dataset, mutate cases, bulk import. Include conflict modes for `case_import`.

### 3.3 `skillgate-check`

Teach: **`check_start`**, **`check_poll`**, **`check_cancel`**, **`report_latest`**, **`report_get`**. Workflow: one run at a time, poll with `include_report`, cancel kill/skip, fetch history. Note headless Claude: `--allowedTools mcp__skillgate` or `mcp__skillgate__doctor`.

### 3.4 Thirteen MCP tools (must appear in combined skill docs)

| Tool | Skill file |
| --- | --- |
| `doctor` | skillgate-setup |
| `validate_skill` | skillgate-setup |
| `dataset_scaffold` | skillgate-setup |
| `dataset_get` | skillgate-dataset |
| `case_add` | skillgate-dataset |
| `case_edit` | skillgate-dataset |
| `case_remove` | skillgate-dataset |
| `case_import` | skillgate-dataset |
| `check_start` | skillgate-check |
| `check_poll` | skillgate-check |
| `check_cancel` | skillgate-check |
| `report_latest` | skillgate-check |
| `report_get` | skillgate-check |

---

## 4. Tests — `tests/test_plugin_folder.py`

**Exact test function names and assertions:**

| Test | Asserts |
| --- | --- |
| `test_plugin_cursor_manifest_name_and_skills` | `plugin/.cursor-plugin/plugin.json` parses; `name == "skillgate"`; `skills == "./skills/"`; `mcpServers == "./mcp.json"` |
| `test_plugin_claude_manifest_name_and_skills` | `plugin/.claude-plugin/plugin.json` parses; `name == "skillgate"`; `skills == "./skills/"` |
| `test_plugin_version_matches_pyproject` | manifest `version` equals `tomllib` `[project].version` |
| `test_cursor_marketplace_lists_plugin_source` | root `.cursor-plugin/marketplace.json` has one plugin entry; `source == "./plugin"`; `name == "skillgate"` |
| `test_claude_marketplace_lists_plugin_source` | root `.claude-plugin/marketplace.json` same assertions |
| `test_mcp_json_skillgate_stdio_no_secrets` | `plugin/mcp.json` and `plugin/.mcp.json` define `mcpServers.skillgate` with `command == "skillgate"`, `args == ["mcp", "--root", "."]`; file text has no `sk-`, no `API_KEY`, no `/Users/` |
| `test_skillgate_setup_skill_frontmatter` | `name == skillgate-setup`; `description` non-empty |
| `test_skillgate_dataset_skill_frontmatter` | `name == skillgate-dataset`; `description` non-empty |
| `test_skillgate_check_skill_frontmatter` | `name == skillgate-check`; `description` non-empty |
| `test_plugin_skills_document_all_mcp_tools` | union of tool names mentioned across three SKILL.md files equals the 13-tool set |

No CI workflow file changes except listing `tests/test_plugin_folder.py` under existing pytest discovery (default: no edit).

---

## 5. Docs — `docs/plugin.md`

Sections:

1. **Prerequisite** — `pip install "skillgate-ai[mcp]"`.
2. **Cursor plugin directory** — install from marketplace repo URL / cursor.directory listing pointing at this GitHub repo (`.cursor-plugin/marketplace.json`).
3. **Claude Code marketplace** — `claude plugin marketplace add <clone-or-github>` then `claude plugin install skillgate@skillgate`.
4. **Local install (Claude)** — `claude plugin install ./plugin --plugin-dir` or marketplace add local path; `claude plugin validate ./plugin`.
5. **Local install (Cursor)** — load `plugin/` via plugin UI or `--plugin-dir` when supported; MCP from bundled `mcp.json`.
6. **MCP** — points to `docs/mcp.md` for `--allowedTools` headless pattern.

Add a short pointer in `README.md` (Agent integrations section or after MCP extra table) linking to `docs/plugin.md`.

---

## 6. Acceptance criteria

- [ ] Tree matches §1; manifests match §2.
- [ ] Three skills load in plugin clients; each teaches its MCP tools; all 13 names documented.
- [ ] MCP configs launch `skillgate mcp` with workspace `.` root; no secrets.
- [ ] `tests/test_plugin_folder.py` passes; all ten named tests green.
- [ ] `ruff check .`, `ruff format --check .`, `mypy src`, `pytest -q -m "not integration"` green.
- [ ] `claude plugin validate ./plugin` exits 0 on Mini (manual QA).
- [ ] Local Claude marketplace install shows skills + skillgate MCP (manual QA).

---

## 7. DO NOT TOUCH

- `src/skillgate_ai/**` (engine, MCP implementation, CLI) — **no changes**.
- `.github/workflows/**` — **no changes** (unless a future dedicated job is explicitly requested; this spec does not require it).
- Version bumps in manifests should track `pyproject.toml` only when releasing; tests read pyproject dynamically.