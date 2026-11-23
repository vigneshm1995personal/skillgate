# SPEC: Typing and lint hardening (PR B of 3): `check_untyped_defs`, TypedDict hot spots, ruff `BLE` + `S`

**Repo:** skillgate (OSS) · **Package:** `skillgate-ai` (`src/skillgate_ai/`) · **Base:** `main` @ `33dc044` ("security: block symlink workspace escape in catalog (#82)") · **Branch:** `cursor/audit-typing-lint-6ac4`
**Source brief:** re-audit 2026-11-22 (summary form). The baseline numbers below were re-measured on `main`. Where they differ from the brief, the measured numbers win.
**Sibling PRs:** PR A (done: security/retries, typing overrides, CI lockfile, code-quality split). **PR C** (next) owns coverage, CI scanning (bandit, pip-audit, CodeQL), and workflow changes. None of that is in this PR.

---

## 0. Baseline (measured on `main` @ `33dc044`)

| Metric | Command | Value |
|---|---|---|
| `dict[str, Any]` lines in `src/` | `rg -c "dict\[str, Any\]" src` (sum) | **553 lines in 71 modules**. The brief said "~600". |
| Worst files | same | `judge_context.py` 27, `judge_openai/outcome.py` 26, `spans.py` 24, `api_payloads.py` 23, `metrics.py` 22, `fixture_bind.py` 20, `api_skills.py` 18, `compare/payload.py` 18 |
| `except Exception` / `except BaseException` | `rg -n "except (Exception\|BaseException)" src tests` | **31 textual matches**: 28 in `src/` code, 1 in `tests/` code, 2 inside string literals in `tests/test_optional_extras.py` |
| mypy | `mypy src` | passes. `check_untyped_defs = false` (`pyproject.toml:135`), `warn_unused_ignores = true` (`:136`) |
| ruff select | `pyproject.toml:114` | `["E", "W", "F", "I", "UP", "B", "SIM"]`. No `BLE`, no `S`. |
| ruff pin | `.pre-commit-config.yaml:11` | `v0.17.6` |

### 0.1 Correction to the re-audit claim about `check_untyped_defs`

`check_untyped_defs` only affects functions with **no annotation at all**: no parameter annotations and no return annotation. A signature-level scan of every `def` in `src/` finds exactly **one** such function:

- `src/skillgate_ai/helper.py:69`: `_StripAuthRedirectHandler.redirect_request(self, req, fp, code, msg, headers, newurl)`

`harness/selection.py:25 _read_selection(workspace: Path)` is **not** unannotated. Its parameter is annotated, so mypy already checks its body today. Its return type is implicitly `Any`, and that is a weakness. This spec fixes it in §5.2 because the re-audit names it, but it is not a `check_untyped_defs` error.

Expected new mypy errors from flipping the flag alone: **0–1, all in `helper.py:69–85`.** Step 1 measures the real number and records it in the PR description.

---

## 1. Goals

1. **(a)** `pyproject.toml`: `check_untyped_defs = true`. `mypy src` passes. There are no blanket ignores and no new `# type: ignore`.
2. **(b)** Replace loose `dict[str, Any]` with `TypedDict`s at the hot spots where this repo **builds** the shape: `spans.py`, `judge_context.py`, `api_payloads.py`, `metrics.py`, `judge.py` (JudgeStamp), plus the direct consumers that must change type with them. Runtime objects stay plain `dict`s, so JSON output is byte-identical.
3. **(c)** `ruff` selects `BLE` and `S`. Every finding is fixed in one of two ways:
   - narrow the `except` to a specific exception tuple, or
   - keep a broad catch at a real boundary with a written justification (`# noqa: CODE - reason`), plus `_LOG.debug(..., exc_info=True)` where the failure is otherwise silent.

## 2. Ground rules (apply to every step)

### Allowed change patterns

These are the PR A patterns.

- **P-A:** hoist and narrow (`raw = d.get("k")`, then `v: T = raw if isinstance(raw, T) else default`).
- **P-B:** honest annotation.
- **P-C:** local rename on redefinition.
- **P-D:** `cast("T", x)` with a one-line `#` comment stating the invariant.
- **P-E:** `@overload`.
- **P-F (new):** replace `row.get("k")` with `row["k"]` **only** where `row` is a TypedDict built in the same function and `"k"` is a required key that is always present. The value is identical at runtime.

### TypedDict rules

- Use TypedDicts for shapes this code **constructs**.
- Parsed external JSON (harness JSONL, LLM responses, history files, HTTP bodies) stays `dict[str, Any]` or `Mapping[str, Any]` on input. Do not invent types for untrusted input.

### Public contract rules

- Never change the return annotation of a FastAPI route function. FastAPI derives `response_model` from it and would validate or filter the output. See §10.
- Never use a TypedDict from this PR as a pydantic field or FastAPI parameter/return annotation.

### Comments and suppressions

- **No new `# type: ignore`.** If one seems unavoidable, stop and record it in the PR description with code and reason.
- Every `# noqa` added or touched for `BLE001` or `Sxxx` has the form `# noqa: CODE[, CODE] - <reason>`.
  - The reason is written in plain English.
  - If that makes the line exceed 100 characters and `E501` fires, put the reason on its own `# BLE001: <reason>` / `# S603: <reason>` comment line directly above, and keep `# noqa: CODE` on the line.
- Place each `noqa` on the **exact line ruff reports** (`ruff check --output-format concise`). For a multi-line `subprocess.run(` call, `S603` reports on the `subprocess.run(` line and `S607` reports on the argv-literal line.

### Logging convention

Use the same convention as `http_retry.py:35` and `openai_http.py:21`: a module-level `_LOG = logging.getLogger(__name__)`.

- Use `.debug(..., exc_info=True)` only.
- Never use `.exception()`, `.error()` or `.warning()`. Python's last-resort handler prints WARNING and above to stderr, which would be a visible behavior change.

---

## 3. Step order (dependencies first; one commit per step; every commit passes `pytest -q -m "not integration"`)

| Step | Commit title | Depends on |
|---|---|---|
| 0 | `test: golden wire-shape tests for spans/judge_context/metrics/judge stamp/api_payloads` | none (must pass on unmodified `main`) |
| 1 | `typing: enable check_untyped_defs; annotate redirect_request; typed selection sentinel` | 0 |
| 2 | `typing: OTLP span TypedDicts in spans.py` | 1 |
| 3 | `typing: judge_context TypedDicts (+ verdict ScorerRow)` | 2 (uses `AttrValue`, widened `attr_map`) |
| 4 | `typing: metrics TypedDicts (+ TaskReport/TaskProgress.metrics)` | 1 |
| 5 | `typing: api_payloads row TypedDicts` | 1 |
| 6 | `typing: JudgeStamp TypedDict; widen EvalRunConfig.judge` | 1 |
| 7 | `lint: narrow broad excepts (BLE001) + tests` | 1 |
| 8 | `lint: enable ruff BLE + S; justified noqa; tests/ per-file ignore` | 7 |
| 9 | `docs: add docs/specs/audit-typing-lint.md` (this file) | none |

- Run `mypy src` after every step from 1 onward. Its error count must be 0 at the end of each step.
- Steps 2–6 are independent of each other except 3→2. Land them in the order shown.

---

## 4. Step 0: golden wire-shape tests (write first; green on `main`)

Create `tests/test_wire_shapes.py`. Each test builds deterministic input, calls the producer, and compares `json.dumps(result)` (default separators, `sort_keys=False`, so key order is part of the contract) to a **string literal captured from unmodified `main`**.

**Capture procedure (deterministic):**

1. Write each test with `EXPECTED_* = "<placeholder>"`.
2. Run `pytest tests/test_wire_shapes.py -q`. It fails and prints the actual JSON.
3. Paste the printed value into the constant.
4. Re-run until green.
5. Commit with no `src/` changes.

These constants must never be edited in steps 1–8.

### 4.1 `test_spans_from_jsonl_golden`

- Monkeypatch `skillgate_ai.spans._id` with a counter: `lambda nbytes=8: f"id{next(counter):02d}"` where `counter = itertools.count()`.
- Monkeypatch `skillgate_ai.spans._now_ns` → `lambda: 1_700_000_000_000_000_000`.
- Input is these 10 lines joined with `"\n"`. Line 10 is literally `not json`.

  ```text
  {"type":"tool_call","subtype":"started","tool_call":{"shellToolCall":{"args":{"command":"python make.py"}}}}
  {"type":"tool_call","subtype":"started","tool_call":{"readToolCall":{"args":{"path":"skills/pdf/SKILL.md"}}}}
  {"type":"item.completed","item":{"type":"file_change","changes":[{"path":"output/a.pdf"},{"path":"output/b.pdf"}]}}
  {"type":"item.completed","item":{"type":"agent_message","text":"Done."}}
  {"type":"assistant","timestamp_ms":1,"message":{"content":[{"type":"text","text":"Hel"}]}}
  {"type":"assistant","timestamp_ms":2,"message":{"content":[{"type":"text","text":"lo"}]}}
  {"type":"assistant","message":{"content":[{"type":"tool_use","id":"t1","name":"Bash","input":{"command":"pytest -q"}}]}}
  {"type":"error","message":"boom"}
  {"type":"turn.failed","error":{"message":"bad turn"}}
  not json
  ```
- Call: `spans_from_jsonl(stdout, trace_id="trace")`.
- Also assert `attr_map(result[1]) == {...}`, using the captured literal.

### 4.2 `test_parse_command_runs_golden` and `test_build_agent_trajectory_golden`

`LOG` is these 6 lines joined with `"\n"`:

```text
{"type":"item.completed","item":{"type":"command_execution","command":"pytest -q","aggregated_output":"3 passed in 0.1s","exit_code":0}}
{"type":"tool_call","tool_call":{"shellToolCall":{"args":{"command":"ls"},"result":"a.txt"}}}
{"type":"assistant","message":{"content":[{"type":"tool_use","id":"c1","name":"Bash","input":{"command":"make test"}}]}}
{"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"c1","content":[{"type":"text","text":"ok"}]}]}}
{"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"zz","content":"orphan"}]}}
==== 2 passed in 0.2s ====
```

Calls:

- `parse_command_runs(LOG)`
- `build_agent_trajectory(spans=None, transcript=LOG, path={"steps": 3, "errors": 0, "had_path": True}, scores=[Score(scorer="file_exists", passed=True, detail="ok", headline="File exists"), {"scorer": "rubric", "passed": False, "detail": "1/2"}], artifacts=ARTIFACTS, command_log=None)`
- `workspace_files_for_judge(ARTIFACTS)`

where `ARTIFACTS = [{"path": "output/a.txt", "present": True, "kind": "text", "body": "x" * 7000}, {"path": "output/missing.txt", "present": False}]`.

`spans_from_jsonl` is reached through `build_agent_trajectory`, so apply the same `_id`/`_now_ns` monkeypatches as §4.1.

### 4.3 `test_metrics_golden`

- `m1 = evaluate_task_metrics({"tokens_total": 50}, None, "$ ls\nchanged a.txt\n", {"tokens_total": 10, "max_steps": 5})`
- `m2 = evaluate_task_metrics(None, None, "", None)`
- `s = suite_metrics_summary([{"id": "a", "metrics": m1}, {"id": "b", "metrics": m2}])`
- Golden for each of `m1`, `m2` and `s`.

### 4.4 `test_judge_stamp_golden`

- `judge_stamp(None)`
- `judge_stamp(SkipJudge())`
- `judge_stamp(types.SimpleNamespace(name="jev", backend=types.SimpleNamespace(name="jev", model="m1"), display_name="Judge", chosen=True))`
- `with_judge(EvalRunConfig(), judge_stamp(SimpleNamespace(...same...))).to_dict()["judge"]`
- `EvalRunConfig.from_dict(with_judge(EvalRunConfig(), <same stamp>).to_dict()).judge`. This pins the existing str-coercion of `chosen` after reload.

### 4.5 `test_api_payloads_golden`

Monkeypatch, all via `monkeypatch.setattr`:

| Target | Replacement |
|---|---|
| `skillgate_ai.api_payloads.load_history` | `lambda path, limit=50: []` |
| `skillgate_ai.api_payloads.load_deploys` | `lambda path: [{"target": "cursor", "status": "installed", "ts": "2026-01-01T00:00:00Z", "file_count": 3, "mode": "local"}]` |
| `skillgate_ai.api_payloads.pack_gate_decision` | `lambda path: ("pending", None)` |
| `skillgate_ai.compare_git.list_skill_git_versions` | `lambda path: [{"ref": "abc1234", "created_at": "2026-01-02T00:00:00Z"}, {"ref": "def5678", "created_at": ""}]` |
| `skillgate_ai.api_payloads.catalog_entries` | `lambda root, **kw: [{"absolute": str(skill_dir)}]` |

Setup: `skill_dir = tmp_path / "demo"` (mkdir), `state = AppState(root=tmp_path)`.

Goldens:

- `history_payload(state, skill_dir)`
- `workspace_history(state)`
- `skill_version_rows(skill_dir)`

### 4.6 Placement

`tests/test_wire_shapes.py` only. `import json, itertools, types`. No `src/` edits in this commit.

---

## 5. Part (a): mypy `check_untyped_defs = true` (Step 1)

### 5.1 Config

`pyproject.toml:135`: `check_untyped_defs = false` → `check_untyped_defs = true`. Change nothing else in `[tool.mypy]`.

### 5.2 Files that change

**`src/skillgate_ai/helper.py:69`**, the only unannotated function in `src/`. Annotate it to match typeshed exactly (`mypy/typeshed/stdlib/urllib/request.pyi:190`):

```python
def redirect_request(
    self,
    req: urllib.request.Request,
    fp: IO[bytes],
    code: int,
    msg: str,
    headers: HTTPMessage,
    newurl: str,
) -> urllib.request.Request | None:
```

- Add `from typing import IO` and `from http.client import HTTPMessage`. `http.client` is already imported at line 11, so use `http.client.HTTPMessage` and skip the new import line.
- The body is unchanged.
- `tests/test_helper.py:458` and `:476` pass `None`/`{}` for `fp`/`headers`. That is fine at runtime, and tests are not mypy-checked.

**`src/skillgate_ai/harness/selection.py:22–42`**: typed sentinel (re-audit item; not a flag error):

```python
import enum
from typing import Final, Literal

class _Missing(enum.Enum):
    MISSING = enum.auto()

_MISSING: Final = _Missing.MISSING

def _read_selection(workspace: Path) -> str | None | Literal[_Missing.MISSING]:
```

- The body is unchanged.
- `harness/prompts.py:132–139`: no edit needed. `pinned is _MISSING` narrows `pinned` to `str | None`, which matches the `pinned_skill: str | None` parameters at `prompts.py:69` and `:161`.
- `harness/__init__.py:139`/`:150` re-exports stay as they are.
- Runtime: identity semantics are preserved. `tests/test_no_trigger_selection.py:47` (`is _MISSING`) and `tests/test_harness_auth.py:93` (monkeypatched lambda) stay green.

### 5.3 Files that will **not** break (checked; do not touch for this flag)

- Every other `def` in `src/` has at least one annotation.
- That includes `api.py:73`/`:79` (`cfg` untyped but return annotated), `api_runs.py:90` (`on_progress(progress) -> None`), `local_guard.py:45`, `cli/gate_output.py:18/31/55` and `report.py:637`. These are already checked today.

### 5.4 If mypy reports anything else after the flip

Fix it with P-A…P-F only. List every such fix (file:line, code, pattern) in the PR description. A new `# type: ignore` is not allowed.

---

## 6. Part (b): TypedDict plan

### 6.1 Naming and placement (binding)

- **Placement:** each TypedDict lives in the module that **constructs** the shape.
  - Put it after imports and module constants and before the first function.
  - Do not create a new `types`/`wire_types` module (no module splits).
  - Consumers import it from the owning module. For annotation-only use inside a module that imports the owner lazily (for example `engine/verdict.py`), use `if TYPE_CHECKING:`. Every touched module already has `from __future__ import annotations`.
- **Names:**
  - PascalCase noun with no `Dict`/`TD` suffix.
  - `*Row` for elements of a list.
  - A plain noun for a top-level object (`AgentTrajectory`, `TaskMetrics`, `JudgeStamp`).
  - The `Otlp*` prefix mirrors OTLP/JSON.
- **Keys:** spelled exactly as on the wire (`traceId`, `startTimeUnixNano`, …). ruff `N` is not selected.
- **Optional keys:** use `total=False` when a row's key set depends on its source (`CommandRun`, `OtlpAnyValue`). Otherwise use `NotRequired[...]` per key. Import `TypedDict`, `NotRequired`, `TypeAlias`, `Literal` from `typing` (Python ≥ 3.11).
- **Pass-through JSON values:** type them as `object`, not `Any`. Use `bool | None` / `int | None` / `str | None` where the producer guarantees that.
- **`__all__`:** none of the touched modules define `__all__`. Do not add one. Do not touch `judge_openai/__init__.py` (`tests/test_public_imports.py:513` pins its `__all__`).

### 6.2 `src/skillgate_ai/spans.py` (Step 2)

**Add** after `KIND_INTERNAL = 1` (line 23):

```python
AttrValue: TypeAlias = str | int | float | bool


class OtlpAnyValue(TypedDict, total=False):
    stringValue: str
    intValue: str
    doubleValue: float
    boolValue: bool


class OtlpKeyValue(TypedDict):
    key: str
    value: OtlpAnyValue


class OtlpStatus(TypedDict):
    code: int


class OtlpSpan(TypedDict):
    traceId: str
    spanId: str
    name: str
    kind: int
    startTimeUnixNano: str
    endTimeUnixNano: str
    status: OtlpStatus
    attributes: list[OtlpKeyValue]
    parentSpanId: NotRequired[str]
```

Imports: `from collections.abc import Mapping` and `from typing import Any, NotRequired, TypeAlias, TypedDict, cast`.

**Edits** (annotations only; bodies unchanged except where stated):

| Line | Function / local | From | To |
|---|---|---|---|
| 34 | `_attr(key, value)` | `value: Any` → `dict[str, Any]` | `value: AttrValue` → `OtlpKeyValue` |
| 53–54 | `make_span(... attributes=...)` | `attributes: dict[str, Any] \| None` → `dict[str, Any]` | `attributes: Mapping[str, AttrValue \| None] \| None` → `OtlpSpan` |
| 59 | `span` local | `dict[str, Any]` | `OtlpSpan` |
| 80 | `_cursor_tool_span` return | `dict[str, Any] \| None` | `OtlpSpan \| None` (`obj` param stays `dict[str, Any]`: parsed JSON) |
| 100, 164, 302 | `attrs` locals | `dict[str, Any]` | `dict[str, AttrValue]` |
| 133 | `_codex_item_span` return | `dict[str, Any] \| None` | `OtlpSpan \| None` |
| 249 | `_set_string_attr(span, ...)` | `span: dict[str, Any]` | `span: OtlpSpan` (keep `setdefault`; mypy supports `TypedDict.setdefault` with a literal key) |
| 260 | `_claude_tool_spans` return | `list[dict[str, Any]]` | `list[OtlpSpan]` (line 262 `parts` stays: parsed JSON) |
| 274 | `spans` local | `list[dict[str, Any]]` | `list[OtlpSpan]` |
| 329 | `spans` local in `spans_from_jsonl` | `list[dict[str, Any]]` | `list[OtlpSpan]` |
| 354 / 356 | `span`, `extra` locals | `dict[str, Any] \| None`, `list[dict[str, Any]]` | `OtlpSpan \| None`, `list[OtlpSpan]` |
| 448 | `return spans` | | `return cast("list[dict[str, Any]]", spans)  # wire boundary: OtlpSpan rows are plain dicts; HarnessResult/TaskReport/history JSON carry JSON dicts` |
| 451 | `attr_map(span)` | `span: dict[str, Any]` | `span: Mapping[str, Any]` (return stays `dict[str, Any]`) |

The **public** return type of `spans_from_jsonl` stays `list[dict[str, Any]]` (line 324). This is deliberate. Its consumers already hold JSON-shaped spans, including spans reloaded from disk:

- `harness/transcripts.py:79` → `HarnessResult.spans`
- `engine/models.py:34/54`
- `engine/task.py:510`
- `report.py:297`
- `metrics.py:114`
- `live.py:349`
- `judge_context.py:273`

A typed return would cascade through invariant `list[...]` fields across ~10 modules. Do not change those consumers.

**Target:** `rg -c "dict\[str, Any\]" src/skillgate_ai/spans.py` → **9**. The remaining lines are 79, 202, 214, 224, 259 and 262 (parsed-JSON inputs), 324 (public return), and 451 and 453 (`attr_map` return and its `out` local).

### 6.3 `src/skillgate_ai/judge_context.py` (Step 3)

**Add** after `_COMMAND_OUTPUT_CAP` (line 26):

```python
class JudgeFileRow(TypedDict):
    path: str
    present: bool
    kind: object
    content: str | None


class CommandRun(TypedDict, total=False):
    source: str
    command: str
    exit_code: object
    output: str | None
    tool: str | None


class TrajectoryCommand(TypedDict):
    kind: str
    tool: AttrValue | None
    args: str
    file: AttrValue | None


class ScorerRow(TypedDict):
    scorer: str | None
    passed: bool | None
    headline: str | None
    detail: str | None


class AgentTrajectory(TypedDict):
    had_path: bool | None
    step_count: int | None
    error_count: int | None
    commands: list[TrajectoryCommand]
    command_runs: list[CommandRun]
    test_mentions: list[str]
    scorer_results: list[ScorerRow]
    transcript_chars: int
    workspace_file_paths: list[str]
```

Imports:

- `from typing import Any, TypedDict`
- `from skillgate_ai.spans import AttrValue, attr_map, spans_from_jsonl` (extends line 15)

**Edits:**

| Line | Function / local | Change |
|---|---|---|
| 54 | `workspace_files_for_judge` | return `list[dict[str, Any]]` → `list[JudgeFileRow]` (param unchanged) |
| 55 | `rows` | `list[JudgeFileRow]` |
| 76 | `parse_command_runs` | return → `list[CommandRun]` |
| 77 | `runs` | `list[CommandRun]` |
| 78 | `pending` | `dict[str, CommandRun]` |
| 174–175 | `_ingest_claude_stream_event(runs, pending, obj)` | `runs: list[CommandRun]`, `pending: dict[str, CommandRun]` (`obj` unchanged) |
| 183 | `row` | `CommandRun` |
| 208 | `_is_shell_evidence(run)` | `run: CommandRun` |
| 219 | `_trim_command_runs` | `runs: list[CommandRun]` → `list[CommandRun]` |
| 235 | `_append_command_run(runs, item)` | `runs: list[CommandRun]` (`item` unchanged) |
| 270 | `build_agent_trajectory` return | `AgentTrajectory` |
| 276 | `commands` | `list[TrajectoryCommand]` |
| 301 | `scorer_rows` | `list[ScorerRow]` |

- Leave unchanged: 29 (`enrich_output_row`: artifact rows have many producers, follow-up), 124/136/152 (parsed-JSON helpers), 264–268 (params), 361–445 (`attach_adherence_context`: question payloads, follow-up).
- Consumers need no change:
  - `engine/verdict.py:121` passes the trajectory through `Judge.judge(**kwargs: Any)`.
  - `judge_openai/payload.py:64` and `judge_openai/outcome.py:172–173` store into `dict[str, Any]`.
  - `outcome.py:190` → `span_facts.resolve_log_facts(outputs: Sequence[Mapping[str, Any]] | ...)` (`span_facts.py:199`) accepts TypedDict lists.

**`src/skillgate_ai/engine/verdict.py:54`:**

- `_score_rows(scores: list[Score]) -> list[dict[str, Any]]` → `-> list[ScorerRow]`.
- Add `if TYPE_CHECKING: from skillgate_ai.judge_context import ScorerRow`, and add `TYPE_CHECKING` to the `typing` import at line 6.

**Targets:** `judge_context.py` → **15**; `engine/verdict.py` → **14**.

### 6.4 `src/skillgate_ai/metrics.py` (Step 4)

**Add** after `MetricsStatus` (line 30):

```python
class PathStats(TypedDict):
    steps: int
    errors: int
    had_path: bool


class BudgetSnapshot(TypedDict):
    tokens_total: int | None
    max_steps: int | None


class TaskMetrics(TypedDict):
    path: PathStats
    budgets: BudgetSnapshot | None
    status: MetricsStatus
    reasons: list[str]
    blocking: bool


class SuiteMetricsSummary(TypedDict):
    budget_fails: list[str]
    status: MetricsStatus
    path: NotRequired[PathStats]
```

Import `NotRequired, TypedDict` from `typing` (line 15).

**Edits:**

- `evaluate_task_metrics` (line 125): return `TaskMetrics`; line 173 `payload: TaskMetrics = {...}`.
- `suite_metrics_summary` (line 220): return `SuiteMetricsSummary`; line 251 `summary: SuiteMetricsSummary = {...}`. The param `tasks: list[dict[str, Any]]` is unchanged.
- Everything else in `metrics.py` reads report JSON and stays unchanged.

**`src/skillgate_ai/engine/models.py`:**

- Line 35 `TaskReport.metrics` and line 55 `TaskProgress.metrics`: `dict[str, Any] | None` → `TaskMetrics | None`.
- Add `from skillgate_ai.metrics import TaskMetrics`. There is no cycle: `metrics.py` imports only `re`, `typing` and `pydantic`.
- The writers stay valid: `engine/task.py:383/406/503` (TypedDict), `engine/run.py:546` (`getattr` → `Any`), `report.py:267` (same field type).

**Targets:** `metrics.py` → **19**; `engine/models.py` → **8**.

### 6.5 `src/skillgate_ai/api_payloads.py` (Step 5)

**Add** after `LIVE_AGENT_HARNESSES` (line 98):

```python
class DeployRow(TypedDict):
    id: int
    target: str
    status: str
    created_at: object
    file_count: object
    mode: object
    dest_label: str


class SkillVersionRow(TypedDict):
    id: int
    semver: str
    created_at: str | None
    skill_md_hash: str


class RunTimelineRow(TypedDict):
    kind: Literal["run"]
    id: object
    at: object
    passed: object
    skill: object
    harness: object
    config_label: object
    gate: object
    status: object
    tryout: object


class DeployTimelineRow(TypedDict):
    kind: Literal["deploy"]
    id: int
    at: object
    skill: str
    target: str
    status: str
    label: str


TimelineRow: TypeAlias = RunTimelineRow | DeployTimelineRow
```

Imports: extend line 9 to `from typing import TYPE_CHECKING, Any, Literal, NoReturn, TypeAlias, TypedDict`.

**Edits:**

- Line 252 `_deploy_payload(...)`: return `-> DeployRow` (param unchanged).
- Line 311 `skill_version_rows` → `list[SkillVersionRow]`; line 315 `rows: list[SkillVersionRow]`.
- Line 336 `timeline = [...]` → `timeline: list[TimelineRow] = [...]`.
- Lines 351–365, deploy timeline append (P-F; `item` is a `DeployRow` built at line 334):
  - `"id": item["id"]`
  - `"at": item["created_at"]`
  - `"target": item["target"]`
  - `"status": item["status"]`
  - label: `f"{SOURCE_LABELS.get(item['target'], item['target'] or 'agent')}"`
- Lines 381–382 `workspace_history`: `timeline: list[TimelineRow] = []`, `deploys: list[DeployRow] = []`.
- **Do not change** the return annotations of `skill_payload`, `history_payload`, `workspace_history`, `run_from_history` or `history_row_to_run` (`dict[str, Any]`). Routes in `api_skills.py:150/266` and `api_evals.py` return them under `-> dict[str, Any]` FastAPI annotations.
- **Fallback, only if mypy rejects the run-row comprehension against the union context** (`[typeddict-item]` or `[misc]` at line 336–350): bind `run_rows: list[RunTimelineRow] = [...]` then `timeline: list[TimelineRow] = list(run_rows)`. The output is identical.

**Target:** `api_payloads.py` → **19**.

### 6.6 `src/skillgate_ai/judge.py` + `src/skillgate_ai/eval_config.py` (Step 6; closes the PR A JudgeStamp follow-up)

**`judge.py`**: add after imports:

```python
class JudgeStamp(TypedDict):
    provider: str
    backend: str
    display_name: str
    chosen: bool
    model: NotRequired[str]
```

- `judge_stamp` (line 316): `-> dict[str, Any]` → `-> JudgeStamp`. The bodies (lines 317–344) are unchanged.
- `typing` import (line 6): add `NotRequired, TypedDict`.

**`eval_config.py`**:

- Line 57 `EvalRunConfig.judge: dict[str, str] | None` → `Mapping[str, object] | None`. Import `Mapping` from `collections.abc`.
- Line 258 `with_judge(run, stamp: dict[str, str] | None)` → `stamp: Mapping[str, object] | None`. The body `dict(stamp) if stamp else None` is unchanged.
- `_judge_stamp` (line 481) is unchanged. `dict[str, str]` is assignable to `Mapping[str, object]`.
- Reads at lines 72, 351–353, 370–381 and 469–477 already wrap values in `str(...)`.

**Why `Mapping[str, object]`:** at runtime `judge["chosen"]` is a `bool` on a fresh run and a `str` after `from_dict` reload. The old `dict[str, str]` annotation was false. `Mapping[str, object]` tells the truth and changes no behavior. Golden §4.4 pins both forms.

- `gate.py:252` needs no edit.
- `engine/verdict.py:186` `**stamp` into a `dict[str, Any]` return needs no edit.

**Target:** `judge.py` → **5**.

### 6.7 Aggregate target

`rg -c "dict\[str, Any\]" src` sum: **553 → ≤ 515**. Per-file targets: spans 9, judge_context 15, metrics 19, api_payloads 19, judge 5, engine/verdict 14, engine/models 8. All other files are unchanged.

### 6.8 Hot spots deliberately deferred (record in the PR description as follow-ups)

| File | Count | Reason |
|---|---|---|
| `judge_openai/outcome.py` | 26 | LLM-answer JSON, parsed input |
| `fixture_bind.py` | 20 | check rows produced by `case_pack/suites.checks_from_pack` and consumed by `pins`, `api_*`, CLI. Needs one `CheckRow` type across ~6 modules: a dedicated PR |
| `api_skills.py` | 18 | route-level; FastAPI return-annotation hazard |
| `compare/payload.py` | 18 | compare report JSON |
| `judge_context.enrich_output_row` / workspace output rows | n/a | 4 producers |

---

## 7. Part (c): ruff `BLE` + `S` (Steps 7–8)

### 7.1 Config (Step 8)

`pyproject.toml:114`:

```toml
select = ["E", "W", "F", "I", "UP", "B", "SIM", "BLE", "S"]
```

`[tool.ruff.lint.per-file-ignores]`: append these entries and keep the existing ones:

```toml
# Tests use assert, subprocess, temp paths and fake secrets by design.
"tests/**/*.py" = ["S"]
# Seed skill packs are hashed fixtures shipped as examples; their scripts are agent-side code.
"skills/**/scripts/*.py" = ["S603"]
```

- The `skills/` exception is required. Editing `skills/pdf*/scripts/agent_entry.py:30` would change the seed packs (`skill_pack_hash`, bundled examples, `--expect-fail` fixture).
- No global `ignore` additions.
- Leave `flake8-bandit.check-typed-exception` at its default (`false`). `S110`/`S112` then fire only on broad catches.

### 7.2 Broad-except decisions (Step 7). Every match from §0, with its decision

How BLE001 decides what to flag (ruff): a handler whose body **re-raises** (bare `raise`, `raise exc`, or `raise … from exc` with the bound name, at any `if` nesting) is **not** flagged.

| # | Site | Flagged? | Decision |
|---|---|---|---|
| 1 | `document_text.py:31` `extract_document_text` | yes | **Keep broad.** Untrusted-file parser boundary: pypdf, python-docx and openpyxl raise undocumented types on malformed files (KeyError, ValueError, AssertionError, RecursionError, zlib/struct errors), and `_pdf_text`/`_docx_text`/`_xlsx_text` lazily import the `docs` extra (ModuleNotFoundError). Add `import logging`, `_LOG = logging.getLogger(__name__)`. Handler: `_LOG.debug("document text extraction failed for %s", path.name, exc_info=True)` then `return None`. Pragma: `except Exception:  # noqa: BLE001 - untrusted file parser boundary; returns None` |
| 2 | `scorers.py:342` `_pdf_pages` | yes | **Keep broad**, same rationale. `import_extra` stays outside the `try`, so a missing extra still raises its friendly error. Add `_LOG` (module-level) and `_LOG.debug("pdf page count failed for %s", path.name, exc_info=True)`. Pragma: `# noqa: BLE001 - untrusted PDF parser boundary; returns None` |
| 3 | `scorers.py:351` `_pdf_text` | yes | **Keep broad**, same. Log message `"pdf text extraction failed for %s"`. |
| 4 | `metrics.py:270` `_as_budgets` | yes | **Narrow** → `except ValidationError:` (already imported, line 17). `model_validate` on a 2-key dict raises only `ValidationError`; validators raise `ValueError`, which pydantic wraps. |
| 5 | `cli/base.py:96` `_stdin_is_tty` | yes | **Narrow** → `except (AttributeError, OSError, ValueError):`. `sys.stdin` can be `None` (AttributeError), a closed stream (ValueError: I/O on closed file), or a broken fd (OSError). |
| 6 | `case_pack/pins.py:122` `_skill_name` | yes (+S110) | **Narrow** → `except (SkillGateError, OSError, ValueError):` and keep `pass`. Add `from skillgate_ai.errors import SkillGateError`. `ingest_skill(strict=False)` is documented "never raises" (`ingest.py:181`). These cover `IngestError`, I/O and pydantic `ValidationError`. A typed catch is not flagged by S110. |
| 7 | `case_pack/store.py:112` `load_case_pack` | yes (`from None`) | **Narrow** → `except ValidationError as exc:`. Add `from pydantic import ValidationError`. `CasePack`/`PackCase`/`JudgeBlock` validators raise only `ValueError` (`case_pack/models.py:73,75,105,135`), which is wrapped. |
| 8 | `case_pack/store.py:132` `save_case_pack` | yes | **Narrow** → `except ValidationError as exc:` |
| 9 | `case_pack/store.py:141` `save_case_pack` (previous pack) | yes | **Narrow** → `except (OSError, UnicodeDecodeError, yaml.YAMLError, ValidationError):` |
| 10 | `suite.py:120` `load_suite` | yes (`from None`) | **Narrow** → `except ValidationError as exc:`. Add `ValidationError` to the `pydantic` import (line 9). |
| 11 | `scaffold.py:47` `create_pack` | **no** (bare `raise`) | **Unchanged.** Cleanup-then-re-raise is the correct idiom. Narrowing would leak a half-created folder on unexpected errors. |
| 12 | `pack.py:547` (`BaseException`) | no (bare `raise`) | Unchanged, same idiom. |
| 13 | `gate.py:287` | no (nested bare `raise`) | Unchanged |
| 14 | `engine/task.py:352` | no (bare `raise`) | Unchanged |
| 15 | `pack_schema.py:299` | no (`from exc`) | Unchanged |
| 16 | `case_pack/suites.py:165` | no (`from exc`) | Unchanged |
| 17 | `cli/cmd_gate.py:79` | no (bare `raise`) | Unchanged. Its existing noqa is harmless (RUF100 is not enabled). |
| 18 | `errors.py:182` | yes | Unchanged. Already `# noqa: BLE001 - fall through to a generic line`. |
| 19 | `live.py:318` `persist_sandbox_poll` | yes (+S110) | Pragma → `# noqa: BLE001, S110 - never break the harness on flush` |
| 20 | `live.py:329` `notify_live` | yes (+S110) | Same as 19 |
| 21 | `live.py:371` `_terminate` | yes | Unchanged (has reason) |
| 22 | `live.py:381` `hard_kill` | yes (+S110) | Unchanged (has both codes + reason) |
| 23 | `helper.py:326` `process_job` | yes | Unchanged. The error is surfaced in the job result. |
| 24 | `helper.py:347` `run_helper` | yes | Unchanged. The claimed job is reported failed. |
| 25 | `api_runs.py:146` worker | yes | Unchanged. The error is surfaced to the poller as the run record. |
| 26 | `api_compare.py:178` worker | yes | Pragma → `# noqa: BLE001 - worker thread boundary; failure is recorded on the compare job` |
| 27 | `api_compare.py:224` worker | yes | Same text as 26 |
| 28 | `sandbox.py:271` `_pump` | yes (+S110) | Unchanged |
| 29 | `tests/test_harness_auth.py:970` | n/a | Unchanged. It already has a noqa, and `tests/` keeps BLE. |
| 30–31 | `tests/test_optional_extras.py:149,159` | n/a | String literals, not code |

**Fallback if ruff disagrees with the "no" rows (11–17):**

- For 15–16, narrow to `except ValidationError as exc:`.
- For 11–14 and 17, add `# noqa: BLE001 - re-raises; <one-line purpose>`.

Do not restructure the code.

**Intended behavior delta (document in the PR description):** every documented and expected failure is still handled. Only programming errors in rows 4–10 (an exception other than `ValidationError` from pydantic validation, a non-I/O error from `isatty`, …) now surface as tracebacks instead of being disguised as user errors. The tests in §8.2 pin both halves.

### 7.3 `S` findings in `src/`, `scripts/` (Step 8). Each gets `# noqa: CODE - reason` on the reported line

| File:line | Code | Reason text |
|---|---|---|
| `helper.py:58` `urllib.request.Request(url, …)` | S310 | `URL is the user's paired Skill Gate base (https or loopback, enforced at connect)` |
| `helper.py:80` `urllib.request.Request(newurl, …)` | S310 | `redirect target already accepted by the stdlib redirect handler` |
| `helper.py:133` `urllib.request.Request(url, …)` | S310 | same as :58 |
| `scripts/skillgate_action.py:65` `urlopen(PYPI_JSON, …)` | S310 | `constant https PyPI URL` |
| `scripts/skillgate_action.py:82` | S603 | `argv list; sys.executable -m pip with a validated version` |
| `scripts/skillgate_action.py:127` | S603 | `argv list; inputs come from the workflow's own with: block` |
| `src/skillgate_build.py:69`, `:73` | S603 | `pnpm resolved by shutil.which; fixed args` |
| `sandbox.py:108` | S603 | `argv list without shell; running the harness CLI is the sandbox's job` |
| `sandbox.py:177` | S603 | `docker argv list without shell; --network none` |
| `sandbox.py:213` (`Popen`) | S603 | `argv list without shell; streaming harness run` |
| `sandbox.py:279` / `:280` | S603 / S607 | `fixed docker inspect argv` / `docker resolved from PATH by design` |
| `harness/login.py:54` (`Popen`) | S603 | `resolved official agent CLI + fixed login subcommand` |
| `harness/auth.py:43`, `:81`, `:129` | S603 | `binary resolved via harness.bins; fixed status subcommand` |
| `api.py:62` / `:63` | S603 / S607 | `fixed git argv, 1s timeout` / `git resolved from PATH by design` |
| `compare_git.py:40`/`:41`, `:61`/`:62`, `:88`/`:89` | S603 / S607 | `fixed git argv; ref and path are separate argv items` / `git resolved from PATH by design` |
| `sync.py:89` / `:90` | S603 / S607 | `validated repo URL passed after --` / `git resolved from PATH by design` |
| `workspace_outputs.py:183` | S603 | `fixed git argv from module constants` |
| `launchd.py:36` `os.chmod(launch_dir, 0o755)` | S103 | `~/Library/LaunchAgents must be traversable by launchd (standard macOS mode)` |
| `metrics.py:22`, `:25` (`REASON_TOKEN_*`) | S105 | `user-facing copy, not a credential` |
| `engine/run.py:263`, `engine/task.py:449`, `judge_bank.py:422` | S101 | `type-narrowing invariant guaranteed by the branch above` |
| `live.py:318`, `:329` | S110 | (combined with BLE001 per §7.2 rows 19–20) |

- **Add each noqa only where ruff reports it.** Depending on the ruff version, `S603` may skip literal-only argv, so `compare_git.py:61` may not be reported. Never add a pragma ruff did not ask for.
- `sandbox.py`, `helper.py` and `launchd.py` are PR A security surfaces. In those files, **only pragma comments may change.**

### 7.4 S findings not listed above

Use exactly this decision rule:

1. `S4xx` (suspicious-import rules, if stable in the pinned ruff): add the code to a new `[tool.ruff.lint] ignore = [...]` with the comment `# import-level bandit rules; call sites are covered by S6xx`.
2. Any other code in `src/` or `scripts/`:
   - If the flagged value comes from user input, a network, or a file in the user's repo, **stop**. Do not suppress it. Report it in the PR description as a finding for PR C.
   - Otherwise, add a `# noqa: CODE - reason` pragma naming where the value comes from.
3. Any finding in `tests/` is already covered by the per-file ignore.

---

## 8. Tests (exact)

### 8.1 `tests/test_wire_shapes.py` (Step 0)

As specified in §4. Its constants must not change in later commits.

### 8.2 `tests/test_narrowed_excepts.py` (Step 7)

All tests are plain pytest functions with `tmp_path`, `monkeypatch` and `caplog` fixtures.

**Metrics (`skillgate_ai.metrics`)**

- `test_as_budgets_invalid_values_fall_back_to_empty`: `_as_budgets({"tokens_total": -5}).is_empty()` and `_as_budgets({"tokens_total": "abc", "max_steps": 3}).is_empty()` are both `True`.
- `test_merge_budgets_ignores_invalid_suite_layer`: `merge_budgets({"max_steps": 0}, {"tokens_total": 10}) == CaseBudgets(tokens_total=10)`.
- `test_as_budgets_unexpected_error_propagates`: monkeypatch `CaseBudgets.model_validate` with a `classmethod` raising `RuntimeError("bug")`. `pytest.raises(RuntimeError)` on `_as_budgets({"tokens_total": 1})`.

**CLI stdin (`skillgate_ai.cli.base._stdin_is_tty`)**

- `test_stdin_none_is_not_tty`: `monkeypatch.setattr(sys, "stdin", None)` → `False`.
- `test_closed_stdin_is_not_tty`: `s = io.StringIO(); s.close()`; set it as stdin → `False`.
- `test_stdin_oserror_is_not_tty`: stub class whose `isatty` raises `OSError` → `False`.
- `test_stdin_tty_true`: stub `isatty` returns `True` → `True`.
- `test_stdin_unexpected_error_propagates`: stub raises `RuntimeError` → `pytest.raises(RuntimeError)`.

**`case_pack.pins._skill_name`**

Setup: `root = tmp_path / "demo"` containing `SKILL.md` with `"---\nname: demo\ndescription: d\n---\n"`.

- Parametrize `exc` over `[IngestError("x"), OSError("x"), ValueError("x")]`. Monkeypatch `skillgate_ai.ingest.ingest_skill` to raise it. Expect `_skill_name(root) == "demo"`.
- `RuntimeError` → `pytest.raises(RuntimeError)`.
- No `SKILL.md` → returns the folder name, and the patched `ingest_skill` is never called (assert via a flag).

**`case_pack.store`**

- `test_load_case_pack_schema_error_is_friendly`:
  - Setup: `root = tmp_path / "demo-skill"`; `evals/cases.yaml` = `"schema: 1\nskill: demo-skill\ncases: 5\n"`.
  - `load_case_pack(root)` raises `SuiteError` with `exit_code == 2`.
  - `"pydantic" not in str(exc.message).lower()`.
  - `exc.__suppress_context__ is True`.
- `test_load_case_pack_unexpected_error_propagates`: monkeypatch `CasePack.model_validate` → `RuntimeError` → propagates.
- `test_save_case_pack_tolerates_unreadable_previous` is parametrized over three existing-file contents:
  - `b"\xff\xfe\x00"` (UnicodeDecodeError)
  - `b"cases: [\n"` (YAMLError)
  - `b"schema: 1\nskill: demo-skill\ncases: 5\n"` (ValidationError)

  For each: `root = tmp_path / "demo-skill"`; write the bytes to `root/"evals"/"cases.yaml"`; `save_case_pack(root, CasePack(schema=1, skill="demo-skill", cases=[PackCase(id="should-trigger-1", status="pinned", prompt="Make a PDF", should_trigger=True)]))` returns `cases_path(root)`. `yaml.safe_load` of the written file has `skill == "demo-skill"`.

**`suite.load_suite`**

- `test_load_suite_schema_error_is_friendly`:
  - Setup: `tmp_path / "suite.yaml"` = `"suite: demo\nskill: ../demo\ntasks: [\"not-a-mapping\"]\n"`.
  - `SuiteError` is raised, its message starts with or contains the friendly "Eval suite" kind, and `__suppress_context__ is True`.
- `test_load_suite_unexpected_error_propagates`: monkeypatch `SuiteSpec.model_validate` → `RuntimeError` → propagates.

**Kept-broad parser boundaries (`pytest.importorskip("pypdf")` not needed: stubs only)**

- `test_extract_document_text_parser_errors_return_none_and_log`, parametrized over `[KeyError("/Root"), ValueError("bad"), ModuleNotFoundError("pypdf"), RecursionError()]`:
  - Write `tmp_path/"out.pdf"` = `b"%PDF-1.4\n"`.
  - Monkeypatch `skillgate_ai.document_text._pdf_text` to raise.
  - Under `caplog.at_level(logging.DEBUG, logger="skillgate_ai.document_text")`, the result is `None` and a record from that logger has `exc_info` set.
- `test_scorers_pdf_helpers_parser_errors_return_none_and_log`, same parametrization:
  - Monkeypatch `skillgate_ai.scorers.import_extra` → `lambda *a, **k: types.SimpleNamespace(PdfReader=raiser)`.
  - `_pdf_pages(p) is None` and `_pdf_text(p) is None`.
  - DEBUG records with `exc_info` from `skillgate_ai.scorers`.
- `test_parser_boundary_logs_are_debug_only`: same setup, under `caplog.at_level(logging.WARNING)`. No records from either logger. This proves no user-visible output.

### 8.3 `tests/test_typing_lint_config.py` (Step 8; read with `tomllib`)

- `test_mypy_checks_untyped_defs`: `cfg["tool"]["mypy"]["check_untyped_defs"] is True` and `warn_unused_ignores is True`.
- `test_ruff_selects_ble_and_s`:
  - `{"BLE", "S"} <= set(select)`.
  - `per-file-ignores["tests/**/*.py"] == ["S"]`.
  - `"BLE001"`, `"BLE"`, `"S"` are not in `lint.get("ignore", [])`.
- `test_bandit_and_ble_noqa_have_reasons`: for every line in `src/**/*.py` and `scripts/*.py` containing `noqa:` with a `BLE001` or `S\d{3}` code, the line matches `r"noqa: [A-Z0-9, ]+\s*(?:-|—)\s*\S"`, or the line directly above matches `r"#\s*(BLE001|S\d{3}):\s*\S"`.
- `test_type_ignores_have_codes_and_reasons`: every `type: ignore` in `src/` matches `r"type: ignore\[[a-z-, ]+\]\s+#\s*\S"`.

### 8.4 Existing tests that must stay green unedited

- `tests/test_helper.py:458,476` (redirect)
- `tests/test_no_trigger_selection.py:47` (`_MISSING`)
- `tests/test_harness_auth.py:93`
- `tests/test_judge_context.py`, `tests/test_judge_dogfood_v5.py`, `tests/test_workspace_outputs.py`
- `tests/test_keys.py:116,133` (monkeypatched `_stdin_is_tty`)
- `tests/test_public_imports.py` (`_MISSING`, `_read_selection` still importable)
- `tests/test_eval_config.py`, `tests/test_report.py`, `tests/test_engine.py`, `tests/test_scaffold.py`, `tests/test_friendly_errors.py`
- all of `tests/integration/`

**No existing test may be edited.** If one needs an edit, behavior changed: stop.

---

## 9. Acceptance criteria

- [ ] `pyproject.toml`:
  - `check_untyped_defs = true`
  - `select` includes `"BLE"` and `"S"`
  - per-file ignores exactly as in §7.1
  - no other `[tool.mypy]` / `[tool.ruff]` changes
- [ ] `mypy src` exits 0 with the repo config. `grep -rn "type: *ignore" src` shows **no new entries** versus `main`.
- [ ] `ruff check` (whole repo) and `ruff format --check` exit 0. `pre-commit run --all-files` exits 0.
- [ ] `pytest -q -m "not integration"` is green, including `tests/test_wire_shapes.py` with goldens unchanged since Step 0.
- [ ] `pytest -q -m integration tests/integration` is green.
- [ ] `skillgate check skills/pdf` exits 0, and `skillgate check skills/pdf-sabotaged --expect-fail` exits 0.
- [ ] `rg -c "dict\[str, Any\]" src` sums to **≤ 515**, with the per-file targets in §6.7 met exactly or lower.
- [ ] Every broad `except` in `src/` matches a row in §7.2. `rg -n "except (Exception|BaseException)" src` shows only rows 1–3 and 11–28 (rows 4–10 are gone).
- [ ] No public API, CLI or JSON output changes:
  - golden tests are unchanged
  - no CLI help or text diff (`skillgate --help` and every `skillgate <cmd> --help` output is identical to `main`; capture it in the PR description)
  - no FastAPI route signature or annotation diff (`git diff main -- src/skillgate_ai/api*.py` touches only `api.py:62–63` pragmas, `api_compare.py:178,224` pragmas, and the `api_payloads.py` edits in §6.5)
- [ ] The PR description lists:
  - the Step 1 measured mypy delta
  - every fix made under §5.4 / §7.4
  - the deferred hot spots (§6.8)
  - the intended BLE behavior delta (§7.2)

---

## 10. DO NOT TOUCH

- **No module splits, moves or renames.** No new modules in `src/` (TypedDicts live in their owning modules). New files are allowed only for: `tests/test_wire_shapes.py`, `tests/test_narrowed_excepts.py`, `tests/test_typing_lint_config.py`, `docs/specs/audit-typing-lint.md`.
- **No coverage or CI scanning changes (PR C):**
  - `.github/workflows/*`
  - `.pre-commit-config.yaml`
  - coverage config
  - bandit, pip-audit or CodeQL jobs
  - `uv.lock` and `[project.dependencies]` / extras
- **No behavior changes:**
  - control flow, defaults, return values, messages, exit codes, exception types for expected failures, key order and JSON bytes all stay the same
  - the only allowed runtime deltas are the documented BLE outcome (§7.2) and the `_MISSING` sentinel object identity class (§5.2)
- **Judge settings lookup:** do not edit `judge_settings.py` (including `judge_settings_path`, line 90, and `load_judge_settings`, line 95), `paths.py` (`project_root`), or any code that decides where the judge settings file is read or written.
- **FastAPI:**
  - do not change any route function's parameters or return annotation (`api.py`, `api_skills.py`, `api_evals.py`, `api_runs.py`, `api_compare.py`, `api_intake.py`, `api_shims.py`, `local_ui/*`)
  - do not use TypedDicts from this PR in pydantic models or FastAPI signatures
- **Security surfaces from PR A:** `sandbox.py`, `http_retry.py`, `openai_http.py`, `local_guard.py`, `run_lock.py`, `helper.py` and `launchd.py` take pragma comments only. The exception is the `helper.py:69` signature annotation (§5.2).
- **Seed packs:** nothing under `skills/` is edited.
- **`judge_openai/__init__.py` `__all__`**, `case_pack/models.py` fields and aliases, and the `Harness` Protocol in `harness/base.py`.
- **mypy:** no plugins (`pydantic.mypy`), no `[[tool.mypy.overrides]]`, no `ignore_errors`.
- **`.spec-prompt-audit-typing-lint.txt`** (untracked): do not commit.

---

## 11. Follow-ups (not this PR)

1. A `CheckRow` TypedDict for `case_pack/suites.checks_from_pack` → `fixture_bind` → `pins.pin_checks` → `api_*`.
2. `OutputRow` for workspace/golden artifact rows (`workspace_outputs`, `case_pack/dataset`, `engine/verdict`, `judge_context.enrich_output_row`).
3. Type `HarnessResult.spans` / `TaskReport.spans` as `list[OtlpSpan]` once every span producer, including history reload, goes through one parser. Then remove the `spans.py:448` cast.
4. `judge_openai/outcome.py` answer/cell TypedDicts.
5. Replace the `str → Literal` `# type: ignore[arg-type]` sites (`api_evals.py`, `cli/pack_case.py`, `pack_edit.py:207,209`) with validated `Literal` narrowing.
6. **PR C:**
   - coverage gate
   - bandit/pip-audit/CodeQL in CI
   - re-evaluate the S603 pragma density versus an allowlisted subprocess wrapper
