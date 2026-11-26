# Audit PR F (5/5 toward 9/10): core wire typing, import layering, boundary mypy

**Save as:** `docs/specs/audit-pr-f.md`  
**Branch:** `cursor/audit-pr-f` (from `main` @ `63ce4a0`, after audit PR #99).  
**Parent context:** Nov 2026 re-audit **8.0/10** (`~/skillgate-reaudit-2026-11-25.md`).  
**Opus spec pass:** drafted with `unset ANTHROPIC_API_KEY && claude -p --model opus` + repo measurements on `63ce4a0` (implementation is a separate PR).

## One-line goal

Tighten **run / check / deploy** wire payloads with shared `TypedDict`s, **enforce package layering** with import-linter in CI (and fix today’s violations), and extend **mypy strict islands** on filesystem/trust modules — **without** changing golden JSON bytes, MCP sources, or `judge_settings.py`.

---

## Scope options

| | **Option A — Narrow** | **Option B — Recommended** | **Option C — Ambitious** |
|---|---|---|---|
| **Typing** | New `payloads/wire.py` only; type `gate.result_payload`, `deploy_gate.run_gate_summary`, `report/dicts.py` return annotations; leave `TaskReport.judge` as `dict` at runtime | Option A + replace `dict[str, Any]` in `engine/models.py`, `engine/verdict.py`, `engine/task.py`, `history.py`, `run_registry.py`, `run_status.py` with wire types / `Mapping` | Option B + `judge_context.py`, `judge_openai/outcome.py`, `api_payloads.py` (still no MCP edits) |
| **`dict[str, Any]` target** | ≤ **490** lines (all `src/skillgate_ai`) | ≤ **430** lines; **mcp/** frozen at **46** lines (not counted toward reduction) | ≤ **380** lines; mcp frozen **46** |
| **import-linter** | Config + CI job; **document-only** waiver for `gate → api_payloads` | Config + CI; **fix** violations (extract scrub helpers; `agent_roots.py`) | B + forbid `cli → api_payloads` lazy imports where possible |
| **mypy** | No change | Add strict overrides: `trusted_roots`, `pack_io`, `contained_fs`, `allow_root` | B + `disallow_untyped_defs` on `engine/verdict.py`, `engine/task.py` |
| **Coverage** | ≥ 84.0% (unchanged `fail_under`) | ≥ 84.0% with **measured** ≥ 84.3% headroom before merge | Raise `fail_under` to **84.5** |
| **FastAPI / ingress** | Out of scope | Out of scope (already `Body()` models on main; no `request.json()` in `api_*.py`) | Tighten `api_models.py` only; no handler refactors |
| **CodeQL triage** | Admin / follow-up | Documented out-of-scope | Out-of-scope |

**Recommendation: Option B.** It addresses the re-audit’s #3 and #5 directly, adds enforceable architecture (#5), extends security typing (#4) on modules touched in PR E, and keeps wire goldens frozen. Option A does not move the Architecture score enough; Option C risks wire drift and a large review surface.

### Expected score gain (re-audit categories → ~9.0 trajectory)

| Category | Baseline (8.0 audit) | Option B target | Δ (est.) |
|---|---|---|---|
| Typing | 7.5 | 8.6 | +1.1 |
| Architecture / Maintainability | 7.4 | 8.5 | +1.1 |
| Code quality | 7.8 | 8.4 | +0.6 |
| Best practices | 8.0 | 8.5 | +0.5 |
| Security | 8.3 | 8.5 | +0.2 (layering + typed history rows) |
| Testing | 8.2 | 8.4 | +0.2 |
| CI / Dependencies | 8.8 | 9.0 | +0.2 (import-linter job) |
| Retries, Documentation | — | — | unchanged this PR |
| **Overall** | **8.0** | **~8.7–8.9** | **+0.7–0.9** (full 9.0 needs CodeQL triage + MCP/FastAPI phase) |

---

## DO-NOT-TOUCH

- **`plugin/**`** — no edits.
- **`src/skillgate_ai/mcp/**`** — no edits; **46** `dict[str, Any]` lines stay frozen.
- **`tests/test_wire_shapes.py`** — no edits; golden `json.dumps(..., sort_keys=True)` bytes must match.
- **`src/skillgate_ai/judge_settings.py`** — no edits.
- **HTTP/MCP JSON wire shapes** — key order, field names, and scalar types unchanged (typed models are annotations + construction helpers only; serialization paths unchanged).
- **`fail_under = 84.0`** in `[tool.coverage.report]` — unchanged unless Option C is explicitly chosen.
- **No** version bump, **no** new `# type: ignore` / `# noqa` to bypass rules, **no** barrier/suppression for CodeQL.
- **Secrets:** never print or commit `~/.skillgate`, vault keys, or live API keys.

---

## Baseline (measure on `main` @ `63ce4a0`)

| Metric | Command | Baseline |
|---|---|---|
| `dict[str, Any]` lines (all src) | `grep -rn 'dict\[str, Any\]' src/skillgate_ai \| wc -l` | **516** |
| … of which `mcp/` (frozen) | `grep -rn 'dict\[str, Any\]' src/skillgate_ai/mcp \| wc -l` | **46** |
| … ex-mcp (in-scope quota) | subtract | **470** |
| TypedDict classes | `grep -rnE 'class \w+\(TypedDict' src/skillgate_ai \| wc -l` | record in step 1 |
| Unit tests | `pytest -q -m "not integration"` | record in step 1 |
| Coverage | `pytest -q -m "not integration" --cov=skillgate_ai --cov-report=term` | ≥ **84.0%** |
| import-linter | n/a | **not installed** |
| mypy strict modules | `pyproject.toml` `[[tool.mypy.overrides]]` | `paths`, `catalog`, `sandbox`, `local_guard` |

**Core cluster (in-scope typing) — line counts on `63ce4a0`:**

| File | `dict[str, Any]` lines |
|---|---|
| `engine/verdict.py` | 16 |
| `engine/models.py` | 8 |
| `engine/task.py` | 7 |
| `history.py` | 11 |
| `run_status.py` | 9 |
| `run_registry.py` | 7 |
| `judge_context.py` | 14 |
| `judge_openai/outcome.py` | 6 |
| `gate.py` | 3 |
| `deploy_gate.py` | 2 |
| `report/lines.py` | 4 |
| `report/dicts.py` | 0 (untyped `dict` returns) |
| `api_payloads.py` | 15 (Option B: defer; Option C: type) |

---

## Scope B — files, functions, and types

### F1. New package: `src/skillgate_ai/payloads/`

| File | Purpose |
|---|---|
| `payloads/__init__.py` | Re-export public wire types only |
| `payloads/wire.py` | `TypedDict` definitions (no runtime validation in hot path) |
| `payloads/scrub.py` | **Move from** `api_payloads`: `scrub_browser_payload`, `scrub_config` (and helpers they need) |

**New `TypedDict` names** (wire-stable; fields must match `tests/test_wire_shapes.py` and `tests/test_report.py` payloads):

| Type | Mirrors | Used by |
|---|---|---|
| `UsageWire` | task `usage` blobs | `TaskReport.usage`, `TaskProgress.usage`, `engine/task._task_usage` |
| `JudgeWire` | `judge_stamp` / report `tasks[].judge` | `TaskReport.judge`, `TaskProgress.judge`, `engine/verdict._no_trigger_skipped_judge` return |
| `SpanWire` | OTel span dicts | `TaskReport.spans`, `engine/task._spans_from_transcript` |
| `TaskOutputWire` | `outputs[]` rows | `TaskReport.outputs`, `engine/verdict._outcome_judge_outputs` |
| `SuiteConfigWire` | `report.config` / `progress.config` | `EvalProgress.config`, `SuiteReport.config`, `result_payload` |
| `CheckResultWire` | `gate.result_payload` top-level | `gate.result_payload` return type |
| `SuiteReportWire` | `report_to_dict` output | `report/dicts.report_to_dict`, `progress_to_dict` |
| `DeployGateSummaryWire` | deploy gate summary rows | `deploy_gate.run_gate_summary` return |
| `HistoryRowWire` | eval history JSONL row | `history.append_eval`, `run_registry` readers |

**Rule:** Builders stay in existing functions; change **annotations** and local variables from `dict[str, Any]` to these types. Use `cast()` only at JSON boundary if unavoidable (prefer `typing_extensions.assert_type` in tests, not in prod).

### F2. `src/skillgate_ai/gate.py`

| Function | Change |
|---|---|
| `run_check` | Type `checks: list[PackCheckWire] \| None` where `PackCheckWire` is a small `TypedDict` for ad-hoc Checks tab rows (fields: `id`, `files`, `golden_path`, `output_path`, `contains` — match `case_pack/suites._file_copies` usage only; **no** wire change). |
| `result_payload` | Return `CheckResultWire`; build literal unchanged; `error` stays `Mapping[str, Any] \| None` only if `errors.error_payload` not yet typed (else `ErrorWire`). |

### F3. `src/skillgate_ai/report/dicts.py`

| Function | Change |
|---|---|
| `report_to_dict` | Annotate return `SuiteReportWire` (still `json.dumps`-compatible plain dict). |
| `progress_to_dict` | Annotate return `ProgressWire` (nested `tasks` = list of progress task wire). |
| `_task_to_dict`, `_progress_task_to_dict`, `_advice_to_dict` | Return typed aliases; **no** key renames. |

Keep `tests/test_report.py` assertions on dict keys — must pass unchanged.

### F4. `src/skillgate_ai/deploy_gate.py`

| Function | Change |
|---|---|
| `run_gate_summary` | Input `row: Mapping[str, object]` or `HistoryRowWire`; return `DeployGateSummaryWire`. |
| `_gate_row` (if present) | Return `HistoryRowWire` fragment. |

Keep **`tests/test_deploy_gate.py`** tests `test_run_gate_summary_*` byte-identical on keys/values.

### F5. `src/skillgate_ai/engine/`

| File | Functions / fields |
|---|---|
| `models.py` | `TaskReport.outputs: list[TaskOutputWire]`; `usage`, `judge`, `spans` fields typed; `SuiteReport.usage_totals` → `UsageWire \| None`. |
| `verdict.py` | All `dict[str, Any]` locals/returns → wire types above; keep logic identical. |
| `task.py` | `_task_usage`, `_run_record`, `_spans_from_transcript` annotations. |
| `run_progress.py` | `running_spans: list[SpanWire] \| None`. |

### F6. `src/skillgate_ai/history.py`, `run_registry.py`, `run_status.py`

- History JSONL rows: `HistoryRowWire` on write paths; readers use `Mapping` + narrow checks (no schema change).
- `run_registry` / `run_status` status blobs: type summaries only where they duplicate deploy gate / check payloads.

### F7. Layering fixes (import-linter)

**New module:** `src/skillgate_ai/agent_roots.py`

- Move `cursor_skills_root`, `codex_skills_root`, `claude_skills_root` **resolution** (env + home paths) out of `deploy.py` **or** re-export thin wrappers from `deploy` for backward compatibility.
- `trusted_roots._agent_roots()` imports getters from `agent_roots.py`, **not** `deploy.py`.

**Violations to fix (measured on `63ce4a0`):**

| From | Imports | Fix |
|---|---|---|
| `gate.py` | `api_payloads.scrub_*` | Import from `payloads.scrub` |
| `cli/gate_output.py` | `api_payloads.scrub_browser_payload` | `payloads.scrub` |
| `mcp/tools.py` | (frozen) | **No edit** — contract: `mcp` may import `api_payloads`; domain must not depend on `mcp` |

**Optional remaining violation (Option B):** `api_payloads` imported by `cli` — allowed if `cli` is a **surface** layer in contracts below.

### F8. import-linter configuration (`pyproject.toml` + CI)

Add dev dependency: `import-linter>=2.0`.

```toml
[tool.importlinter]
root_package = "skillgate_ai"

[[tool.importlinter.contracts]]
name = "Filesystem core is below domain"
type = "layers"
layers = [
  "skillgate_ai.path_traversal",
  "skillgate_ai.fs_anchor",
  "skillgate_ai.contained_fs",
  "skillgate_ai.pack_layout",
  "skillgate_ai.allow_root",
  "skillgate_ai.pack_io",
  "skillgate_ai.paths",
  "skillgate_ai.trusted_roots",
]
containers = "skillgate_ai"

[[tool.importlinter.contracts]]
name = "Domain does not import HTTP UI"
type = "forbidden"
source_modules = [
  "skillgate_ai.engine",
  "skillgate_ai.gate",
  "skillgate_ai.deploy",
  "skillgate_ai.case_pack",
  "skillgate_ai.harness",
  "skillgate_ai.history",
  "skillgate_ai.run_registry",
  "skillgate_ai.run_status",
  "skillgate_ai.payloads",
]
forbidden_modules = [
  "skillgate_ai.api",
  "skillgate_ai.api_payloads",
  "skillgate_ai.api_evals",
  "skillgate_ai.api_skills",
  "skillgate_ai.api_runs",
  "skillgate_ai.api_compare",
  "skillgate_ai.api_shims",
  "skillgate_ai.server",
]

[[tool.importlinter.contracts]]
name = "Core FS does not import surfaces"
type = "forbidden"
source_modules = [
  "skillgate_ai.paths",
  "skillgate_ai.trusted_roots",
  "skillgate_ai.contained_fs",
  "skillgate_ai.pack_io",
]
forbidden_modules = [
  "skillgate_ai.cli",
  "skillgate_ai.api",
  "skillgate_ai.server",
  "skillgate_ai.mcp",
]

[[tool.importlinter.contracts]]
name = "MCP is a leaf (domain must not import MCP)"
type = "forbidden"
source_modules = ["skillgate_ai"]
forbidden_modules = ["skillgate_ai.mcp"]
ignore_imports = [
  # Tests only; production must stay clean
]
```

**CI (`.github/workflows/gate.yml`):** add lint step after ruff:

```yaml
- name: Import layering (import-linter)
  run: lint-imports
```

### F9. mypy (Option B)

Extend `[[tool.mypy.overrides]]` module list in `pyproject.toml`:

```toml
module = [
  "skillgate_ai.paths",
  "skillgate_ai.catalog",
  "skillgate_ai.sandbox",
  "skillgate_ai.local_guard",
  "skillgate_ai.trusted_roots",
  "skillgate_ai.pack_io",
  "skillgate_ai.contained_fs",
  "skillgate_ai.allow_root",
]
```

Same flags as existing block (`disallow_untyped_defs`, `disallow_any_generics`, etc.). Fix any new errors only in those modules — **no** global `strict = true`.

---

## Tests (exact names and assertions)

### Keep (must stay green, no edits unless noted)

| Test | File | Assert |
|---|---|---|
| All golden wire tests | `tests/test_wire_shapes.py` | **DO NOT EDIT** — full file unchanged |
| `test_run_gate_summary_running_record` | `tests/test_deploy_gate.py` | Summary dict keys/values unchanged |
| `test_run_gate_summary_drops_reason_for_official` | `tests/test_deploy_gate.py` | `tryout_reason` None for official |
| `test_run_gate_summary_error_row` | `tests/test_deploy_gate.py` | Error row shape unchanged |
| `test_run_gate_summary_tryout_pending` | `tests/test_deploy_gate.py` | Tryout flags unchanged |
| Report payload tests | `tests/test_report.py` | All `report_to_dict` key assertions unchanged |
| `test_entry_points_unchanged` | `tests/test_public_imports.py` | `report_to_dict` export unchanged |

### New

| Test | File | Assert |
|---|---|---|
| `test_result_payload_matches_report_wire_subset` | `tests/test_gate.py` | `result_payload(CheckResult(...))` has keys `run_id`, `exit_code`, `error`, `report`; `report["tasks"][0]` contains `judge`, `usage`, `spans` with same types as `report_to_dict` for a minimal fake `SuiteReport`. |
| `test_report_to_dict_is_json_roundtrip` | `tests/test_report.py` | `json.loads(json.dumps(report_to_dict(r)))` equals `report_to_dict(r)` (key stability). |
| `test_deploy_gate_summary_typed_keys` | `tests/test_deploy_gate.py` | `run_gate_summary({...})` returns dict with only allowed keys from `DeployGateSummaryWire` (`status`, `passed`, `tryout`, `tryout_reason`, `error`, … — exact set documented in spec commit). |
| `test_scrub_helpers_importable_without_api` | `tests/test_api_local.py` or **new** `tests/test_payloads_scrub.py` | `from skillgate_ai.payloads.scrub import scrub_browser_payload` works; `import skillgate_ai.gate` does not require importing `api_payloads` at module level (optional: `importlib` check). |
| `test_agent_roots_used_by_trusted_roots` | `tests/test_trusted_roots.py` | `trusted_roots.pack_access_root` under mocked `agent_roots.cursor_skills_root` still returns `FsAnchor.AGENT_CURSOR` (regression for deploy decouple). |
| `test_import_linter_config_present` | `tests/test_oss_surface.py` or new `tests/test_import_linter.py` | `pyproject.toml` contains `[tool.importlinter]` and at least 3 contracts; CI script invokes `lint-imports` (read file / subprocess dry-run). |

### Optional (Option C only)

| Test | File | Assert |
|---|---|---|
| `test_api_payloads_history_row_shape` | `tests/test_api_local.py` | `history_payload` keys unchanged vs golden snapshot substring |

---

## Step order

1. **Commit this spec** on `cursor/audit-pr-f` (spec-only).
2. Re-run baseline table; record counts in PR description.
3. Add `import-linter` to `[project.optional-dependencies] dev` + `[tool.importlinter]` contracts; CI step — expect **red** until F7.
4. Add `payloads/scrub.py`; switch `gate.py`, `cli/gate_output.py` imports; run tests.
5. Add `payloads/wire.py` types; annotate `report/dicts.py`, `gate.result_payload`, `deploy_gate.run_gate_summary`.
6. Refactor `engine/models.py`, `verdict.py`, `task.py`, `run_progress.py` annotations.
7. Type `history.py` / `run_registry.py` / `run_status.py` row helpers.
8. Add `agent_roots.py`; rewire `trusted_roots._agent_roots`; keep `deploy.py` public API via re-export.
9. Run `lint-imports` until green; fix any contract drift.
10. Extend mypy overrides; fix only listed modules.
11. Full `pytest -q -m "not integration" --cov`; coverage ≥ 84.0%; `ruff check`, `mypy src/skillgate_ai`.
12. Push; open PR when implementation begins (not in spec commit).

---

## Acceptance criteria

- `grep -rn 'dict\[str, Any\]' src/skillgate_ai | wc -l` ≤ **430** (Option B) and `mcp/` still **46** lines unchanged.
- `lint-imports` passes with contracts in this spec.
- `pytest -q -m "not integration"` — **0 failures**; count ≥ baseline on `63ce4a0`.
- Coverage ≥ **84.0%** (`fail_under` unchanged).
- `tests/test_wire_shapes.py` — **unchanged** on disk.
- GitHub **gate** workflow: ruff, mypy, import-linter, tests, **codeql/enforce**, **all-gates** green.
- No module **> 600** lines; no edits under DO-NOT-TOUCH paths.
- Re-audit spot-check: Architecture and Typing categories ≥ **8.5** on the PR branch (informal self-score in PR body).

---

## Risks

| Risk | Mitigation |
|---|---|
| Wire JSON drift vs UI / Actions | TypedDict only; run `test_wire_shapes` + `test_report` + gate summary tests; no key renames |
| `gate` ↔ `api_payloads` circular import after scrub move | New `payloads` package imports only `redact` / stdlib; no `api` imports |
| import-linter false positives on lazy imports | Keep lazy imports inside functions; add `ignore_imports` only with comment + issue link |
| Mypy strict islands expand breakage | Limit overrides to FS/trust modules; fix in-place, no blanket ignores |
| Large diff noise in `verdict.py` | Single commit per step; annotate before refactors |
| Agent root move breaks deploy | Re-export from `deploy.py`; `test_deploy*` + `test_trusted_roots` green |

---

## Out of scope (documented)

- **CodeQL alert triage** (49 open on older baseline) — admin/ops; merge gate already on PR E.
- **`mcp/**` typing** — follow-up PR G.
- **`judge_settings.py` bare asserts** — separate hygiene PR.
- **Branch coverage** and **fail_under 85+** — Option C or later.
- **Plugin / Flutter / packaging** — unchanged.

---

## User-visible behavior

**None** intended. CLI exit codes, report JSON for UI, deploy gate summaries, and history JSONL on disk stay compatible. Types are for maintainers, CI, and mypy — not runtime validation changes.