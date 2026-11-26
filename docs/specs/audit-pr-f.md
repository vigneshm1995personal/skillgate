# Audit PR F: FS-core decoupling, enforced import layering, typed gate/run payloads, wider strict mypy

**Authored by Claude Opus** (`claude -p --model opus`, Pro login, no API key). It is a critical rewrite of the Composer draft. All file, line and symbol references were checked against the tree before writing.

Save as: `docs/specs/audit-pr-f.md`
Branch: `cursor/audit-pr-f`, base `main` @ `63ce4a0` (PR #99 merged). The spec-only commit `8a4f52d` sits on top. One PR, one commit per step in "Step order".
Parent context: re-audit **8.0/10** (`~/skillgate-reaudit-2026-11-25.md`, scored on `d0b27d4`, **before** PR E). PR E's CodeQL gate and `Body()` ingress models are not reflected in those scores yet.

This PR has four scopes:

- **L. Layering.** Move the agent-skill root getters out of `deploy.py` so the filesystem core stops importing domain code. Move the browser scrub helpers out of `api_payloads.py` so domain modules stop importing the HTTP surface. Then enforce both directions with import-linter in CI and pre-commit.
- **M. mypy.** Extend the existing strict override block from 4 modules to the whole FS core (12 modules).
- **T. Typing.** Remove `dict[str, Any]` lines from the run/check/gate cluster, with a per-file budget. Add TypedDicts only where a function builds a dict literal and returns it.
- **R. Ratchets.** Tighten `tests/test_audit_ratchets.py` so the new numbers cannot regress.

**User-visible behavior: none intended.** No JSON, CLI, HTTP or MCP shape changes. No message text, exit code or dict key order changes. The only runtime-observable difference is which modules end up in `sys.modules` after importing `trusted_roots` / `fs_anchor` / `gate` / `history`: `deploy` and `api_payloads` are no longer loaded as a side effect.

---

## Corrections to the Composer draft (why this spec differs)

| Draft claim | Reality on `63ce4a0` | Consequence |
|---|---|---|
| `layers` contract over `path_traversal → … → trusted_roots` | `paths`, `trusted_roots`, `pack_layout`, `contained_fs` and `fs_anchor` import each other lazily, in both directions (for example `paths.py:32` → `trusted_roots` and `trusted_roots.py:11` → `paths`). import-linter counts function-level imports. | A layers contract over these modules can never pass. Replaced with `forbidden` contracts (FS core → domain/surfaces) and a "primitives are leaves" contract. |
| Only `trusted_roots` imports `deploy` | `fs_anchor.py:53/57/61` and `catalog.py:8` import it too | `agent_roots.py` must cover all three. |
| Violations are `gate.py` and `cli/gate_output.py` | Domain → `api_payloads` imports are at **`gate.py:67`, `history.py:177` and `compare/payload.py:202`**, all lazy. `cli/gate_output.py:13` is surface → surface, which is fine. | All three domain sites move to `skillgate_ai.scrub`. |
| `run_gate_summary` keys `status, passed, tryout, …` | Actual keys, in order: `kind`, `moves_gate`, `decision`, `reason`, `tryout_reason` (`deploy_gate.py:66–72`) | Test and TypedDict use the real keys. |
| `TaskReport.judge: JudgeWire` etc. | `judge` values come from the `Judge.judge` protocol, which returns `dict[str, Any]` (kept by the PR D rule). mypy rejects assigning `dict[str, Any]` to a TypedDict, and rejects passing a TypedDict where `dict[str, Any]` is expected, unless you `cast()`, which is banned. | No TypedDicts on engine dataclass fields that are fed by protocols. Use `Mapping[str, Any]` for read-only data, and TypedDicts only for dicts built from a literal. |
| `report/dicts.py` annotations reduce the count | `report/dicts.py` has **0** `dict[str, Any]` lines (it uses bare `dict`). Its output is mutated downstream (`hydrate_report_spans`, scrubs). | Out of scope for B. Annotating it moves no metric and risks invariance errors. |
| Target ≤ 430 for Option B | The in-scope cluster (excluding `mcp/`, routes and `judge_context`) holds **69** lines, and many are mutation sites kept under the PR D rules | Realistic B target: **≤ 487** planned, **≤ 492** hard. |
| A central `payloads/wire.py` | Conflicts with PR D rule 5 (a TypedDict lives in the file that builds it) | New TypedDicts live next to their builder. No `payloads/` package. Scrub becomes a single module, `scrub.py`. |
| Contract "MCP is a leaf" with `source_modules = ["skillgate_ai"]` | The source contains the forbidden module itself, which is invalid config. `cli/cmd_mcp.py:32` legitimately imports `mcp.server`. | Expressed as "domain and HTTP surfaces must not import `mcp`". |
| Adding a dev dependency is just `pyproject` | CI runs `uv sync --locked`, and pip-audit audits the lockfile | `uv lock` must be rerun and committed, and the new dependencies (`import-linter`, `grimp`) must pass pip-audit. |
| `test_trusted_roots` stays green untouched | 3 tests patch `"skillgate_ai.deploy.cursor_skills_root"` (`tests/test_trusted_roots.py:55` and two more) | Patch strings move to `skillgate_ai.agent_roots.cursor_skills_root`, and `trusted_roots` must keep resolving the getter at call time. |

---

## Scope options

| | **Option A: Narrow** | **Option B: Recommended** | **Option C: Ambitious** |
|---|---|---|---|
| **Layering** | `agent_roots.py` + `scrub.py` moves; import-linter **not** added | A + import-linter (4 contracts, direct-import mode for contract 2) in CI + pre-commit | B + contract 2 switched to indirect-import mode; untangle `paths` ↔ `trusted_roots` so a true `layers` contract fits |
| **mypy strict** | unchanged (4 modules) | 12 modules (whole FS core + `agent_roots`, `scrub`) | B + `engine.verdict`, `engine.task`, `deploy_gate`, `gate` |
| **`dict[str, Any]` lines** | ≤ **508** (gate, deploy_gate, run_progress, report/lines) | ≤ **487** planned / ≤ **492** hard | ≤ **470** (adds `judge_context` 14→≤8, `api_payloads` non-route helpers, deeper `verdict`) |
| **`mcp/`** | frozen at 46 | frozen at 46 | frozen at 46 |
| **New TypedDicts** | `GateSummary`, `CheckResultPayload` | A + ≤ 4 engine/history literals (decided in step 1) | B + `judge_context` shapes |
| **Coverage** | ≥ 84.0 | ≥ 84.0; record the measured value | `fail_under` → 84.5 (needs measured CI ≥ 84.5) |
| **Ratchets** | dict budget → 508 | dict budget → 492, mcp == 46, TypedDict floor, strict-module set | as B with C numbers |

**Recommendation: Option B.** It is the smallest change that turns "flat layout, no layering" (re-audit gap #5) into an enforced CI contract. It removes the two real dependency smells (FS core → `deploy` → `history` → …, and domain → HTTP payloads). It gives the PR E security modules strict typing (gap #4) and makes measurable progress on gap #3, all without touching wire shapes. Option A leaves architecture unenforced, so the score does not move. Option C's untangling of `paths` ↔ `trusted_roots` is a security-sensitive refactor of the PR E containment code, and it deserves its own PR.

### Expected score gain (Option B; re-audit categories)

| Category | Re-audit (8.0, pre-PR E) | Option B estimate | Δ | Driver |
|---|---|---|---|---|
| Architecture / Maintainability | 7.4 | 8.2 | +0.8 | Enforced contracts; FS core no longer pulls in `deploy`/`history`/`ingest`/`pack` |
| Typing | 7.5 | 8.0 | +0.5 | 12 strict modules; −29 dict lines; TypedDicts for gate/check payloads |
| Code quality | 7.8 | 8.0 | +0.2 | Scrub helpers in one cohesive module; no domain → surface lazy imports |
| CI / Dependencies | 8.8 | 9.0 | +0.2 | `lint-imports` in CI + pre-commit; locked |
| Best practices | 8.0 | 8.2 | +0.2 | Architecture-as-config |
| Security | 8.3 | 8.4 | +0.1 | Strict typing on every containment module |
| Testing | 8.2 | 8.3 | +0.1 | Layering and seam tests; ratchets |
| Retries, Documentation | 8.5 / 8.0 | unchanged | 0 | — |
| **Overall** | **8.0** | **~8.3–8.4** (plus whatever PR E earns on re-score) | | 9.0 still needs: CodeQL backlog triaged to 0 high, typed `mcp/` boundary, coverage headroom ≥ 1 pt, branch coverage |

---

## DO-NOT-TOUCH

- **`plugin/**`**: no edits.
- **`src/skillgate_ai/mcp/**`**: no edits. Its 46 `dict[str, Any]` lines stay. `mcp/tools.py:10` imports `history_row_to_run` and `scrub_browser_payload` from `skillgate_ai.api_payloads`, so **both names must keep resolving there** (re-export).
- **`tests/test_wire_shapes.py`**: no edits. Its golden bytes stay byte-identical.
- **`src/skillgate_ai/judge_settings.py`**: no edits.
- **Wire shapes**: JSON, CLI, HTTP and MCP shapes stay the same, including dict key order. FastAPI route return annotations stay `dict[str, Any]` (PR D rule 1).
- **`fail_under = 84.0`**: unchanged (Option C only).
- **Lint config**: no new `# noqa`, `# type: ignore`, `cast()` or `ignore_imports` in import-linter contracts. No relaxation of `[tool.ruff*]` or `[tool.mypy]`. An `ignore_imports` entry is allowed only if a frozen file (`mcp/**`) forces it, and then it carries a comment naming the file. None is expected.
- **Public imports**: `REGISTRY`, `PASS_THROUGH`, `JUDGE_OPENAI_ALL`, `CLI_SURFACE_SHA256` and `test_entry_points_unchanged` stay unchanged. `deploy`, `api_payloads` and `history` are not in `REGISTRY`, and nothing gets added.
- **Lazy-import timing**: in-function imports stay in-function. `fs_anchor` and `trusted_roots` must import `agent_roots` **inside** the function, so `monkeypatch.setattr("skillgate_ai.agent_roots.…")` takes effect.
- **Versions**: no version bump.
- **Secrets**: never read, print or commit `~/.skillgate`, `.skillgate/keys` or API keys. Tests use `tmp_path` plus `monkeypatch.setenv("HOME", …)`.
- **Do not commit**: `evals/`, `experiments/` (untracked at branch start), `.coverage`, `coverage.xml`, `.import_linter_cache/`. Add the last one to `.gitignore`.
- **Known flaky tests**: `test_compare_models_cancel_stops_next_arm` and `test_run_inherited_keyboard_interrupt_kills_group`. Rerun once and record the result. Do not edit.

---

## Baseline (measured on `cursor/audit-pr-f` @ `8a4f52d` = `main` + spec)

| Metric | Command | Baseline |
|---|---|---|
| `dict[str, Any]` lines, all src | `grep -rn 'dict\[str, Any\]' src/skillgate_ai \| wc -l` | **516** |
| …under `mcp/` (frozen) | `grep -rn 'dict\[str, Any\]' src/skillgate_ai/mcp \| wc -l` | **46** |
| TypedDict classes | `grep -rnE 'class \w+\(TypedDict' src/skillgate_ai \| wc -l` | **27** |
| Unit tests | `pytest -q -m "not integration"` | **2138** passed, 35 deselected |
| Coverage | `pytest -q -m "not integration" --cov=skillgate_ai --cov-report=term` | ~**84.06%** (`fail_under = 84.0`) |
| mypy strict modules | `pyproject.toml` `[[tool.mypy.overrides]]` (line 160) | `paths`, `catalog`, `sandbox`, `local_guard` |
| import-linter | — | not configured |
| `deploy` importers in FS core | `grep -n 'skillgate_ai.deploy import' src/skillgate_ai/{fs_anchor,trusted_roots,catalog}.py` | `fs_anchor.py:53,57,61`; `trusted_roots.py:21`; `catalog.py:8` |
| Domain → `api_payloads` | `grep -rn 'from skillgate_ai.api_payloads' src/skillgate_ai/{gate,history}.py src/skillgate_ai/compare/payload.py` | `gate.py:67`, `history.py:177`, `compare/payload.py:202` |

**In-scope cluster, per file (`grep -c`):**

| File | Now | Option B budget | Notes |
|---|---|---|---|
| `gate.py` | 3 | ≤ 1 | 399/401 → `CheckResultPayload`; 122 `checks` → `Sequence[Mapping[str, Any]] \| None` if read-only |
| `deploy_gate.py` | 2 | ≤ 1 | 55 → `GateSummary`; 146 (mutated `row`) kept |
| `engine/run_progress.py` | 2 | 0 | 22, 53 `running_spans: Sequence[Mapping[str, Any]] \| None` if only read |
| `engine/models.py` | 8 | ≤ 4 | 30–35, 54–57, 108: read-only fields → `Mapping`; fields fed by `Judge.judge` or mutated later stay |
| `engine/verdict.py` | 16 | ≤ 10 | params → `Mapping`; literal-built returns → local TypedDict |
| `engine/task.py` | 7 | ≤ 5 | |
| `history.py` | 11 | ≤ 7 | `_scrub_history_row` keeps its signature (−0); readers → `Mapping` |
| `run_status.py` | 9 | ≤ 6 | |
| `run_registry.py` | 7 | ≤ 5 | |
| `report/lines.py` | 4 | ≤ 1 | renderer params read-only → `Mapping` |
| `api_payloads.py` | 15 | ≤ 15 | scrub lines **move** to `scrub.py`; total unchanged |
| **Planned removal** | | **−29** → **487** | Hard acceptance ≤ **492** (5 reverts allowed) |

Step 1 replaces "≤" with a line-level table (line → change → Δ) in the PR body, in the PR D Scope B format.

---

## Scope L: layering

### L1. New module `src/skillgate_ai/agent_roots.py`

- **Moves verbatim from `deploy.py`:** `_override_root` (around line 50), `cursor_skills_root` (54), `codex_skills_root` (60), `claude_skills_root` (64), and the env var names `SKILLGATE_CURSOR_SKILLS`, `SKILLGATE_CODEX_SKILLS`, `SKILLGATE_CLAUDE_SKILLS`.
- **Imports:** stdlib only (`os`, `pathlib.Path`). No `skillgate_ai.*` imports.
- **`deploy.py`** re-exports with `from skillgate_ai.agent_roots import claude_skills_root as claude_skills_root, codex_skills_root as codex_skills_root, cursor_skills_root as cursor_skills_root`. Its internal calls (lines 138–154) are unchanged. If `_override_root` has no other caller in `deploy.py`, it is not re-exported.
- **`fs_anchor.py:53/57/61`**: the lazy imports switch to `from skillgate_ai.agent_roots import …`. They stay in-function.
- **`trusted_roots._agent_roots` (line 20)**: the lazy import switches to `skillgate_ai.agent_roots` and stays in-function.
- **`catalog.py:8`**: switches to `from skillgate_ai.agent_roots import …`. `catalog` keeps its other imports. It is not part of the FS core contract, because it imports `ingest` and `pack`.
- **Patch seam:** `tests/test_trusted_roots.py` changes its 3 `monkeypatch.setattr("skillgate_ai.deploy.cursor_skills_root", …)` calls to `"skillgate_ai.agent_roots.cursor_skills_root"`. No other test patches these names (`grep -rn '_skills_root' tests | grep -E 'setattr|patch'`). Rerun that grep after the change.

### L2. New module `src/skillgate_ai/scrub.py`

- **Moves verbatim from `api_payloads.py`:** `_scrub_judge` (143), `_scrub_config` (153), `scrub_config` (176), `_scrub_browser` (183), `_neutral_scored_by` (213, lazy `judge_copy` import kept), `scrub_browser_payload` (237), and any module constant used **only** by these helpers. Step 1 greps `LIVE_AGENT_HARNESSES`. If `api_payloads` still uses it elsewhere, it stays defined in `scrub.py` and `api_payloads` imports it from there.
- **Imports allowed in `scrub.py`:** stdlib, `typing`, `collections.abc`, and lazy `skillgate_ai.judge_copy`. Nothing from `api*`, `server`, `cli` or `mcp`.
- **`api_payloads.py`** re-exports `scrub_browser_payload` and `scrub_config` with `from skillgate_ai.scrub import scrub_browser_payload as scrub_browser_payload, scrub_config as scrub_config`. It also re-exports any private name imported by `tests/test_api_payloads_scrub.py` or `tests/test_api_local.py` (check their import blocks in step 1). These keep `mcp/tools.py:10` and the existing tests working unedited.
- **Import switches** (all stay lazy where they are lazy today):
  - `gate.py:67` → `from skillgate_ai.scrub import scrub_browser_payload, scrub_config`
  - `history.py:177` → `from skillgate_ai.scrub import scrub_browser_payload`
  - `compare/payload.py:202` → `from skillgate_ai.scrub import scrub_browser_payload`
  - `cli/gate_output.py:13` and `cli/pack_history.py:109` may switch too (optional, surface → surface is allowed). Prefer switching `gate_output` for consistency, and leave `history_row_to_run` users alone.

### L3. import-linter

**Dependency:** add `"import-linter>=2.1"` to `[project.optional-dependencies] dev` (after `pip-audit`). Run `uv lock` and commit `uv.lock`. Run the pip-audit command from `gate.yml:188–190` locally before pushing.

**Config:** add to `pyproject.toml` after `[tool.coverage.report]`. Exact contract **names** are fixed because a test asserts them:

1. **`FS core does not import domain or surfaces`**: `type = "forbidden"`, indirect imports **not** allowed (default).
   - `source_modules`: `path_traversal`, `fs_anchor`, `contained_fs`, `pack_layout`, `allow_root`, `pack_io`, `paths`, `trusted_roots`, `agent_roots` (all `skillgate_ai.`-prefixed).
   - `forbidden_modules`: `deploy`, `deploy_gate`, `history`, `catalog`, `ingest`, `pack`, `engine`, `gate`, `case_pack`, `harness`, `judge`, `judge_openai`, `cli`, `api`, `api_payloads`, `api_models`, `api_intake`, `api_evals`, `api_skills`, `api_runs`, `api_compare`, `api_shims`, `server`, `checks_show`, `mcp`.
   - Violations today: `fs_anchor` → `deploy` (×3) and `trusted_roots` → `deploy`. L1 fixes both.
2. **`Domain does not import HTTP, CLI or MCP surfaces`**: `type = "forbidden"`, `allow_indirect_imports = true` in Option B (Option C flips it).
   - `source_modules`: `engine`, `gate`, `history`, `deploy`, `deploy_gate`, `case_pack`, `harness`, `judge_openai`, `report`, `compare`, `run_registry`, `run_status`, `scrub`, `agent_roots`.
   - `forbidden_modules`: `api`, `api_payloads`, `api_models`, `api_intake`, `api_evals`, `api_skills`, `api_runs`, `api_compare`, `api_shims`, `server`, `checks_show`, `cli`, `mcp`.
   - Violations today: `gate:67`, `history:177`, `compare/payload:202`. L2 fixes all three. Step 4 runs `lint-imports` before the fix to confirm no **other** direct violations exist. Any newcomer gets fixed the same way (move the helper down) or listed in the PR body as a blocker. It is never added to `ignore_imports`.
3. **`HTTP surface does not import CLI or MCP`**: `type = "forbidden"`.
   - `source_modules`: `api`, `api_payloads`, `api_models`, `api_intake`, `api_evals`, `api_skills`, `api_runs`, `api_compare`, `api_shims`, `server`.
   - `forbidden_modules`: `cli`, `mcp`.
   - Expected to pass today. Step 4 confirms it.
4. **`FS primitives are leaves`**: `type = "forbidden"`.
   - `source_modules`: `path_traversal`, `allow_root`, `agent_roots`.
   - `forbidden_modules`: `fs_anchor`, `paths`, `trusted_roots`, `contained_fs`, `pack_layout`, `pack_io`.
   - Today `allow_root` imports only `path_traversal`, and `path_traversal` imports nothing internal.

There is **no `layers` contract** in Option B. The `paths` ↔ `trusted_roots` ↔ `pack_layout` ↔ `contained_fs` ↔ `fs_anchor` cycle is intentional lazy-import containment code from PR E. The PR body records it as the Option C follow-up.

If the pinned import-linter supports `exclude_type_checking_imports`, set it to `true`. `api_payloads.py:13` (`fastapi.Request`) is external anyway, so this only matters for future internal `TYPE_CHECKING` imports. Verify in step 4 and drop the key if `lint-imports` rejects it.

**CI:** in `.github/workflows/gate.yml`, in the lint job right after `- run: mypy src` (line 73), add a step named `Import layering (import-linter)` that runs `lint-imports`.

**Pre-commit:** add a `repo: local` hook with `id: import-linter`, `entry: lint-imports`, `language: system`, `pass_filenames: false`, and `types: [python]`.

**Ignore:** add `.import_linter_cache/` to `.gitignore`.

---

## Scope M: mypy strict overrides

Extend the module list in the **existing** `[[tool.mypy.overrides]]` block (`pyproject.toml:160–172`). The flags stay identical (`disallow_any_generics`, `disallow_untyped_defs`, `disallow_incomplete_defs`, `check_untyped_defs`, `no_implicit_optional`, `warn_return_any`).

Final module list (12): `paths`, `catalog`, `sandbox`, `local_guard` (existing), plus `trusted_roots`, `fs_anchor`, `contained_fs`, `pack_layout`, `pack_io`, `allow_root`, `path_traversal`, `agent_roots`, `scrub`. That is 13 with `scrub`. If `scrub` needs more than 5 annotation edits beyond the move, drop it to Option C and record why. The acceptance floor is the 12 without `scrub`.

Fix new errors **only** inside the listed modules, with annotations and no behavior changes. No global `strict`. No `ignore_missing_imports` changes.

---

## Scope T: typing

### Rules (PR D rules 1–6 apply unchanged, plus)

7. **A TypedDict is allowed only where the function builds the dict from a literal in the same function, and every consumer accepts it**: `Mapping[str, Any]`, `Any`, `json.dumps`, or the TypedDict itself. If any consumer parameter is `dict[str, Any]`, either widen that parameter to `Mapping[str, Any]` (if it is read-only) or don't introduce the TypedDict.
8. **Never type a field fed by `Judge.judge`, `CompareResult.payload` or any other protocol result as a TypedDict.** Use `Mapping[str, Any]` if it is read-only, otherwise keep `dict[str, Any]`.
9. **TypedDict field declaration order matches the runtime literal key order.** This is for readability only. Runtime order still comes from the literal.

### T1. `deploy_gate.py`

- New `class GateSummary(TypedDict)`, defined directly above `run_gate_summary`, with fields in this order:
  - `kind: Literal["tryout", "official"]`
  - `moves_gate: bool`
  - `decision: str`
  - `reason: str`
  - `tryout_reason: str | None`
- `run_gate_summary(row: Mapping[str, Any], *, tryout_reason: str | None = None) -> GateSummary`. The body is unchanged.
- Step 1 checks callers (`grep -rn run_gate_summary src`). Every caller that stores the result into a `dict[str, Any]` slot or passes it to a `dict[str, Any]` param applies rule 7 or reverts.

### T2. `gate.py`

- New `class CheckResultPayload(TypedDict)`, defined directly above `result_payload` (line 399). Fields:
  - `run_id: str`
  - `exit_code: int`
  - `demo_notice: str | None`
  - `expect_fail_notice: str | None`
  - `error: Mapping[str, Any] | None`, or the actual declared type of `CheckResult.error`, whichever is narrower and passes mypy
  - `report: dict[str, Any] | None`, mirroring `report_to_dict`'s bare `dict`; written as `dict[Any, Any]` if mypy demands it under bare `dict`
- `result_payload(...) -> CheckResultPayload`, with local `payload: CheckResultPayload = {…}`. The literal is unchanged.
- Line 122, the `checks: list[dict[str, Any]] | None` parameter of `run_check`: becomes `Sequence[Mapping[str, Any]] | None` only if `run_check` and its callees don't mutate or `list`-concatenate it. Otherwise it is kept.

### T3. `engine/run_progress.py`, `report/lines.py`

Read-only params go to `Mapping`/`Sequence[Mapping]` per PR D rule 3. Nothing else.

### T4. `engine/models.py`, `engine/verdict.py`, `engine/task.py`

Apply rules 3, 7 and 8 per line, within the budget table. Step 1 classifies each of the 31 lines as **param-readonly / literal-return / protocol-fed / mutated**. Only the first two change. New TypedDicts, if any, live in `verdict.py` or `task.py` next to their builders. There are at most 4 across T4 and T5, and the PR body lists them by name.

### T5. `history.py`, `run_status.py`, `run_registry.py`

Same classification. JSONL row **writers** keep `dict[str, Any]` where rows are mutated before `_append_jsonl`. Row **readers** take `Mapping[str, Any]`. No on-disk schema change.

---

## Tests

### Must stay green, unedited

- `tests/test_wire_shapes.py` (whole file)
- `tests/test_deploy_gate.py`: `test_run_gate_summary_running_record`, `test_run_gate_summary_drops_reason_for_official`, `test_run_gate_summary_error_row`, `test_run_gate_summary_tryout_pending`
- `tests/test_api_payloads_scrub.py` (exercises the `api_payloads` re-exports)
- `tests/test_report.py`, `tests/test_report_hydrate.py`, `tests/test_history.py`, `tests/test_history_compare.py`, `tests/test_catalog.py`, `tests/test_gate_output_helpers.py`
- `tests/test_public_imports.py` (all tests, including `test_entry_points_unchanged` and `test_defined_symbols_belong_to_their_module`)

### Edited

- **`tests/test_trusted_roots.py`**: 3 patch strings change from `skillgate_ai.deploy.cursor_skills_root` to `skillgate_ai.agent_roots.cursor_skills_root` (affects `test_agent_skill_immediate_child`, `test_agent_skill_without_evals_dir` and `test_rejects_nested_agent_path`). The assertions are unchanged.
- **`tests/test_audit_ratchets.py`**:
  - `test_dict_any_line_budget`: total `≤ 492` (Option B). The message becomes `"(baseline 516; PR F plan ≤492)"`. The `outcome.py ≤ 11` assertion is kept.

### New

**`tests/test_agent_roots.py`**

1. `test_cursor_root_env_override`: `monkeypatch.setenv("SKILLGATE_CURSOR_SKILLS", str(tmp_path / "c"))` → `cursor_skills_root() == (tmp_path / "c").resolve()`. The same test is parametrized over codex/claude and their env vars.
2. `test_agent_roots_default_under_home`: delete the three env vars and set `HOME` to `tmp_path`. Then `cursor_skills_root() == (tmp_path / ".cursor" / "skills").resolve()`, and likewise for `.codex` / `.claude`.
3. `test_deploy_reexports_agent_roots`: `deploy.cursor_skills_root is agent_roots.cursor_skills_root`, and the same for codex/claude.
4. `test_fs_core_import_does_not_load_deploy`: run a subprocess with `sys.executable -I -c` that imports `skillgate_ai.trusted_roots`, `skillgate_ai.fs_anchor` and `skillgate_ai.pack_io`, calls `FsAnchor.AGENT_CURSOR`'s base resolver (or `trusted_roots._agent_roots()`), and exits non-zero if `"skillgate_ai.deploy" in sys.modules`. Assert returncode 0. Pass `HOME` as `tmp_path` and the env with `SKILLGATE_CURSOR_SKILLS` set.

**`tests/test_scrub_module.py`**

5. `test_api_payloads_reexports_scrub`: `api_payloads.scrub_browser_payload is scrub.scrub_browser_payload` and `api_payloads.scrub_config is scrub.scrub_config`. This guards frozen `mcp/tools.py:10`.
6. `test_scrub_owner_module`: `scrub.scrub_browser_payload.__module__ == "skillgate_ai.scrub"`.
7. `test_domain_scrub_paths_do_not_load_api_payloads`: run a subprocess (`-I`) that imports `skillgate_ai.gate`, `skillgate_ai.history` and `skillgate_ai.compare.payload` and calls `history._scrub_history_row({"report": {"judge": {"model": "x"}}})` and `compare.payload.scrub_customer_compare_payload({"arms": []})`. Assert `"skillgate_ai.api_payloads" not in sys.modules`.
8. `test_mcp_tools_still_imports_scrub`: `pytest.importorskip("mcp")`; `import skillgate_ai.mcp.tools` succeeds, and `skillgate_ai.mcp.tools.scrub_browser_payload is skillgate_ai.scrub.scrub_browser_payload`.

**`tests/test_import_layering.py`**

9. `test_importlinter_contract_names`: load `pyproject.toml` with `tomllib`. `{c["name"] for c in data["tool"]["importlinter"]["contracts"]}` equals the 4 names in L3 exactly, and `root_package == "skillgate_ai"`.
10. `test_fs_core_contract_lists_every_fs_module`: contract 1's `source_modules` ⊇ the 9 FS modules listed in L3, and `forbidden_modules` includes `skillgate_ai.deploy`, `skillgate_ai.history` and `skillgate_ai.mcp`.
11. `test_lint_imports_passes`: `pytest.importorskip("importlinter")`; run `subprocess.run(["lint-imports", "--no-cache"], cwd=ROOT)`; returncode 0, and the output contains `"0 broken"` (or the `KEPT` count equals 4).
12. `test_gate_workflow_runs_lint_imports`: `.github/workflows/gate.yml` text contains `run: lint-imports`, and `.pre-commit-config.yaml` contains `entry: lint-imports`.

**`tests/test_deploy_gate.py`** (append)

13. `test_run_gate_summary_matches_typed_dict`: for a running record and an official error row (reuse the fixtures from the existing four tests), `list(run_gate_summary(row)) == ["kind", "moves_gate", "decision", "reason", "tryout_reason"] == list(GateSummary.__annotations__)`.

**`tests/test_gate.py`** (append)

14. `test_result_payload_key_order`: a minimal `CheckResult(run_id="r", exit_code=1, report=None, …)` with the other required fields at their defaults or `None`. `list(result_payload(res)) == ["run_id", "exit_code", "demo_notice", "expect_fail_notice", "error", "report"] == list(CheckResultPayload.__annotations__)`, `res_payload["report"] is None`, and `json.loads(json.dumps(res_payload)) == res_payload`.

**`tests/test_audit_ratchets.py`** (append)

15. `test_mcp_dict_any_lines_frozen`: the count of lines containing `dict[str, Any]` under `src/skillgate_ai/mcp` `== 46`.
16. `test_typed_dict_floor`: the count of `class \w+\(TypedDict` under `src/skillgate_ai` is `>= 29`.
17. `test_mypy_strict_overrides_cover_fs_core`: parse `pyproject.toml`. The first override whose module list contains `skillgate_ai.paths` must be ⊇ the 12 modules in Scope M and must have `disallow_untyped_defs is True`.

That is 17 new or appended tests, plus 1 edited ratchet and 3 edited patch strings.

---

## Step order (one commit each; `ruff check && ruff format --check && mypy src && pytest -q -m "not integration"` before every commit)

1. **Baseline + classification.** Rerun every Baseline command. Produce:
   - the T1–T5 line-level table (each in-scope line classified as param-readonly / literal-return / protocol-fed / mutated)
   - the list of private scrub names that tests import from `api_payloads`
   - the `run_gate_summary` / `result_payload` caller list

   Paste all of it into the PR body. No code.
2. **L1 `agent_roots.py`.** Write tests 1–4 first (test 4 fails red: `deploy` is loaded). Move the code, switch `fs_anchor`, `trusted_roots` and `catalog`, re-export from `deploy`, and repoint the 3 `test_trusted_roots.py` patch strings. Run `pytest tests/test_trusted_roots.py tests/test_agent_roots.py tests/test_catalog.py tests/test_deploy*.py -q`.
3. **L2 `scrub.py`.** Write tests 5–8 first (5–7 fail red). Move the helpers, re-export from `api_payloads`, and switch `gate`, `history` and `compare/payload`. Run `pytest tests/test_api_payloads_scrub.py tests/test_api_local.py tests/test_wire_shapes.py tests/test_history*.py tests/test_scrub_module.py -q` plus the `python -c "import skillgate_ai.mcp.server"` smoke with the `mcp` extra.
4. **L3 import-linter.** Add the dependency, run `uv lock`, add the 4 contracts, the CI step, the pre-commit hook and the `.gitignore` entry. Run `lint-imports`. It must pass now that steps 2–3 have landed. Any unexpected violation is fixed in this commit or escalated in the PR body (never ignored). Add tests 9–12. Run the pip-audit export + audit locally.
5. **M mypy.** Extend the override list and fix errors in the listed modules only. Add test 17.
6. **T1 + T2.** Add `GateSummary` and `CheckResultPayload`, plus tests 13–14. Run `pytest tests/test_deploy_gate.py tests/test_gate.py tests/test_wire_shapes.py -q`.
7. **T3.** `run_progress.py`, `report/lines.py`.
8. **T4.** `engine/models.py`, `verdict.py`, `task.py`. Apply the revert rule and log reverts.
9. **T5.** `history.py`, `run_status.py`, `run_registry.py`.
10. **R ratchets.** Tighten `test_dict_any_line_budget` to the measured value (≤ 492) and add tests 15–16.
11. **Scorecard.** Update `docs/audit-scorecard.md`: the new dict count, the TypedDict count, the strict-module list, an "import-linter: 4 contracts, KEPT" row, and the open items (CodeQL triage, the `mcp/` typing PR G, the FS-cycle `layers` contract, coverage headroom).
12. **Full gate.** Run `pytest -q -m "not integration" --cov=skillgate_ai --cov-report=term`, `ruff check`, `ruff format --check`, `mypy src`, `lint-imports`, `skillgate check skills/pdf` and `skillgate check skills/pdf-sabotaged --expect-fail`. Push, then open the PR (body ends with the attribution line).

---

## Acceptance criteria

| # | Check | Target |
|---|---|---|
| 1 | `grep -rn 'dict\[str, Any\]' src/skillgate_ai \| wc -l` | **≤ 492** (planned 487) |
| 2 | `grep -rn 'dict\[str, Any\]' src/skillgate_ai/mcp \| wc -l` | **== 46** |
| 3 | Per-file budgets in the Baseline table | each met or reverted under PR D rule 6 and listed under "Kept" |
| 4 | `grep -rnE 'class \w+\(TypedDict' src/skillgate_ai \| wc -l` | **≥ 29** |
| 5 | `lint-imports` | 4 contracts, **0 broken**, no `ignore_imports` entries |
| 6 | mypy strict override module list | **≥ 12 modules** (Scope M); `mypy src` clean |
| 7 | `grep -rn 'skillgate_ai.deploy import' src/skillgate_ai/{fs_anchor,trusted_roots,catalog}.py` | **0** |
| 8 | `grep -rn 'api_payloads' src/skillgate_ai/{gate,history}.py src/skillgate_ai/compare/payload.py` | **0** |
| 9 | `pytest -q -m "not integration"` | 0 failures; passed count **≥ 2138 + 17** |
| 10 | Coverage | **≥ 84.0%**, `fail_under` unchanged; record the measured value |
| 11 | `git diff main -- tests/test_wire_shapes.py plugin src/skillgate_ai/mcp src/skillgate_ai/judge_settings.py` | empty |
| 12 | New `# noqa` / `# type: ignore` / `cast(` in the diff | **0** added |
| 13 | Modules > 600 lines | 0 (existing ratchet) |
| 14 | CI `gate` workflow | lint (ruff, format, mypy, **import-linter**), tests matrix, pip-audit, CodeQL, all-gates green |
| 15 | `uv.lock` | updated in the same commit as the dependency; `uv sync --locked` passes |

---

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Patch seam break: tests or users patch `deploy.cursor_skills_root` and expect `trusted_roots` to see it | Medium | Grep shows only 3 test sites, repointed in step 2. `trusted_roots` and `fs_anchor` keep in-function imports so `agent_roots.*` patches apply. Test 3 guards the re-export. |
| Contract 2 surfaces more direct violations than the three known ones | Low–Medium | Step 4 runs `lint-imports` before declaring done. The fix pattern is "move the helper down". `ignore_imports` is never used. |
| `allow_indirect_imports = true` hides real transitive leaks | Accepted for B | Recorded as Option C work. Contract 1 (FS core) stays strict-indirect. |
| TypedDict invariance errors cascade (TypedDict passed to a `dict[str, Any]` param) | Medium | Rules 7–8. Only literal-built returns get TypedDicts. The revert rule caps the scope. Hard target leaves 5 lines of slack. |
| Scrub move changes output | Low | Verbatim move. `test_wire_shapes`, `test_api_payloads_scrub` and `test_api_local` stay unedited and green. |
| `import-linter` / `grimp` fails pip-audit or lacks wheels for 3.11–3.13 | Low | Run the audit locally in step 4. If it is blocked, pin to the latest clean release and record why. |
| Strict mypy on `fs_anchor` / `contained_fs` forces non-trivial edits to PR E containment code | Low–Medium | Annotation-only changes. Any logic change is out of scope: drop that module from the list and record it. The floor stays 12 only if `scrub` substitutes; otherwise lower the floor to the count achieved and record why. |
| Coverage dips below 84.0 (no headroom today) | Low | Moved code keeps its tests, and the 17 new tests add coverage. If it is still short, add tests (never lower the floor). |
| Import cycle `scrub` ↔ `judge_copy` | Low | `judge_copy` import stays lazy inside `_neutral_scored_by`. Contract 2 includes `scrub` as a source. |

---

## Out of scope (documented in the scorecard)

- CodeQL alert triage (49 open at re-audit; merge gate added in PR E), which is admin work.
- Typing for `mcp/**` (PR G).
- A `layers` contract for the FS cycle, and indirect-mode contract 2 (Option C / PR H).
- `judge_context.py`, `judge_openai/outcome.py` and `api_payloads.py` non-scrub typing (Option C).
- Branch coverage and `fail_under ≥ 84.5`.
- `judge_settings.py` bare asserts.
- Plugin, Flutter, packaging and the web UI.

---

## User-visible behavior

**None intended.** CLI output and exit codes, report/progress JSON, deploy-gate summaries, history JSONL on disk, HTTP responses and MCP tool results are all byte-for-byte unchanged. Env overrides `SKILLGATE_{CURSOR,CODEX,CLAUDE}_SKILLS` behave identically. The only observable difference is internal: importing FS-core or domain modules no longer loads `skillgate_ai.deploy` or `skillgate_ai.api_payloads` as a side effect.
