## DO-NOT-TOUCH
- `tests/**` except the new file `tests/test_engine.py`. Do not edit `conftest.py`, `test_judge.py`, `test_no_trigger_selection.py`, or any `test_qa_*`/`test_dogfood_*` file. If one of them goes red, fix your change, not the test.
- Any runtime expression in `src/`. No reordered statements, no new `assert`/`isinstance`/`if`, no changed defaults, no renames, no file splits, no moves.
- `[tool.mypy]` global keys (`check_untyped_defs = false`, `warn_unused_ignores = false`, `ignore_missing_imports`, `exclude`), `[tool.ruff*]`, `[tool.pytest.ini_options]`, `[project*]` deps.
- `.github/workflows/gate.yml`, `.pre-commit-config.yaml`, `Dockerfile`, `skills/`, `src/skillgate_ai/local_ui/static/`, `src/skillgate_ai/examples/`.
- `docs/specs/mypy-engine-tests.md` is superseded by this spec. Leave it in place.

## Step order
Make one commit per step. Run `pytest -q && ruff check && ruff format --check && mypy src` after each one, and every step must be green before the next starts.
1. **Baseline.** Copy `pyproject.toml` to `/tmp/pp.toml`, delete its `[[tool.mypy.overrides]]` block, and run `mypy --config-file /tmp/pp.toml src --no-pretty --no-error-summary | cut -d: -f1 | sort | uniq -c | sort -n`. Save the output for the PR body. Do not commit the temp file.
2. **Add `tests/test_engine.py`** against the unmodified `engine.py`. It must pass before any `src/` edit.
3. **`engine.py`**: the 3 edits below. Delete `"skillgate_ai.engine"` from the override.
4. **`mode.py`, `run_lock.py`, `gate.py`, `judge_images.py`**: one commit each, deleting each entry from the override as you go.
5. **Tier B REMOVE modules**, one commit each, in table order. If one hits the flip rule, revert that commit and mark the module KEEP.
6. **`pyproject.toml`**: rewrite the header comment and add a reason comment to every KEEP entry.

**Allowed edits** (no other kind): annotation widen/narrow to match what the code already does · a bare local declaration (`x: T`) · `Final` constants · `cast()` where an earlier line already proves the type · `if TYPE_CHECKING:` imports · scoped `# type: ignore[<code>]  # <reason>` (never a bare ignore).

**Flip rule:** a module needs more than 10 edits, or any edit outside the allowed list → it is KEEP. Exception: the 5 Tier A modules may not flip. Their extra errors get allowed edits, with a scoped ignore as the last resort.

## Mypy shrink (per module)
### Tier A — REMOVE (mandatory, exact edits)
| Module | Exact edit |
|---|---|
| `engine` | (1) L713: `) -> tuple[bool, list[str], dict[str, Any] \| None]:` → `) -> tuple[bool \| None, list[str], dict[str, Any] \| None]:` (L756 returns `None`). (2) Insert `passed: bool \| None` as a new line right after L972 `review = False`, at the same indent. (3) L803 `passed: bool,` → `passed: bool \| None,`. Leave `_apply_mismatch` alone: it only ever receives a `bool`. |
| `mode` | L10 `from typing import Literal` → `from typing import Final, Literal`. L12 `LOCAL = "local"` → `LOCAL: Final = "local"`. L13 `CLOUD = "cloud"` → `CLOUD: Final = "cloud"`. |
| `run_lock` | L14 `fcntl = None` → `fcntl = None  # type: ignore[assignment]  # Windows has no fcntl`. |
| `gate` | L220 `harness: str,` → `harness: str \| None,` (`run_check` passes `str \| None` at L194, and L239 already handles `None`). Fix any other error with the allowed list only. |
| `judge_images` | No known errors. Delete the entry and fix anything step 1 reported with the allowed list only. |

### Tier B — REMOVE (attempt; the flip rule applies)
| Module | Expected error shape → allowed fix |
|---|---|
| `compare_git` | subprocess `str \| bytes` and `Optional` locals → local declarations. |
| `scaffold` | `Path \| str` params → widen the annotation. |
| `pack_edit` | template `dict` invariance → `Mapping[str, Any]` on params it only reads. |
| `checks_show` | `object` after an existing `isinstance` → `cast`. |
| `workspace_outputs` | return `list[dict]` widening → annotation only. |
| `sandbox` | `Sandbox` Protocol vs `LocalSandbox`/`DockerSandbox` attrs → change the Protocol annotations only. Do not touch `run` bodies. |
| `judge_settings` | config dict reads → `cast` or local declarations. |

### KEEP (write the exact `# reason` comment shown, at the end of each entry's line)
| Module | Reason comment |
|---|---|
| `advice` | `# FixAdvice unions over judge dicts; needs TypedDict` |
| `api` | `# untyped request JSON; needs validation models` |
| `api_compare` | `# untyped request JSON; needs validation models` |
| `api_runs` | `# route returns mix dict/Response; behavior-adjacent` |
| `case_import` | `# YAML Any unions; needs guarded rewrites` |
| `case_pack` | `# 1k lines of YAML/JSON Any; own PR` |
| `catalog` | `# dynamic catalog rows; needs TypedDict` |
| `cli` | `# Typer Option defaults + str\|None flows` |
| `cli_pack` | `# Typer Option defaults + str\|None flows` |
| `compare` | `# deep report-dict Any; own PR` |
| `harness` | `# 2k lines JSONL/subprocess Any; own PR` |
| `helper` | `# sync payload dicts; needs TypedDict` |
| `judge` | `# Judge Protocol kwargs vs impls; own PR` |
| `judge_context` | `# trajectory dict Any unions; own PR` |
| `judge_openai` | `# raw HTTP payloads; needs provider TypedDicts` |
| `judge_spec` | `# merged YAML spec dicts; own PR` |
| `local_ui.api` | `# untyped request JSON; needs validation models` |
| `local_ui.server` | `# dynamic http.server handler attrs` |
| `report` | `# report_to_dict Any fan-out; own PR` |
| `span_facts` | `# span dict Any unions; own PR` |
| `usage` | `# numeric dict math over Any; own PR` |

**Final override:** 21 KEEP entries (plus any Tier B flips), sorted alphabetically, with `ignore_errors = true` unchanged. Replace the header comment (L133–134) with:
`# Modules still ignored. Each line says why. Shrink one module per PR (annotation-only).`

## tests/test_engine.py
**Rules:** no network, no subprocess, no agent CLI. Pass `judge=SkipJudge()` or a fake to every `run_eval`/`_run_task` call. Fakes stay local to the file.

**Fixtures and fakes**
- `skill_dir(tmp_path)`: writes `tmp_path/"skills"/"demo"/"SKILL.md"` = `"---\nname: demo\ndescription: Demo skill for engine tests.\n---\n# demo\n"` and returns that dir.
- `_skill(skill_dir)` = `ingest_skill(skill_dir, strict=False)`.
- `_task(id, prompt=None, expect="demo", **kw)` = `TaskSpec(id=id, prompt=prompt or f"do {id}", expect_skill=expect, scorers=[ScorerSpec(type="skill_trigger")], **kw)`.
- `_spec(*tasks, timeout=10)` = `SuiteSpec(suite="s", skill="demo", timeout_sec=timeout, tasks=list(tasks))`.
- `_rep(passed, id="t")` = `TaskReport(task_id=id, prompt="p", expect_skill=None, passed=passed, scores=[], selected_skill=None)`.
- `FakeHarness(name="fake", picks: dict[str, str | None] | None = None, raises=None, stderr="", on_run=None)`: `run()` appends the prompt to `self.calls`. If `raises` is set, it raises that. Otherwise it calls `on_run()` if set and returns `HarnessResult(trigger=TriggerEvidence(selected_skill=picks.get(prompt, "demo")), stderr=stderr, transcript="t")`. Set `supported_models = ()`.
- `RecordingJudge(verdict: dict, why="because")`: `name="openai"`. `judge(*a, **k)` appends to `self.judge_calls` and returns `dict(verdict)`. `explain_fail(*a, **k)` appends to `self.why_calls` and returns `why`.
- `ExplodingJudge`: both methods raise `AssertionError`.
- `FakeControl(kill_after_end=None)`: plain attrs `kill_requested=False`, `skip_requested=False`, `begun=[]`, `ended=0`. `begin_task(id, prompt)` appends `id`. `end_task()` adds 1 to `ended` and sets `kill_requested = True` when `ended == kill_after_end`. `note_usage(u)` does nothing. `usage_dict()` returns `None`.
- `RecordingSandbox(inner: LocalSandbox)` proxies `workspace`/`output_sink`/`run` and sets `closed=True` in `close()`. Patch it in with `monkeypatch.setattr(engine, "open_sandbox", ...)`.
- `crumbs` fixture: `monkeypatch.setattr(engine, "breadcrumb_task", lambda phase, tid, **kw: calls.append((phase, tid, kw)))`.

**Pure helpers**
- `test_suite_passed_false_beats_none`: `_suite_passed([_rep(True), _rep(None), _rep(False)]) is False`.
- `test_suite_passed_none_when_any_unscored`: `[_rep(True), _rep(None)]` → `is None`.
- `test_suite_passed_true_when_all_pass`: `[_rep(True), _rep(True)]` → `is True`, and `_suite_passed([]) is True`.
- `test_task_timeout_override_wins`: setenv `SKILLGATE_TASK_TIMEOUT_SEC=30`, `_task("a", timeout_sec=20)`, `_spec(timeout=10)`, `timeout_override=5` → `== 5`.
- `test_task_timeout_env_beats_task_and_spec`: env `"30"` → `== 30`.
- `test_task_timeout_env_ignored_when_invalid` (parametrize `["", "  ", "abc", "0", "-5"]`): `env_task_timeout_sec() is None` and `task_timeout_sec(...) == 20`.
- `test_task_timeout_task_beats_suite_default`: delenv → `20`. A task with `timeout_sec=None` → `10`.
- `test_apply_mismatch_noop_without_mismatch`: `_apply_mismatch(True, ["a"], None) == (True, ["a"])`, and the same with `""`.
- `test_apply_mismatch_prepends_once`: `(True, ["a"], "m")` → `(False, ["m", "a"])`. `(True, ["m"], "m")` → `(False, ["m"])`.
- `test_resolve_path_absolute_passthrough`: `_resolve_path(r, s, str(abs_p)) == abs_p`.
- `test_resolve_path_first_existing_base`: file only under `suite_dir` → `== (suite_dir/rel).resolve()`. File under both root and suite_dir → root wins.
- `test_resolve_path_falls_back_to_root`: nothing exists → `== (root/rel).resolve()`.
- `test_resolve_pack_stamp_fingerprint_defaults_ids_to_tasks`: `fp="fp"`, `ids=None`, tasks a,b → `("fp", ("a", "b"))`. `ids=["x"]` → `("fp", ("x",))`.
- `test_resolve_pack_stamp_none_without_skill_path`: `(None, spec, pack_fingerprint=None, pack_case_ids=None) == (None, None)`.
- `test_why_expected_no_trigger_short_name_uppercased`: `skill_name="pdf"` → `"No PDF skill triggered"`. `"longname"` → `"No longname skill triggered"`. `None` → `"No skill triggered"`.
- `test_why_expected_golden_dict_wins`: trigger task, golden `{"body": "x"}` → `is` that same dict.
- `test_why_expected_file_then_check_contains`: scorer `files=[FileExpect(path="o", contains="F")]` → `"F"`. Only `checks=[RubricCheck(id="c", contains="C")]` → `"C"`.
- `test_why_expected_none_when_nothing_declared`: trigger task, golden `None`, plain scorer → `is None`.
- `test_usage_totals_none_without_usage`: `SuiteReport(... tasks=[_rep(True)]).usage_totals is None`.
- `test_usage_totals_sums_and_rounds_cost`: usages `{"tokens_in": 1, "cost_usd": 0.1234567}` and `{"tokens_in": 2, "cost_usd": 0.1}` → `tokens_in == 3`, `cost_usd == round(0.2234567, 6)`, and `"tokens_out"` is absent.
- `test_usage_totals_single_label_propagates`: both rows have `agent_cost_label="sub"` → `== "sub"`. Different labels → key absent.
- `test_usage_totals_flags_cost_unknown`: `{"tokens_total": 5}` → `cost_unknown is True`. Add `agent_cost_label="sub"` → `"cost_unknown"` is absent.
- `test_eval_progress_done_running_queued`: tasks t1–t3, reports `[_rep(True, "t1")]`, `pack_case_ids=["a"]` → statuses `["done", "running", "queued"]`, `current_task_id == "t2"`, `completed_count == 1`, `task_count == 3`, `pack_case_ids == ("a",)`.
- `test_eval_progress_forced_running_task`: `running_task=t3`, `running_transcript="tx"` → t2 `"queued"`, t3 `"running"` with transcript `"tx"`, `current_task_id == "t3"`.

**Verdict logic** (paths that `test_judge.py` does not cover)
- `test_live_verdict_trigger_fail_forces_red_and_clears_review`: judge `{"passed": True, "review": True}`, `trigger_passed=False`, `det_failures=["x"]` → `(False, ["x"], {..., "passed": False, "review": False})`.
- `test_live_verdict_trigger_fail_default_reason`: `det_failures=[]`, judge `None` → `(False, ["Did not trigger (description does not match this request)"], None)`.
- `test_live_verdict_non_dict_judge_keeps_det`: judge `None`, det `(True, [])` → `(True, [], None)`.
- `test_live_verdict_extra_failures_fail`: `{"extra_failures": [" e ", ""], "passed": True}` → `passed is False`, `failures == ["e"]`, `stamped["passed"] is False`.
- `test_live_verdict_error_unusable_answer_is_red`: `{"status": "error", "reason": UNUSABLE_ANSWER}`, det True → `(False, [UNUSABLE_ANSWER])`, `stamped["passed"] is False`, `stamped["quality_unscored"] is True`.
- `test_live_verdict_error_reason_fallback_chain`: `{"status": "error", "reasons": ["r2"]}` → `failures == ["r2"]`, `passed is None`. `{"status": "error"}` → `["Quality was not scored."]`.
- `test_live_verdict_judge_pass_overrides_det`: `{"passed": True, "reasons": []}`, `det_passed=False` → `passed is True`. This pins current behavior.
- `test_live_verdict_judge_fail_without_reasons_uses_det_or_default`: det `["d"]` → `["d"]`. det `[]` → `["The judge couldn't score this check."]`.
- `test_live_verdict_filters_blank_warnings`: `warnings=["w", " "]` → `stamped["warnings"] == ["w"]`.
- `test_stabilize_passthrough_non_dict`: `stabilize_adherence_review(None, []) is None`.
- `test_stabilize_unchanged_when_scorer_failed`: a failing `Score` → the result `is judged` (identity).
- `test_stabilize_clears_unsure_pass_lock_cell`: `key` = first `CHECK_CELL_ORDER` entry that is in `PASS_LOCK`, `choice = sorted(PASS_LOCK[key])[0]`. Precondition: `canonical_choice(key, choice).strip().lower() in PASS_LOCK[key]`. Cell `{"status": "unsure", "choice": choice}`, warnings `[LOW_CONFIDENCE_WARNING]` → `"status" not in out["cells"][key]`, `out["review"] is False`, `LOW_CONFIDENCE_WARNING not in out["warnings"]`.
- `test_stabilize_keeps_unsure_failing_choice_without_extras`: choice `"zzz-not-a-choice"` → the result `is judged`.
- `test_explain_fail_skipped_when_passed`: `passed=True` with `RecordingJudge` → returns judged unchanged, `why_calls == []`.
- `test_explain_fail_skipped_on_error_or_unscored`: `{"status": "error"}` and `{"quality_unscored": True}` → `why_calls == []`.
- `test_explain_fail_attaches_stripped_why`: `why="  w  "`, `passed=False` → `out["why"] == "w"`, `len(why_calls) == 1`. Also run with `passed=None` → `"why"` is set.
- `test_explain_fail_blank_why_ignored`: `why="  "` → `"why" not in out`.

**`_run_task`** (all calls use `sandbox=LocalSandbox(tmp_path/"ws")`, `root=suite_dir=tmp_path`, `skills=[_skill(skill_dir)]`)
- `test_run_task_missing_golden_short_circuits`: monkeypatch `skillgate_ai.case_pack.task_missing_golden` to return True → `failures == [MISSING_GOLDEN_REASON]`, `passed is False`, `harness.calls == []`.
- `test_run_task_missing_input_file_raises_suite_error`: `files=[FileCopy(src="evals/fixtures/nope.pdf", dest="in.pdf")]` → `SuiteError`, with `"nope.pdf"` in `.message`.
- `test_run_task_golden_input_files_are_skipped`: `FileCopy(src="evals/goldens/x.txt", dest="x")` → no raise, `passed is True`.
- `test_run_task_check_aborted_maps_reason` (parametrize `(KILL, KILL_FAILURE)`, `("skip", SKIP_FAILURE)`): `raises=CheckAborted(r)` → `skipped is True`, `failures == [expected]`.
- `test_run_task_timeout_is_mapped`: `raises=subprocess.TimeoutExpired(["x"], 5)` → `HarnessError`.
- `test_run_task_other_exception_reraised_unchanged`: `RuntimeError("boom")` → `pytest.raises(RuntimeError, match="boom")`.
- `test_run_task_quota_raises_harness_error_exit_2` (parametrize stderr `"Weekly usage limit reached"` → hint `"Wait until the agent quota resets, then retry."`, `"Cannot use this model: x"` → hint `"Pick an available model, then retry."`): `exc.exit_code == 2`, `exc.hint == hint`.
- `test_run_task_kill_or_skip_after_run_returns_skipped` (parametrize attr `kill_requested`→KILL_FAILURE / `skip_requested`→SKIP_FAILURE): `on_run` sets the attr on `FakeControl` → `failures == [expected]`, `control.ended == 1`.
- `test_run_task_non_live_harness_is_deterministic`: `ExplodingJudge`, picks `"demo"` → `passed is True`, `judge is None`. Picks `"other"` → `passed is False`, `failures != []`.
- `test_run_task_live_pass_sets_review_from_judge`: `name="cursor-agent"`, verdict `{"status": "done", "passed": True, "reasons": [], "review": True, "cells": {}}` → `passed is True`, `review is True`, `len(judge_calls) == 1`, `why_calls == []`.
- `test_run_task_live_fail_calls_explain_fail_once`: verdict `passed False`, `reasons ["bad"]` → `failures == ["bad"]`, `len(why_calls) == 1`, `report.judge["why"] == "because"`.
- `test_run_task_no_trigger_live_skips_judge`: `expect=None`, picks `None`, `cursor-agent`, `ExplodingJudge` → `passed is True`, and `report.judge["status"] == "skip"`.
- `test_run_task_resets_sink_and_ends_control_on_error`: `FakeControl` plus `RuntimeError` → after the raise, `sandbox.output_sink is None`, `control.ended == 1`, `control.begun == ["a"]`.
- `test_run_task_breadcrumb_end_once` (uses `crumbs`): on success, the phases are `["start", "end"]` and the end kwargs contain `"passed"`. On `RuntimeError`, the phases are `["start", "end"]` and the end kwargs are `{"passed": False}`.

**`run_eval`** (`project_root=tmp_path`, `skill_override=str(skill_dir)`, `sandbox_kind="local"`, `docker_image="x"`, `judge=SkipJudge()`, `strict_ingest=False`)
- `test_run_eval_requires_suite_or_spec`: no `spec` and no path → `SuiteError`, message `"No eval suite given."`.
- `test_run_eval_red_when_any_task_fails`: picks `{"do t2": "other"}` → `passed is False`, `[t.passed for t in r.tasks] == [True, False]`.
- `test_run_eval_green_when_all_pass`: `passed is True`, `r.incomplete is False`, `r.timeout_effective == 10`.
- `test_run_eval_max_tasks_slices`: 3 tasks, `max_tasks=1` → `incomplete is True`, `next_task_index == 1`, `passed is False`, `advice is None`, `len(tasks) == 1`.
- `test_run_eval_start_index_keeps_prior_reports`: `start_index=1`, `prior_reports=[_rep(True, "t1")]` → task ids `["t1", "t2", "t3"]`, `harness.calls == ["do t2", "do t3"]`.
- `test_run_eval_kill_marks_remaining_skipped_in_order`: `FakeControl(kill_after_end=1)` → ids `["t1", "t2", "t3"]`, `tasks[0].skipped is False`, `tasks[1:]` skipped with `failures == [KILL_FAILURE]`.
- `test_run_eval_emits_progress_once_plus_per_task`: 2 tasks → 3 events, `[e.completed_count for e in events] == [0, 1, 2]`.
- `test_run_eval_closes_sandbox_even_when_task_raises`: `RecordingSandbox` plus `raises=RuntimeError` → raises, `sandbox.closed is True`.
- `test_run_eval_explicit_fingerprint_stamped`: `pack_fingerprint="fp"` → `r.pack_fingerprint == "fp"`, `r.pack_case_ids == ("t1", "t2")`.

## Acceptance criteria
- `mypy src` exits 0. The override has at most 21 entries, and every entry carries a `# reason` comment from the KEEP table.
- `git diff main -- src/` contains only allowed-edit lines. The `engine.py` diff is exactly the 3 edits, and `mode.py` is exactly 3 lines.
- `pytest -q` passes with no edits to existing tests. `pytest tests/test_engine.py -q` collects at least 60 cases and finishes in under 5 s.
- `test_engine.py` imports nothing from `subprocess` except `TimeoutExpired` and does no network I/O.
- `ruff check`, `ruff format --check`, `skillgate check skills/pdf` (exit 0), and `skillgate check skills/pdf-sabotaged --expect-fail` (exit 0) all pass.
- The PR body contains the step 1 baseline table, the final per-module result, and any Tier B flips with their error counts.

## Explicit non-goals
- No new mypy flags (`check_untyped_defs`, `disallow_untyped_defs`, `strict`, `warn_unused_ignores`).
- No fixes to KEEP modules, even trivial ones.
- No behavior changes. `test_live_verdict_judge_pass_overrides_det` pins the current behavior; it is not a bug fix.
- No new fixtures in `conftest.py`, no new dependencies, no shared fake module.
- No deduplication or deletion of overlapping tests in `test_judge.py` or `test_qa_*`.
- No changes to `docs/` beyond this spec, no CHANGELOG entry, no version bump.
