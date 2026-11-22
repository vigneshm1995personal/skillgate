# SPEC: Code-quality remediation (PR 4/4): split oversized CLI modules, remove dead code, fix flaky tests

**Repo:** skillgate (OSS) · **Package:** `skillgate-ai` · **Base:** `main` @ `2d5d2eb` ("CI: lockfile, pinned actions, Python 3.11–3.13 matrix, gated release (audit PR 3/4) (#77)") · **Branch:** `cursor/audit-code-quality`

## 1. Audit context

- PRs 1–3 have merged: #75 (security and retries), #76 (typing, with `warn_unused_ignores = true`) and #77 (deps and CI). This PR covers code quality only.
- `skillgate ui` (`cli/cmd_ui.py:32`) uses the FastAPI server `skillgate_ai.server.serve_ui`. Nothing in `src/` imports `skillgate_ai.local_ui`, and `local_ui/server.py` is the only module that imports `local_ui/api.py`. Only these tests still reach it: `tests/test_local_ui.py` (through `start_background`), `tests/test_oss_surface.py` and `tests/test_optional_extras.py`.
- `observability.py` contains 10 no-op functions. They are called from `gate.py`, `engine/run.py`, `engine/task.py` and `sandbox.py`.
- Two functions write a LaunchAgent plist with nearly the same code: `helper.install_launchd_plist` (`helper.py:364`) and `sync.install_launchd_plist` (`sync.py:250`).
- These four modules are oversized: `cli_compare.py` (258 lines), `cli/cmd_judge.py` (295), `cli/cmd_gate.py` (262) and `cli/pack_history.py` (236).
- Two tests are flaky: `tests/test_compare_cli.py::test_compare_models_cancel_stops_next_arm` and `tests/test_harness_auth.py::test_run_inherited_keyboard_interrupt_kills_group`.
- `tests/test_packaging_ui.py::test_web_static_matches_fresh_pnpm_build` fails with an `AssertionError` or `CalledProcessError` when `pnpm` or the `web/` toolchain is missing. It should skip cleanly instead.

### Contracts this PR must keep (enforced by `tests/test_public_imports.py`; do not edit these constants)

- `CLI_SURFACE_SHA256 = "130695a0…83a1"`, `TOP_COMMANDS` and `SUB_COMMANDS` must not change. That means every command name, option, default, help string, docstring and the registration order stay the same.
- `REGISTRY["skillgate_ai.cli"]`: every name must still be importable from `skillgate_ai.cli`, and its `__module__` must be `skillgate_ai.cli` or start with `skillgate_ai.cli.`.
- `PASS_THROUGH["skillgate_ai.cli"] = ("register_compare_commands", "register_pack_commands")` must still resolve.
- `test_no_submodule_shadows_a_symbol`: a new `cli/` submodule must not share a name with any `REGISTRY["skillgate_ai.cli"]` symbol (for example `helper`, `sync`, `deploy`, `version`, `login`, `doctor`, `ingest`, `connect`, `app` or `console`). All the names in §3 have been checked and are safe.
- `test_shims_hold_no_code`: `cli/__init__.py` must stay import-only.

## 2. Scope

| # | Item | Files | Kind |
|---|---|---|---|
| A1 | Split `cli_compare.py` | `cli_compare.py` (becomes a shim), new `cli/cmd_compare.py`, `cli/compare_run.py`, `cli/compare_jobs.py`, `cli/tree.py`, `cli/__init__.py` | Move only |
| A2 | Split `cli/cmd_judge.py` | `cli/cmd_judge.py`, new `cli/cmd_case.py`, `cli/cmd_judge_provider.py`, `cli/tree.py`, `cli/__init__.py` | Move only |
| A3 | Split `cli/cmd_gate.py` | `cli/cmd_gate.py`, new `cli/gate_output.py`, `cli/__init__.py` | Move only |
| A4 | Split `cli/pack_history.py` | `cli/pack_history.py`, new `cli/history_format.py` | Move only |
| B1 | Delete the dead stdlib UI | Delete `src/skillgate_ai/local_ui/**` and `tests/test_local_ui.py`. Edit `pyproject.toml`, `MANIFEST.in`, `tests/test_oss_surface.py`, `tests/test_optional_extras.py`, `tests/test_api_local.py` (+1 test), `AGENTS.md` | Delete |
| B2 | Delete the no-op observability module | Delete `observability.py`. Edit `gate.py`, `engine/run.py`, `engine/task.py`, `sandbox.py`, `tests/test_engine.py`, `scripts/extract-from-skillgate-ai.sh` | Delete |
| B3 | Consolidate the launchd writers | New `launchd.py`. Edit `helper.py`, `sync.py`. New `tests/test_launchd.py` | Refactor |
| C1 | Make the compare cancel test deterministic | `tests/test_compare_cli.py` | Test |
| C2 | Make the KeyboardInterrupt process-group test deterministic | `tests/test_harness_auth.py` | Test |
| D | Skip the pnpm build test cleanly | `tests/test_packaging_ui.py` | Test |
| E | Changelog | `CHANGELOG.md` (one Unreleased bullet) | Docs |

## 3. (A) CLI module split map

Rules for every move:
- Copy each function **verbatim**: same name, signature, decorators, docstring, `typer.Argument`/`typer.Option` arguments, lazy imports and body.
- Change only the module-level imports each file needs.
- Line numbers below refer to `main` @ `2d5d2eb`.
- Target: every file touched in §3 is **≤ 200 lines**.

### A1. `cli_compare.py` (258 lines) → 3 modules + 1 shim

The commands are closures inside `register_compare_commands`. Keep them as closures: split the function into one sub-registrar per command. Do **not** turn them into module-level functions, because `key_env_help` reaches the `--key-env` help text through the closure.

| New module | Content (source lines) | Est. lines |
|---|---|---|
| `src/skillgate_ai/cli/cmd_compare.py` | `register_compare_commands(app: typer.Typer, *, key_env_help: str) -> None` keeps its signature. Body: build `compare_app` exactly as at lines 19–23 (`add_completion=False`, `no_args_is_help=True`, `help="Side-by-side compare on one Dataset (models or versions)."`). Then call `app.add_typer(compare_app, name="compare")`. Then, **in this order**: `register_compare_models(compare_app, key_env_help=key_env_help)`, `register_compare_versions(compare_app, key_env_help=key_env_help)`, `register_compare_show(compare_app)`, `register_compare_cancel(compare_app)`, `register_compare_list(compare_app)`. Module docstring: `"""CLI commands for compare runs (models + versions)."""` | ~35 |
| `src/skillgate_ai/cli/compare_run.py` | `register_compare_models(compare_app: typer.Typer, *, key_env_help: str) -> None`: wraps `compare_models_cmd` (lines 26–98). `register_compare_versions(compare_app: typer.Typer, *, key_env_help: str) -> None`: wraps `compare_versions_cmd` (lines 100–164). Each starts with `_KEY_ENV_HELP = key_env_help` and the lazy import `from skillgate_ai.cli import _bind_key_env, _emit_json, _resolve_pack_arg, console`. Top-level imports: `sys`, `uuid`, `Path`, `typer`, `project_root`. | ~170 |
| `src/skillgate_ai/cli/compare_jobs.py` | `register_compare_show(compare_app)`: `compare_show_cmd`, lines 166–195; lazy import `_boot, _emit_json, _resolve_pack_arg, console`. `register_compare_cancel(compare_app)`: `compare_cancel_cmd`, lines 197–213; lazy import `_boot, console`. `register_compare_list(compare_app)`: `compare_list_cmd`, lines 215–258; lazy import `_emit_json, _resolve_pack_arg, console`. Top-level imports: `Path`, `typer`, `project_root`. | ~110 |
| `src/skillgate_ai/cli_compare.py` (shim) | Docstring plus `from skillgate_ai.cli.cmd_compare import register_compare_commands as register_compare_commands`. No code. Keep it so `import skillgate_ai.cli_compare` still works. | 5 |

Wiring:
- In `cli/tree.py:39`, change the import to `from skillgate_ai.cli.cmd_compare import register_compare_commands`. Line 73 stays the same.
- In `cli/__init__.py:63`, change the import to `from skillgate_ai.cli.cmd_compare import register_compare_commands as register_compare_commands`.

**Import cycle check:** nothing under `src/` may import `skillgate_ai.cli_compare` after this change. If it did, a first import of the shim would hit a partially initialized module through `cli/__init__ → tree`.

Each sub-registrar keeps the lazy `from skillgate_ai.cli import …` inside its body. It runs during `register_all()`, which is the last statement of `cli/__init__`, and by then every re-export already exists. Pass only the names each closure uses, or ruff F401 will flag the rest.

### A2. `cli/cmd_judge.py` (295 lines) → 3 modules

| Module | Functions (source lines) | Imports | Est. lines |
|---|---|---|---|
| `cli/cmd_judge.py` (kept) | `checks_show_cmd` (14–29), `judge_show` (32–116), `judge_reset` (119–131), `judge_add_question_cmd` (134–160) | `sys`, `Path`, `typer`, `base`, `SkillGateError` | ~165 |
| `cli/cmd_case.py` (new) | `case_add_cmd` (163–213) | `Path`, `typer`, `base`, `SkillGateError` | ~60 |
| `cli/cmd_judge_provider.py` (new) | `judge_provider_show` (216–228), `judge_provider_set` (231–264), `_run_judge_test` (267–279), `judge_test` (282–287), `judge_provider_test` (290–295) | `typer`, `base`, `SkillGateError` | ~95 |

- **Every** module-level `typer.Option(... help=base._KEY_ENV_HELP)` and `help=base._VERBOSE_HELP` default stays exactly as written. They are evaluated at import time.
- `cli/tree.py`:
  - Import `case_add_cmd` from `skillgate_ai.cli.cmd_case`.
  - Import `judge_provider_show`, `judge_provider_set`, `judge_test` and `judge_provider_test` from `skillgate_ai.cli.cmd_judge_provider`.
  - The `register_all()` body (lines 42–73) stays **byte-identical**.
- `cli/__init__.py`, lines 42–51:
  - Re-export `case_add_cmd` from `cmd_case`.
  - Re-export `_run_judge_test`, `judge_provider_set`, `judge_provider_show`, `judge_provider_test` and `judge_test` from `cmd_judge_provider`.
  - The rest still come from `cmd_judge`.

### A3. `cli/cmd_gate.py` (262 lines) → 2 modules

| Module | Functions (source lines) | Imports | Est. lines |
|---|---|---|---|
| `cli/gate_output.py` (new) | `_present_check` (20–30), `_verbose_scoring_lines` (33–40), `_exit_with_error` (43–54), `_finish_gate` (78–119) | `os`, `sys`, `Path`, `NoReturn`, `typer`, `base`, `scrub_browser_payload`, `SkillGateError`, `format_cli`, `format_github`, `report_to_dict` | ~115 |
| `cli/cmd_gate.py` (kept) | `_tryout_checks` (57–75, including `raise AssertionError("unreachable")`), `_run_gate` (122–168, including `# noqa: BLE001 — TimeoutExpired must not dump the prompt`), `check_pack` (171–220), `run_suite` (223–262) | `sys`, `Path`, `typer`, `base`, `SkillGateError`, `timeout_harness_error`, `run_check`, `project_root`, `resolve_user_path`, and `from skillgate_ai.cli.gate_output import _exit_with_error, _finish_gate` | ~160 |

- `run_check` stays a top-level import in `cmd_gate.py`, so its patch target is unchanged.
- `cli/__init__.py`, lines 37 and 39: re-export `_present_check` and `_verbose_scoring_lines` from `skillgate_ai.cli.gate_output`.
- `_run_gate`, `check_pack` and `run_suite` are still re-exported from `cmd_gate`.
- `cli/tree.py` is unchanged.

### A4. `cli/pack_history.py` (236 lines) → 2 modules

| Module | Functions (source lines) | Imports | Est. lines |
|---|---|---|---|
| `cli/history_format.py` (new) | `_print_history_rows` (13–59), `_print_skill_versions` (62–74), `_print_history_run` (153–211) | `Path`, `Any` | ~140 |
| `cli/pack_history.py` (kept) | `register_history_app` (77–84), `register_history_callback` (87–114), `_find_history_row` (117–150), `register_history_show` (214–236) | `Path`, `typer`, `SkillGateError`, and `from skillgate_ai.cli.history_format import _print_history_rows, _print_history_run, _print_skill_versions` | ~100 |

- Keep every lazy `from skillgate_ai import cli as _cli` and `from skillgate_ai.cli import _emit_json` exactly where it is now.
- `cli/pack_commands.py` is unchanged.

### A-verification (beyond tests)

- Before and after, from a clean venv on `main` and then on this branch:
  ```bash
  for c in "" compare "compare models" "compare versions" "compare show" "compare cancel" \
    "compare list" judge "judge show" "judge reset" "judge add-question" "judge test" \
    "judge provider" "judge provider show" "judge provider set" "judge provider test" \
    "case add" "checks show" check run history "history show"; do
    echo "== $c"; COLUMNS=100 skillgate $c --help; done > /tmp/help-$(git rev-parse --short HEAD).txt
  ```
  `diff /tmp/help-2d5d2eb.txt /tmp/help-<new>.txt` must print nothing.
- `python -I -c "import skillgate_ai.cli_compare as m; print(m.register_compare_commands.__module__)"` prints `skillgate_ai.cli.cmd_compare`, run in a fresh interpreter so the shim is the first import.

## 4. (B) Dead code

### B1. Stdlib loopback UI: delete

**Delete:**
- `src/skillgate_ai/local_ui/__init__.py`, `api.py`, `server.py`
- `src/skillgate_ai/local_ui/static/app.css`, `app.js`, `favicon.svg`, `index.html`
- the untracked `src/skillgate_ai/local_ui/__pycache__/`
- `tests/test_local_ui.py` (21 tests, all of which drive `start_background` or read `local_ui/static/*`)

**Packaging and lint edits:** these are the only `pyproject.toml` edits allowed in this PR.
- `pyproject.toml:95`: delete `"local_ui/static/*",` from `[tool.setuptools.package-data]`.
- `pyproject.toml:127`: delete `"tests/test_local_ui.py" = ["E501"]`. Keep the comment on line 125, because `test_wording_facts.py` still uses it.
- `MANIFEST.in:5`: delete `recursive-include src/skillgate_ai/local_ui/static *`.

**Test edits:**
- `tests/test_optional_extras.py::test_core_modules_import_without_extras`: remove `"skillgate_ai.local_ui.api",` and `"skillgate_ai.local_ui.server",` from `mods` (lines 129–130). The other 11 modules stay.
- `tests/test_oss_surface.py`:
  - Rename `test_local_ui_may_exist_without_hosted_names` to `test_local_ui_removed_and_no_hosted_names`.
  - Change line 105 to `assert not (ROOT / "local_ui").exists()`.
  - Delete line 108 (`local_ui/wizard.py`); it is implied by line 105.
  - Keep every other assertion in that test unchanged: `web.py`, `wizard.py`, `api.py`, `server.py`, `mode.py`, `web/package.json`, and the `cli/` import scan.
- `tests/test_oss_surface.py::test_static_index_is_packaged`: delete it, because the asset is gone. The FastAPI bundle's packaging is covered by `test_packaging_ui.py::test_web_static_is_tracked_and_not_gitignored` and the CI wheel job.
- `tests/test_oss_surface.py::test_helper_and_sync_stay_cli_only`: keep unchanged. It still guards against `local_ui` imports.

**Coverage of the deleted `test_local_ui.py` tests**

| Deleted test | Fate |
|---|---|
| `test_app_js_is_valid_javascript`, `test_ui_copy_has_no_internal_jargon`, `test_ui_wizard_motion_is_wired_not_just_class_names`, `test_ui_skill_page_run_motion_is_wired`, `test_ui_wizard_is_setup_only_then_skill_page`, `test_ui_only_start_check_posts_check`, `test_ui_static_index`, `test_app_js_check_detail_helpers_run_in_node` | These test only the deleted vanilla assets. The React UI is covered by `pnpm test` (`web/`) and `test_api_local::test_ui_static_attaches_without_fastapi_error`. |
| `test_ui_meta_no_account` | `test_api_local::test_status_local_hides_paid_slots`, `::test_status_hides_gateway_fields` |
| `test_ui_pack_display_path_is_relative` | `display_path` exists only in `local_ui/api.py`. Nothing to port. |
| `test_ui_env_writes_only_supplied_keys` | `test_api_local::test_settings_keys_write_vault` |
| `test_ui_wizard_first_run_opens_skill_page_without_check` | `test_api_local::test_generate_does_not_start_a_run` |
| `test_ui_rejects_dotdot_and_symlink_escape` | `..`: `test_ui_security::test_pack_path_outside_project_is_rejected` and `test_api_local::test_pack_file_outside_skill_is_400`. Symlink: see the **probe** below. |
| `test_ui_env_rejects_newlines` | **Port it:** add `test_settings_keys_reject_line_breaks` (below). |
| `test_ui_name_mismatch_400` | Shared validation: `test_scaffold.py:30`, `test_ingest.py:24` (`"must match"`) |
| `test_ui_check_without_key_is_409`, `test_ui_live_without_key_is_409`, `test_ui_new_pack_no_key_is_409`, `test_ui_apply_advice_does_not_run_without_key` | `test_api_local::test_run_without_key_is_conflict` |
| `test_ui_live_with_key_does_not_use_builtin`, `test_ui_demo_flag_still_runs_live` | The `live`/`demo` body flags exist only in `local_ui/api.py::_start_check`. Nothing to port. |

**New test**, added to `tests/test_api_local.py` right after `test_settings_keys_write_vault`:
```python
def test_settings_keys_reject_line_breaks(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    res = client.put(
        "/api/settings/keys/OPENAI_API_KEY", json={"value": "sk-line1\nMALICIOUS=1"}
    )
    assert res.status_code == 400, res.text
    assert "line break" in res.text.lower()
    vault = tmp_path / ".skillgate" / "keys"
    assert not vault.exists() or "MALICIOUS" not in vault.read_text(encoding="utf-8")
```
This exercises `api.py:186–187`.

**Symlink probe**, done once by hand and not committed:
1. With `TestClient(create_app(root=ws))`, create `ws/skills/escape` as a symlink to a pack outside `ws`.
2. `GET /api/skills/escape`.
3. If the response is 400 or 404, add `test_symlinked_pack_outside_workspace_is_rejected` to `tests/test_ui_security.py`, asserting `status_code in {400, 404}`.
4. If the response is **200**, stop. Report it as a security finding in the PR description and do not fix it in this PR.

**Orphans:** do not delete anything else. Some names imported by `local_ui/api.py` may now have no other users, for example in `scaffold`, `pack` or `advice`. Run `grep -rn` on each name imported at `local_ui/api.py:13–43` and list any whose only importer was `local_ui` in the PR description as follow-ups.

**`AGENTS.md:8`:** replace it with:
`- Optional local UI: \`skillgate ui\` (FastAPI \`skillgate_ai.server\`, needs \`skillgate-ai[ui]\`; React app from \`web/\` shipped as \`src/skillgate_ai/web_static/\`)`

### B2. `observability.py`: delete, and remove every call site

Delete `src/skillgate_ai/observability.py`. Remove each call site below. None of these calls has a side effect, so removing them changes no behavior.

| File | Lines | Edit |
|---|---|---|
| `gate.py` | 33–38 | Delete the `from skillgate_ai.observability import (capture_run_failure, eval_transaction, log_eval_finished, set_eval_passed)` block. |
| `gate.py` | 234 | Delete `skill_label = …`. It is only used by `eval_transaction`. |
| `gate.py` | 260–268 | Delete `mode = "live"` and the `with eval_transaction(...):` header. Dedent the body (lines 269–309, from `started = True` through `persist_eval(...)`) by one level. It stays inside the outer `try:`. |
| `gate.py` | 291–297 | Delete `set_eval_passed(report.passed)` and the `log_eval_finished(...)` call. |
| `gate.py` | 315, 319 | Delete both `capture_run_failure(...)` lines. The surrounding branches stay. |
| `engine/run.py` | 28 | Delete the import. |
| `engine/run.py` | 315, 332 | Delete `set_eval_passed(passed)` and `report_eval_outcome(report, run_id=run_id)`. |
| `engine/run.py` | 260, 291, 308, 429 | `run_id` is now unused in the private helpers. Remove the `run_id: str` parameter from `_eval_finish` (260) and `_complete_suite_report` (308), and the `run_id=run_id` kwargs at 291 and 429. **Keep** `run_eval(..., run_id: str = "")` (line 346) unchanged; it is public and `gate.py` passes it. |
| `engine/task.py` | 35 | Delete the import. |
| `engine/task.py` | 318–319 | `with span("eval.score", task.id):` → just `scores = score_task(task, artifacts, skills=skills)`. |
| `engine/task.py` | 350–359 | Delete the `with span("eval.harness", harness.name):` header and dedent the `try/except` block one level. |
| `engine/task.py` | 435–507 | Delete `breadcrumb_task("start", …)` (435), `ended = False` (436), the `with span("eval.task", …):` header (438), all three `ended = True` lines (442, 457, 487), the `breadcrumb_task("end", …)` call (481–486) and the `if not ended: breadcrumb_task(...)` lines (506–507). Dedent the former `with` body one level. The `try:`/`finally:` that resets `sandbox.output_sink` and calls `control.end_task()` **stays**. |
| `sandbox.py` | 18, 104, 128, 177, 197 | Delete the import and the four `breadcrumb_*` lines. No other change to `sandbox.py`. |
| `scripts/extract-from-skillgate-ai.sh` | 46 | Delete `src/skillgate_ai/observability.py` from `ALLOW`, so a re-extract cannot restore the private Sentry module. |

Test edits in `tests/test_engine.py`:
- Delete the `crumbs` fixture (lines 47–55). Its only user is the test below.
- Replace `test_run_task_breadcrumb_end_once` (lines 970–1000) with `test_run_task_harness_error_propagates`. Use the same setup and keep the non-breadcrumb half:
  - the first `engine._run_task(task=_task("a"), …)` returns a report with `report.task_id == "a"`;
  - the second call with `FakeHarness(raises=RuntimeError("boom"))` still satisfies `pytest.raises(RuntimeError, match="boom")`.

### B3. LaunchAgent writers: one shared writer

New module `src/skillgate_ai/launchd.py`:

```python
"""Per-user macOS LaunchAgent plists for `skillgate helper` and `skillgate sync`."""

from __future__ import annotations

import os
import plistlib
import shutil
from pathlib import Path


def launch_agents_dir() -> Path:
    return Path.home() / "Library" / "LaunchAgents"


def skillgate_binary() -> str:
    return shutil.which("skillgate") or "skillgate"


def write_launch_agent(
    launch_dir: Path,
    *,
    label: str,
    program_arguments: list[str],
    keep_alive: bool | None = None,
) -> Path:
    """Write ``<launch_dir>/<label>.plist`` (0644) with RunAtLoad; dir is 0755."""
    plist: dict[str, object] = {
        "Label": label,
        "RunAtLoad": True,
        "ProgramArguments": program_arguments,
    }
    if keep_alive is not None:
        plist["KeepAlive"] = keep_alive
    launch_dir.mkdir(parents=True, exist_ok=True)
    try:  # noqa: SIM105
        os.chmod(launch_dir, 0o755)
    except OSError:
        pass
    dest = launch_dir / f"{label}.plist"
    with open(dest, "wb") as handle:
        plistlib.dump(plist, handle)
    os.chmod(dest, 0o644)
    return dest
```

Constraints that keep behavior and test hooks the same:
- **The macOS check stays in each caller** as `if sys.platform != "darwin": raise SkillGateError("LaunchAgent autostart is macOS-only.")`.
  - In `sync`, it must still run **before** `normalize_targets` and the repo-URL check, so errors keep their current order.
  - The tests patch `helper_mod.sys.platform` and `sync_mod.sys.platform`, so `import sys` must stay in both modules.
- `sync` must call `launch_agents_dir()` through **its own module global**, because `test_sync.py:200` patches `sync_mod.launch_agents_dir`. Import it into `sync` and delete the local `def launch_agents_dir` (`sync.py:246–247`).
- Plist bytes stay the same. `plistlib.dump` sorts keys by default. Helper keeps `KeepAlive: False`, and sync still has no `KeepAlive` key.

`helper.install_launchd_plist()` keeps its signature and docstring. Body:
```python
    if sys.platform != "darwin":
        raise SkillGateError("LaunchAgent autostart is macOS-only.")
    return write_launch_agent(
        launch_agents_dir(),
        label=LAUNCH_AGENT_LABEL,
        program_arguments=[skillgate_binary(), "helper"],
        keep_alive=False,
    )
```
Imports: add `from skillgate_ai.launchd import launch_agents_dir, skillgate_binary, write_launch_agent`. Delete `import plistlib` and `import shutil`; each was used only here. Keep `os`, which line 176 uses, and `sys`.

`sync.install_launchd_plist(repo_url, *, targets=None, interval=0)` keeps its signature and docstring.
- Lines 257–267 stay as they are, except `binary = skillgate_binary()`.
- Replace lines 268–283 with `return write_launch_agent(launch_agents_dir(), label=LAUNCH_AGENT_LABEL, program_arguments=program)`.
- Imports: add the same `launchd` import. Delete `import plistlib`. Keep `os` (`os.walk`), `shutil` (`rmtree`) and `sys`.

`LAUNCH_AGENT_LABEL` stays defined in each module (`com.skillgate-ai.helper` and `com.skillgate-ai.sync`). The CLI callers in `cli/cmd_deploy.py:78–83` and `128–136` are unchanged.

New `tests/test_launchd.py`. All four tests use `tmp_path`, `monkeypatch.setattr(Path, "home", lambda: tmp_path)` and `monkeypatch.setattr("skillgate_ai.launchd.shutil.which", lambda _: "/opt/bin/skillgate")`.
- `test_write_launch_agent_omits_keep_alive_by_default`: the loaded plist has no `"KeepAlive"` key, the file mode is `0o644` and the dir mode is `0o755`.
- `test_write_launch_agent_writes_keep_alive_false`: `plistlib.loads(...)["KeepAlive"] is False`.
- `test_helper_plist_bytes_unchanged`: set `sys.platform` to `"darwin"`. `install_launchd_plist().read_bytes()` must equal `plistlib.dumps({"Label": "com.skillgate-ai.helper", "RunAtLoad": True, "KeepAlive": False, "ProgramArguments": ["/opt/bin/skillgate", "helper"]})`.
- `test_sync_plist_bytes_unchanged`: call `sync.install_launchd_plist("https://github.com/acme/skills.git", targets=["cursor"], interval=60)`. The bytes must equal `plistlib.dumps({"Label": "com.skillgate-ai.sync", "RunAtLoad": True, "ProgramArguments": ["/opt/bin/skillgate", "sync", "--repo", "https://github.com/acme/skills.git", "--targets", "cursor", "--interval", "60"]})`.

The existing tests stay unchanged and must still pass: `test_helper.py::test_helper_install_launchd_plist`, `::test_helper_install_launchd_plist_non_mac` and `test_sync.py::test_sync_install_launchd_plist`.

## 5. (C) Flaky test fixes

Rules: no `sleep`, retry, rerun or skip, and no timing thresholds. Keep every original assertion, and strengthen where noted.

### C1. `tests/test_compare_cli.py::test_compare_models_cancel_stops_next_arm` (lines 262–322)

**Root cause:**
- A `threading.Timer(0.05, cancel)` races against `time.sleep(0.08)` inside arm A.
- On a loaded runner the timer can fire after arm A returns. The loop check `job_control.cancelled()` (`compare/models.py:231`) is then still False, so arm B runs and the result has `status == "done"` with two arms.
- The timer can also fire after `clear_compare_cancel` and leak a cancel flag.

**Fix:** cancel synchronously while arm A is in flight. This is the same call the CLI and UI make (`request_cancel_compare`). `create_compare_control` registered the control before the arm loop started, so the call returns `"requested"`, sets the event and writes the flag.
- Set `compare_id = "abcd12345678"`.
- Inside `fake_run_check`, on `calls["n"] == 1`, run `cancel_outcomes.append(request_cancel_compare(tmp_path, compare_id))` in place of the `Timer` and the `sleep`.
- The `SuiteReport`/`CheckResult` construction stays verbatim.
- Drop the `run()` wrapper and `compare_id_holder`, and call `run_models_compare(pack, arms=[parse_arm_spec("A:codex", arm_id="a", index=0), parse_arm_spec("B:cursor-agent", arm_id="b", index=1)], root=tmp_path, compare_id=compare_id)` directly.
- Assertions:
  - kept: `result.payload["status"] == "cancelled"`, `len(result.payload["arms"]) == 1`, `load_compares(pack)[-1]["status"] == "cancelled"`
  - added: `cancel_outcomes == ["requested"]`, `calls["n"] == 1`
- Remove `import threading` and `import time` (lines 5–6); this test was their only user.

**Mutation check** (by hand, not committed): with the `if job_control.cancelled():` check at `compare/models.py:231–233` commented out, the test must fail on every run.

### C2. `tests/test_harness_auth.py::test_run_inherited_keyboard_interrupt_kills_group` (lines 892–952)

**Root causes:**
1. The parent writes `pids.txt` as soon as it spawns the grandchild, before the grandchild has run `signal.signal(SIGTERM, on_term)`. A SIGTERM that arrives first uses the default action, so the grandchild dies without writing `dead.txt` and `assert dead_marker.is_file()` fails.
2. `pids.txt` can be read half-written, because `is_file()` is True before `write` finishes. That gives `ValueError` in `int(...)`.
3. Both waits poll with `time.sleep(0.05)` under 5 s deadlines.

**Fix:** use a blocking stdout handshake plus EOF.
- The grandchild prints `ready` **after** it installs its handler.
- The parent prints its pids.
- The test raises `KeyboardInterrupt` only after reading both lines.
- After the interrupt, reading stdout to EOF blocks until both processes have exited. EOF means every holder of the write end is gone, so the grandchild's handler has already finished writing `dead.txt`.
- `_run_inherited` and `harness/login.py` are **not** changed.

Replacement body. The signature and the `from skillgate_ai.harness import login as harness_login` line stay. Add `from typing import Any` to the module imports.
```python
    grandchild = tmp_path / "grandchild.py"
    grandchild.write_text(
        "import signal, sys\n"
        "def on_term(signum, frame):\n"
        "    open(sys.argv[1], 'w').write('dead')\n"
        "    sys.exit(0)\n"
        "signal.signal(signal.SIGTERM, on_term)\n"
        "print('ready', flush=True)\n"
        "while True:\n"
        "    signal.pause()\n",
        encoding="utf-8",
    )
    parent = tmp_path / "parent.py"
    parent.write_text(
        "import os, signal, subprocess, sys\n"
        "child = subprocess.Popen([sys.executable, sys.argv[1], sys.argv[2]])\n"
        "print(f'{os.getpid()} {child.pid}', flush=True)\n"
        "while True:\n"
        "    signal.pause()\n",
        encoding="utf-8",
    )
    dead_marker = tmp_path / "dead.txt"
    real_popen = harness_login.subprocess.Popen
    seen: dict[str, Any] = {}

    class KeyboardInterruptPopen:
        def __init__(self, argv, start_new_session=False):
            self._proc = real_popen(
                argv, start_new_session=start_new_session, stdout=subprocess.PIPE, text=True
            )
            self.start_new_session = start_new_session
            self._interrupted = False
            seen["proc"] = self._proc

        @property
        def pid(self):
            return self._proc.pid

        def wait(self, timeout=None):
            if not self._interrupted:
                self._interrupted = True
                # Blocks until the parent is up and the grandchild's SIGTERM handler is installed.
                seen["lines"] = [self._proc.stdout.readline().strip() for _ in range(2)]
                raise KeyboardInterrupt()
            return self._proc.wait(timeout=timeout)

        def poll(self):
            return self._proc.poll()

    monkeypatch.setattr("skillgate_ai.harness.login.subprocess.Popen", KeyboardInterruptPopen)
    with pytest.raises(KeyboardInterrupt):
        harness_login._run_inherited(
            [sys.executable, str(parent), str(grandchild), str(dead_marker)]
        )
    lines = seen["lines"]
    assert "ready" in lines, lines
    (pid_line,) = [line for line in lines if line != "ready"]
    parent_pid, child_pid = (int(part) for part in pid_line.split())
    assert _pid_gone(parent_pid)
    proc = seen["proc"]
    proc.stdout.read()  # EOF only after parent and grandchild have both exited
    proc.stdout.close()
    assert dead_marker.is_file()
    assert _pid_gone(child_pid)
```

- **Assertions kept:** `pytest.raises(KeyboardInterrupt)`, `_pid_gone(parent_pid)`, `dead_marker.is_file()`, `_pid_gone(child_pid)`.
- **Assertion added:** `"ready" in lines`.
- `_pid_gone` (lines 70–76) is the shared helper and is unchanged. Here it only waits for the kernel or init to reap processes that have already exited.
- Leave `test_run_inherited_kills_process_group_on_timeout` (856–889) alone. It has the same handler-install race but is out of scope (see §10).

**Mutation check** (by hand, not committed): with `_terminate_process_group(proc)` deleted from the `except KeyboardInterrupt:` branch (`harness/login.py:72`), the test must fail at `assert _pid_gone(parent_pid)`.

## 6. (D) pnpm/tsc skip for `test_web_static_matches_fresh_pnpm_build`

Edit `tests/test_packaging_ui.py`:
- Add `import os` and `import pytest`.
- Add this helper after `_git_indexed_web_static`:
  ```python
  def _web_toolchain_missing() -> str | None:
      """Why `pnpm exec tsc` / `vite build` cannot run here, or None when they can."""
      if shutil.which("pnpm") is None:
          return "pnpm is not on PATH"
      bin_dir = WEB_DIR / "node_modules" / ".bin"
      missing = [tool for tool in ("tsc", "vite") if not (bin_dir / tool).exists()]
      if missing:
          return f"web/node_modules/.bin has no {' or '.join(missing)}"
      return None
  ```
- In the test, insert this between the `git_tree` assertion (lines 107–113, unchanged) and `working = PACKAGED_UI / "index.html"`. It must come **before** the working tree is poisoned:
  ```python
      missing = _web_toolchain_missing()
      if missing is not None:
          if os.environ.get("CI"):
              pytest.fail(f"{missing}; CI must run the web_static freshness check.")
          pytest.skip(
              f"{missing}; run `cd web && pnpm install --frozen-lockfile` to check web_static freshness."
          )
      pnpm = shutil.which("pnpm")
      assert pnpm is not None
  ```
- Delete lines 119–120 (the old `pnpm = …` and `assert pnpm, …` inside `try:`). The rest of the `try`/`finally` stays verbatim.

**Exact skip messages:**
- `pnpm is not on PATH; run \`cd web && pnpm install --frozen-lockfile\` to check web_static freshness.`
- `web/node_modules/.bin has no tsc or vite; run \`cd web && pnpm install --frozen-lockfile\` to check web_static freshness.` The middle part names only the missing tools: `tsc`, `vite` or `tsc or vite`.

CI is unaffected. `gate.yml` installs pnpm and runs `pnpm install --frozen-lockfile` before `pytest` (lines 70–82), and `release.yml:46` reuses `gate.yml`. The `CI` guard makes sure CI can never skip this test silently.

## 7. Step order (one commit per step; each commit passes `pytest -q -m "not integration"`)

1. **C1**: cancel test.
2. **C2**: KeyboardInterrupt test.
3. **D**: pnpm skip.
4. **B3**: `launchd.py`, `helper.py`, `sync.py`, `tests/test_launchd.py`.
5. **B2**: observability removal, including the `test_engine.py` swap and the script `ALLOW` line.
6. **B1**:
   - First add `test_settings_keys_reject_line_breaks` and do the symlink probe.
   - Then delete `local_ui/**` and `tests/test_local_ui.py`.
   - Then make the `pyproject.toml`, `MANIFEST.in`, `test_oss_surface.py`, `test_optional_extras.py` and `AGENTS.md` edits.
7. **A3**: `cmd_gate` → `gate_output`.
8. **A2**: `cmd_judge` → `cmd_case` and `cmd_judge_provider`.
9. **A4**: `pack_history` → `history_format`.
10. **A1**: `cli_compare` → `cmd_compare`, `compare_run`, `compare_jobs`, plus the shim.
11. **E**: add one `CHANGELOG.md` bullet under `## Unreleased`:
    `- Internal cleanup: removed the unused stdlib \`skillgate_ai.local_ui\` server and assets (\`skillgate ui\` is the FastAPI app) and the no-op observability stubs; one shared LaunchAgent writer for \`helper\`/\`sync\`; split large CLI modules. No CLI changes.`

## 8. Verification

Run from the repo root in a venv set up with `pip install -e ".[dev]"`:

```bash
ruff check
ruff format --check
mypy src
pytest -q -m "not integration"
pytest -q -m integration tests/integration
pytest -q tests/test_public_imports.py          # CLI digest, order, REGISTRY, shims
skillgate check skills/pdf
skillgate check skills/pdf-sabotaged --expect-fail

# 20x flake loops (each must print 20 passes, zero failures)
for i in $(seq 1 20); do
  pytest -q -p no:cacheprovider \
    "tests/test_compare_cli.py::test_compare_models_cancel_stops_next_arm" || { echo "FAIL run $i"; break; }
done
for i in $(seq 1 20); do
  pytest -q -p no:cacheprovider \
    "tests/test_harness_auth.py::test_run_inherited_keyboard_interrupt_kills_group" || { echo "FAIL run $i"; break; }
done
# Repeat both loops while `pytest -q -m "not integration"` runs in a second shell (CPU contention).

# pnpm skip: skips without pnpm, fails under CI=1, leaves web_static untouched
env -u CI PATH="$(dirname "$(command -v python)"):/usr/bin:/bin" \
  python -m pytest -q -rs tests/test_packaging_ui.py::test_web_static_matches_fresh_pnpm_build   # SKIPPED + message
CI=1 PATH="$(dirname "$(command -v python)"):/usr/bin:/bin" \
  python -m pytest -q tests/test_packaging_ui.py::test_web_static_matches_fresh_pnpm_build        # FAILED
git status --porcelain src/skillgate_ai/web_static                                                # empty
pytest -q tests/test_packaging_ui.py                                                              # passes with toolchain

# Dead-code greps
grep -rn "observability" src tests scripts                 # no hits
grep -rn "local_ui" src pyproject.toml MANIFEST.in AGENTS.md   # no hits
grep -rn "local_ui" tests                                  # only test_oss_surface.py (removed-check + helper/sync leak check)
grep -rln "plistlib" src                                   # only src/skillgate_ai/launchd.py
wc -l src/skillgate_ai/cli_compare.py src/skillgate_ai/cli/{cmd_compare,compare_run,compare_jobs,cmd_judge,cmd_case,cmd_judge_provider,cmd_gate,gate_output,pack_history,history_format}.py   # each ≤ 200
python -I -c "import skillgate_ai.cli_compare as m; print(m.register_compare_commands.__module__)"     # skillgate_ai.cli.cmd_compare
```

Also run the `--help` diff from §3 (A-verification). It must print nothing.

## 9. Acceptance checklist

- [ ] `test_public_imports.py` passes with `CLI_SURFACE_SHA256`, `TOP_COMMANDS`, `SUB_COMMANDS`, `REGISTRY` and `PASS_THROUGH` **unchanged**.
- [ ] The `--help` output diff against `main` is empty for every command listed in §3.
- [ ] The four oversized modules and all seven new `cli/` modules are each ≤ 200 lines. `cli_compare.py` is an import-only shim.
- [ ] `src/skillgate_ai/local_ui/` and `tests/test_local_ui.py` are gone. Package-data, `MANIFEST.in`, the ruff per-file ignore and `AGENTS.md` are updated.
- [ ] `test_settings_keys_reject_line_breaks` exists and passes. The result of the symlink probe is recorded in the PR description, with a test added if it returned 400 or 404.
- [ ] `observability.py` is gone, with no remaining references. The `_run_task` `try/finally` still calls `control.end_task()`. `run_eval` keeps its signature.
- [ ] `launchd.write_launch_agent` is the only plist writer. The helper and sync plist bytes match the golden `plistlib.dumps` values. All three existing launchd tests pass unchanged.
- [ ] Both flaky tests are free of `sleep`, `Timer`, retries and skips, and pass 20/20 twice: once idle and once under load. Both mutation checks fail as expected.
- [ ] The pnpm test skips with the exact message when the toolchain is missing, fails under `CI=1`, and never changes `web_static/`.
- [ ] `ruff check`, `ruff format --check`, `mypy src`, the unit and integration pytest runs, and both seed-pack gate commands are green.
- [ ] There is one `CHANGELOG.md` bullet under Unreleased.

## 10. DO NOT TOUCH

- **CLI and public API:**
  - No changes to command names, options, defaults, help or docstrings, or registration order.
  - No changes to `[project.scripts]`.
  - No renames of re-exported `skillgate_ai.cli` symbols.
  - Keep `skillgate_ai.cli_compare.register_compare_commands`, `helper.install_launchd_plist()`, `sync.install_launchd_plist(...)` and `engine.run_eval(...)` signatures.
- **CI, deps and tooling:**
  - No edits to `.github/workflows/*`, `uv.lock`, `.pre-commit-config.yaml` or `Dockerfile`.
  - No `[project.dependencies]` or optional-dependency changes, and no `[tool.mypy]`, `[tool.pytest]` or ruff `select` changes.
  - The only allowed `pyproject.toml` edits are the two deletions in §4 B1.
- **Trees:** `web/**`, `skills/**`, `src/skillgate_ai/examples/**`, `src/skillgate_ai/web_static/**`, `docs/plans/**`, and `docs/specs/*` other than this file.
- **Security and retry surface:**
  - `http_retry.py`, `openai_http.py`, `local_guard.py`, `run_lock.py`, `harness/login.py` (fix the test, not the code), `compare/*.py` and `compare_control.py`.
  - In `sandbox.py`, change only the five observability lines.
- **Tests:**
  - Edit only the tests named in §§4–6.
  - Do not loosen or delete any other assertion.
  - Do not add `pytest.mark.flaky`, reruns or `xfail`.
  - Leave `test_run_inherited_kills_process_group_on_timeout` unchanged.
- **No extra refactors:** no deleting orphaned helpers beyond §4 (list them as follow-ups), no type-annotation sweeps of moved functions, and no renaming of moved private functions.

## 11. Follow-ups (not this PR)

- Apply the C2 handshake (`ready` line + EOF) to `test_run_inherited_kills_process_group_on_timeout`. It has the same handler-install race, which its 1 s timeout only makes rarer.
- Delete any helpers whose only importer was `local_ui/api.py` (see the list in the PR description).
- If the symlink probe returned 200, harden the FastAPI catalog against symlinked packs that point outside the workspace.
