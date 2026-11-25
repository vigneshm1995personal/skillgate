# Audit PR D (4/4 toward 9/10): narrow the broad excepts, cut `dict[str, Any]`, split the last >600-line modules, raise coverage to ~85%

Save as: `docs/specs/audit-pr-d.md`
Branch: `cursor/audit-pr-d` (already created from `main` @ `cc8919a`). One PR, one commit per step in "Step order".

This PR has five scopes:

- **A.** Replace broad `except Exception` handlers with specific exception types. A handler stays broad only if it is a real boundary, and then it carries a written justification.
- **B.** Replace `dict[str, Any]` with TypedDicts, `Mapping[str, Any]` or `Sequence[Mapping[str, Any]]` in the four priority files first, then in a fixed list of secondary files.
- **C.** Split `tool_checks.py` (715 lines), `advice.py` (614) and `usage.py` (610) into packages. Re-export shims keep every existing import path working.
- **D.** Raise unit-test coverage from 77.39% to about 85% with meaningful tests, then raise `fail_under` to match.
- **E.** Fix the per-file `dict[str, Any]` cap violation in `judge_openai/outcome.py` (12 lines → ≤ 11).

Nothing a user can see changes: no JSON, CLI, HTTP or MCP shape, no message text, no exit code. The only intended runtime difference is in Scope A. Five handlers become narrower, so a programming error (`RuntimeError`, `KeyError`, …) that used to be wrapped or swallowed at those sites now propagates. No real input reaches those paths today. Tests pin the new behavior.

---

## DO-NOT-TOUCH

- **MCP server:** `src/skillgate_ai/mcp/**` gets no edits. Its imports from `skillgate_ai.*` must keep resolving through the shims. Its 46 `dict[str, Any]` lines stay and are excluded from the Scope B plan.
- **Cursor/Claude plugin:** `plugin/**` gets no edits.
- **Public CLI surface:** `TOP_COMMANDS`, `SUB_COMMANDS`, `CLI_SURFACE_SHA256` and `test_entry_points_unchanged` in `tests/test_public_imports.py` stay byte-identical. No command, option, default or help string changes.
- **Public imports:**
  - Every existing `REGISTRY` and `PASS_THROUGH` entry, and the import path behind it, stays unchanged.
  - New entries may only be **added**, for the three new shims (step C4).
  - `JUDGE_OPENAI_ALL` stays unchanged.
- **`tests/test_wire_shapes.py`:** no edits. Its golden bytes must stay byte-identical.
- **Wire shapes:** JSON, CLI, HTTP and MCP wire shapes stay the same, including dict key order. FastAPI route return annotations are part of the wire contract (Scope B, rule 1).
- **`src/skillgate_ai/judge_settings.py`:** no edits. Its S101 bare asserts belong to a separate PR.
- **Lint config:** no new `# noqa`, `# type: ignore` or `cast()`. No relaxation of `[tool.ruff]`, `[tool.ruff.lint]`, `per-file-ignores` or `[tool.mypy]`.
  - Existing `# noqa: BLE001 …` comments on handlers that stay broad are kept.
  - `noqa` comments are only ever **removed**, from handlers that get narrowed.
- **Versions:** no version bump. `MARKETING_VERSION` does not apply, and `pyproject` `version` is not touched.
- **Secrets:** never print, read into tests, or commit `.skillgate/keys`, `~/.skillgate` or any API key. Tests use `tmp_path` and `monkeypatch.setenv("HOME", …)` wherever key paths could be touched.
- **Do not commit:** `.coverage`, `coverage.xml`, `.spec-prompt-audit-pr-d.txt`, `.spec-prompt-audit-typing-lint.txt`, `docs/specs/_audit-structure-coverage-prompt.md`, `scripts/_audit_split_helper.py` or `.venv-mcp-smoke/`.
- **Behavior:** user-facing messages, exit codes, lazy-import timing (in-function imports stay in-function) and the dependency direction between modules all stay as they are.
- **Known flaky tests:** do not touch `test_compare_models_cancel_stops_next_arm` or `test_run_inherited_keyboard_interrupt_kills_group`, or the determinism fixes earlier PRs made for them. If one fails, rerun it once and record the result in the PR body. Do not change it.

---

## Baseline (measured on `main` @ `cc8919a`)

| Metric | Command | Baseline |
|---|---|---|
| Broad excepts | `grep -rnE 'except Exception\b' src/skillgate_ai \| wc -l` | **23** in 16 files |
| `dict[str, Any]` **lines**, all of src | `grep -rn 'dict\[str, Any\]' src/skillgate_ai \| wc -l` | **583** |
| …of which under `mcp/` (frozen) | `grep -rn 'dict\[str, Any\]' src/skillgate_ai/mcp \| wc -l` | 46 |
| Per file: `judge_openai/outcome.py` / `fixture_bind.py` / `api_skills.py` / `compare/payload.py` | `grep -c 'dict\[str, Any\]' <file>` | 12 / 7 / 17 / 10 |
| `Mapping[str, Any]` lines | `grep -rn 'Mapping\[str, Any\]' src/skillgate_ai \| wc -l` | record in step 1 |
| `TypedDict` classes | `grep -rnE 'class \w+\(TypedDict' src/skillgate_ai \| wc -l` | record in step 1 |
| Modules over 600 lines | `wc -l src/skillgate_ai/*.py src/skillgate_ai/*/*.py \| sort -n -r \| sed -n 2,6p` | `tool_checks.py` 715, `advice.py` 614, `usage.py` 610 (next largest: `engine/task.py` 559) |
| Unit coverage | `pytest -q -m "not integration" --cov=skillgate_ai --cov-report=term-missing` | 77.39% (`fail_under = 77`, `precision = 2`) |
| Per-module coverage | same command | record the 25 lowest-covered modules in step 1 |
| Unit tests | `pytest -q -m "not integration"` | record in step 1 |

**Measurement rules.**

- The `dict[str, Any]` metric counts **lines**, not occurrences. `deploy_gate.py:11` has two occurrences on one line and counts as 1.
- Use exactly the commands above for both the before and after numbers.
- The PR C scorecard reported 480 `dict[str, Any]` lines "after". The command above gives 583 on `cc8919a`. Step 1 re-measures with both `grep` and `rg -c` (summed), records both, and treats the `grep` number as canonical. The PR D scorecard row replaces the stale PR C figure.

---

## Scope E: `judge_openai/outcome.py` `dict[str, Any]` lines (12 → 6; cap is ≤ 11)

Scope E is one commit on its own and lands before the rest of Scope B. All line numbers are from `cc8919a`.

**New TypedDict** in `outcome.py`, placed directly after `JudgeUsageSum` (line 54–58). It is not exported from the `judge_openai` shim.

```python
class JudgePayload(TypedDict):
    status: str
    provider: str
    backend: str
    display_name: str
    chosen: bool
    score_no_trigger: bool
    extra_failures: list[str]
    model: str
    passed: bool
    reasons: list[str]
    why: str | None
    answers: Any
    soft_answers: Mapping[str, Any]
    questions: Mapping[str, Any]
    soft_questions: Mapping[str, Any]
    cells: Mapping[str, Any]
    citations: Mapping[str, Any]
    usage: Any
    warnings: list[str]
    min_confidence: float
    supports_confidence: bool
    review: bool
    scoring_endpoint: NotRequired[str]
    upstream: NotRequired[str]
    extra_failure_ids: NotRequired[dict[str, str]]
    votes: NotRequired[list[Any]]
```

Key order in the class does not affect runtime key order. Runtime order still comes from the literal in `_payload` (lines 297–320) and the later assignments, and both stay untouched.

| Line | Change | Δ |
|---|---|---|
| 61 | `def _extra_cell(question: JudgeQuestion, raw: Any) -> tuple[ExtraCell, Mapping[str, Any] \| None]:`. The local `cleaned = dict(raw)` (line 94) is still a dict while it is mutated. Callers only store it at `extra_answers[question.id] = cleaned` (line 433), which is a `dict[str, Any]` value slot. | −1 |
| 296 | `_payload(...) -> JudgePayload:` and `payload: JudgePayload = {` at line 297 | −1 |
| 334 | `_stamp_error(...) -> JudgePayload:` | −1 |
| 391 | `_stamp(...) -> JudgePayload:` | −1 |
| 470 | `_finish_payload(self, payload: JudgePayload, *, …)` | −1 |
| 475 | `) -> JudgePayload:` | −1 |
| 232 | In `judge`, change `return self._stamp(` to `return dict(self._stamp(`, with the matching closing paren. `judge` keeps `-> dict[str, Any]` (protocol, line 149). `dict(TypedDict)` is `dict[str, object]`, which mypy accepts for `dict[str, Any]`. The shallow copy keeps insertion order, and the original is never referenced again, so the content is identical. | 0 |
| kept | 146, 149 (`Judge.judge` protocol). 228 (`answers` is mutated with `.update(facts)`). 248 (`_majority_reask` result is assigned to `evaluated`, which `DecisionModel.evaluate` types as `dict[str, Any]`). 368, 369 (`cells` holds `_cell_entry` dicts that are mutated at line 375). | — |

**Result:** `grep -c 'dict\[str, Any\]' src/skillgate_ai/judge_openai/outcome.py` → **6**.

**Fallback:** if mypy rejects `JudgePayload` at any site, revert only the 296–475 rows. Line 61 alone already gets the file to 11 and satisfies E. Record the mypy error in the scorecard.

---

## Scope B: typing

### Rules (unchanged from PR C, restated)

1. **FastAPI route return annotations stay `dict[str, Any]`.** FastAPI derives `response_model` from them. In `api_skills.py` that means lines 109, 113, 134, 143, 147, 169, 187, 197, 232, 241, 251, 258, 285 and 294 (14 lines). The same applies to `checks_show.py` 149, 160, 164 and 171 and to every route in `api*.py`.
2. **Protocol and boundary signatures stay as they are.** This covers `Judge.judge`, `CompareResult.payload`, and any function whose result is mutated by a caller or returned into a `dict[str, Any]` slot.
3. **Read-only parameters become `Mapping[str, Any]` / `Sequence[Mapping[str, Any]]`.** Locally built fixed shapes become TypedDicts. Runtime code is unchanged, including `isinstance(x, dict)` checks. Widening a parameter is always safe for callers.
4. **No disguises:** no `cast()`, no alias for `dict[str, Any]`, no `# type: ignore`.
5. **New TypedDicts live in the file that builds them.** They are never added to a shim.
6. **Revert rule.** If mypy rejects a planned row, revert that row (or that call chain) only, keep the line, and list it under "Kept" in the scorecard with the mypy message.

### B1. Priority files

**`fixture_bind.py` (7 → 3)**

| Line | Change | Δ |
|---|---|---|
| 172 | `decide_gate(..., report: Mapping[str, Any] \| None = None, ...)` | −1 |
| 191 | `decide_gate_result(..., report: Mapping[str, Any] \| None = None, ...)` | −1 |
| 213 | `_pass_warnings(skill_path, report: Mapping[str, Any] \| None, checks)`. Needs the B2 `metrics.py` rows for `metrics_blocking` and `budget_gate_reason`, so land those first in the same commit. | −1 |
| 246 | `def _template_check(checks: Sequence[Mapping[str, Any]], description: str) -> Mapping[str, Any]:`. The local `template = dict(item)` is still mutated inside. The only caller, `expand_from_folder`, only calls `template.get(...)`. | −1 |
| kept | 66, 91 (returned lists that callers mutate). 99 (`created` is concatenated with `kept_triggers` of type `list[dict]`; list invariance). | — |

**`api_skills.py` (17 → 14)**

| Line | Change | Δ |
|---|---|---|
| 89–100 | Rewrite `_listed_skill` without in-place mutation, as shown below. `{**payload, k: v}` keeps the original position of any key that already exists and appends new keys at the end. That matches the current `payload["source"] = …` order exactly. | −2 (89, 90) |
| 103 | `def _listed_skills(state: AppState) -> list[Mapping[str, Any]]:` | −1 |
| kept | 14 route annotations (rule 1) | — |

```python
def _listed_skill(state: AppState, item: Mapping[str, Any]) -> Mapping[str, Any]:
    payload: Mapping[str, Any]
    try:
        payload = skill_payload(state, Path(item["absolute"]))
    except (SkillGateError, OSError, ValueError):
        payload = _broken_skill_row(item)
    source = str(item.get("source") or "")
    return {
        **payload,
        "source": source,
        "source_label": _PICKER_SOURCE_LABELS.get(source, str(item.get("source_label") or source)),
    }
```

`BrokenSkillRow` keeps its `source` and `source_label` `NotRequired` fields. They document the row shape.

**`compare/payload.py` (10 → 4)**

| Line | Change | Δ |
|---|---|---|
| 38 | `def _usage_for_task_ids(report: Mapping[str, Any], task_ids: list[str]) -> Mapping[str, Any] \| None:`. Its result fills `ComparePlanArm.usage`, which is already `Mapping[str, Any] \| None`. | −1 |
| 55 | `out: dict[str, int \| float] = {}`. Same shape as `CompareCell.usage`. | −1 |
| 123 | `def _usage_from_report(report: Mapping[str, Any] \| None) -> Mapping[str, Any] \| None:`. Callers in `compare_git.py:221` and `compare/versions.py:279` only store it as a dict value. | −1 |
| 130, 136 | `-> dict[str, Mapping[str, Any]]` and `out: dict[str, Mapping[str, Any]] = {}`. Callers (`compare/models.py:136`, `compare_git.py:223`, `versions.py:269`) only call `.get` or store the value. | −2 |
| 245 | `) -> tuple[int, int, dict[str, Mapping[str, Any]]]:` | −1 |
| `compare/models.py:135` | Second tuple element becomes `Mapping[str, Any] \| None`, to match line 38. The line still contains `dict[str, Any]` (first element), so the count is unchanged. | 0 |
| kept | 70 (`_dry_run_payload` is returned into `dict[str, Any]` payload slots). 177 and 200 (public scrub functions return mutated deep copies). 210 (`cfg` goes to `customer_config_label`; see the B2 `eval_config` row, which keeps it). | — |

### B2. Secondary files

Line numbers are from `cc8919a`. Apply B2 **before** the Scope C splits, so the new annotations move verbatim into the submodules.

| File | Lines → change | Δ |
|---|---|---|
| `metrics.py` (19) | 215 `metrics_blocking(report: Mapping[str, Any] \| None)`. 220 `budget_gate_reason(report: Mapping[str, Any] \| None)`. 339 `_blocking_tasks(report: Mapping[str, Any] \| None) -> list[Mapping[str, Any]]`. 341 `out: list[Mapping[str, Any]] = []`. 348 `_task_blocking(task: Mapping[str, Any])`. 357 `_task_status(task: Mapping…)`. 365 `_task_reasons(task: Mapping…)`. 299 `_tokens_total(usage: Mapping[str, Any] \| None)`. 310 `_is_path_span(span: Mapping…)`. 315 `_is_error_span(span: Mapping…)`. 151 `usage: Mapping[str, Any] \| None`. 152 `spans: Sequence[Mapping[str, Any]] \| None`. | −12 |
| `usage.py` (13) | 147 `usage_from_event(obj: Mapping[str, Any])`. 400 `_usage_objects(obj: Mapping[str, Any])`. 457 `_number_field(raw: Mapping[str, Any], …)`. 509, 535, 549, 584: renderer parameters → `Mapping[str, Any]`. 260, 261 `combine_task_usage(agent: Mapping[str, Any] \| None, judged: Mapping[str, Any] \| None, …)` (revert rule applies). Kept: 230, 266, 304, 405. | −9 |
| `spans.py` (10) | 110, 290 `obj: Mapping[str, Any]`. 233 `_assistant_text(obj: Mapping…)`. 245 `_is_cursor_partial_assistant(obj: Mapping…)`. 255 `_is_cursor_assistant_dup_flush(obj: Mapping…)`. Kept: 293, 355, 480 (existing `cast`, untouched), 483, 485. | −5 |
| `judge_context.py` (19) | 96 `workspace_files_for_judge(artifacts: Sequence[Mapping[str, Any]] \| None)`. 178 `_claude_tool_command(part: Mapping…)`. 194 `_claude_tool_output(part: Mapping…)`. 218 `obj: Mapping[str, Any]`. 277 `_append_command_run(runs, item: Mapping[str, Any])`. Revert rule applies per function. | −5 |
| `eval_config.py` (14) | Change these as one chain; on any mypy error, revert the whole chain. 79 `from_dict(cls, data: Mapping[str, Any] \| None)`. 301, 361, 392 `run: EvalRunConfig \| Mapping[str, Any] \| None`. 417 `config_label(run: EvalRunConfig \| Mapping[str, Any] \| None)`. 437, 438 `current`/`previous` likewise. 455 `coerce_eval_config(value: EvalRunConfig \| Mapping[str, Any] \| None)`. Runtime `isinstance(run, dict)` checks stay. Kept: 60, 177, 205, 439, 448, 465. | −8 |
| `deploy_gate.py` (8) | 11 `row_is_tryout(row: Mapping[str, Any], report: Mapping[str, Any] \| None = None)`. 23 `error: Mapping[str, Any] \| None`. 36 `row_gate_moved(row: Mapping…)`. 73 `run_gate_decision(row: Mapping…)`. Kept: 54, 95, 121, 130. | −4 |
| `advice.py` (2) | 196 `cells: Mapping[str, Any] = …`. 198 `questions: Mapping[str, Any] = …`. Both are read-only. | −2 |
| `tool_checks.py` (6) | 460 `_args_match(call, spec: Mapping[str, Any] \| None)`. 491 `_fmt_args(spec: Mapping[str, Any] \| None)`. Kept: 133 (dataclass field), 210, 341, 502. | −2 |
| `history.py` (16) | 22 `_append_jsonl(dest, row: Mapping[str, Any])`. 110 `_row_ts(item: Mapping[str, Any])`. | −2 |
| `api_payloads.py` (19) | 216 `_neutral_scored_by(text, stamp: Mapping[str, Any] \| None)`. 298 `_deploy_payload(row: Mapping[str, Any], *, index: int = 0)`. | −2 |
| `case_pack/suites.py` (11) | 299 `checks_fingerprint(checks: Sequence[Mapping[str, Any]], *, skill: str)` | −1 |

### B totals

| | Lines removed |
|---|---|
| E (`outcome.py`) | 6 |
| B1 (`fixture_bind` 4, `api_skills` 3, `compare/payload` 6) | 13 |
| B2 (secondary files) | 52 |
| **Planned total** | **71** → 583 − 71 = **512** |

**Hard acceptance:** total ≤ **520**, which leaves room for at most 8 lines reverted under rule 6.

The approved "~480" figure cannot be reached in this PR without touching one of two frozen areas:

- FastAPI route annotations (rule 1): 14 lines in `api_skills.py` alone, plus the routes in the other `api*.py` files and `checks_show.py`.
- `mcp/` (46 lines).

The scorecard records this gap explicitly as an open item.

---

## Scope A: broad exception handlers (23 → 15)

### Rules

- A narrowed handler loses its `# noqa: BLE001…` comment. Ruff stops flagging it, and RUF100 must stay clean.
- A handler that stays broad keeps or gains a justification. The same-line `# noqa: BLE001 - <reason>` is already present on 14 of the 15 kept handlers. The one without a `noqa` (`scaffold.py:47`, a cleanup-and-re-raise) gets a one-line comment on the line above. Ruff does not flag `except Exception:` followed by a bare `raise`, so no new `noqa` is needed.
- Add `import subprocess` at module level where the table says so. It is stdlib and already imported transitively by every one of these paths, so lazy-import timing is unchanged.

| # | Location (cc8919a) | Old | New | Why |
|---|---|---|---|---|
| 1 | `engine/task.py:400` (`_harness_result_or_skip`) | `except Exception as exc:` → map or bare `raise` | `except subprocess.TimeoutExpired as exc:` (body unchanged: `blocked = timeout_harness_error(exc, timeout_sec=timeout)`; `if blocked is not None: raise blocked from None`; `raise`) | `timeout_harness_error` returns non-None only for `subprocess.TimeoutExpired` (`errors.py:120`). Every other exception was already re-raised unchanged. **Identical behavior.** |
| 2 | `cli/cmd_gate.py:79` | `except Exception as exc:  # noqa: BLE001 — TimeoutExpired…` | `except subprocess.TimeoutExpired as exc:` (body unchanged) | Same reasoning. **Identical behavior.** |
| 3 | `gate.py:287` (`_execute_check`) | `except Exception as exc:` with inner `if not isinstance(exc, SkillGateError): raise` | `except (SkillGateError, subprocess.TimeoutExpired) as exc:`. The inner `isinstance` re-raise stays (now only a type guard). | Only these two types were handled; everything else was re-raised. **Identical behavior.** |
| 4 | `pack_schema.py:299` (`parse_judge_block`) | `except Exception as exc:` → `SuiteError` | `except ValidationError as exc:`, with `from pydantic import ValidationError` added to the existing pydantic import (line 11) | pydantic v2 wraps validator `ValueError`/`AssertionError` in `ValidationError`. Before narrowing, grep `JudgeBlock` and its nested models for `raise TypeError` in validators. If one exists, use `(ValidationError, TypeError)`. A non-validation bug now propagates. |
| 5 | `case_pack/suites.py:180` (`suite_from_pack`) | `except Exception as exc:` → `SuiteError(f"Couldn't turn these checks into a run: {exc}")` | `except ValidationError as exc:` (`from pydantic import ValidationError`). Same `TypeError` check on `SuiteSpec`/`TaskSpec` validators. | Message text unchanged. |
| 6 | `live.py:376` (`RunControl._terminate`, `process.terminate()`) | `except Exception:  # noqa: BLE001 - best effort` | `except OSError:` | `Popen.terminate` raises only `OSError` (`ProcessLookupError`, `PermissionError`). |
| 7 | `live.py:381` (`signal_group(process, SIGTERM)`) | same | `except OSError:` | `os.killpg` raises only `OSError`. |
| 8 | `live.py:394` (`hard_kill`) | `except Exception:  # noqa: BLE001, S110 - best effort` | `except OSError:` followed by `pass`. S110 only flags `Exception`/bare excepts, so no `noqa` is needed. | `poll`/`kill`/`kill_group` raise only `OSError`. |
| 9 | `scaffold.py:47` | `except Exception:` → `rmtree`, `raise` | **Keep.** Add on the line above: `# Cleanup-and-reraise: any failure must not leave a half-written pack.` | A real re-raise boundary. |
| 10–11 | `scorers.py:358`, `:368` | untrusted PDF parser | **Keep** (justification already present) | pypdf raises many unrelated types (`PdfReadError`, `KeyError`, `struct.error`, `zlib.error`, `RecursionError`, …). |
| 12 | `document_text.py:34` | untrusted docx/xlsx/pdf parser | **Keep** | Same as 10–11. |
| 13 | `sandbox.py:297` | output-sink callback | **Keep** | Third-party sink code must not kill the harness. |
| 14–15 | `live.py:319`, `:330` | flush callbacks | **Keep** | Callback boundary. |
| 16 | `run_registry.py:240` | run worker thread | **Keep** | Worker boundary. The failure is recorded for the poller. |
| 17–18 | `api_compare.py:178`, `:224` | compare worker thread | **Keep** | Worker boundary. The job would otherwise stay "running" forever. |
| 19 | `helper.py:335` | per-target install | **Keep** | Adapter code is open-ended. Each target must report "failed". |
| 20 | `helper.py:356` | claimed job | **Keep** | A claimed job must report back. |
| 21 | `errors.py:202` | `exc.errors()` on an arbitrary exception | **Keep** | Called on arbitrary third-party exceptions; it falls back to a generic line. |
| 22 | `harness/diagnostics.py:112` | auth probe | **Keep** | The probe runs a subprocess and must not break diagnostics. |
| 23 | `harness/messages.py:269` | diagnostics builder | **Keep** | Must not mask the auth `HarnessError`. |

**Result:** `grep -rnE 'except Exception\b' src/skillgate_ai | wc -l` → **15**. Every kept line has a justification. `test_broad_excepts_are_documented_boundaries` (Scope D) enforces both.

---

## Scope C: module splits

### Rules (same as PR C, `docs/specs/audit-structure-coverage.md` "Rules for every split")

1. **Code moves verbatim**, including the Scope B annotation edits made earlier in this PR. Only import lines change. Decorators, docstrings, comments and blank lines move with the code. Lazy imports move with their function.
2. **The shim is the package `__init__.py`.** It contains:
   - the original module docstring, verbatim, plus one paragraph: "Re-export shim. Code lives in the submodules listed below. Patching a name on this shim does not affect code inside the package; patch the submodule that defines it."
   - `from __future__ import annotations`
   - `from skillgate_ai.X.sub import name as name` for every name
   - no `def`, `class`, logic or `__all__`.
3. **Re-export every module-scope name defined in the old file**, private names included. Do **not** re-export names the old file only imported: `re`, `shutil`, `json`, `yaml`, `Path`, `Any`, `Score`, `Skill`, `TaskSpec`, `tokenize`, `select_skill_from_descriptions`, `FRONTMATTER_RE`, `CHECK_CELL_ORDER`, `SOFT_CELL_ORDER`, `_INVOKE_TOOLS`, `_parse_calls_log`, `_span_invokes`, `attr_map`, `spans_from_jsonl`, `DEFAULT_CALLS_LOG`, `TaskToolChecks`, `ToolCallRule`, `declared_patterns`.
4. **Submodules never import their own package's `__init__`.** They import siblings directly. Imports from other packages' shims (`skillgate_ai.span_facts`, `skillgate_ai.harness`, `skillgate_ai.judge_spec`) stay as they are.
5. **No submodule may share a name with a re-exported symbol.** `test_no_submodule_shadows_a_symbol` enforces this.
6. **Each submodule imports only what it uses.** Ruff F401 enforces this, and `ruff format` must be clean.
7. **Every new file is ≤ 320 lines.**
8. **Patch seams.** There are none to repoint. `grep -rnE "(monkeypatch|patch)\(.*skillgate_ai\.(advice|usage|tool_checks)" tests` returns nothing on `cc8919a`. Rerun it after the split; it must still return nothing.

### C1. `advice.py` (614) → package `src/skillgate_ai/advice/`

| New file | Moves (old lines) | ≈ lines |
|---|---|---|
| `advice/__init__.py` | shim: docstring line 1 + 33 re-exports | ~45 |
| `advice/model.py` | 19–52: `BEHAVIOR_FAIL_LEAD`, `TRIGGER_SECONDARY_NOTE`, `_MEAL_NOISE`, `FixAdvice` | ~45 |
| `advice/text.py` | 564–614: `_frontmatter`, `_clip`, `_is_script_failure`, `_command_fail_snippet`, `_task_output_path`, `_suggested_steps` | ~60 |
| `advice/behavior.py` | 183–238: `behavior_fail_line`, `behavior_question_ids`, `_behavior_fix` | ~65 |
| `advice/quality.py` | 263–377: `_VAGUE_TOKENS`, `_THIN_HINT`, `_VAGUE_HINT`, `_WHEN_HINT`, `_PADDED_TOKEN`, `_WHEN_SPLIT`, `description_is_usable`, `_content_tokens` | ~120 |
| `advice/rewrite.py` | 379–435: `rewrite_skill_description`, `description_from_paste`, `apply_description_fix` | ~65 |
| `advice/synth.py` | 240–261 `synthesize_trigger_description`; 481–562 `_retarget_description`, `_description_from_prompts`, `_when_clause`, `_force_keywords`, `_tighten_description` | ~115 |
| `advice/fixes.py` | 54–181 `advise_task`, `advise_suite`; 437–479 `_trigger_fix` | ~185 |

- **Dependency order:** `model` → `text` → `behavior` → `quality` → `rewrite` → `synth` → `fixes`.
  - `behavior` imports `FixAdvice`, `BEHAVIOR_FAIL_LEAD` and `TRIGGER_SECONDARY_NOTE` from `model`, plus `CHECK_CELL_ORDER` and `SOFT_CELL_ORDER`.
  - `quality` imports `tokenize` from `skillgate_ai.harness`.
  - `rewrite` imports `shutil`, `yaml` and `FRONTMATTER_RE`.
  - `synth` imports `_MEAL_NOISE` (model), `_clip` (text), `select_skill_from_descriptions`, `tokenize` and `Skill`.
  - `fixes` imports from all of the above.
- **External readers keep working through the shim:**
  - `engine/task.py:9`, `engine/models.py:8`, `engine/run_finish.py:7` and `api_skills.py:18`
  - the lazy import at `report/lines.py:22`
  - `tests/test_advice.py` and `tests/test_report.py`
- **`REGISTRY["skillgate_ai.advice"]`** (33 names): `BEHAVIOR_FAIL_LEAD`, `TRIGGER_SECONDARY_NOTE`, `_MEAL_NOISE`, `FixAdvice`, `advise_task`, `advise_suite`, `behavior_fail_line`, `behavior_question_ids`, `_behavior_fix`, `synthesize_trigger_description`, `_VAGUE_TOKENS`, `_THIN_HINT`, `_VAGUE_HINT`, `_WHEN_HINT`, `_PADDED_TOKEN`, `_WHEN_SPLIT`, `description_is_usable`, `_content_tokens`, `rewrite_skill_description`, `description_from_paste`, `apply_description_fix`, `_trigger_fix`, `_retarget_description`, `_description_from_prompts`, `_when_clause`, `_force_keywords`, `_tighten_description`, `_frontmatter`, `_clip`, `_is_script_failure`, `_command_fail_snippet`, `_task_output_path`, `_suggested_steps`.

### C2. `usage.py` (610) → package `src/skillgate_ai/usage/`

| New file | Moves (old lines) | ≈ lines |
|---|---|---|
| `usage/__init__.py` | shim: docstring 1–35 verbatim + 36 re-exports | ~75 |
| `usage/model.py` | 44–132: `_IN_KEYS`, `_OUT_KEYS`, `_TOTAL_KEYS`, `_MODEL_USD_PER_MILLION`, `SUBSCRIPTION_COST_LABEL`, `_COST_KEYS`, `_CODEX_BOOKKEEPING`, `_CURSOR_BOOKKEEPING`, `_NON_CONTENT_EVENTS`, `Usage` (keep the comment lines 44–45, 49, 88, 90) | ~95 |
| `usage/parse.py` | 42 `_Num`; 133–170 `parse_usage_line`, `usage_from_event`, `merge_usage`, `usage_from_mapping`; 392–478 `_pick`, `_usage_objects`, `_usage_from_tokens`, `_number_field` | ~140 |
| `usage/cost.py` | 171–336: `_add_int`, `_add_float`, `_normalize_model_id`, `estimate_usage_cost_usd`, `normalize_judge_api_usage`, `combine_task_usage` | ~175 |
| `usage/stream.py` | 337–391 `is_non_content_stream_line`, `render_stream_line`; 479–610 `_render_codex_item`, `_CURSOR_ARG_KEYS`, `_render_cursor_thinking`, `_render_cursor_assistant`, `_claude_tool_command`, `_render_claude_tool_results`, `_claude_tool_result_text`, `_render_cursor_tool_call`, `_cursor_tool_args` | ~195 |

- **Dependency order:** `model` → `parse` → `cost` → `stream`. If `parse` turns out to need `_normalize_model_id`, move that one function to `model.py` instead, to avoid a `parse` ↔ `cost` cycle. Record the move in the commit message.
- **External readers keep working through the shim:**
  - `live.py:21`, `harness/base.py:13`, `harness/transcripts.py:9`
  - the lazy imports at `engine/task.py:293`, `judge_openai/decisions.py:99` and `judge_openai/outcome.py:504`
  - tests `test_usage_combine`, `test_harness_auth`, `test_report` and `test_judge_dogfood_v5`
- **`REGISTRY["skillgate_ai.usage"]`** (36 names): `_Num`, `_IN_KEYS`, `_OUT_KEYS`, `_TOTAL_KEYS`, `_MODEL_USD_PER_MILLION`, `SUBSCRIPTION_COST_LABEL`, `_COST_KEYS`, `_CODEX_BOOKKEEPING`, `_CURSOR_BOOKKEEPING`, `_NON_CONTENT_EVENTS`, `Usage`, `parse_usage_line`, `usage_from_event`, `merge_usage`, `usage_from_mapping`, `_add_int`, `_add_float`, `_normalize_model_id`, `estimate_usage_cost_usd`, `normalize_judge_api_usage`, `combine_task_usage`, `is_non_content_stream_line`, `render_stream_line`, `_pick`, `_usage_objects`, `_usage_from_tokens`, `_number_field`, `_render_codex_item`, `_CURSOR_ARG_KEYS`, `_render_cursor_thinking`, `_render_cursor_assistant`, `_claude_tool_command`, `_render_claude_tool_results`, `_claude_tool_result_text`, `_render_cursor_tool_call`, `_cursor_tool_args`.

### C3. `tool_checks.py` (715) → package `src/skillgate_ai/tool_checks/`

| New file | Moves (old lines) | ≈ lines |
|---|---|---|
| `tool_checks/__init__.py` | shim: docstring line 1 + 40 re-exports | ~50 |
| `tool_checks/rules.py` | 28–128: `TOOL_CHECK_SCORERS`, `_INTERPRETERS`, `_SAFE_TOOLS`, `_READ_VERBS`, `_SHELL_TOOLS`, `_SEP`, `_SUDO_PREFIX`, `_ENV_PREFIX`, `_SHELL_RULES` (imports `_INVOKE_TOOLS` from the `skillgate_ai.span_facts` shim) | ~105 |
| `tool_checks/aliases.py` | 129–209: `ToolCall`, `normalize_tool_name`, `tool_aliases`, `_shell_rule_aliases`, `_pattern_forms`, `matches_pattern` | ~90 |
| `tool_checks/collect.py` | 210–427: `_args_from_row`, `_name_from_argv`, `_name_from_row`, `_shell_segments`, `_command_stem`, `_shell_rule_calls`, `_declared_shell_calls`, `_args_from_span`, `_safe_calls_log_path`, `collect_tool_calls` | ~225 |
| `tool_checks/assertions.py` | 428–558: `_get_path`, `_match_expected`, `_args_match`, `_matching_calls`, `_count_matching`, `_fmt_args`, `_score_assertions` | ~140 |
| `tool_checks/consequential.py` | 559–676: `_alias_segments`, `is_consequential`, `_allowed_consequential`, `_consequential_display_name`, `_allow_consequential_hint`, `_score_consequential` | ~125 |
| `tool_checks/scoring.py` | 677–715: `score_tool_checks` (keeps its lazy `from skillgate_ai.scorers import headline_for`), `tool_check_failures` | ~45 |

- **Dependency order:** `rules` → `aliases` → `collect` → `assertions` → `consequential` → `scoring`.
- **External readers keep working through the shim:**
  - `tool_evidence.py:13` (`TOOL_CHECK_SCORERS`) and `engine/task.py:41`
  - `tests/test_tool_checks.py:13` and the `test_tool_checks_*` files
- **`REGISTRY["skillgate_ai.tool_checks"]`** (40 names): `TOOL_CHECK_SCORERS`, `_INTERPRETERS`, `_SAFE_TOOLS`, `_READ_VERBS`, `_SHELL_TOOLS`, `_SEP`, `_SUDO_PREFIX`, `_ENV_PREFIX`, `_SHELL_RULES`, `ToolCall`, `normalize_tool_name`, `tool_aliases`, `_shell_rule_aliases`, `_pattern_forms`, `matches_pattern`, `_args_from_row`, `_name_from_argv`, `_name_from_row`, `_shell_segments`, `_command_stem`, `_shell_rule_calls`, `_declared_shell_calls`, `_args_from_span`, `_safe_calls_log_path`, `collect_tool_calls`, `_get_path`, `_match_expected`, `_args_match`, `_matching_calls`, `_count_matching`, `_fmt_args`, `_score_assertions`, `_alias_segments`, `is_consequential`, `_allowed_consequential`, `_consequential_display_name`, `_allow_consequential_hint`, `_score_consequential`, `score_tool_checks`, `tool_check_failures`.

### C4. `tests/test_public_imports.py` edits (additive only)

1. Add the three `REGISTRY` entries above, after `"skillgate_ai.engine.run"`. Before committing, cross-check each list against the old file with `python -c "import ast,sys; t=ast.parse(open(sys.argv[1]).read()); print(sorted({n.id for s in t.body if isinstance(s,(ast.Assign,ast.AnnAssign)) for n in (s.targets if isinstance(s,ast.Assign) else [s.target]) if isinstance(n,ast.Name)} | {s.name for s in t.body if isinstance(s,(ast.FunctionDef,ast.ClassDef))}))" <(git show cc8919a:src/skillgate_ai/advice.py)`, then the same for `usage.py` and `tool_checks.py`.
2. Change `_SPLIT_TARGETS = ("span_facts", "report", "judge_spec", "pack")` to `("span_facts", "report", "judge_spec", "pack", "advice", "usage", "tool_checks")`.
3. Add one new test:

```python
def test_pr_d_split_targets_are_packages() -> None:
    for name in ("advice", "usage", "tool_checks"):
        assert (SRC / name / "__init__.py").is_file(), name
        assert not (SRC / f"{name}.py").exists(), name
```

`test_shims_hold_no_code`, `test_defined_symbols_belong_to_their_module` and `test_no_submodule_shadows_a_symbol` then cover the new shims with no further edits.

---

## Scope D: coverage (77.39% → ~85%)

### D1. Measure (step 1, no code)

Run `pytest -q -m "not integration" --cov=skillgate_ai --cov-report=term-missing`. Paste the 25 lowest-covered modules (stmts / miss / cover) into the PR description.

The test files in D2 target code that has no direct tests on `cc8919a`:

- `fixture_bind.py`, `compare_format.py` and `local_guard.py`: no test imports them directly.
- The description helpers in `advice.py`: `description_is_usable`, `description_from_paste`, `rewrite_skill_description`, `apply_description_fix`, `synthesize_trigger_description` and `behavior_question_ids` are not referenced by any test.
- The `openai_http.py` helpers.
- The `usage.py` model and cost helpers.
- The newly narrowed handlers.

If D1 shows a module under 60% that is not covered below, add tests for it in D3.

### D2. New and extended tests (≥ 25 required; 58 listed)

Rules for every test:

- Assert behavior (return values, raised types, file contents). Do not merely execute lines.
- No network, no real API keys.
- `tmp_path` for every filesystem write.
- Private helpers are imported through the shim (`from skillgate_ai.advice import _clip`). That also exercises the re-export.

**`tests/test_advice_description.py` (new)**

1. `test_description_is_usable_rejects_short_text`: `description_is_usable("Edit PDFs.") == (False, _THIN_HINT)`.
2. `test_description_is_usable_rejects_repeated_char_padding`: `"Extract text from aaaaaaaaaaaa files. Use when the user mentions a pdf invoice."` → `(False, _VAGUE_HINT)`.
3. `test_description_is_usable_requires_when_clause`: `"Extract text, merge pages, rotate scans and split large PDF invoices into separate documents quickly."` → `(False, _WHEN_HINT)`.
4. `test_description_is_usable_accepts_concrete_when_clause`: `"Extract text and merge PDFs. Use when the user mentions a .pdf file, invoices, or combining documents."` → `(True, "")`.
5. `test_description_is_usable_require_when_false_skips_clause`: the text from test 3 with `require_when=False` → `(True, "")`.
6. `test_description_from_paste_returns_trimmed_description`: `"---\nname: pdf\ndescription: '  Extract PDFs.  '\n---"` → `"Extract PDFs."`. This also covers the missing trailing newline.
7. `test_description_from_paste_rejects_missing_frontmatter`: `pytest.raises(ValueError, match="Paste a SKILL.md frontmatter block")` for `"no frontmatter"`.
8. `test_description_from_paste_rejects_empty_description`: `"---\nname: pdf\n---\n"` → `ValueError` matching `"has no description"`.
9. `test_rewrite_skill_description_preserves_name_and_body`: start from `"---\nname: pdf\ndescription: old\n---\n# Body\n"`. Afterwards the file text `== "---\nname: pdf\ndescription: new desc\n---\n# Body\n"`.
10. `test_rewrite_skill_description_without_frontmatter_raises`: `ValueError` matching `"no YAML frontmatter"`. The file is unchanged.
11. `test_apply_description_fix_copies_and_restores_scripts`: `src/demo/SKILL.md` plus `src/demo/scripts/a.py` (`"broken"`), and `ref/scripts/a.py` (`"good"`). Call with `dest_root=tmp_path/"work"` and `restore_scripts_from=ref`. Check that:
    - the return value `== tmp_path/"work"/"demo"`
    - the dest `SKILL.md` contains `description: new`
    - `scripts/a.py` reads `"good"`
    - the source `SKILL.md` is unchanged.
12. `test_apply_description_fix_rewrites_in_place_when_dest_is_source`: `dest_root=source.parent` → return value `== source`, and the source `SKILL.md` is rewritten.
13. `test_behavior_question_ids_maps_cell_reason_to_id`: `{"extra_failures": ["Cited? No"], "cells": {"cite": {"reason": "Cited? No"}}}` → `["cite"]`.
14. `test_behavior_question_ids_matches_instructions_and_strips_no`: `{"extra_failures": ["Asked first? No", "Loose text No"], "questions": {"ask_first": {"instructions": "Asked first?"}}}` → `["ask_first", "Loose text"]`.
15. `test_behavior_question_ids_ignores_reserved_and_non_dict`: `behavior_question_ids(None) == []`, and `behavior_question_ids({"extra_failures": [CHECK_CELL_ORDER[0]]}) == []`.
16. `test_command_fail_snippet_prefers_error_line`: `_command_fail_snippet("usage: x\nerror: bad flag --y\n") == "bad flag --y"`, and `_command_fail_snippet("") == ""`.
17. `test_is_script_failure_ignores_json_stderr`: `(1, '{"e":1}')` → False, `(2, "Traceback")` → True, `(0, "x")` → False, `(None, "x")` → False.
18. `test_clip_breaks_on_word_boundary`: `_clip("alpha beta gamma", 12) == "alpha..."`, and `_clip("  a   b ", 10) == "a b"`.
19. `test_tighten_description_is_idempotent`: a `Skill` with description `"Edit PDFs."`. The first call returns `"Edit PDFs. Do not use this skill for unrelated questions (weather, unit tests, general chat)."`, and calling it again on that output returns the same string.
20. `test_synthesize_trigger_description_selects_skill_for_failed_prompt`: a skill `pdf-tool` with description `"Unrelated."` and the prompt `"Extract the text from invoice.pdf"`. The result is ≤ 1024 characters, and `select_skill_from_descriptions(prompt, [Skill(path=…, name="pdf-tool", description=result, body="")]) == "pdf-tool"`.

**`tests/test_fixture_bind.py` (new)**

21. `test_is_completion_check_detects_output_contains_or_golden`: parametrize over `{"output_path": "o.txt"}`, `{"contains": "x"}`, `{"expected": "x"}` and `{"golden_path": "g"}` → True. `{"prompt": "p"}` → False.
22. `test_is_trigger_only_excludes_negative_and_completion`: `{"should_trigger": False}` → False, `{"contains": "x"}` → False, `{"prompt": "p"}` → True.
23. `test_prompt_for_file_swaps_existing_filename`: `_prompt_for_file("Summarize report.pdf now", "evals/fixtures/a.pdf") == "Summarize evals/fixtures/a.pdf now"`.
24. `test_prompt_for_file_prefixes_read_when_no_filename`: `_prompt_for_file("Summarize it", "a.txt") == "Read a.txt, summarize it."`.
25. `test_prompt_for_file_empty_template_uses_default_output`: `_prompt_for_file("", "a.txt") == "Read a.txt and save the result to output/result.txt."`.
26. `test_unique_id_appends_counter`: `_unique_id("Complete Report", {"complete-report", "complete-report-2"}) == "complete-report-3"`, and `_unique_id("!!!", set()) == "complete"`.
27. `test_has_files_requires_src_and_dest`: `[{"src": "a"}]` → False, `[{"src": "a", "dest": "b"}]` → True, `"x"` → False, `[]` → False.
28. `test_template_check_falls_back_to_default_prompt`: `dict(_template_check([{"should_trigger": False}], "desc")) == {"prompt": "Read the input and save the result to output/result.txt.", "should_trigger": True, "output_path": "output/result.txt", "contains": "desc"}`.
29. `test_decide_gate_result_status_branches`:
    - `status="running"` → `GateVerdict("pending", "Evaluation is still running.")`
    - `status="error"` → decision `"blocked"`
    - `harness=None, passed=True` → reason `"Deploy needs a live harness."`
    - `harness="cursor-agent", passed=False` → reason `"Get a passing run to unlock Deploy."`
30. `test_report_covers_pinned_ids`: `({"tasks": [{"id": "a"}, {"id": "b"}]}, ("a",))` → True, `("c",)` → False, `()` → False.
31. `test_coverage_required_from_report_files`: `coverage_required(None, report={"tasks": [{"files": [{"src": "a", "dest": "b"}]}]})` → True, and `coverage_required(None)` → False.
32. `test_authentic_completion_passed_requires_task_completion_score`: `{"tasks": [{"passed": True, "scores": [{"scorer": "rubric", "passed": True}]}]}` → False.

**`tests/test_compare_format.py` (new)**

33. `test_fmt_cost_formats_sub_cent_and_missing`: `None` → `"—"`, `0.005` → `"$0.0050"`, `1.234` → `"$1.23"`, `0` → `"$0.00"`.
34. `test_fmt_duration_minutes_and_seconds`: `59.6` → `"1m 00s"`, `5` → `"5s"`, `-3` → `"0s"`.
35. `test_row_to_line_pads_and_truncates`: `_row_to_line([]) == ""`, and `_row_to_line(["case", None], arm_col_width=4) == "case".ljust(32) + " | " + "—   "`.
36. `test_arm_column_title_dry_run_appends_subtitle`:
    - `{"label": "A", "subtitle": "Codex"}` with `status="dry_run"` → `"A · Codex"`
    - the same arm with `status="done"` → `"A"`
    - `{"label": "Codex arm", "subtitle": "Codex"}` with `"dry_run"` → `"Codex arm"`.
37. `test_format_compare_cli_dry_run_lists_every_arm`: build `_dry_run_payload(tmp_path/"pdf", arms=[two CompareArmSpec], compare_id="c1", case_ids=["a", "b"], max_spend_usd=None)` and pass it to `format_compare_cli`. The output contains both arm labels, `"a"` and `"b"`.

**`tests/test_openai_http.py` (new)**

38. `test_redact_secrets_masks_configured_key_and_sk_tokens`: `redact_secrets("key=abc123 sk-proj-XYZ", "abc123")` contains `"***"` and `"sk-***"` and does not contain `"abc123"` or `"XYZ"`. Also `redact_secrets("") == ""`.
39. `test_sanitize_upstream_collapses_whitespace_and_trims`: `sanitize_upstream("  bad   request .  ") == "bad request"`.
40. `test_refuse_chat_judge_url_raises_exit_2`: for each fragment in `_CHAT_JUDGE_URLS`, `refuse_chat_judge_url(f"https://x.example{frag}")` raises `SkillGateError` with `exit_code == 2`. `refuse_chat_judge_url("https://x.example/v1/decisions")` returns None.
41. `test_openai_error_message_non_json_returns_none`: `openai_error_message(httpx.Response(500, content=b"not json")) is None`.

**`tests/test_local_guard.py` (new; starts with `pytest.importorskip("starlette")`)**

42. `test_hostname_of_handles_ipv6_and_port`: `"[::1]:8000"` → `"::1"`, `"LocalHost:3000"` → `"localhost"`, `""` → `""`.
43. `test_origin_is_loopback`: `"http://127.0.0.1:5173"` → True, `"https://evil.example"` → False.

**`tests/test_usage_model.py` (new)**

44. `test_merge_usage_is_monotonic`: `merge_usage(Usage(tokens_in=10, tokens_total=20), Usage(tokens_in=5, tokens_out=3)) == Usage(10, 3, 20, None)`.
45. `test_estimate_usage_cost_prefers_reported_cost`: `estimate_usage_cost_usd("x", Usage(cost_usd=0.5)) == 0.5`, and `estimate_usage_cost_usd("x", None) is None`.
46. `test_estimate_usage_cost_uses_longest_prefix_match`: `estimate_usage_cost_usd("anthropic/claude-sonnet-4-5-latest", Usage(tokens_in=1_000_000, tokens_out=0)) == 3.0`.
47. `test_estimate_usage_cost_total_only_counts_as_input`: `estimate_usage_cost_usd("gpt-5.6-luna", Usage(tokens_total=2_000_000)) == 0.2`.
48. `test_usage_from_mapping_rejects_non_dict`: `usage_from_mapping([1]) is None`.
49. `test_parse_usage_line_ignores_non_json`: `"hello"`, `"{bad"` and `"[1]"` → None.

**`tests/test_narrowed_excepts.py` (extend; covers Scope A)**

50. `test_parse_judge_block_validation_error_becomes_suite_error`:
    - Capture a real error with `err = pytest.raises(ValidationError, pydantic.TypeAdapter(int).validate_python, "x").value`.
    - Monkeypatch `JudgeBlock.model_validate` to raise `err`.
    - `parse_judge_block({"x": 1})` must raise `SuiteError`.
51. `test_parse_judge_block_unexpected_error_propagates`: monkeypatch `JudgeBlock.model_validate` to raise `RuntimeError("bug")` → `pytest.raises(RuntimeError, match="bug")`.
52. `test_suite_from_pack_unexpected_error_propagates`: monkeypatch `skillgate_ai.case_pack.suites.SuiteSpec.model_validate` to raise `RuntimeError` → it propagates instead of becoming `SuiteError`.
53. `test_harness_result_or_skip_maps_timeout_to_harness_error`: a fake harness whose `run` raises `subprocess.TimeoutExpired("agent", 5)` → `_harness_result_or_skip(...)` raises `HarnessError` with `exit_code == 2`, and `__cause__` is None (`from None`).
54. `test_harness_result_or_skip_reraises_other_errors`: the fake raises `ValueError("x")` → `pytest.raises(ValueError)`.
55. `test_run_control_terminate_swallows_oserror`: a fake process with `pid=None`, `terminate` raising `ProcessLookupError` and `poll` set to `None` → `RunControl(...)._terminate(fake)` returns None without raising.

**`tests/test_audit_ratchets.py` (new; locks in this PR's metrics)**

56. `test_no_source_module_over_600_lines`: every `src/skillgate_ai/**/*.py`, excluding `examples/`, has ≤ 600 lines. The failure message names the file.
57. `test_broad_excepts_are_documented_boundaries`: collect every line matching `except Exception\b` under `src/skillgate_ai`. Assert:
    - there are ≤ 15 of them
    - each one either carries `# noqa: BLE001` followed by a reason of at least two words after `-` or `—`, or the line immediately above it is a `#` comment.
58. `test_dict_any_line_budget`: the number of lines containing `dict[str, Any]` under `src/skillgate_ai` is ≤ 520, and `judge_openai/outcome.py` has ≤ 11.

The public-imports additions in C4 come on top of these (+1 test, plus new parametrized cases).

### D3. If coverage is still below 84.00% after D2

Use the D1 list. Add tests, in order, for the lowest-covered modules among these:

- `cli/cmd_keys.py`, `cli/pack_history.py`, `cli/compare_jobs.py`: `typer.testing.CliRunner`. Assert exit codes and the exact strings copied from the command source. `HOME` points at `tmp_path`.
- `deploy_gate.py`: `local_gate`, `pack_gate_decision` with an empty history (→ `("pending", "Run checks to set the gate.")`), and `newest_gate_moving_row` skipping tryout rows.
- `catalog.py`, `case_import.py` (`_parse_csv`, `_parse_jsonl`, `_dict_from_flat_row`), `checks_show.py` (`preview_question`, `list_check_rows` on `skills/pdf`).
- `judge_providers/clef.py` and `judge_providers/jev.py` request and response mapping, with `httpx.MockTransport`.

Name each new test `test_<module>_<behavior>` and list it in the PR body.

### D4. Raise the floor

In `pyproject.toml` `[tool.coverage.report]`, set `fail_under` to the measured CI (Linux, 3.12) total, rounded **down** to the nearest 0.5. Examples: 85.37 → `85.5` is **wrong**, it must be `85`; 84.62 → `84.5`. `precision = 2` and `skip_covered = true` stay.

- **Target:** 85.
- **Minimum acceptable for merge:** `fail_under = 84`.

If CI measures lower than local, do **not** lower the floor below the CI number. Record which tests are platform-skipped.

---

## Step order (one commit each)

1. **Baseline.** Run every Baseline command, plus D1. Write the numbers into the PR description. No code changes.
2. **Scope A.** Narrow handlers 1–8, add the `scaffold.py:47` comment, and add tests 50–55 to `tests/test_narrowed_excepts.py`. Run `ruff check` (BLE, S110, RUF100), `mypy src` and `pytest -q -m "not integration"`.
3. **Scope E.** `outcome.py`. Run `pytest tests/test_judge_openai.py tests/test_wire_shapes.py tests/test_judge.py -q` and `mypy src`.
4. **Scope B1.** `fixture_bind.py`, `api_skills.py`, `compare/payload.py` (+ `compare/models.py:135`), together with the `metrics.py` B2 row that B1 depends on.
5. **Scope B2.** The remaining secondary files, on the monolith line numbers. Apply the revert rule as needed, and log reverts for the scorecard.
6. **Scope C1.** Split `advice`.
7. **Scope C2.** Split `usage`.
8. **Scope C3.** Split `tool_checks`.
9. **Scope C4.** `test_public_imports.py` additions. After it, run the full unit suite plus `python -c "import skillgate_ai.mcp.server"` with the `mcp` extra, to prove MCP imports still resolve without edits.
10. **Scope D2/D3.** Add the new test files (tests 1–49, 56–58, and D3 tests if needed).
11. **Scope D4.** Raise `fail_under`.
12. **Scorecard.** Update `docs/audit-scorecard.md`.

Run `ruff check && ruff format --check && mypy src && pytest -q -m "not integration"` before every commit.

---

## Acceptance checklist

```bash
ruff check
ruff format --check
mypy src
pytest -q -m "not integration" --cov=skillgate_ai --cov-report=term-missing   # passes fail_under
pytest -q -m integration
pip-audit   # same invocation as the gate.yml `audit` job
skillgate check skills/pdf
skillgate check skills/pdf-sabotaged --expect-fail
grep -rnE 'except Exception\b' src/skillgate_ai | wc -l          # 15
grep -rn 'dict\[str, Any\]' src/skillgate_ai | wc -l             # ≤ 520 (planned 512)
grep -c 'dict\[str, Any\]' src/skillgate_ai/judge_openai/outcome.py   # ≤ 11 (planned 6)
wc -l src/skillgate_ai/*.py src/skillgate_ai/*/*.py | sort -n -r | sed -n 2p   # ≤ 600
git diff --stat cc8919a -- src/skillgate_ai/mcp plugin tests/test_wire_shapes.py src/skillgate_ai/judge_settings.py   # empty
```

- [ ] All of the above pass. CI is green on `lint`, `test-matrix` (3.11–3.13), `audit` and `analyze`.
- [ ] `test -f src/skillgate_ai/advice.py`, `usage.py` and `tool_checks.py` all fail; each is now a package directory with every file ≤ 320 lines.
- [ ] `git diff cc8919a -- tests/test_public_imports.py` shows additions only: three `REGISTRY` entries, the extended `_SPLIT_TARGETS` and one new test. `CLI_SURFACE_SHA256`, `TOP_COMMANDS` and `SUB_COMMANDS` are untouched.
- [ ] No new `# noqa`, `# type: ignore` or `cast(`: `git diff cc8919a -- src | grep -E '^\+.*(noqa|type: ignore|cast\()'` is empty.
- [ ] At least 25 new test functions; 58 are listed. Each listed test exists with the stated assertions.
- [ ] `fail_under` is raised per D4, to ≥ 84.
- [ ] Docker smoke: `docker build -t skillgate:test --target runtime . && docker run --rm -v "$PWD/skills/pdf:/pack" skillgate:test` behaves as on `cc8919a` (exits 2 when run keyless).
- [ ] The two known-flaky tests pass, or their reruns are recorded in the PR body.

---

## Scorecard update: `docs/audit-scorecard.md`

Append a new section. Do not rewrite the PR C section, except to add a footnote on its `dict[str, Any]` "After 480" row: "re-measured on `cc8919a` as 583; see PR D".

```markdown
## PR D/4 — excepts, typing, last splits, coverage

| Metric | Before (cc8919a) | After | Command |
|---|---|---|---|
| Broad `except Exception` | 23 (16 files) | 15 (all documented boundaries) | `grep -rnE 'except Exception\b' src/skillgate_ai \| wc -l` |
| `dict[str, Any]` lines (all src) | 583 | <measured> (plan 512) | `grep -rn 'dict\[str, Any\]' src/skillgate_ai \| wc -l` |
| …excluding frozen `mcp/` | 537 | <measured> | |
| `judge_openai/outcome.py` | 12 | <measured> (plan 6; cap ≤ 11) | `grep -c` |
| `fixture_bind.py` / `api_skills.py` / `compare/payload.py` | 7 / 17 / 10 | <m> / <m> / <m> (plan 3 / 14 / 4) | `grep -c` |
| `Mapping[str, Any]` lines | <step 1> | <measured> | |
| `TypedDict` classes | <step 1> | <measured> (+1 `JudgePayload`) | |
| Largest module | 715 (`tool_checks.py`) | <measured> (≤ 600) | `wc -l … \| sort -n -r` |
| Modules > 600 lines | 3 | 0 | |
| Unit coverage | 77.39% | <measured> | `pytest -m "not integration" --cov` |
| `fail_under` | 77 | <D4 value> | `pyproject.toml` |
| Unit tests passed | <step 1> | <measured> | |

### Kept broad excepts (boundaries)
| Location | Boundary |
|---|---|
| `scorers.py` ×2, `document_text.py` | untrusted file parsers (logged at debug) |
| `sandbox.py`, `live.py` ×2 | third-party sink / flush callbacks |
| `run_registry.py`, `api_compare.py` ×2 | worker threads; failure recorded on the job |
| `helper.py` ×2 | helper daemon; every target/job reports failed |
| `errors.py` | `errors()` on arbitrary exceptions |
| `harness/diagnostics.py`, `harness/messages.py` | diagnostics must not mask auth errors |
| `scaffold.py` | cleanup-and-reraise |

### Kept `dict[str, Any]` (selected)
| File | Reason |
|---|---|
| `api_skills.py` (14), `checks_show.py` routes, other `api*.py` routes | FastAPI `response_model` contract |
| `mcp/**` (46) | frozen this PR |
| `outcome.py` 146/149, 228, 248, 368/369 | `Judge.judge` protocol; mutated answers/cells |
| <every rule-6 revert, with its mypy message> | |

### Open items
- `dict[str, Any]` ≈480 target needs a wire-safe plan for FastAPI route models (OpenAPI-neutral) and an MCP typing pass
- S101 in `judge_settings.py` (separate PR)
- CodeQL alert triage / ruleset enablement (admin)
```

---

## Risks

- **Narrowed handlers surface bugs that used to be hidden.** This is intended. Tests 51, 52 and 54 pin the propagation. `live.py` `_terminate` only ever receives `subprocess.Popen`, which raises only `OSError`.
- **`dict(self._stamp(...))` copy in `OutcomeJudge.judge`.** It keeps the same keys and order, and no caller holds the pre-copy object. `test_wire_shapes.py` and `test_judge_openai.py` must pass unchanged.
- **`_listed_skill` merge.** `{**payload, ...}` keeps existing-key positions, so the JSON order of `/api/skills` is unchanged. `test_api_local.py` covers it.
- **Submodule import cycles (`usage.parse` ↔ `usage.cost`).** Use the escape hatch in C2, and confirm with `python -c "import skillgate_ai.usage, skillgate_ai.advice, skillgate_ai.tool_checks"` in a fresh interpreter.
- **Optional extras.** No new submodule may import fastapi, pypdf or similar at module level. `tests/test_optional_extras.py` must pass without the `ui`/`docs` extras.
- **Coverage differs between platforms.** Set the floor from the CI number (D4), never from the local number alone.

## PR body checklist

- [ ] States that the PR is behavior-preserving except for the 5 narrowed handlers listed in Scope A (rows 4–8), whose new behavior is pinned by tests.
- [ ] Before/after metrics copied from `docs/audit-scorecard.md`.
- [ ] D1 lowest-25 coverage table (before and after).
- [ ] List of rule-6 reverts, or "none".
- [ ] Results of reruns of the known-flaky tests, if any were needed.
- [ ] Remaining work: route-model typing plan, MCP typing pass, `judge_settings` S101, CodeQL triage.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
