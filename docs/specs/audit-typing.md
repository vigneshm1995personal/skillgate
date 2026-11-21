# SPEC — Typing remediation (PR 2/4): remove the blanket `ignore_errors` override

**Repo:** skillgate (OSS) · **Package:** `skillgate-ai` · **Base:** `main` @ `6c4a64c` ("fix: audit security and retries (PR 1/4) (#75)") · **Branch:** `cursor/audit-typing-e1e3`

## 1. Audit context

- `pyproject.toml` lines 145–169 hold one `[[tool.mypy.overrides]]` block with `ignore_errors = true`. It lists **20** module patterns. The brief said 21, but there are 20 entries in the file and 20 in the brief's own list. Use 20 everywhere.
- If you remove that block and keep the current global config (`check_untyped_defs = false`, `ignore_missing_imports = true`), `mypy src` reports **82 errors in 25 files** (131 source files checked). The log also shows one `unused-ignore`, so the audit run had `--warn-unused-ignores` on.
- PR 1/4 (#75) already landed the security and retry fixes. This PR only fixes typing.
- Goal: after this PR, `mypy src` passes with **no** `ignore_errors` overrides.

## 2. Override patterns → error count with overrides removed

| # | Override pattern | Files with errors | Errors |
|---|---|---|---|
| 1 | `skillgate_ai.advice` | `advice.py` | 3 |
| 2 | `skillgate_ai.api` | `api.py` | 1 |
| 3 | `skillgate_ai.api_compare` | none | **0** |
| 4 | `skillgate_ai.api_runs` | `api_runs.py` | 11 |
| 5 | `skillgate_ai.case_import` | `case_import.py` | 2 |
| 6 | `skillgate_ai.case_pack.*` | `case_pack/pins.py` (3), `case_pack/suites.py` (2) | 5 |
| 7 | `skillgate_ai.catalog` | `catalog.py` | 1 |
| 8 | `skillgate_ai.cli.*` | `cli/pack_skill.py` (3), `cli/pack_history.py` (7), `cli/cmd_deploy.py` (1) | 11 |
| 9 | `skillgate_ai.compare.*` | `compare/payload.py` | 5 |
| 10 | `skillgate_ai.harness.*` | `harness/resolve.py` (6), `harness/login.py` (3), `harness/selection.py` (1), `harness/prompts.py` (1) | 11 |
| 11 | `skillgate_ai.helper` | `helper.py` | 1 |
| 12 | `skillgate_ai.judge` | `judge.py` | 3 |
| 13 | `skillgate_ai.judge_context` | `judge_context.py` | 2 |
| 14 | `skillgate_ai.judge_openai.*` | `judge_openai/outcome.py` | 8 |
| 15 | `skillgate_ai.judge_spec` | `judge_spec.py` | 3 |
| 16 | `skillgate_ai.local_ui.api` | `local_ui/api.py` | 1 |
| 17 | `skillgate_ai.local_ui.server` | `local_ui/server.py` | 4 |
| 18 | `skillgate_ai.report` | `report.py` | 6 |
| 19 | `skillgate_ai.span_facts` | `span_facts.py` | 1 |
| 20 | `skillgate_ai.usage` | `usage.py` | 3 |
| | **Total** | **25 files** | **82** |

Two of these errors have their root cause in a module that is **not** overridden: `deploy.py` (the `DeployAdapter` Protocol). The errors surface in `helper.py` and `cli/cmd_deploy.py`.

## 3. Shared fix patterns

These are the only allowed kinds of change. Each one leaves runtime behavior the same.

- **P-A: hoist and narrow.** Mypy cannot narrow the result of a call such as `x.get("k")` with `isinstance`. Rewrite this:
  ```python
  v = d.get("k") if isinstance(d.get("k"), dict) else {}
  ```
  as this:
  ```python
  raw_v = d.get("k")
  v: dict[str, Any] = raw_v if isinstance(raw_v, dict) else {}
  ```
  The same goes for `list`, `str` and `Mapping`. On a plain `dict` or `Mapping`, calling `.get` once instead of twice gives the same result. This pattern covers about half of the errors.
- **P-B: honest annotation.** Add or widen an annotation on a local, a return type or a class attribute.
- **P-C: local rename.** Use this only when mypy pins a variable's type from its first assignment and a later, unrelated assignment reuses the name (`no-redef` or `assignment`). Rename the later binding inside the same scope. Nothing else changes.
- **P-D: `cast`.** Use this only when a runtime invariant guarantees the type and mypy cannot see it, such as an earlier guard or a pydantic `mode="before"` validator. Every `cast` gets a one-line `#` comment that states the invariant.
- **P-E: `@overload`.** Use this only to make an existing signature precise. It has no runtime effect.
- **`# type: ignore`.** Use it as a last resort. Format: `# type: ignore[<code>]  # <reason>`. None of the fixes below should need a new one.

## 4. Per-module fix approach (every file in the error log)

### 4.1 Protocol and shared-type roots (do first)

**`deploy.py`** (not overridden; fixes `helper.py:320` and `cli/cmd_deploy.py:52`)
- `DeployAdapter.install` (line 37) is declared as `(*, skill, source)`, but `_PackAdapter.install` (line 71) also accepts `force: bool = False, remote_gated: bool = False`, and callers pass both.
- Fix (P-B): widen the Protocol signature to `install(self, *, skill: Skill, source: Path, force: bool = False, remote_gated: bool = False) -> DeployResult`.
- Do not change `_PackAdapter`.

**`harness/agents.py`** (fixes all 6 `harness/resolve.py` errors)
- `Harness` (`harness/base.py:82`) declares `supported_models: tuple[str, ...]`. Mypy infers each implementation's class attribute as a fixed-length tuple, and a mutable Protocol attribute is invariant.
- Fix (P-B): annotate the three class attributes as `supported_models: tuple[str, ...] = (...)`. They are at lines 65 (`CursorAgentHarness`), 128 (`CodexCliHarness`) and 217 (`ClaudeCodeHarness`).
- Leave `harness/base.py` unchanged.

**`case_pack/models.py`** (reference only; do not edit)
- `CasePack.schema_version` has `Field(alias="schema")`. Pydantic's `dataclass_transform` exposes the **alias** as the `__init__` keyword.
- The repo already builds `CasePack(schema=1, ...)` in `scaffold.py:58` and `scaffold.py:110`. See `case_pack/*` below.

### 4.2 Leaf utilities

**`usage.py`** (156–158, `arg-type` ×3)
- `_pick(current: float | None, update: float | None) -> float | None` (line 390) widens `int` to `float`.
- Fix (P-B): make it generic with a constrained TypeVar, `_Num = TypeVar("_Num", int, float)`, and `def _pick(current: _Num | None, update: _Num | None) -> _Num | None`. Use `TypeVar`, not PEP 695 syntax, because the project targets 3.11.
- `max()` behavior is unchanged.

**`judge_spec.py`** (179, 377, 526)
- Line 179: `float(layer.get("min_confidence"))` sits under the guard `"min_confidence" in layer and ... is not None`. Change it to `float(layer["min_confidence"])`. The key is guaranteed present, and `TypeError`/`ValueError` handling is unchanged.
- Line 526: `float(pass_if.get("gte"))` sits under the guard `"gte" in pass_if`. Change it to `float(pass_if["gte"])`, for the same reason.
- Line 377: `_gte(..., default=0.8)` is typed as returning `float | None`. Fix (P-E): add overloads to `_gte` (line 522):
  - `default: float` → `float`
  - `default: None` → `float | None`
- The second caller, line 387 with `default=None`, keeps `float | None`.

**`span_facts.py`** (514, `union-attr`)
- At line 513, `err = resp.get("error") if isinstance(resp.get("error"), Mapping) else {}`.
- Fix (P-A): `raw_err = resp.get("error")`, then `err: Mapping[str, Any] = raw_err if isinstance(raw_err, Mapping) else {}`.

**`advice.py`** (205, 211, 527)
- Lines 194–195 (`cells`, `questions`). Fix (P-A): hoist `judge.get(...)` and annotate as `dict[str, Any]`.
- Line 527: change `bits = []` to `bits: list[str] = []`.

**`catalog.py`** (257, `dict-item`)
- `loaded.warning` is `str | None`. Fix (P-B): widen line 211 to `imported: list[dict[str, str | None]] = []`.

**`case_import.py`** (367, 386)
- Line 366: apply P-A. `raw_files = raw.get("files")`, then `file_items: list[Any] = raw_files if isinstance(raw_files, list) else []`.
- Line 386: `contains if isinstance(contains, list) else contains` returns the same value on both branches, and `PackCase._contains_list` (a `mode="before"` validator, `models.py:108`) normalizes `str` or `None`.
- Fix (P-D): `contains=cast("list[str]", contains)  # _contains_list before-validator normalizes str/None`.

### 4.3 Judge layer

**`judge_context.py`** (196, `assignment` + `arg-type`)
- `row` is first bound at line 183 as `dict[str, str | None]`. Line 196 rebinds it from `pending: dict[str, dict[str, Any]]`.
- Fix:
  - P-B: annotate line 183 as `row: dict[str, Any] = {...}`.
  - P-C: rename the `tool_result` binding at lines 196–198 to `matched`, i.e. `matched = pending.pop(call_id, None) if call_id else None`, then `if matched is not None: matched["output"] = ...`.

**`judge.py`** (322, 333, 343, `dict-item`)
- `judge_stamp()` is declared `-> dict[str, str]` but sets `"chosen": bool`.
- Fix (P-B): change the return type to `dict[str, Any]`.
- Do **not** widen it to `dict[str, str | bool]`. That would cascade into `eval_config.with_judge(stamp: dict[str, str] | None)` (line 258) and `EvalRunConfig.judge`, which are outside this PR's error set. Record a TypedDict for the stamp as a follow-up.

**`judge_openai/outcome.py`** (210, 393, 404–406; 8 errors)
- Line 210. Fix (P-A): `raw_answers = evaluated.get("answers")`, then `answers: dict[str, Any] = dict(raw_answers) if isinstance(raw_answers, dict) else {}`.
- Line 391. Fix (P-A): `raw_answers = evaluated.get("answers")`, then `answers: dict[str, Any] = raw_answers if isinstance(raw_answers, dict) else {}`.
- With `answers` typed at 391, the errors at 393, 404, 405 and 406 clear.
- The function and variable names stay the same.

### 4.4 Report and compare

**`report.py`** (560, 562, 570, 612, 617, 621)
- Line 551 (`answers_map`). Fix (P-A): annotate as `dict[str, Any]`. This clears 560 and 562.
- Line 570. Change `rows: list[dict[str, str]] = []` to `rows = []`. The type is already declared at line 552 in the same function. This fixes `no-redef`.
- Lines 609–610 (`cells`, `answers`). Fix (P-A): annotate both as `dict[str, Any]`. This clears 612, 617 and 621.

**`compare/payload.py`** (22–26, 178)
- Line 21 (`usage`) and line 177 (`cfg`). Fix (P-A): annotate both as `dict[str, Any]`.

**`case_pack/pins.py`** (67, 104, 296) and **`case_pack/suites.py`** (261, 316)
- `CasePack(schema_version=1, ...)` → `CasePack(schema=1, ...)` at all four sites (pins 67 and 104, suites 261 and 316).
- This is safe at runtime: `populate_by_name=True` accepts both keywords, and `scaffold.py` already uses `schema=`.
- Do **not** enable the `pydantic.mypy` plugin. It would change the error surface repo-wide.
- `pins.py:295`. Fix (P-B): `kind: Literal["json", "text"] = "json" if suffix == ".json" else "text"`. Import `Literal` if it is not already imported.

### 4.5 Harness

**`harness/resolve.py`** (30, 32, 34, 69, 71, 73)
- No edits here. All six errors clear once §4.1 annotates `harness/agents.py`.

**`harness/login.py`** (60, 68, 71, `arg-type`)
- At line 53, `subprocess.Popen(argv, start_new_session=True)` is `Popen[bytes]`.
- Fix (P-B): change line 19 to `_terminate_process_group(proc: subprocess.Popen[Any]) -> None`. It only calls `poll`, `pid` and `wait`, so it does not depend on the stream type.

**`harness/selection.py`** (122, `arg-type`)
- Fix (P-A) at line 121: `raw_args = item.get("args")`, then `args: dict[str, Any] = raw_args if isinstance(raw_args, dict) else {}`.
- Use a distinct name, or annotate at first use, so the earlier `args` bindings at lines 107 and 111 don't conflict. If they do conflict, rename this binding `skill_args` (P-C).

**`harness/prompts.py`** (138, `unused-ignore`)
- `selection._read_selection` (`selection.py:25`) has no return annotation, so `pinned` is `Any` and the ignore suppresses nothing.
- Fix: delete `# type: ignore[arg-type]` on line 138.
- Do not annotate `_read_selection` in this PR. Its return type mixes a sentinel `object` and would need a `Literal` or enum sentinel, which is a refactor. Record it as a follow-up.

### 4.6 HTTP / UI / API surfaces

**`api_runs.py`** (76–79, 97, 113–116, 125, 154; 11 errors)
- Line 55 (`config`). Fix (P-A): `raw_config = body.get("config")`, then `config: dict[str, Any] = raw_config if isinstance(raw_config, dict) else {}`. This clears 9 errors.
- Line 125 (`harness` was already `str` from line 99). Fix (P-C): rename to `final_harness = (report or {}).get("harness") or record.get("harness")` and use it in the `record.update` at line 136.
- Line 154 (`exit_code`). Fix (P-B): declare `exit_code: int | None` before the `if blocked is not None:` branch at line 147.

**`local_ui/api.py`** (233, `list-item`)
- Change `raw = (qs.get("path") or [None])[0]` to:
  ```python
  paths = qs.get("path")
  raw = paths[0] if paths else None
  ```
- The result is identical for a missing key, an empty list and a non-empty list. `pack_payload` already accepts `str | None` (line 178).

**`local_ui/server.py`** (44, 117, 143, 158)
- Line 44. Fix (P-D): `port = cast("tuple[str, int]", self.server.server_address)[1]`, with comment `# TCP HTTPServer: (host, port)`. The f-string output is unchanged.
- Lines 142 and 157. Fix (P-D): `bound_host, bound_port = cast("tuple[str, int]", server.server_address[:2])`, with comment `# AF_INET bind → (str, int)`. This clears `str-bytes-safe` at 143 and 158.
- Line 117: `data` was pinned to `bytes` by the static-file branches at lines 99 and 108. Fix (P-C): rename the `handle(...)` result to `status, payload_data, ctype` and update lines 120–125.
- The `payload` local at line 114 already exists, so don't reuse that name.

**`api.py`** (259, `arg-type`)
- `key_env` is inferred as `dict[str, Any | None]`, and `**`-spreading it is checked against every keyword, including `_persist_decisions_path: bool`.
- Fix (P-B): change line 249 to `key_env: dict[str, Any] = {"key_env": body.get("key_env")} if "key_env" in body else {}`.

### 4.7 CLI

**`cli/pack_skill.py`** (56, 57, 108)
- Line 55. Fix (P-D): `path = cast(Path, zip_path or markdown)`, with comment `# guarded: one of --zip/--md is set`. Do not use `assert`, because `-O` strips it.
- Line 106. Fix (P-B): annotate `data: str | bytes` on the first assignment.
- Check that `pack.write_pack_file(content=...)` (`pack.py:182`) accepts `str | bytes`. It must already, because both reach it at runtime. If it is narrower, widen **that annotation only**.

**`cli/pack_history.py`** (33, 158, 166, 170, 171, 182, 183; 7 errors)
- Line 33 (`who` was already `str` from line 31). Fix (P-A): `scored_by = report.get("scored_by")`, then `who = scored_by if isinstance(scored_by, str) else ""`.
- Line 154 (`report`). Fix (P-A): annotate as `dict[str, Any]`. This clears 158, 166, 170 and 171.
- Line 182 (`tasks`). Fix (P-A): annotate as `list[Any]`. This clears 182 and 183.
- If line 20 has the same shape, apply P-A there too for consistency. It's optional, because line 20 isn't flagged.

**`cli/cmd_deploy.py`** (52, `call-arg`)
- No edits here. It clears once §4.1 widens the `DeployAdapter.install` Protocol.

## 5. Step order

Run `mypy src` after each step. The error count should only go down.

1. **Protocols and shared types:** `deploy.py` (`DeployAdapter.install`) and `harness/agents.py` (`supported_models`). Expected −8 (helper 1, cmd_deploy 1, resolve 6).
2. **Leaf utilities:** `usage.py`, `judge_spec.py`, `span_facts.py`.
3. **Pack models consumers:** `case_pack/pins.py`, `case_pack/suites.py`, `case_import.py`, `catalog.py`.
4. **Judge layer:** `judge.py`, `judge_context.py`, `judge_openai/outcome.py`, `advice.py`.
5. **Report and compare:** `report.py`, `compare/payload.py`.
6. **Harness leftovers:** `harness/login.py`, `harness/selection.py`, `harness/prompts.py` (delete the unused ignore).
7. **Surfaces:** `api.py`, `api_runs.py`, `local_ui/api.py`, `local_ui/server.py`, `cli/pack_skill.py`, `cli/pack_history.py`.
8. **Config:**
   - Delete the whole `[[tool.mypy.overrides]]` block (`pyproject.toml` lines 145–169), including its header comment.
   - Set `warn_unused_ignores = true`. The audit run shows the only unused ignore is the one removed in step 6.
   - Leave `check_untyped_defs = false` alone. Flipping it is out of scope (see §7).
9. **Existing ignores:** add reasons per §6.
10. **Full local gate:** `ruff check`, `ruff format --check`, `mypy src`, `pytest -q`, `skillgate check skills/pdf`, `skillgate check skills/pdf-sabotaged --expect-fail`.

Order to land commits: one commit per step. Each commit must pass `pytest -q`. Steps 1–7 pass under the existing override, so they can land in any order. Step 8 makes the result visible to mypy.

## 6. Acceptance criteria

- [ ] `pyproject.toml` has **zero** `ignore_errors = true` overrides. If anything must stay, it needs a justified short list (one module per line, a reason, and a linked follow-up issue). **Target: none.**
- [ ] `mypy src` exits 0 with the repo config (overrides removed, `warn_unused_ignores = true`).
- [ ] Every `# type: ignore` in `src/` has an error code **and** a trailing `# <reason>`. Verify with `grep -rn "type: *ignore" src`.
- [ ] No new `# type: ignore`. Each `cast(...)` has an invariant comment.
- [ ] `ruff check`, `ruff format --check`, `pytest -q` and both seed-pack gate commands are green.
- [ ] The diff only changes annotations, P-A hoists, P-C local renames, P-D casts, P-E overloads, the alias keyword `schema=` at the 4 `CasePack(...)` sites, and the `local_ui/api.py:233` index expression. No test changes should be needed. If a test needs changing, behavior changed — stop.

### Existing `# type: ignore` comments (all have codes; most lack reasons)

| Location | Current | Action |
|---|---|---|
| `run_lock.py:14` | `[assignment]  # Windows has no fcntl` | OK, keep |
| `checks_show.py:12` | `[assignment,misc]  # core checks show needs no web stack` | OK, keep |
| `harness/prompts.py:138` | `[arg-type]`, **unused** | **Delete** (§4.5) |
| `api_evals.py:129`, `:136` | `[arg-type]` | Add reason: `# conflict validated against ON_CONFLICT values above; str → Literal` (confirm the exact guard) |
| `cli/pack_case.py:125` | `[arg-type]` | Same reason as `api_evals` (Typer passes a `str`; values constrained) |
| `pack_edit.py:207`, `:209` | `[arg-type]` | Add reason: `# parse_extra_question validated type/on_fail; str → Literal` |
| `openai_http.py:206` | `[return-value]` | Add reason: `# RetryableStatus.response is the last HTTP response object`. Behavior is security/retry-adjacent: **comment only, no code change** |
| `engine/verdict.py:249` | `[return-value]` | Add reason: `# tri-state verdict: None = unscored; signature declares bool` |

Replacing these ignores with `Literal` narrowing is **out of scope**. Add reasons only.

## 7. DO NOT TOUCH

- **Behavior:**
  - No change to control flow, defaults, return values, exception types or messages.
  - No `assert` used for narrowing.
  - No `str(...)` or `int(...)` coercions added to satisfy mypy. For example, `harness` at `api_runs.py:125` must stay possibly-`None`.
- **Security and retries (PR 1/4 surface):** `http_retry.py`, `openai_http.py` (comment-only per §6), `local_guard.py`, `sandbox.py`, `run_lock.py`, the `_terminate_process_group` body, and anything under `judge_providers/` beyond annotations.
- **No refactors:**
  - No splitting or moving files, extracting helpers, renaming public functions, adding TypedDicts or Pydantic models, or adding sentinel enums.
  - Those are follow-ups, including `_read_selection`, the judge-stamp TypedDict and request validation models.
- **`harness/base.py` `Harness` Protocol:** leave as is. Fix the implementations instead.
- **`case_pack/models.py`:** no field or alias changes.
- **Dependencies and tooling:** no edits to `[project.dependencies]` or extras, no lockfile changes, no `.github/workflows/*` or `pre-commit` config changes, no mypy plugins, and no `check_untyped_defs = true`. The only allowed `pyproject.toml` edits are deleting the override block and setting `warn_unused_ignores = true`.
- **Tests:** don't edit `tests/`. That includes `test_judge_spec.py` and `test_harness_agents.py`, which use `CasePack(schema_version=...)`; they work at runtime and are not mypy-checked.
- **Out of scope:** `src/skillgate_ai/examples/` stays excluded.

## 8. Follow-ups (not this PR)

- Annotate `harness/selection._read_selection` with a typed sentinel, then confirm `harness/prompts.py:138` needs no ignore.
- Add a `JudgeStamp` TypedDict and thread it through `eval_config.with_judge` and `EvalRunConfig.judge`.
- Replace the `str → Literal` ignores in `api_evals`, `pack_case` and `pack_edit` with validated `Literal` narrowing.
- Evaluate `check_untyped_defs = true` and the `pydantic.mypy` plugin in a separate PR, with a fresh error count.
