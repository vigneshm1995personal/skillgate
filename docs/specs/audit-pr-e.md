# Audit PR E: CodeQL path barriers, typed FastAPI ingress, strict security typing

**Base:** `main` @ `d0b27d4` · **Branch:** `cursor/audit-pr-e` · **Re-audit:** 8.0/10 (2026-11-25)

Targets re-audit gaps **1** (CodeQL + CI gate), **2** (Pydantic ingress), **4** (strict mypy on security modules).

## DO-NOT-TOUCH

- `plugin/**`, `src/skillgate_ai/mcp/**`, `tests/test_wire_shapes.py`, `src/skillgate_ai/judge_settings.py`
- HTTP/MCP/CLI response JSON shapes (including key order and 422 vs `fail()` 400 semantics)
- `fail_under = 84.0`; no deleted tests; no version bump

## Baseline (d0b27d4)

| Metric | Command | Value |
|---|---|---|
| Open CodeQL | `gh api …/code-scanning/alerts?state=open` (paginate) | 49 (47 high, 2 med) |
| `request.json()` ingress | `rg 'await request\\.json\\(\\)' src/skillgate_ai` | 17 |
| `dict[str, Any]` lines | `rg -c 'dict\\[str, Any\\]' src/skillgate_ai \\| awk -F: '{s+=$2} END{print s}'` | 516 |
| Coverage | `pytest -q -m "not integration" --cov=skillgate_ai` | 84.08% |

## Step order

1. `paths.PathTraversalError`, `contained_path`, `require_under`; fixed `FsAnchor` roots (see `docs/specs/audit-pr-e-fixed-roots.md`)
2. Route filesystem sinks through helpers; non-path fixes (launchd 0600, `action.yml`, secret masking, stack traces, anchored regex)
3. `api_models.py` + replace all 17 `request.json()` handlers with `Body()` models
4. `[[tool.mypy.overrides]]` on `paths`, `catalog`, `sandbox`, `local_guard` — fix errors in those modules only
5. `codeql.yml` `workflow_call` + `enforce` job; `gate.yml` calls reusable CodeQL and `all-gates` needs `codeql`
6. `tests/test_paths.py`, extend `test_ui_security.py` / API tests as needed for new validation paths

## Scope A — CodeQL (fix in code; never dismiss)

- **43 × py/path-injection:** `contained_path` / `require_under` at sinks; `catalog.find_skill` choke; fixed-root `pack_access_root` (no env-pin laundering)
- **2 × py/overly-permissive-file:** `launchd.py` plist `0600`; stop chmod on `LaunchAgents` dir
- **1 × py/stack-trace-exposure:** generic 404 message in `api.py`
- **1 × py/clear-text-logging-sensitive-data:** mask via `::add-mask::` without logging secret bytes
- **1 × actions/code-injection/medium:** `ACTION_SCRIPTS` env in `action.yml`
- **1 × js/regex/missing-regexp-anchor:** anchor `https://example.com/v1` in `copy.test.ts`

**Acceptance:** `enforce` job reports 0 open high/critical alerts after analysis on this branch.

## Scope B — Pydantic ingress (`api_models.py`)

Models per route (names): `SetKeyBody`, `JudgeSettingsBody`, `SkillsImportBody`, `SkillPatchBody`, `SkillScriptsPatchBody`, `RunStartBody`, `EvalPinsBody`, `EvalSuiteBody`, `EvalFixtureBindBody`, `CompareStartBody`, `CompareCancelBody`, `CheckPreviewBody`, hosted shim bodies in `api_shims.py`. Invalid types → FastAPI 422; business rules unchanged → `fail(400, …)`.

## Scope C — mypy strict (security modules)

`disallow_any_generics`, `disallow_untyped_defs`, `disallow_incomplete_defs`, `no_implicit_optional`, `warn_return_any` on `skillgate_ai.paths`, `catalog`, `sandbox`, `local_guard`.

## Tests (new / extended)

- `test_contained_path_rejects_dotdot`, `test_require_under_rejects_outside`
- Existing `test_ui_security.py` symlink cases must remain green
- `test_launchd` plist mode 0600
- API tests in `test_api_intake_local.py` / skill routes: unchanged response bytes for valid payloads

## Acceptance checklist

- [ ] 0 open high CodeQL on PR head (post-analyze)
- [ ] 0 `await request.json()` in `src/skillgate_ai`
- [ ] `mypy src` green; strict override modules clean
- [ ] ≥84% coverage; `dict[str, Any]` lines ≤ 516
- [ ] `gate` workflow `all-gates` green including `codeql`