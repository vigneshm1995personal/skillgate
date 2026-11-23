# Skill Gate MCP server: combined implementation spec (MCP PRs 1–3)

**Base:** `ac355f80` (main) · **Target:** a single PR on top of main · **Status:** ready to implement

---

## 1. Overview

This PR ships three changes together:

1. **`RunRegistry`** (`src/skillgate_ai/run_registry.py`). A headless home for the run table, the worker thread and the `RunControl` lifecycle. It is taken almost line for line from `api_runs.start_run`. It does not depend on FastAPI or `AppState`. The local UI's `POST /api/runs` hands off to it, and HTTP behaviour stays the same.
2. **`skillgate_ai.mcp`**. A stdio-only MCP server built on the official Python `mcp` SDK (`FastMCP`). `skillgate mcp [--root PATH]` starts it, with `SKILLGATE_ROOT` as the fallback for `--root`. It ships as an optional extra: `pip install 'skillgate-ai[mcp]'`.
3. **13 tools**. Each one is a thin wrapper around an existing function. A pack argument can point at the pack folder, a skill name, or a `SKILL.md` file; a `SKILL.md` path becomes its parent folder. A live check is refused up front when no agent can start (no API key and no CLI login).

Non-goals: no HTTP/SSE transport, no MCP resources or prompts, no compare tools, no deploy, and no changes to any wire shape.

---

## 2. Architecture

```
skillgate mcp (cli/cmd_mcp.py)
  └─ require_extra("mcp") → resolve root → skillgate_ai.mcp.server.serve(root)
        └─ FastMCP("skillgate") over stdio
             └─ 13 @tool shims (server.py)  →  mcp/tools.py (pure functions, no SDK import)
                                                 ├─ McpContext(root, registry)   (mcp/context.py)
                                                 ├─ pack_edit / case_import / case_pack / scaffold / workspace
                                                 ├─ history.latest_eval + api_payloads.history_row_to_run
                                                 ├─ harness.harness_auth_status + keys.key_presence
                                                 └─ RunRegistry (run_registry.py)
                                                        └─ worker thread → gate.run_check(…, control, source="mcp")
                                                                              └─ run_lock.project_run_lock (inside run_check)

skillgate ui → api.py → api_runs.register_run_routes
                         └─ start_run(state, body) → RunRegistry(state.root, runs=state.runs,
                                                                 lock=state.lock, busy=state.gate_busy).start(…)
```

**Rules**

- `mcp/tools.py` and `mcp/context.py` must import cleanly without `fastapi` and without the `mcp` SDK. Only `mcp/server.py` imports the SDK.
- `run_registry.py` must not import `fastapi`, `api_runs` or `AppState`. It may import `deploy_gate`, `gate`, `live`, `report`, `errors`, `config` and `eval_config`.
- `api_payloads` does not import FastAPI at module load (FastAPI appears only under `TYPE_CHECKING` and inside `fail`), so `tools.py` can import `scrub_browser_payload` and `history_row_to_run` from it.
- On the stdio transport, stdout belongs to the protocol. No tool, and no code a tool calls in-process, may write to stdout. All CLI diagnostics in `cmd_mcp` go to stderr.
- Inside `skillgate_ai/mcp/server.py`, `from mcp.server.fastmcp import FastMCP` resolves to the top-level SDK because Python uses absolute imports. Never use `from . import` names that collide with the SDK.

---

## 3. `RunRegistry` API (`src/skillgate_ai/run_registry.py`, new)

```python
"""Headless run table: start a check on a worker thread, poll it, skip/kill it.

Shared by the local UI (api_runs) and the MCP server. No FastAPI.
"""

from __future__ import annotations

import copy
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from skillgate_ai.deploy_gate import local_gate
from skillgate_ai.errors import SkillGateError, timeout_harness_error
from skillgate_ai.gate import run_check
from skillgate_ai.live import create_control, drop_control, get_control
from skillgate_ai.report import progress_to_dict, report_to_dict

RunRecord = dict[str, Any]

HARNESS_PREFS = frozenset({"auto", "cursor-agent", "codex", "claude"})
BUSY_MESSAGE = "A check or compare is already running."


class RunBusyError(SkillGateError):
    """Another check/compare is running in this process. Cannot run, not a fail."""
    exit_code = 2


@dataclass(frozen=True)
class RunRequest:
    skill_path: Path
    harness: str = "auto"
    checks: list[dict[str, Any]] | None = None
    config: dict[str, Any] = field(default_factory=dict)
    tryout: bool = False
    no_judge: bool = False
    source: str = "ui"


def attach_stamped_config(record: RunRecord, report: dict[str, Any] | None) -> None:
    """(moved verbatim from api_runs)"""


def resolve_harness(config: dict[str, Any], requested: str | None) -> str:
    """config.harness_pref wins if it's a known pref, else requested, else 'auto'.
    Verbatim logic from api_runs worker lines 98-104."""


class RunRegistry:
    def __init__(
        self,
        root: Path,
        *,
        runs: dict[str, RunRecord] | None = None,
        lock: threading.Lock | None = None,
        busy: Callable[[], bool] | None = None,
    ) -> None: ...

    root: Path
    runs: dict[str, RunRecord]      # shared by reference when injected
    lock: threading.Lock            # shared by reference when injected

    def busy(self) -> bool:
        """Injected predicate if given (UI: AppState.gate_busy), else any record
        with status == 'running' (checked under self.lock)."""

    def start(self, request: RunRequest) -> dict[str, str]:
        """Raise RunBusyError if self.busy(). Seed the record (exact keys/values
        of today's api_runs seed), create_control(run_id), spawn daemon thread
        'skillgate-run-{run_id}', return {'id': run_id, 'status': 'running'}."""

    def get(self, run_id: str) -> RunRecord | None:
        """Deep copy of the live record under self.lock, or None. Unscrubbed."""

    def skip(self, run_id: str) -> bool:
        """get_control(run_id).request_skip(); False if no live control."""

    def kill(self, run_id: str) -> bool:
        """get_control(run_id).request_kill(); False if no live control."""

    def join(self, run_id: str, timeout: float | None = None) -> bool:
        """Wait for the worker thread. True if finished. For tests/shutdown."""

    def _work(self, run_id: str, request: RunRequest) -> None:
        """Body of today's api_runs.worker, verbatim, with:
           body.get('harness')  → request.harness
           checks               → request.checks
           config               → request.config
           tryout               → request.tryout
           bool(body.get('no_judge')) → request.no_judge
           source='ui'          → source=request.source
           state.root           → self.root
           state.runs[run_id]   → self.runs[run_id]
        finally: drop_control(run_id)."""
```

**Invariants**

- **Deadlock rule.** `start()` must call `self.busy()` **before** it acquires `self.lock`. The UI injects `busy=state.gate_busy`, which takes the same non-reentrant `state.lock`.
- The seed record keys, order and values are byte-identical to today's (`id, status, passed, gate, gate_decision, skill, skill_path, harness, tryout, completed_count, task_count, current_task_id, error, report, config, model, timeout_sec, temperature, reasoning_effort`). The seed's `harness` is `request.harness` (the UI passes `str(body.get("harness") or "auto")`, as it does today).
- Worker harness resolution: `resolve_harness(request.config, request.harness)`. If the UI didn't send a harness, `request.harness == "auto"`. The old code mapped `"" → "auto"`, so the result is the same.
- The registry does **not** probe `project_run_lock`. `run_check` already takes the lock inside the worker and returns `CheckResult(error=…, exit_code=2)` when it is busy. The UI behaviour is unchanged. MCP adds its own synchronous probe (§6.8).
- `self._threads: dict[str, threading.Thread]` is used only by `join`.

---

## 4. `api_runs.py` minimal diff

This is the only edit to the local UI. Do not touch `api.py`, `api_payloads.py` or `server.py`.

```diff
-import threading
-import uuid
 from typing import Any
@@
 from skillgate_ai.api_payloads import (
     AppState,
     fail,
-    local_gate,
     run_from_history,
     scrub_browser_payload,
     state_of,
 )
 from skillgate_ai.catalog import find_skill
 from skillgate_ai.config import get_llm_config, load_env, missing_key_error
-from skillgate_ai.errors import SkillGateError, timeout_harness_error
-from skillgate_ai.gate import run_check
-from skillgate_ai.live import create_control, drop_control, get_control
-from skillgate_ai.report import progress_to_dict, report_to_dict
+from skillgate_ai.live import get_control
+from skillgate_ai.run_registry import RunRegistry, RunRequest
+from skillgate_ai.run_registry import attach_stamped_config as attach_stamped_config
-
-
-def attach_stamped_config(...):  # moved to run_registry
-    ...
 
 def start_run(state: AppState, body: dict[str, Any]) -> dict[str, Any]:
     ... lines 46-58 unchanged (load_env, skill, tryout, checks, key check, config, gate_busy → fail(409)) ...
-    with state.lock:
-        ... seed ...
-    def worker() -> None:
-        ...
-    threading.Thread(target=worker, name=f"skillgate-run-{run_id}", daemon=True).start()
-    return {"id": run_id, "status": "running"}
+    registry = RunRegistry(state.root, runs=state.runs, lock=state.lock, busy=state.gate_busy)
+    return registry.start(
+        RunRequest(
+            skill_path=skill_path,
+            harness=str(body.get("harness") or "auto"),
+            checks=[dict(item) for item in checks] if checks else None,
+            config=config,
+            tryout=tryout,
+            no_judge=bool(body.get("no_judge")),
+            source="ui",
+        )
+    )
```

- `register_run_routes` stays as it is: `get_run` reads `state.runs`, and skip/kill use `get_control`.
- `attach_stamped_config` stays importable from `skillgate_ai.api_runs` through the re-export (`tests/test_eval_config.py:289`).
- In the seed, `task_count` uses `len(checks)` for the original list. The `RunRequest.checks` copy has the same length.

---

## 5. MCP package files

| File | Purpose |
|---|---|
| `src/skillgate_ai/mcp/__init__.py` | Docstring only. Must not import the SDK. |
| `src/skillgate_ai/mcp/context.py` | `McpContext`, `resolve_pack`, `tool_error_payload` |
| `src/skillgate_ai/mcp/tools.py` | 13 plain functions `(ctx, **args) -> dict`. No SDK import. |
| `src/skillgate_ai/mcp/server.py` | `build_server(ctx) -> FastMCP`, `serve(root) -> None`. The only SDK importer. |
| `src/skillgate_ai/cli/cmd_mcp.py` | `mcp_cmd` Typer command |

### 5.1 `context.py`

```python
@dataclass
class McpContext:
    root: Path
    registry: RunRegistry

    @classmethod
    def for_root(cls, root: Path) -> McpContext:
        root = root.expanduser().resolve()
        return cls(root=root, registry=RunRegistry(root))


def resolve_pack(ctx: McpContext, skill: str) -> Path:
    """Accept a pack dir, a skill name/slug, or a path to SKILL.md.
    - strip; empty → SkillGateError("A skill name is required.")
    - if Path(text).name == "SKILL.md" (case-sensitive) → use parent dir string
    - delegate to catalog.find_skill(ctx.root, text)  (keeps root containment +
      symlink-escape rules from #82; no new path logic)"""
```

### 5.2 Error mapping (`server.py`)

Every tool shim calls `tools.<name>(ctx, …)` inside `_call(fn, …)`:

- `SkillGateError` (this covers `SuiteError`, `CaseImportError`, `RunBusyError` and `MissingLLMKeyError`) → `raise ToolError(_render(exc))`, where `_render` is `exc.message` plus `"\nHint: " + exc.hint` when a hint exists. `ToolError` is imported from `mcp.server.fastmcp.exceptions`. The SDK turns it into `isError: true`.
- `CaseImportError` with `rows` → the message already lists each row (see `apply_case_import`), so pass it through unchanged.
- Any other exception propagates (`# noqa` is not needed). FastMCP reports it as a tool error. Do **not** add a broad `except Exception` (ruff BLE).

### 5.3 `server.py`

```python
def build_server(ctx: McpContext) -> FastMCP:
    server = FastMCP("skillgate", instructions=SERVER_INSTRUCTIONS)
    # 13 @server.tool() shims, typed params (Literal for enums), docstring = tool description
    return server

def serve(root: Path) -> None:
    build_server(McpContext.for_root(root)).run(transport="stdio")
```

`SERVER_INSTRUCTIONS` (one short paragraph): "Local Skill Gate. Tools act on skill packs under the project root. Start a check with check_start, then poll check_poll until status is not 'running'. Then use report_get for the full report. One check at a time."

---

## 6. Tool schemas

Shared conventions:

- `skill` is always a `str`, resolved with `resolve_pack`.
- Mutating tools return `{"ok": true, …, "dataset": dataset_view(pack)}`.
- Every return value is JSON-serialisable: a plain dict or list made of str, int, float, bool and None.
- No tool returns key values, env values or the contents of a vault file.

### 6.1 `validate_skill`
- **Input:** `skill: str`
- **Calls:** `ingest.ingest_skill(pack, strict=True)`
- **Output:** `{"ok": true, "name", "description", "warning": str|null, "path": str}`. A `SkillGateError` raised by `ingest_skill` is a **result**, not a tool error: `{"ok": false, "path", "error": {"message", "hint"}}`. Failing to resolve `skill` itself is a tool error.

### 6.2 `dataset_scaffold`
- **Input:** `skill: str | None = None`, `name: str | None = None`, `force: bool = False`. Exactly one of `skill` or `name` must be set; otherwise raise `SkillGateError("Pass skill or name, not both.")` (or "…one of skill or name").
- **`name` set:** `workspace.new_skill(ctx.root, name)`, which creates `skills/<name>` and pins the trigger cases.
- **`skill` set:** if `case_pack.skill_has_dataset(pack)` and not `force` → `SkillGateError("This skill already has cases.", hint="Pass force=true to replace them with the two starter cases.")`. Otherwise `scaffold.scaffold_trigger_cases(pack)`.
- **Output:** `{"ok": true, "path": str, "created": bool (true for name), "dataset": dataset_view(path)}`

### 6.3 `dataset_get`
- **Input:** `skill: str`
- **Calls:** `case_pack.dataset_view(pack)`. `None` → `SkillGateError("Not a skill folder.")`
- **Output:** `{"path": str, "dataset": {...}}`

### 6.4 `case_add`
- **Input:** `skill: str`, `prompt: str`, `case_id: str | None = None`, `expected: str | None = None`, `output_path: str | None = None`, `should_trigger: bool = True`, `inputs: list[str] | None = None`, `output_optional: bool = False`, `force: bool = False`
- **Calls:** `pack_edit.add_pack_case(pack, prompt=…, case_id=…, expected=…, output_path=…, should_trigger=…, inputs=…, force=…, output_optional=…)`
- **Output:** `{"ok": true, "case_id": str, "dataset": …}`. `case_id` is the new id (the set difference of ids before and after the call; if the call replaced a case, use the slugged `case_id` that was passed in).

### 6.5 `case_edit`
- **Input:** `skill: str`, `case_id: str`, `prompt: str | None = None`, `expected: str | None = None`, `output_path: str | None = None`, `output_optional: bool | None = None`. If every optional field is None → `SkillGateError("Nothing to change.")`.
- **Calls:** `pack_edit.edit_pack_case(...)`. The seed-lock error passes through.
- **Output:** `{"ok": true, "case_id": slug, "dataset": …}`

### 6.6 `case_remove`
- **Input:** `skill: str`, `case_id: str`
- **Calls:** `pack_edit.remove_pack_case(pack, case_id)`
- **Output:** `{"ok": true, "removed": slug, "dataset": …}`

### 6.7 `case_import`
- **Input:** `skill: str`, `content: str` (max 2 MiB UTF-8; larger → `SkillGateError("Import is too large (max 2 MiB).")`), `format: Literal["csv","jsonl","yaml"] | None = None`, `filename: str | None = None`, `on_conflict: Literal["fail","skip","replace"] = "fail"`, `dry_run: bool = False`
- **Calls:** `case_import.apply_case_import(pack, content.encode("utf-8"), filename=filename, format_hint=format, on_conflict=on_conflict, dry_run=dry_run)`
- **Output:** `{"ok": true, "dry_run": bool, "format": plan.format, "rows": [asdict(r) for r in plan.rows], "warnings": plan.warnings, "applied": 0 if dry_run else len(plan.checks), "dataset": …}`

### 6.8 `check_start`
- **Input:** `skill: str`, `harness: Literal["auto","cursor-agent","codex","claude"] = "auto"`, `case_ids: list[str] | None = None`, `tryout: bool = False`, `no_judge: bool = False`, `model: str | None = None`, `timeout_sec: int | None = None`
- **Preflight, in this order:**
  1. `pack = resolve_pack(ctx, skill)`
  2. `config.load_env(ctx.root)`
  3. If not `config.get_llm_config(ctx.root).has_any_key`, `raise config.missing_key_error()`. `has_any_key` is `has_startable_agent`, so a CLI login counts.
  4. If `ctx.registry.busy()` → `RunBusyError(BUSY_MESSAGE, hint=run_lock.BUSY_HINT)`
  5. Probe the cross-process lock with `with run_lock.project_run_lock(ctx.root): pass`. It raises a `SkillGateError` with `BUSY_MESSAGE` when the CLI or the UI holds it. A small race remains between the probe and the worker; `run_check` still guards it and records `status: "error"`.
- **Checks:** if `case_ids` is set → `checks = [c for cid in case_ids for c in pack_edit.tryout_checks(pack, cid)]` and force `tryout=True`, because `run_check` only honours a case subset when `only_listed=tryout`. Tryout runs never move the gate.
- **Config:** `{k: v for k, v in {"model": model, "timeout_sec": timeout_sec}.items() if v is not None}`
- **Calls:** `ctx.registry.start(RunRequest(skill_path=pack, harness=harness, checks=checks, config=config, tryout=tryout, no_judge=no_judge, source="mcp"))`
- **Output:** `{"id": str, "status": "running", "skill": pack.name, "tryout": bool}`

### 6.9 `check_poll`
- **Input:** `run_id: str`, `include_report: bool = False`
- **Lookup:** `ctx.registry.get(run_id)`. If it's missing, fall back to history (`_history_row(ctx, run_id, None)` from §6.12) mapped through `history_row_to_run`. If both miss → `SkillGateError(f"Unknown run {run_id}")`.
- **Output:** `scrub_browser_payload(record)`. When `status != "running"` and not `include_report`, replace `report` with `None` and add `"report_omitted": true`. While a run is in progress, `report` holds the small progress dict and is always kept.

### 6.10 `check_cancel`
- **Input:** `run_id: str`, `mode: Literal["kill","skip"] = "kill"`
- **Calls:** `ctx.registry.kill` or `ctx.registry.skip`. `False` → `SkillGateError(f"Run {run_id} is not running.")`
- **Output:** `{"ok": true, "id": run_id, "mode": mode, "status": "running"}`. The poller sees the final status.

### 6.11 `report_latest`
- **Input:** `skill: str`
- **Calls:** `history.latest_eval(pack)`
- **Output:** `{"run": history_row_to_run(row, pack) | None, "path": str}`

### 6.12 `report_get`
- **Input:** `run_id: str`, `skill: str | None = None`
- **Lookup (`_history_row`):** if `skill` is given → scan `history.load_history(pack, limit=0)` for `run_id`. Otherwise scan each `catalog_entries(ctx.root)` pack, then the root pack itself if `paths.is_skill_pack(ctx.root)`. A miss → `SkillGateError(f"No run named {run_id}.")`, the same text as the CLI.
- **Output:** `history_row_to_run(row, skill_path)`, returned **as-is** (no wrapper and no extra keys). The contract is that `json.dumps(result, indent=2, ensure_ascii=True) + "\n"` equals the stdout of `skillgate history show <run_id> --pack <pack> --json` for the same pack. Before writing the test, confirm the flag name in `cli/pack_history.py:96`.

### 6.13 `doctor`
- **Input:** none
- **Calls:** `load_env(ctx.root)`, then `cfg = get_llm_config(ctx.root)`, then `harness_auth_status(cfg)` and `keys.key_presence(ctx.root)`
- **Output:**
  ```json
  {
    "root": "<abs>",
    "can_check": true,
    "agents": [ { "name", "kind", "agent", "installed", "auth", "status", "install", "command" } ],
    "keys": { "OPENAI_API_KEY": { "set": true, "from_vault": false, "from_env": true, "from_home": false }, "...": {} },
    "version": "<skillgate_ai.__version__>"
  }
  ```
  `keys` is rebuilt as `{name: {k: bool(v) for k, v in meta.items()}}`, so only booleans leave the process. `harness_auth_status` already guarantees it returns no secrets.

---

## 7. `cli/cmd_mcp.py`

```python
"""skillgate mcp — local MCP server over stdio."""

from __future__ import annotations

from pathlib import Path

import typer

from skillgate_ai.config import load_env
from skillgate_ai.errors import SkillGateError
from skillgate_ai.paths import project_root


def mcp_cmd(
    root: Path | None = typer.Option(
        None, "--root", envvar="SKILLGATE_ROOT", help="Project root the tools act on"
    ),
) -> None:
    """Local MCP server (stdio) for agents. No account. Checks need `skillgate login` or a key."""
    from skillgate_ai.extras import MCP_FEATURE, MissingExtraError, require_extra

    try:
        require_extra("mcp", feature=MCP_FEATURE)
    except MissingExtraError as exc:
        typer.echo(exc.render(), err=True)
        raise typer.Exit(exc.exit_code) from None
    workspace = (root or project_root()).expanduser().resolve()
    if not workspace.is_dir():
        typer.echo(f"Root {workspace} is not a folder.", err=True)
        raise typer.Exit(2)
    load_env(workspace)
    from skillgate_ai.mcp.server import serve

    try:
        serve(workspace)
    except SkillGateError as exc:
        typer.echo(exc.render(), err=True)
        raise typer.Exit(exc.exit_code) from None
```

- Messages go to **stderr only** (`typer.echo(..., err=True)`). Do not use `base.console`, because Rich writes to stdout.
- **`cli/tree.py`:** add `from skillgate_ai.cli.cmd_mcp import mcp_cmd` and register it with `app.command("mcp")(mcp_cmd)` immediately after `app.command("ui")(ui_cmd)`.
- If `test_cli_parity.py` or `test_oss_surface.py` pins the command list, add `mcp` there.

---

## 8. `pyproject.toml` and `extras.py`

```toml
[project.optional-dependencies]
mcp = [
  "mcp>=1.9,<2",
]
all = [
  "skillgate-ai[ui,docs,mcp]",
]
```

```python
# extras.py
MCP_FEATURE: Final = "the MCP server (skillgate mcp)"
EXTRA_MODULES = {
    "ui": ("fastapi", "uvicorn"),
    "docs": (...),
    "mcp": ("mcp",),
    "all": ("fastapi", "uvicorn", "pypdf", "docx", "openpyxl", "reportlab", "mcp"),
}
```

- Regenerate `uv.lock` (`uv lock`) in the same PR. CI installs from the lockfile.
- mypy already runs with `ignore_missing_imports = true`. Add no new overrides.
- Ruff S rules: no `subprocess`, no `assert` in `src`, no `eval`.

---

## 9. Tests (exact names)

`tests/**` ignores `S`. Each test patches `skillgate_ai.gate.run_eval` with a fake that returns a minimal `SuiteReport` (copy the pattern from `tests/test_gate.py:177`), so nothing calls a real agent. Each test also resets `live` controls with `live.reset_controls()` in a fixture, and sets `SKILLGATE_ROOT` to a `tmp_path` that holds a copy of `skills/pdf`.

### `tests/test_run_registry.py`
- `test_start_returns_id_and_running_seed`
- `test_seed_record_keys_match_ui_seed` (compares the key order with a literal list taken from the old seed)
- `test_worker_finishes_done_with_mocked_run_eval`
- `test_worker_records_error_on_exception`
- `test_busy_raises_run_busy_error`
- `test_injected_busy_predicate_is_used`
- `test_injected_shared_lock_does_not_deadlock` (passes `busy` that takes the same lock)
- `test_kill_and_skip_return_false_for_unknown_run`
- `test_kill_requests_control_on_live_run`
- `test_get_returns_deep_copy`
- `test_resolve_harness_pref_wins_over_requested`
- `test_registry_imports_without_fastapi` (blocks `fastapi` in `sys.modules`, then imports `skillgate_ai.run_registry`)

### `tests/test_api_local.py` (existing, add)
- `test_post_run_delegates_to_run_registry` (checks that `state.runs` is filled and that `GET /api/runs/{id}` gives the same payload shape as before)
- `test_post_run_busy_still_409`

### `tests/test_mcp_tools.py` (no SDK required)
- `test_resolve_pack_accepts_skill_md_path`
- `test_resolve_pack_accepts_name_and_dir`
- `test_resolve_pack_rejects_outside_root`
- `test_validate_skill_ok`
- `test_validate_skill_invalid_returns_ok_false`
- `test_dataset_scaffold_new_name_creates_skill`
- `test_dataset_scaffold_refuses_existing_without_force`
- `test_dataset_get_lists_cases`
- `test_case_add_edit_remove_roundtrip`
- `test_case_edit_nothing_to_change_errors`
- `test_case_import_dry_run_does_not_write`
- `test_case_import_conflict_fail_lists_rows`
- `test_check_start_refuses_without_key_or_login` (monkeypatch `LLMConfig.has_any_key` → False; expect `MissingLLMKeyError`, and the registry stays empty)
- `test_check_start_busy_in_process`
- `test_check_start_busy_when_project_lock_held` (holds `project_run_lock(root)` in the test)
- `test_check_start_case_ids_forces_tryout`
- `test_check_start_poll_until_done_with_mocked_run_eval`
- `test_check_poll_omits_report_when_done_unless_requested`
- `test_check_poll_falls_back_to_history`
- `test_check_poll_unknown_run_errors`
- `test_check_cancel_unknown_run_errors`
- `test_report_latest_none_when_never_run`
- `test_report_get_matches_history_show_json` (runs `CliRunner().invoke(app, ["history","show",run_id,"--pack",str(pack),"--json"])` and asserts `result.stdout == json.dumps(tool_out, indent=2, ensure_ascii=True) + "\n"`)
- `test_report_get_unknown_run_errors`
- `test_doctor_reports_bools_only` (walks `keys` and asserts every leaf is a `bool`)
- `test_no_key_values_in_any_tool_output` (sets `OPENAI_API_KEY=sk-test-SENTINEL-123`, calls all 13 tools along the happy path, and asserts the sentinel is not in `json.dumps(out)`)
- `test_tools_write_nothing_to_stdout` (`capsys` across all tools → `out == ""`)
- `test_tools_import_without_fastapi_or_mcp_sdk`

### `tests/test_mcp_server.py` (`pytest.importorskip("mcp")`)
- `test_build_server_registers_thirteen_tools` (exact name set)
- `test_tool_error_maps_skillgate_error_to_is_error`
- `test_tool_schemas_have_descriptions`
- `test_stdio_roundtrip_list_tools` (`mcp.client.stdio` spawns `sys.executable -m skillgate_ai.cli mcp --root tmp`, then calls `initialize` and `list_tools`; marked `@pytest.mark.timeout(30)`)

### `tests/test_mcp_cli.py`
- `test_mcp_command_registered`
- `test_mcp_missing_extra_exits_2_on_stderr` (monkeypatch `require_extra` to raise)
- `test_mcp_root_option_and_env` (monkeypatch `serve` and assert the resolved root for `--root` and for `SKILLGATE_ROOT`)
- `test_mcp_bad_root_exits_2`

### `tests/test_optional_extras.py` (existing, add)
- `test_mcp_extra_declared` (`"mcp>="` in `extras["mcp"]` and `mcp` in `all`)
- `test_require_extra_mcp_names_extra`

---

## 10. Step order

Each step ends green on `pytest -q && ruff check && ruff format --check && mypy src`.

1. **Extras:** add the `pyproject` `[mcp]` extra and the `all` update, add `MCP_FEATURE` and `EXTRA_MODULES` to `extras.py`, run `uv lock`, add the extras tests.
2. **RunRegistry:** add `run_registry.py` with the worker moved verbatim, plus `test_run_registry.py`.
3. **api_runs delegation:** apply the minimal diff from §4 and the new `test_api_local.py` tests. Confirm that `test_eval_config.py::test_attach_stamped_config_replaces_auto_request` and `test_wire_shapes.py` pass **unchanged**.
4. **`mcp/context.py` and `mcp/tools.py`:** write the 13 functions and `test_mcp_tools.py`, test-first per tool.
5. **`mcp/server.py`:** FastMCP shims, error mapping, `test_mcp_server.py`.
6. **CLI:** `cli/cmd_mcp.py`, the `tree.py` registration, `test_mcp_cli.py`, and any update the surface/parity tests need.
7. **Docs:** a short `docs/mcp.md` covering install, the `claude mcp add skillgate -- skillgate mcp --root .` and Cursor `mcp.json` snippets, and the tool table. Link it from the README's command list.
8. **Smoke:** run `skillgate check skills/pdf` and `skillgate check skills/pdf-sabotaged --expect-fail`, then `skillgate mcp --root .` driven by an MCP inspector to do `doctor` → `dataset_get` → `check_start` → `check_poll`.

---

## 11. Acceptance criteria

- `pip install skillgate-ai` (no extras) → `skillgate mcp` exits 2 and prints the `pip install 'skillgate-ai[mcp]'` message on **stderr**, with stdout empty.
- `pip install 'skillgate-ai[mcp]'` → `skillgate mcp` speaks MCP over stdio, and `list_tools` returns exactly these 13: `validate_skill, dataset_scaffold, dataset_get, case_add, case_edit, case_remove, case_import, check_start, check_poll, check_cancel, report_latest, report_get, doctor`.
- `--root` beats `SKILLGATE_ROOT`, which beats `project_root()`.
- A `skill` argument ending in `SKILL.md` resolves to its parent pack. Paths outside the root are rejected with the same message `find_skill` uses.
- `check_start` without a key or CLI login → MCP `isError` and no thread started. A second `check_start` while one is running, or while the CLI or UI holds `.skillgate/run.lock` → `isError` with "already running".
- `report_get` output serialises byte-for-byte the same as `skillgate history show <id> --json`.
- `doctor` and every other tool emit no secret values. Key info is booleans only.
- Local UI: `POST /api/runs`, `GET /api/runs/{id}`, `/skip` and `/kill` behave exactly as on `ac355f80`. `test_api_local.py`, `test_ui_security.py` and `test_wire_shapes.py` pass, and `test_wire_shapes.py` is unmodified.
- CI passes: `ruff check`, `ruff format --check`, `mypy src`, and `pytest -q` on Python 3.11, 3.12 and 3.13.
- History rows written by MCP runs carry `source="mcp"`. They follow the same lenient-ingest path as `"ui"`, because `gate.run_check` only special-cases `"cli"` and `"compare"`.

---

## 12. Do not touch

These files must have **zero diff** in this PR:

- `src/skillgate_ai/span_facts.py`
- `src/skillgate_ai/pack.py`
- `src/skillgate_ai/report.py`
- `src/skillgate_ai/judge_spec.py`
- `src/skillgate_ai/engine/run.py`
- `src/skillgate_ai/outcome.py`
- `src/skillgate_ai/fixture_bind.py`
- `src/skillgate_ai/api_skills.py`
- `src/skillgate_ai/compare/payload.py`
- `tests/test_wire_shapes.py`

Also unchanged by policy: `api.py`, `api_payloads.py`, `server.py`, `gate.py`, `run_lock.py`, `live.py`, `cli/pack_history.py` and `cli/base.py`. There is no `cli.py` move and no `web.py`. If a step seems to need one of these changed, stop and raise it in the PR description instead.

Verify with `git diff --stat ac355f80 -- <paths above>`, which must print nothing.
