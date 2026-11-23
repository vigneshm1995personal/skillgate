# Audit structure & coverage (PR C/3): behavior-preserving splits, typing, CI gates

Save as: `docs/specs/audit-structure-coverage.md`
Branch: `cursor/audit-structure-coverage` (already created). One PR, one commit per step below.

This PR moves the repo audit score from 7.7 toward 9/10. It does five things:

- **A.** Split the five largest modules into submodules. Every existing import path keeps working through a re-export shim.
- **B.** Replace `dict[str, Any]` with TypedDicts or read-only `Mapping`s in four files, wherever that can be done without changing behavior or the wire format.
- **C.** Add a coverage floor (77%), `pip-audit` and CodeQL to CI.
- **D.** Publish a before/after scorecard at `docs/audit-scorecard.md`.
- **E.** Fix one tautological test assertion.

Nothing a user can see changes: no JSON/CLI/API shape, no message, no exit code.

---

## DO-NOT-TOUCH

- `tests/test_wire_shapes.py`: no edits at all. Its golden bytes must stay byte-identical.
- JSON, CLI and HTTP API wire shapes, including dict key order. FastAPI route return annotations count as wire contract (see Scope B, "Rules").
- `src/skillgate_ai/judge_settings.py`: no edits. Its S101 bare asserts are handled in a separate PR.
- Behavior, user-facing messages, exit codes, lazy-import timing, and dependency direction between modules.
- `[tool.ruff]`, `[tool.ruff.lint]`, `per-file-ignores`, `[tool.mypy]`: no relaxations. Add no new `# noqa`, `# type: ignore` or `cast()` lines.
- `scripts/extract-from-skillgate-ai.sh`: leave as is. It already lists the pre-split `engine.py` and `cli.py`, so it is a known-stale historical script.
- Version numbers: no bump. Do not commit `.coverage`, `.spec-prompt-*.txt` or `docs/specs/_audit-structure-coverage-prompt.md`.

---

## Baseline (measured on main after #82–#84)

| Metric | Command | Baseline |
|---|---|---|
| `span_facts.py` / `pack.py` / `report.py` / `judge_spec.py` / `engine/run.py` lines | `wc -l` | 678 / 661 / 648 / 627 / 590 |
| `dict[str, Any]` **lines** in src | `grep -rn 'dict\[str, Any\]' src/skillgate_ai \| wc -l` | 516 |
| per file: `judge_openai/outcome.py`, `fixture_bind.py`, `api_skills.py`, `compare/payload.py` | `grep -c 'dict\[str, Any\]' <file>` | 26, 20, 18, 18 |
| `Mapping[str, Any]` lines in src | `grep -rn 'Mapping\[str, Any\]' src/skillgate_ai \| wc -l` | record in step 1 |
| broad excepts | `grep -rnE 'except Exception\b' src/skillgate_ai \| wc -l` | 20 |
| unit coverage | `pytest -q -m "not integration" --cov=skillgate_ai --cov-report=term` | 77% |
| unit tests | `pytest -q -m "not integration"` | 1282 passed |

The `dict[str, Any]` metric counts **lines**, not occurrences. Use exactly the commands above for both the before and after numbers.

---

## Rules for every split (Scope A)

These follow `docs/specs/split-giant-files.md`.

1. **Code moves verbatim.** Only import lines change. Each moved block keeps its decorators, docstrings, comments and the blank lines between definitions. Lazy (in-function) imports move with their function and keep their targets.
2. **The shim is the package's `__init__.py`.** For `engine/run`, it is the trimmed `run.py` itself. A shim contains:
   - the original module docstring, verbatim, plus one paragraph: "Re-export shim. Code lives in the submodules listed below. Patching a name on this shim does not affect code inside the package; patch the submodule that defines it."
   - `from __future__ import annotations`
   - re-exports written as `from skillgate_ai.X.sub import name as name`
   - no `def`, `class`, logic or `__all__`.
3. **Re-export every module-scope name defined in the old file**, private names included. The full lists are in step 1.
   - Do **not** re-export names the old file only imported: stdlib modules (`shutil`, `re`, `json`, …), `Any`, `write_pdf`, `SkillGateError`, `attr_map`, `JudgeQuestion` (from `span_facts`), and so on. A stale monkeypatch then fails loudly instead of silently doing nothing.
4. **Submodules never import their own package's `__init__`.** They import siblings directly: `from skillgate_ai.pack.pathsafe import safe_relpath`. Imports from *other* packages' shims stay as they are today (`from skillgate_ai.engine import SuiteReport`, `from skillgate_ai.judge_spec import JudgeSpec`).
5. **No submodule may share a name with a re-exported symbol.** This is enforced by `test_no_submodule_shadows_a_symbol`.
6. **Each submodule imports only what it uses.** Ruff F401 enforces this, and `ruff format` must be clean.
7. **Size cap.** Every new or remaining file in scope is ≤ 320 lines. A new test enforces this.
8. **Line ranges** below are on main and include trailing blank lines up to the next definition. "Header" means the docstring plus imports.

---

## Scope A: module splits

### A1. `span_facts.py` (678 lines) → package `src/skillgate_ai/span_facts/`

| New file | Moves (old lines) | ≈ lines |
|---|---|---|
| `span_facts/__init__.py` | shim: docstring line 1 + re-exports | ~65 |
| `span_facts/patterns.py` | 13–72: `_TOOL_TICK`, `_TOOL_CALLED`, `_SNAKE`, `_MORE_THAN_ONCE`, `_AT_MOST_ONCE`, `_NO_DUPLICATE`, `_ANSWER_NO_IF`, `_FILE`, `_REPLY`, `_RETURN`, `_STATUS`, `_WORD`, `_INVOKE_TOOLS`, `_WRITE_PAYLOAD`, `LOG_FACT_KINDS`, `_STOP` | ~65 |
| `span_facts/tools.py` | 73–193: `count_tool_calls`, `_span_invokes`, `tool_results`, `count_file_reads` | ~130 |
| `span_facts/asks.py` | 327–413: `log_fact_kind`, `_predicate`, `_primary_tool`, `_tool_candidates`, `_fact_kind`, `_primary_file`, `_count_is_yes` | ~100 |
| `span_facts/reply.py` | 414–678: `_ISSUED_RE`, `_HEDGE_RE`, `_MONEY_RE`, `_ALREADY_ISSUED_ASK`, `_NEVER_SAW_ASK`, `_CONTRADICT_ASK`, `_AMOUNT_ASK`, `_output_file`, `_reply_text`, `_parse_calls_log`, `_argv_of`, `_issue_refund_rows`, `_response_of`, `_refund_status`, `_count_from_calls_log`, `_succeeded_amounts`, `_lookup_shows_refund`, `_connector_succeeded`, `_reply_hedges`, `_reply_claims_issued`, `_compute_reply_fact`, `_wanted_status` | ~285 |
| `span_facts/resolve.py` | 194–326: `resolve_log_facts`, `apply_log_facts`, `_merge_wording_facts`, `_compute_question` | ~145 |

- **Dependency order:** `patterns` → `tools` → `asks` → `reply` → `resolve`. The graph has no cycles:
  - `asks` uses `count_tool_calls`.
  - `reply` uses `_predicate`, `_primary_tool`, `tool_results`, `_REPLY` and `_STATUS`.
  - `resolve` uses all of the above plus `_ANSWER_NO_IF`.
- **Imports:** `JudgeQuestion` and `JudgeSpec` still come from the `skillgate_ai.judge_spec` shim.
- **External readers keep working through the shim:**
  - `wording_facts.py` reads `_reply_text` with lazy imports (lines 141 and 241).
  - `judge_openai/outcome.py` reads `resolve_log_facts`.
  - `tests/test_span_facts.py` and `tests/test_wording_facts.py` also import through the shim.

### A2. `report.py` (648 lines) → package `src/skillgate_ai/report/`

| New file | Moves (old lines) | ≈ lines |
|---|---|---|
| `report/__init__.py` | shim | ~35 |
| `report/scoring.py` | 15–24 `_report_gate`; 351–417 `_judge_stamp`, `_has_choice_answers`, `scored_by_line`; 500–510 `_scoring_endpoint` | ~100 |
| `report/lines.py` | 418–499 `_GENERIC_FAILS`, `_task_fail_line`, `_named_builtin_fail`, `_task_happened`; 511–636 `_cell_answer`, `_task_check_answers`, `_source_label`, `_check_source`, `_extra_source_lines`, `_task_warnings` | ~225 |
| `report/formatting.py` | 25–175: `format_cli`, `_cost_line`, `format_github` | ~165 |
| `report/dicts.py` | 176–350: `progress_to_dict`, `report_to_dict`, `_progress_task_to_dict`, `hydrate_report_spans`, `_task_status`, `_task_to_dict`; 637–648 `_advice_to_dict` | ~200 |

- **Dependency order:** `scoring` → `lines` → `formatting` and `dicts`. Both `formatting` and `dicts` import from `scoring` and `lines`; neither imports the other.
- **External readers keep working through the shim:**
  - `api_runs`, `gate`, `compare_git`, `compare/models` and `cli/gate_output` import from it.
  - `tests/test_jev_extra_questions.py` imports `_task_happened` through it.

### A3. `judge_spec.py` (627 lines) → package `src/skillgate_ai/judge_spec/`

| New file | Moves (old lines) | ≈ lines |
|---|---|---|
| `judge_spec/__init__.py` | shim | ~50 |
| `judge_spec/model.py` | header imports 5–27 as needed; 29–48 constants `MAX_QUESTIONS`, `MAX_EXTRAS`, `RESERVED_IDS`, `QUESTION_ID_RE`, `TYPE_ALIASES`, `RESERVED_ID_MESSAGE`, `CAP_MESSAGE`, `TYPE_MESSAGE`; 50–152 `JudgeQuestion`, `JudgeSpec`, `builtin_questions`, `builtin_spec`; 475–485 `_on_fail_value` | ~175 |
| `judge_spec/parse.py` | 153–245 `resolve_judge_spec`, `parse_extra_question`; 467–474 `_extra_list`; 486–521 `_parse_choices`, `_parse_levels` | ~145 |
| `judge_spec/schema.py` | 246–271 `spec_decisions_questions`, `spec_structured_schema`; 437–466 `judge_block_to_dict`, `_extra_schema_property` | ~70 |
| `judge_spec/verdict.py` | 272–436 `spec_verdict`, `extra_block_failures`, `_NOT_APPLICABLE`, `_is_not_applicable`, `extra_question_passed`, `low_confidence_for_spec`; 522–627 the three `@overload`-decorated `_gte` defs, `coerce_extra_answer`, `_extract_probability`, `_extract_score`, `_extract_choice_value`, `_choice_passes`, `_pass_levels`, `_unusable_or_fail`, `_reason_key` | ~290 |

- **Dependency order:** `model` → `parse` → `schema` → `verdict`.
  - `model` keeps `dataclass` and `replace`.
  - `schema` imports `_extra_list` from `parse`.
  - `verdict` imports only `model` and `judge_bank`.
- **External readers keep working through the shim:** `pack_schema` reads `_on_fail_value` with lazy imports at lines 71 and 99.

### A4. `pack.py` (661 lines) → package `src/skillgate_ai/pack/`

| New file | Moves (old lines) | ≈ lines |
|---|---|---|
| `pack/__init__.py` | shim, docstring 1–12 | ~65 |
| `pack/constants.py` | 26–50 `FIXTURE_DIR`, `GOLDEN_DIR`, `ASSET_DIR`, `DEFAULT_FIXTURE_GLOB`, `CASE_SUFFIXES`, `_SKIP_DIR_NAMES`, `_SKIP_FILE_NAMES`, `_SAFE_NAME`, `IMAGE_SUFFIXES`, `PDF_DEMO_FIXTURE_NAMES`, `_UNSYNTHESIZABLE`, `_PDF_MAGIC`, `_IMAGE_MAGICS`; 465–482 `TEXT_SUFFIXES`, `PREVIEW_TEXT_LIMIT` | ~55 |
| `pack/pathsafe.py` | 164–181 `safe_relpath`; 306–322 `is_pack_relative`, `fixture_src_for`; 373–387 `implied_fixture_name`; 617–629 `_path_under_skill`; 650–661 `_rel_to_skill`, `_safe_filename` | ~85 |
| `pack/samples.py` | 52–61 `CannotSynthesizeFixture`; 210–266 `implies_photo_scan`, `as_fixture_bytes`, `is_authentic_fixture_bytes`, `cannot_synthesize_sample`, `generate_sample_bytes` | ~90 |
| `pack/listing.py` | 62–163 `list_pack_files`, `fixture_files`, `relevant_eval_fixtures`, `_glob_match`, `skill_pack_hash`; 388–403 `_is_pdf_example_dir`, `_without_leaked_pdf_demo`; 485–495 `browser_files` | ~145 |
| `pack/resolve.py` | 404–464 `_inside_other_skill`, `_accept_input_file`, `resolve_input_file`, `file_copy_from_rel` | ~70 |
| `pack/writes.py` | 182–209 `write_pack_file`; 267–305 `write_sample_fixture`, `copy_into_pack`; 323–372 `promote_file_into_pack`, `persist_case_file` | ~130 |
| `pack/tree.py` | 496–616 `copy_skill_pack`, `pack_file_path`, `pack_preview`, `_content_type`; 630–649 `_pack_copy_ignore` | ~155 |

- **Dependency order:** `constants` → `pathsafe` → `samples` → `listing` → `resolve` → `writes` → `tree`.
  - `samples` imports `write_pdf` from `skillgate_ai.demo_files` and `implied_fixture_name` from `pathsafe`.
  - `listing` uses `is_authentic_fixture_bytes` and `_rel_to_skill`.
  - `writes` uses `resolve_input_file`, `generate_sample_bytes` and others.
  - `tree` imports `shutil` and uses `list_pack_files`.
- **Patch seam (test edit, path only).** Four tests patch `"skillgate_ai.pack.shutil.copytree"`. That target resolves through `getattr(skillgate_ai.pack, "shutil")`, which no longer exists. Repoint each to `"skillgate_ai.pack.tree.shutil.copytree"`. The patch still replaces the global `shutil.copytree`, so the tests behave the same. The four sites:
  - `tests/test_sync.py:130`
  - `tests/test_helper.py:178`
  - `tests/test_deploy.py:52`
  - `tests/test_deploy.py:88`
- **`tests/test_optional_extras.py:122`:** `import skillgate_ai.pack` must still work without the ui/docs extras. No submodule may import fastapi, pypdf and the like at module level.

### A5. `engine/run.py` (590 lines) → `run.py` + three sibling submodules

`engine` is already a package, and `engine/run.py` stays a module because it holds the `open_sandbox` patch seam.

| File | Contents (old lines) | ≈ lines |
|---|---|---|
| `engine/run.py` (kept) | header 1–31 trimmed; 173–242 `_run_tasks_loop`; 330–425 `run_eval`; plus re-exports `from skillgate_ai.engine.run_<x> import name as name` for every moved helper | ~210 |
| `engine/run_progress.py` | 481–590 `_emit_progress`, `_eval_progress` | ~120 |
| `engine/run_setup.py` | 32–59 `_load_eval_inputs`; 103–172 `_eval_bootstrap`, `_eval_run_preamble`; 434–480 `_resolve_path`, `_reference_twin`, `_resolve_pack_stamp` | ~160 |
| `engine/run_finish.py` | 60–102 `_fill_killed`, `_sliced_report`; 243–329 `_eval_finish`, `_complete_suite_report`; 426–433 `_suite_passed` | ~150 |

- **Seam stays put.** `tests/test_engine.py:1134` patches `"skillgate_ai.engine.run.open_sandbox"`. `_run_tasks_loop` stays in `run.py` and keeps reading the module-global `open_sandbox`, so this target is **unchanged**.
- **`engine/__init__.py` lines 21–26:** import each helper from its new home.
  - `_emit_progress` and `_eval_progress` from `engine.run_progress`.
  - `_reference_twin`, `_resolve_pack_stamp` and `_resolve_path` from `engine.run_setup`.
  - `_suite_passed` from `engine.run_finish`.
  - Line 27 (`run_eval`) stays on `engine.run`.
  - Keep the statements in their current position and order.
- **Dependency order:** `run_progress` → `run_setup` (uses `_emit_progress`) → `run_finish` → `run`.
  - `run_setup` imports `default_judge`, `load_suite`, `ingest_skill` and `ingest_skills`.
  - `run_finish` imports `advise_suite`.
  - `run.py` keeps `open_sandbox`, `_run_task`, `task_timeout_sec` and `RunControl`.

---

## Scope B: typing

### Rules

1. **FastAPI route return annotations stay `dict[str, Any]`.** FastAPI uses the return annotation as its `response_model`. A TypedDict would make pydantic validate the response and drop unknown keys, which changes the wire format and the OpenAPI schema.
2. **Protocol and boundary signatures stay as they are:**
   - `Judge.judge` (`judge.py:25`, and `OutcomeJudge.judge` with its `artifacts` parameter)
   - `CompareResult.payload`
   - `metrics_blocking` and `budget_gate_reason` (they take `dict[str, Any]`)
   - any function whose result is mutated or returned into a `dict[str, Any]` slot.

   mypy does not treat a TypedDict as assignable to `dict[str, Any]`.
3. **Read-only parameters become `Mapping[str, Any]` or `Sequence[Mapping[str, Any]]`.** Locally built shapes become TypedDicts. Runtime code stays the same, including `isinstance(x, dict)` checks, so behavior is identical.
4. **No disguises:** no `cast()`, no type alias for `dict[str, Any]`, no `# type: ignore`. If mypy forces a line to stay, keep it and list it in the scorecard.
5. **New TypedDicts live in the file that builds them.** Do not add them to any package shim.

### B1. `src/skillgate_ai/judge_openai/outcome.py` (26 → ≤ 11 lines)

Add `JudgeQuestion` to the existing `skillgate_ai.judge_spec` import. Add `NotRequired` and `TypedDict` to the `typing` import, and `Sequence` to the `collections.abc` import.

```python
class ExtraCell(TypedDict):
    label: str
    choice: str | None
    reason: str | None
    source: NotRequired[str]
    probability: NotRequired[float]
    score: NotRequired[Any]
    status: NotRequired[str]


class JudgeUsageSum(TypedDict):
    tokens_in: int | None
    tokens_out: int | None
    tokens_total: int | None
    cost_usd: float | None
```

| Line | Change |
|---|---|
| 43 | `def _extra_cell(question: JudgeQuestion, raw: Any) -> tuple[ExtraCell, dict[str, Any] \| None]:` (stays counted: `cleaned` is a raw passthrough that gets mutated) |
| 44 | `cell: ExtraCell = {` (−1) |
| 270, 271, 272, 275, 276 | `_payload` parameters `soft_answers`, `cells`, `citations`, `questions`, `soft_questions` → `Mapping[str, Any]` (−5) |
| 313, 314 | `_stamp_error` parameters `citations`, `soft_questions` → `Mapping[str, Any]` (−2) |
| 345, 346 | `_verdict_cells` parameters `pass_answers`, `soft_answers` → `Mapping[str, Any]` (−2) |
| 350, 351 | `-> dict[str, dict[str, Any] \| ExtraCell]` and `cells: dict[str, dict[str, Any] \| ExtraCell] = {}`. Required because line 413 stores an `ExtraCell` in `cells`. Both lines stay counted. |
| 369, 370 | `_stamp` parameters `artifacts`, `omitted` → `Sequence[Mapping[str, Any]]` (−2) |
| 391 | `answers: Mapping[str, Any] = …` (−1). `spec_verdict` and `extra_block_failures` already take `Mapping`. |
| 483 | `def _sum_judge_usage(rounds: list[Mapping[str, Any]]) -> JudgeUsageSum \| None:` (−1) |
| kept | 128 and 131 (protocol), 210 (mutated), 230, 278, 316, 450, 455 (returned or mutated payloads) |

### B2. `src/skillgate_ai/fixture_bind.py` (20 → ≤ 7 lines)

Add `NotRequired`-free `TypedDict` to the `typing` import and `Mapping`/`Sequence` from `collections.abc`.

```python
class FileCopy(TypedDict):
    src: str
    dest: str
```

| Line | Change |
|---|---|
| 32, 36, 44 | `check: Mapping[str, Any]` (−3) |
| 48 | `def file_copies(fixtures: Sequence[Mapping[str, Any]]) -> list[FileCopy]:` (−1). Its only caller is in this file. |
| 54, 81 | `checks: Sequence[Mapping[str, Any]] \| None` (−2) |
| 116, 117 | `checks: Sequence[Mapping[str, Any]] \| None`, `report: Mapping[str, Any] \| None` (−2) |
| 134 | `report: Mapping[str, Any] \| None` (−1) |
| 167, 186, 208 | `checks: Sequence[Mapping[str, Any]] \| None` (−3) |
| 232 | `report: Mapping[str, Any] \| None` (−1) |
| 240 | `def _template_check(checks: Sequence[Mapping[str, Any]], description: str) -> dict[str, Any]:` (stays counted: return value) |
| kept | 60 and 85 (callers get mutable dicts back), 93 (`created` is concatenated with dicts), 166, 185, 207 (`report` flows into `metrics_blocking`, which takes `dict`) |

Callers in `api_evals.py:175–177` and `pack_edit.py:175–177` pass `list[dict]`, which is compatible. No caller edits are needed.

### B3. `src/skillgate_ai/api_skills.py` (18 → ≤ 17 lines)

Most of this file is FastAPI route returns, which Rule 1 freezes. Import `AppState` from `skillgate_ai.api_payloads`.

```python
class BrokenSkillRow(TypedDict):
    id: str
    name: str
    slug: str
    description: str
    warning: str
    path: str
    absolute: str
    uploaded: bool
    seed: bool
    sabotaged: bool
    gate: str
    pack_files: list[Mapping[str, Any]]
    source: NotRequired[str]
    source_label: NotRequired[str]
```

| Line | Change |
|---|---|
| 53 | `def _broken_skill_row(item: Mapping[str, Any]) -> BrokenSkillRow:` (−1) |
| 71 | `def _listed_skill(state: AppState, item: Mapping[str, Any]) -> dict[str, Any] \| BrokenSkillRow:`; first body line `payload: dict[str, Any] \| BrokenSkillRow` (net +1) |
| 84 | `def _listed_skills(state: AppState) -> list[dict[str, Any] \| BrokenSkillRow]:` (stays counted) |
| 96 | `body: Mapping[str, Any] = {}` (−1) |
| kept | 90, 94, 115, 124, 128, 150, 168, 178, 213, 222, 232, 239, 266, 275 (route `response_model`s) |

The real gain here is that `state: Any` becomes `AppState` and broken skill rows get a checked shape. Record that in the scorecard.

### B4. `src/skillgate_ai/compare/payload.py` (18 → ≤ 10 lines)

```python
class CompareCell(TypedDict):
    passed: bool | None
    usage: NotRequired[dict[str, int | float]]
    duration_sec: NotRequired[float]


class CompareCaseRow(TypedDict):
    case_id: str
    results: dict[str, CompareCell]
    disagreement: bool


class ComparePlanArm(TypedDict):
    arm_id: str
    label: str
    subtitle: str
    source: str
    passed_count: int | None
    task_count: int
    usage: Mapping[str, Any] | None
    duration_sec: float | None
```

| Line | Change |
|---|---|
| 14 | `report: Mapping[str, Any]` (return stays `dict[str, Any] \| None`, a passthrough of stored report usage; line stays counted) |
| 22 | `usage: Mapping[str, Any] = …` (−1) |
| 47, 60 | annotate the locals `arm_rows: list[ComparePlanArm]` and `cases: list[CompareCaseRow]`. The literals are unchanged. Return stays `dict[str, Any]` (`CompareResult.payload`). |
| 87 | `report: Mapping[str, Any]` (−1) |
| 99, 106 | parameter → `Mapping[str, Any] \| None`. Keep the `isinstance(report, dict)` checks. Returns are kept, so both lines stay counted. |
| 119 | `def _build_cases(arms: Sequence[Mapping[str, Any]], case_ids: list[str]) -> list[CompareCaseRow]:` (−1). All three callers (`compare/models.py:173`, `compare/versions.py:307`, `compare_git.py:236`) place the result in a `dict[str, Any]` value. |
| 120, 122, 128 | `rows: list[CompareCaseRow]`, `results: dict[str, CompareCell]`, `cell: CompareCell` (−3) |
| 203, 213 | `report: Mapping[str, Any]` (−2) |
| kept | 31, 112, 146, 169, 179, 214 |

**Expected total:** 516 → about 479 `dict[str, Any]` lines. `Mapping[str, Any]` lines go up by about 30. Report both numbers.

---

## Scope C: CI and security gates

### C1. `pyproject.toml`

```toml
dev = [
  "skillgate-ai[all]",
  "pytest>=8.2",
  "pytest-cov>=5.0",
  "pytest-timeout>=2.3",
  "ruff>=0.5",
  "mypy>=1.10",
  "pre-commit>=4.0",
  "pip-audit>=2.7",
]
```

Append after `[tool.mypy]`:

```toml
[tool.coverage.run]
source = ["skillgate_ai"]

[tool.coverage.report]
fail_under = 77
precision = 2
skip_covered = true
```

- **Do not add `--cov` to `addopts`.** The integration-only run (`pytest -m integration tests/integration`) would then trip `fail_under`.
- **Regenerate the lock** with `uv lock`, without `--upgrade`. The `uv.lock` diff may only *add* `pytest-cov`, `coverage`, `pip-audit` and their transitive packages. No version already pinned may change; check with `git diff uv.lock | grep '^-version'`, which must be empty.
- **`.gitignore`:** append `.coverage`, `.coverage.*`, `coverage.xml` and `htmlcov/`.

### C2. `.github/workflows/gate.yml`

Replace the last step of `test-matrix` (line 87, `- run: pytest -q -m "not integration"`) with:

```yaml
      - if: matrix.python-version != '3.12'
        run: pytest -q -m "not integration"
      - if: matrix.python-version == '3.12'
        name: Unit tests with coverage floor (fail_under in pyproject)
        run: pytest -q -m "not integration" --cov --cov-report=term
```

Add a new job after `integration`. It reuses the exact pinned SHAs already in this file:

```yaml
  audit:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
        with:
          ref: ${{ inputs.ref || github.ref }}
      - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065 # v5.6.0
        with:
          python-version: "3.12"
      - uses: astral-sh/setup-uv@1db35dd8eee11c5894872e0b383ae6c406cf738d # v10.4.0
        with:
          version: ${{ env.UV_VERSION }}
          enable-cache: true
          cache-dependency-glob: "uv.lock"
          cache-suffix: py3.12-${{ github.job }}
      - run: uv sync --locked --extra dev --python 3.12
      - run: echo "$PWD/.venv/bin" >> "$GITHUB_PATH"
      - name: Export locked dependency set (all extras, hashed)
        run: uv export --locked --all-extras --no-emit-project --format requirements-txt -o "$RUNNER_TEMP/audit-requirements.txt"
      - name: pip-audit (fail on any known vulnerability)
        run: pip-audit --strict --disable-pip --require-hashes -r "$RUNNER_TEMP/audit-requirements.txt"
```

If pip-audit reports a vulnerability that has a fix, bump that package with `uv lock --upgrade-package <name>` in the same commit. Use `--ignore-vuln <ID>` only when no fixed version exists, and record the ID and reason in the scorecard.

### C3. New `.github/workflows/codeql.yml` and `.github/codeql/codeql-config.yml`

```yaml
name: codeql

on:
  push:
    branches: [main]
  pull_request:
  schedule:
    - cron: "17 4 * * 1"

permissions:
  contents: read

concurrency:
  group: codeql-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}

jobs:
  analyze:
    name: analyze (${{ matrix.language }})
    runs-on: ubuntu-latest
    timeout-minutes: 30
    permissions:
      contents: read
      security-events: write
      actions: read
    strategy:
      fail-fast: false
      matrix:
        language: [python, javascript-typescript, actions]
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
      - uses: github/codeql-action/init@<SHA> # v<X.Y.Z>
        with:
          languages: ${{ matrix.language }}
          build-mode: none
          config-file: ./.github/codeql/codeql-config.yml
      - uses: github/codeql-action/analyze@<SHA> # v<X.Y.Z>
        with:
          category: "/language:${{ matrix.language }}"
```

**Pinning.** Pin both `codeql-action` steps to the same commit SHA of the latest release tag at implementation time. Resolve it with:

```bash
gh api repos/github/codeql-action/releases/latest --jq .tag_name
gh api repos/github/codeql-action/commits/<tag> --jq .sha
```

Never type in a SHA from memory.

`codeql-config.yml`:

```yaml
name: skillgate
queries:
  - uses: security-extended
paths-ignore:
  - src/skillgate_ai/web_static
  - src/skillgate_ai/examples
  - skills
  - tests
```

**How CodeQL gates PRs.** The analysis job fails on extractor or analysis errors. Alerts block merges through GitHub's code-scanning merge protection, which needs a maintainer action after this PR merges, once main has a baseline analysis. Without a main baseline, every pre-existing alert would count as "new" on this PR. The steps:

1. Merge this PR, then confirm the `codeql` run on `main` is green.
2. Repo Settings → Rules → Rulesets → branch `main`:
   - "Require code scanning results": tool `CodeQL`, Security alerts `High or higher`, Alerts `Errors`.
   - "Require status checks": add `analyze (python)`, `analyze (javascript-typescript)`, `analyze (actions)` and `audit`.
3. Triage the pre-existing alerts in the Security tab. Fixing them is out of scope here; list counts in the scorecard.

Name these steps in the PR body as **manual, admin-only**. The implementer does not change repo settings.

### C4. Docs

Add to the `AGENTS.md` Commands block, after `pytest -q`:

```
pytest -q -m "not integration" --cov   # coverage floor from pyproject
```

Add the same line to `CONTRIBUTING.md` wherever its test commands are listed.

---

## Scope D: `docs/audit-scorecard.md` (new)

Structure:

1. **Summary:** one paragraph. The PR is behavior-preserving, and it lists the metrics that moved.
2. **Metrics table:** columns Metric | Before | After | Command. Rows:
   - each of the five files' line counts, and after the split the largest file in each new package
   - largest `.py` in `src/skillgate_ai` (top 10 from `find src/skillgate_ai -name '*.py' -not -path '*/examples/*' -exec wc -l {} + | sort -n | tail -n 11`)
   - `dict[str, Any]` lines, total and for the four Scope B files
   - `Mapping[str, Any]` lines
   - TypedDict classes (`grep -rnE 'class \w+\(TypedDict' src/skillgate_ai | wc -l`)
   - broad excepts (20 → 20; unchanged here and tracked separately)
   - unit coverage %, using the exact two-decimal number from `--cov-report=term`
   - unit test count
3. **Kept `dict[str, Any]` lines:** a table of each remaining line in the four files with its reason (FastAPI response contract, Judge protocol, `CompareResult` boundary, mutated passthrough).
4. **Scanners and gates:**

   | Scanner | Where | Blocks merge |
   |---|---|---|
   | ruff (incl. S, BLE) | `gate.yml` lint job | ✅ |
   | mypy (`check_untyped_defs`) | lint | ✅ |
   | pytest unit + integration | 3.11/3.12/3.13 | ✅ |
   | coverage ≥ 77% | `test-matrix` 3.12 | ✅ |
   | pip-audit (locked, hashed) | `audit` | ✅ |
   | CodeQL python, js/ts, actions | `codeql.yml` | ✅ via ruleset (manual step) |
   | pinned action SHAs and `uv.lock` | all workflows | — |
5. **Open items:**
   - S101 asserts in `judge_settings.py` (separate PR)
   - 20 broad excepts
   - CodeQL baseline alert counts
   - enabling the ruleset
   - raising the coverage floor in a later PR

---

## Scope E: test fix

In `tests/test_judge_home_fallback.py::test_api_get_judge_returns_home`:

- After line 343, add `home_before = home_path.read_bytes()`.
- Replace line 350 with `assert home_path.read_bytes() == home_before`.

No other edits. Sanity check, local only and not committed: temporarily change the PUT handler's target to the home path, confirm the test now fails, then revert.

---

## New and changed tests

All in `tests/test_public_imports.py`, added in step 1 so they are written against the flat modules first.

**`REGISTRY` additions.** These are every module-scope name defined in each old file.

```python
"skillgate_ai.span_facts": (
    "_TOOL_TICK", "_TOOL_CALLED", "_SNAKE", "_MORE_THAN_ONCE", "_AT_MOST_ONCE",
    "_NO_DUPLICATE", "_ANSWER_NO_IF", "_FILE", "_REPLY", "_RETURN", "_STATUS", "_WORD",
    "_INVOKE_TOOLS", "_WRITE_PAYLOAD", "LOG_FACT_KINDS", "_STOP", "count_tool_calls",
    "_span_invokes", "tool_results", "count_file_reads", "resolve_log_facts",
    "apply_log_facts", "_merge_wording_facts", "_compute_question", "log_fact_kind",
    "_predicate", "_primary_tool", "_tool_candidates", "_fact_kind", "_primary_file",
    "_count_is_yes", "_ISSUED_RE", "_HEDGE_RE", "_MONEY_RE", "_ALREADY_ISSUED_ASK",
    "_NEVER_SAW_ASK", "_CONTRADICT_ASK", "_AMOUNT_ASK", "_output_file", "_reply_text",
    "_parse_calls_log", "_argv_of", "_issue_refund_rows", "_response_of", "_refund_status",
    "_count_from_calls_log", "_succeeded_amounts", "_lookup_shows_refund",
    "_connector_succeeded", "_reply_hedges", "_reply_claims_issued", "_compute_reply_fact",
    "_wanted_status",
),
"skillgate_ai.report": (
    "_report_gate", "format_cli", "_cost_line", "format_github", "progress_to_dict",
    "report_to_dict", "_progress_task_to_dict", "hydrate_report_spans", "_task_status",
    "_task_to_dict", "_judge_stamp", "_has_choice_answers", "scored_by_line",
    "_GENERIC_FAILS", "_task_fail_line", "_named_builtin_fail", "_task_happened",
    "_scoring_endpoint", "_cell_answer", "_task_check_answers", "_source_label",
    "_check_source", "_extra_source_lines", "_task_warnings", "_advice_to_dict",
),
"skillgate_ai.judge_spec": (
    "MAX_QUESTIONS", "MAX_EXTRAS", "RESERVED_IDS", "QUESTION_ID_RE", "TYPE_ALIASES",
    "RESERVED_ID_MESSAGE", "CAP_MESSAGE", "TYPE_MESSAGE", "JudgeQuestion", "JudgeSpec",
    "builtin_questions", "builtin_spec", "resolve_judge_spec", "parse_extra_question",
    "spec_decisions_questions", "spec_structured_schema", "spec_verdict",
    "extra_block_failures", "_NOT_APPLICABLE", "_is_not_applicable", "extra_question_passed",
    "low_confidence_for_spec", "judge_block_to_dict", "_extra_schema_property", "_extra_list",
    "_on_fail_value", "_parse_choices", "_parse_levels", "_gte", "coerce_extra_answer",
    "_extract_probability", "_extract_score", "_extract_choice_value", "_choice_passes",
    "_pass_levels", "_unusable_or_fail", "_reason_key",
),
"skillgate_ai.pack": (
    "FIXTURE_DIR", "GOLDEN_DIR", "ASSET_DIR", "DEFAULT_FIXTURE_GLOB", "CASE_SUFFIXES",
    "_SKIP_DIR_NAMES", "_SKIP_FILE_NAMES", "_SAFE_NAME", "IMAGE_SUFFIXES",
    "PDF_DEMO_FIXTURE_NAMES", "_UNSYNTHESIZABLE", "_PDF_MAGIC", "_IMAGE_MAGICS",
    "CannotSynthesizeFixture", "list_pack_files", "fixture_files", "relevant_eval_fixtures",
    "_glob_match", "skill_pack_hash", "safe_relpath", "write_pack_file", "implies_photo_scan",
    "as_fixture_bytes", "is_authentic_fixture_bytes", "cannot_synthesize_sample",
    "generate_sample_bytes", "write_sample_fixture", "copy_into_pack", "is_pack_relative",
    "fixture_src_for", "promote_file_into_pack", "persist_case_file", "implied_fixture_name",
    "_is_pdf_example_dir", "_without_leaked_pdf_demo", "_inside_other_skill",
    "_accept_input_file", "resolve_input_file", "file_copy_from_rel", "TEXT_SUFFIXES",
    "PREVIEW_TEXT_LIMIT", "browser_files", "copy_skill_pack", "pack_file_path", "pack_preview",
    "_content_type", "_path_under_skill", "_pack_copy_ignore", "_rel_to_skill",
    "_safe_filename",
),
"skillgate_ai.engine.run": ("run_eval", "_run_tasks_loop"),
```

**`PASS_THROUGH` addition:**

```python
"skillgate_ai.engine.run": (
    "_load_eval_inputs", "_fill_killed", "_sliced_report", "_eval_bootstrap",
    "_eval_run_preamble", "_eval_finish", "_complete_suite_report", "_suite_passed",
    "_resolve_path", "_reference_twin", "_resolve_pack_stamp", "_emit_progress",
    "_eval_progress",
),
```

Before committing step 1, cross-check these lists with a one-off AST scan of `ast.Module.body` (Assign, AnnAssign, FunctionDef, ClassDef) for each flat file. Do not commit the scan script.

**New test: `test_split_modules_under_line_cap`.** It checks that every `.py` under these paths has ≤ 320 lines:

- `src/skillgate_ai/span_facts/`
- `src/skillgate_ai/report/`
- `src/skillgate_ai/judge_spec/`
- `src/skillgate_ai/pack/`
- `src/skillgate_ai/engine/run.py`
- `src/skillgate_ai/engine/run_*.py`

Paths that don't exist yet are skipped, so the test passes in step 1 and bites as each split lands.

```python
_SPLIT_TARGETS = ("span_facts", "report", "judge_spec", "pack")


def test_split_modules_under_line_cap() -> None:
    files = [p for t in _SPLIT_TARGETS if (SRC / t).is_dir() for p in (SRC / t).glob("*.py")]
    files += sorted((SRC / "engine").glob("run*.py"))
    for path in files:
        lines = len(path.read_text(encoding="utf-8").splitlines())
        assert lines <= 320, f"{path.relative_to(SRC)}: {lines} lines"
```

The existing tests then cover the rest automatically:

- `test_symbol_importable` checks the shims.
- `test_defined_symbols_belong_to_their_module` checks that each owner is `pkg` or `pkg.*`. This is why the engine helpers sit in REGISTRY under `skillgate_ai.engine` and in PASS_THROUGH under `engine.run`.
- `test_no_submodule_shadows_a_symbol` checks submodule names.
- `test_shims_hold_no_code` checks the new `__init__.py` files.

---

## Step order (one commit each; every commit passes all Acceptance commands)

1. `test: lock import surface of span_facts/report/judge_spec/pack/engine.run` adds the REGISTRY/PASS_THROUGH entries and `test_split_modules_under_line_cap`. Also record the `Mapping[str, Any]` baseline.
2. `test: assert home judge bytes unchanged after PUT` (Scope E).
3. `refactor: split span_facts into package` (A1).
4. `refactor: split report into package` (A2).
5. `refactor: split judge_spec into package` (A3).
6. `refactor: split pack into package` (A4), including the four `shutil` patch-path edits.
7. `refactor: split engine/run helpers into run_setup/run_progress/run_finish` (A5), including the `engine/__init__.py` repoint.
8. `typing: TypedDicts and read-only Mappings in outcome/fixture_bind/api_skills/compare payload` (B1–B4).
9. `ci: pytest-cov floor 77%, pip-audit job` covers C1, C2, C4, `uv.lock` and `.gitignore`.
10. `ci: CodeQL workflow (python, js/ts, actions)` (C3).
11. `docs: audit scorecard` (D), measured on the final tree. This also commits this spec file.

---

## Acceptance criteria

- [ ] All of these pass at every commit:
  ```bash
  ruff check
  ruff format --check
  mypy src
  pytest -q -m "not integration"
  pytest -q -m integration tests/integration
  skillgate check skills/pdf-sabotaged --expect-fail
  ```
- [ ] `pytest -q -m "not integration" --cov` passes, with total ≥ 77.00%. The unit test count is 1282 + the new parametrized cases. No test is skipped or deselected that wasn't before.
- [ ] `git diff main -- tests/test_wire_shapes.py src/skillgate_ai/judge_settings.py` is empty.
- [ ] `git diff main --stat -- tests/` shows edits only in:
  - `test_public_imports.py`
  - `test_judge_home_fallback.py`
  - `test_sync.py`, `test_helper.py`, `test_deploy.py` (patch path only)
- [ ] `test -f src/skillgate_ai/span_facts.py`, `report.py`, `judge_spec.py` and `pack.py` all fail; each is now a package directory.
- [ ] `grep -rn '"skillgate_ai.pack.shutil' tests` is empty.
- [ ] `grep -rnE '^(def |class )' src/skillgate_ai/{span_facts,report,judge_spec,pack}/__init__.py` is empty.
- [ ] No file covered by the line-cap test is over 320 lines.
- [ ] `dict[str, Any]` line counts are at or below: outcome 11, fixture_bind 7, api_skills 17, compare/payload 10. The total is reported in the scorecard.
- [ ] No new `cast(`, `type: ignore` or `noqa`: `git diff main -U0 -- src | grep -E '^\+.*(cast\(|type: ignore|noqa)'` is empty.
- [ ] `uv lock --locked` passes, and no existing locked version changed.
- [ ] On the PR, these CI checks are green:
  - `lint`
  - `test (3.11|3.12|3.13)` (the 3.12 leg prints the coverage table)
  - `integration`
  - `gate`
  - `web-build`
  - `oss-surface`
  - `docker`
  - `audit`
  - `analyze (python|javascript-typescript|actions)`
- [ ] Docker smoke: `docker build -t skillgate:test --target runtime . && docker run --rm -v "$PWD/skills/pdf:/pack" skillgate:test` exits 2 when run keyless, as today.
- [ ] `docs/audit-scorecard.md` exists with measured before/after numbers and the scanner table.

## Risks

- **Silent no-op monkeypatches.** The only seams are the four `shutil` targets (repointed) and `engine.run.open_sandbox` (unchanged). Shims don't re-export stdlib names, so any stale target raises `AttributeError`.
- **Partially initialized packages.** Submodules import only their siblings, never their own `__init__`.
- **FastAPI response models.** Rule B1 freezes route annotations, so the OpenAPI schema and responses stay byte-identical.
- **Coverage differs between platforms.** The 77% baseline was measured locally. If CI on Linux 3.12 measures below 77.00, do **not** lower the floor. Find which tests are platform-skipped, record the finding, and raise it in the PR.
- **CodeQL's first run reports old alerts as new.** Turn on the ruleset only after main has a baseline analysis (see C3).

## PR body checklist

- [ ] Behavior-preserving. Wire goldens untouched.
- [ ] Before/after metrics copied from `docs/audit-scorecard.md`.
- [ ] Manual admin steps listed (ruleset and required checks).
- [ ] Remaining work listed: `judge_settings` S101, broad excepts, CodeQL alert triage, raising the coverage floor.
