# Split giant modules (behavior-preserving)

This change turns six oversized modules in `src/skillgate_ai/` (`harness`, `engine`, `cli`, `case_pack`, `judge_openai`, `compare`) into packages of the same name, and splits `cli_pack.register_pack_commands` into one register function per command. Each package's `__init__.py` becomes a re-export shim, so every import path that works today keeps working and returns the same objects. After the split, no file in scope is over 600 lines and no function is over 100 lines. Nothing else changes: CLI text, exit codes, command order, lazy-import timing and dependencies stay the same. Tests change only where a monkeypatch target has to follow the code to its new module (see "Patch seams"), plus two tests that read source files by path. One new test, `tests/test_public_imports.py`, locks the import surface and the CLI surface. It is written first, against the current flat modules.

## DO-NOT-TOUCH
- **Behavior.** Do not change messages, hints, exit codes, stdout/stderr text, JSON keys, command or option names, help strings, the order commands are registered, or defaults. Lazy (function-local) imports stay lazy. They move with the code they guard and keep their import target, except for the three repoints listed under "Patch seams". Add no new dependencies and no new top-level imports of third-party packages.
- **`tests/**`.** No changes to assertions, test names, skips or xfails, and no deleted tests. The only allowed test edits are:
  - (a) the monkeypatch targets in the "Patch seams" table;
  - (b) the `cli.py` path read in `tests/test_oss_surface.py`;
  - (c) the `judge_openai.py` entry in `_JUDGE_SOURCES` in `tests/test_decision_judges_only.py`;
  - (d) the new `tests/test_public_imports.py`.
  
  Do not add `__init__.py` or a second `conftest.py` under `tests/`.
- **`pyproject.toml`.** Leave `[project*]` alone, including the version, dependencies, extras and the `skillgate` / `skillgate-ai = "skillgate_ai.cli:app"` scripts. Leave `[tool.pytest*]` alone. Only two edits are allowed:
  1. rewrite override module strings in place to the `.*` form (see Acceptance);
  2. add one ruff per-file-ignore line for `src/skillgate_ai/cli/*.py` (B008, the same rule `cli*.py` already has).
- **`.github/workflows/gate.yml`** must stay byte-identical. Also leave `Dockerfile`, `.pre-commit-config.yaml`, `web/`, `skills/`, `src/skillgate_ai/examples/`, `src/skillgate_ai/local_ui/static/` and `CHANGELOG.md` alone.
- **`cli_compare.py`** stays a sibling file and is untouched. It keeps its lazy `from skillgate_ai.cli import _bind_key_env, _boot, _emit_json, _resolve_pack_arg, console`.
- **`scripts/extract-from-skillgate-ai.sh`** lists file paths from the source repo. Leave it as is and list it in the PR body as a follow-up.
- **`docs/`**: change nothing except this spec. Delete `docs/specs/_split-giant-files-prompt.md` in the final commit, not in step 1. Leave the untracked `.spec-prompt-slim-deps.txt` alone.

## Acceptance criteria
- **No leftover flat files.** `src/skillgate_ai/{harness,engine,cli,case_pack,judge_openai,compare}.py` no longer exist; each is now a package directory with `__init__.py`. `cli_pack.py` remains as a re-export shim file.
- **Size limits.** Every `.py` file under those six packages, plus `cli_pack.py`, is **≤ 600 lines**. Every `def` in them, including methods and nested defs, is **≤ 100 lines**, measured as `end_lineno - lineno + 1` on the `def` node. Check both with:
  ```bash
  python - <<'EOF'
  import ast, pathlib
  base = pathlib.Path("src/skillgate_ai")
  files = [base / "cli_pack.py"] + [p for d in ("harness","engine","cli","case_pack","judge_openai","compare") for p in (base / d).rglob("*.py")]
  bad = []
  for p in files:
      text = p.read_text(encoding="utf-8")
      if text.count("\n") > 600: bad.append(f"{p}: {text.count(chr(10))} lines")
      for n in ast.walk(ast.parse(text)):
          if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.end_lineno - n.lineno + 1 > 100:
              bad.append(f"{p}:{n.lineno} {n.name} {n.end_lineno - n.lineno + 1}")
  print("\n".join(bad) or "ok"); raise SystemExit(1 if bad else 0)
  EOF
  ```
- **mypy overrides.** In `[[tool.mypy.overrides]]`, rewrite these five strings in place: `"skillgate_ai.harness"`, `"skillgate_ai.cli"`, `"skillgate_ai.case_pack"`, `"skillgate_ai.compare"` and `"skillgate_ai.judge_openai"` each become `"<same>.*"` and keep their comment. mypy's `foo.*` matches `foo` and every submodule. The list stays at **21 entries**; nothing is added. `skillgate_ai.engine` is not in the list and its package must pass mypy as is. You may delete the `"skillgate_ai.cli_pack"` entry if `mypy src` stays green; otherwise keep it.
- **CI commands pass after every commit:**
  ```bash
  ruff check src tests
  ruff format --check src tests
  mypy src
  pytest -q
  pytest -q -m integration tests/integration
  (cd web && pnpm install --frozen-lockfile && pnpm test)
  ```
  The web command matches the `test` job in `gate.yml`.
- **Public import test.** `tests/test_public_imports.py` passes at every commit, starting with step 1 on the unsplit code.
- **No stale patch targets.** `grep -rnE '"skillgate_ai\.harness\.[A-Za-z_]+"' tests` lists only `harness_auth_status`, `run_official_login` and `description_fits_request`. `grep -rn 'setattr(engine,' tests` prints nothing. `grep -rn 'skillgate_ai.compare.run_check' tests` prints nothing.
- **Entry point.** `skillgate --help`, `skillgate checks show path_efficiency` and `python -m skillgate_ai.cli --help` all exit 0.

## Rules that apply to every package
1. **Layout.** Use a package (`X/__init__.py` plus submodules), not `X_*.py` siblings, for three reasons:
   - The import path `skillgate_ai.X` stays the same module object.
   - The mypy override can be rewritten in place to `X.*` without adding entries. Siblings would need new override entries, which is forbidden.
   - Each module's code stays in one directory.
2. **Shim = `__init__.py`.** It holds a docstring, `from __future__ import annotations`, and re-exports written as `from skillgate_ai.X.sub import name as name` (the redundant alias satisfies ruff F401 and mypy). `judge_openai` also keeps its current `__all__`, unchanged. `cli` also makes one call, `register_all()` (see cli). The shim contains no `def`, `class` or logic.
   - **Re-export set** = every name bound at module scope in the original file (every `def`, `class` and constant in the AST inventory, private names included) plus the listed pass-through imports.
   - Do **not** re-export stdlib modules (`subprocess`, `shutil`, `getpass`, `Path`, …) or other helpers that were only imported. Leaving them out makes any stale monkeypatch fail loudly with `AttributeError` instead of silently doing nothing.
   - Do not add `__all__` to shims that lack one today; that would change `import *` behavior.
3. **Move code verbatim.** Only imports change. Run `ruff check --fix` (isort) and `ruff format` after each move. Splitting a >100-line function means extracting methods: cut contiguous blocks into private helpers in the same submodule and pass state in and out as arguments and return values. Identical blocks may share one helper (only in `cli._run_gate`, named below).
4. **Dependency direction.** Each package has a strict order, low to high, given per package. A submodule imports only from lower submodules, with absolute imports (`from skillgate_ai.harness.base import …`).
   - Submodules **never** import their own package's `__init__`. Importing any submodule runs the parent `__init__` first, so a submodule that imports the shim at module level would see it half-built.
   - If moving code exposes an upward dependency, move the symbol down. If that is impossible, use a function-local import and note it in the PR body.
   - A private constant lives next to its readers. If its readers span several submodules, it goes in the lowest one.
5. **Submodule names must not equal any re-exported name.** Importing `pkg.foo` sets the attribute `pkg.foo`, which would clash with a re-exported `foo`. The names below were chosen to avoid this, and `test_public_imports.py` enforces it.
6. **Patch seams.** A seam is a name that a test monkeypatches. Tests patch a seam where it is **looked up**:
   - Code in the seam's defining submodule calls it by its bare name.
   - Code in **other submodules** must call it as `module.seam(...)` after `from skillgate_ai.harness import bins` (or the equivalent). It must **not** use `from … import seam`, because that binds the name at import time and the patch would never reach it.
   - The table lists every seam and its new patch target.
7. **Patching a shim has no effect** on code inside the package, except for the three seams that are only read through the shim by lazy imports outside the package. Say this in each shim docstring.

## Patch seams (test edits allowed, path only)

| Today's target (file:line) | New target | Why |
|---|---|---|
| `"skillgate_ai.harness._resolve_agent_bin"` (conftest:98, test_harness_agents, test_harness_auth) | `"skillgate_ai.harness.bins._resolve_agent_bin"` | callers in agents/resolve/auth/login use `bins.` |
| `"skillgate_ai.harness._resolve_codex_bin"`, `"…_resolve_claude_bin"` (conftest:99, …) | `"skillgate_ai.harness.bins.<same>"` | same |
| `"skillgate_ai.harness._codex_ready"`, `_cursor_ready`, `_claude_ready` | `"skillgate_ai.harness.auth.<same>"` | callers in agents/resolve use `auth.` |
| `"skillgate_ai.harness._codex_session_ok"`, `_cursor_session_ok`, `_claude_session_ok` (conftest:53-55, …) | `"skillgate_ai.harness.auth.<same>"` | read inside auth |
| `"skillgate_ai.harness._probe_codex_login_status"`, `_probe_cursor_login_status`, `_probe_claude_login_status` | `"skillgate_ai.harness.auth.<same>"` | read inside auth |
| `"skillgate_ai.harness.claude_auth_kind"` | `"skillgate_ai.harness.auth.claude_auth_kind"` | read in auth, and by `cli login` (repointed, see below) |
| `"skillgate_ai.harness._run_inherited"` | `"skillgate_ai.harness.login._run_inherited"` | read inside login |
| `"skillgate_ai.harness._write_selection"`, `_read_selection`, `_parse_selected`, `_resolve_trigger_evidence`, `_parse_read_paths` | `"skillgate_ai.harness.selection.<same>"` | callers in agents/prompts use `selection.` |
| `"skillgate_ai.harness.subprocess.run"` (test_harness_auth:212) | `"skillgate_ai.harness.auth.subprocess.run"` | patches stdlib globally; auth imports `subprocess` |
| `"skillgate_ai.harness.subprocess.Popen"` (test_harness_auth:822, 914) | `"skillgate_ai.harness.login.subprocess.Popen"` | global; login imports `subprocess` |
| `"skillgate_ai.harness.shutil.which"`, `"skillgate_ai.harness.Path.home"` (test_harness_auth:770-771) | `"skillgate_ai.harness.bins.shutil.which"`, `"skillgate_ai.harness.bins.Path.home"` | global; bins imports both |
| `"skillgate_ai.harness.harness_auth_status"`, `run_official_login`, `description_fits_request` | **unchanged** | only read through the shim by lazy imports in `cli`, `api` and `scorers`; there are no readers inside the package |
| `monkeypatch.setattr(engine, "breadcrumb_task", _crumb)` (test_engine:54) | `monkeypatch.setattr("skillgate_ai.engine.task.breadcrumb_task", _crumb)` | only `_run_task` reads it |
| `monkeypatch.setattr(engine, "open_sandbox", open_rec)` (test_engine:1153) | `monkeypatch.setattr("skillgate_ai.engine.run.open_sandbox", open_rec)` | only `run_eval` reads it |
| `monkeypatch.setattr(case_pack, "task_missing_golden", …)` (test_engine:692) | **unchanged** | `engine.task` lazily does `from skillgate_ai.case_pack import task_missing_golden`, which reads the shim |
| `"skillgate_ai.compare.run_check"` (test_compare_cli:84,245,305; test_compare_models:114,172,305) | `"skillgate_ai.compare.models.run_check"` | `_run_models_compare` reads its module global |
| `"skillgate_ai.cli._stdin_is_tty"` (test_keys:116,130; test_harness_auth:671) | `"skillgate_ai.cli.base._stdin_is_tty"` | defined in base; `_login_targets` calls `base._stdin_is_tty()` |
| `"skillgate_ai.cli.getpass.getpass"` (test_keys:117) | `"skillgate_ai.cli.base.getpass.getpass"` | global; base imports `getpass` |

**Source import repoints.** These are the only changes to import targets, and each keeps its lazy or top-level placement:
1. `compare_git.run_git_versions_compare`: lazy `from skillgate_ai.compare import run_check as default_run` becomes `from skillgate_ai.compare.models import run_check as default_run`. This gives every `run_check` lookup in compare a single namespace.
2. `cli login`'s lazy import block: import `claude_auth_kind` from `skillgate_ai.harness.auth`. Leave the other names on the shim, since `harness_auth_status` and `run_official_login` are shim seams. Do this in step 6, while it is still in `cli.py`.
3. `register_pack_commands`' lazy `from skillgate_ai.cli import …` stays as written. It is now split per register function, and each function imports only the names it uses.

## Step order
Work on branch `cursor/split-giant-files` in one PR, with one commit per step. Every commit must pass every Acceptance command before the next step starts. The order goes from fewest seams and dependents to most. `cli` comes last because it depends on every other shim and carries the registration-order risk.

1. **`tests/test_public_imports.py`** against the flat modules. Fill `CLI_SURFACE_SHA256` from the observed value. If the observed command order differs from the lists in this spec, use the observed order and record it in the PR under **Spec deviations**.
2. **`judge_openai`** becomes `src/skillgate_ai/judge_openai/{__init__,backend,payload,outcome,decisions}.py`. Also: the `_JUDGE_SOURCES` path edit, and the override `"skillgate_ai.judge_openai.*"`.
3. **`case_pack`** becomes `src/skillgate_ai/case_pack/{__init__,models,store,dataset,pins,suites}.py`. Override `"skillgate_ai.case_pack.*"`.
4. **`compare`** becomes `src/skillgate_ai/compare/{__init__,core,payload,models,versions,store}.py`. Also: the `compare_git` lazy repoint, retargeting `run_check` in tests, and the override `"skillgate_ai.compare.*"`.
5. **`engine`** becomes `src/skillgate_ai/engine/{__init__,models,adherence,verdict,task,run}.py`. Also: the two test_engine retargets. No override change.
6. **`harness`** becomes `src/skillgate_ai/harness/{__init__,base,messages,transcripts,bins,selection,commands,prompts,auth,login,agents,resolve}.py`. Also: the harness seam retargets (conftest, test_harness_auth, test_harness_agents and others), the `cli.py` `claude_auth_kind` repoint, and the override `"skillgate_ai.harness.*"`.
7. **`cli` + `cli_pack`**: create `src/skillgate_ai/cli/{__init__,__main__,base,tree,cmd_agents,cmd_gate,cmd_deploy,cmd_keys,cmd_scaffold,cmd_judge,cmd_ui,pack_commands,pack_skill,pack_history,pack_case,pack_judge}.py`, and turn `src/skillgate_ai/cli_pack.py` into a shim. Also:
   - the `test_oss_surface.py` path edit;
   - the cli seam retargets;
   - the ruff per-file-ignore `"src/skillgate_ai/cli/*.py" = ["B008"]`;
   - the override `"skillgate_ai.cli.*"`.
8. **Cleanup.** Delete `docs/specs/_split-giant-files-prompt.md`.

In each package step, create the submodules first, then replace the original file with `__init__.py`. Delete the old `X.py`: a module and a package with the same name must not both exist.

---

## judge_openai (1001 lines)

**Order:** `backend` → `payload` → `outcome` → `decisions`. Nothing in the package may import `judge_providers.jev` or `clef` at module level, because they import `skillgate_ai.judge_openai` at their top.

| Symbol | New module |
|---|---|
| `DEFAULT_MODEL`, `GATEWAY_DECISIONS_MODEL`, `DEFAULT_TIMEOUT_SEC`, `WHY_TIMEOUT_SEC`, `WHY_MAX_OUTPUT_TOKENS`, `WHY_OUTPUT_CHARS`, `TRANSCRIPT_TAIL_CHARS`, `DISPLAY_NAME`, `GATEWAY_DISPLAY_NAME`, `CHOSEN_DISPLAY_NAME`, `_decisions_model`, `JudgeBackend`, `_OpenAIPosted` | `backend` |
| `_tail`, `_cell_entry`, `_user_content`, `_state_text`, `_artifacts_without_bodies`, `_expected_outcome_text`, `_text_blob`, `_path_is_recorded`, `_path_not_available_cell`, `_finished_answers`, `_answer_row`, `_normalize_answers`, `_answers_from_decisions_list`, `_lift_decision_answer`, `_annotate_payload_too_large` | `payload` |
| `OutcomeJudge`, `_scoring_endpoint`, `_sum_judge_usage`, `_as_path` | `outcome` |
| `DecisionsBackend`, `ping_openai_backend`, `make_openai_judge` | `decisions` |

**Shim:** re-exports every symbol above. Pass-throughs are imported straight from their source modules: `DEFAULT_BASE_URL`, `OUT_OF_CREDITS`, `redact_secrets` and `user_message_for_status` from `skillgate_ai.openai_http`; `IMAGE_MAX_BYTES`, `IMAGE_MAX_COUNT` and `collect_images` from `skillgate_ai.judge_images`. Keep `__all__` byte-identical, including its `# Re-export for tests` comment.

**Over 100 lines:** `OutcomeJudge._stamp` (143). Split it within `outcome.py`:
- `OutcomeJudge._stamp_error(self, evaluated, *, model, citations, soft_questions, extra_warnings, spec) -> dict`: the whole `status != "completed"` branch (current L712-739), including the `upstream` stamp.
- `OutcomeJudge._verdict_cells(self, pass_answers, soft_answers, *, include_path, confidence) -> dict[str, dict]`: the CHECK and SOFT cell loops (L756-767).
- Module-level `_extra_cell(question, raw) -> tuple[dict[str, Any], dict[str, Any] | None]`: the body of the `for question in resolved.extras` loop (L769-807). It returns the cell and the cleaned raw answer, or `None` when `raw` is not a Mapping. The caller does `cells[q.id] = cell` and, when the cleaned value is not `None`, `extra_answers[q.id] = cleaned`, in the same order as today.

`judge` (97 lines) and `DecisionsBackend.evaluate` (47) move verbatim.

**Test path edit:** in `tests/test_decision_judges_only.py`, replace the `ROOT / "src" / "skillgate_ai" / "judge_openai.py"` entry of `_JUDGE_SOURCES` with `*sorted((ROOT / "src" / "skillgate_ai" / "judge_openai").glob("*.py"))`. The banned-fragment scan must still cover all judge code. Without this edit, an emptied file would pass vacuously.

## case_pack (1091 lines)

**Order:** `models` → `store` → `dataset` → `pins` → `suites`.

| Symbol | New module |
|---|---|
| `CASES_REL`, `PIN_NEEDS_EXPECTED`, `PIN_NEEDS_EXPECTED_HINT`, `NO_TRIGGER_OUTPUT_WARNING`, `EXPECTED_WITHOUT_TARGET`, `PACK_FINGERPRINT_FIELDS`, `_CASE_ID_RE`, `_JSONISH_RE`, `CaseFileCopy`, `CaseInput`, `CaseGolden`, `PackCase`, `CasePack`, `TrustSuite`, `_reject_missing_seed_cases`, `_reject_removed_seed_cases` | `models` |
| `pack_judge_dict`, `save_pack_judge`, `reset_pack_judge`, `expected_without_target_warning`, `cases_path`, `load_case_pack`, `save_case_pack`, `_dump_pack`, `_validate_pack_on_disk` | `store` |
| `dataset_view`, `_preview_file`, `_OPTIONAL_OUTPUT_NOTE`, `golden_state`, `actual_output_state`, `case_for_task`, `MISSING_GOLDEN_REASON`, `no_trigger_output_warning`, `task_missing_golden` | `dataset` |
| `pin_checks`, `pin_case_ids`, `_skill_name`, `_file_copies`, `_inline_input_text`, `_case_from_check`, `_file_content`, `_persist_input_files`, `_disk_golden`, `_persist_golden` | `pins` |
| `pack_fingerprint`, `suite_fingerprint`, `suite_from_pack`, `checks_from_pack`, `skill_has_dataset`, `trust_suite_for_skill`, `suite_from_checks`, `expand_from_pack`, `checks_fingerprint`, `_project_root_for_skill`, `_bundled_suite_trust`, `_template_trust` | `suites` |

**Shim:** re-exports all of the above, plus these pass-throughs: `GOLDEN_TAIL_CHARS`, `read_capped_text` and `sniff_output_bytes` from `skillgate_ai.pack_files`; `ExtraQuestion` and `JudgeBlock` from `skillgate_ai.pack_schema`.

**Over 100 lines:** none. `suite_from_pack` (80), `golden_state` (56) and `dataset_view` (49) move verbatim.

**Cycles:** `engine` reads `case_pack` only through lazy imports of the shim, and that must stay so: the `task_missing_golden` seam depends on it. `case_pack` imports neither `engine` nor `harness`.

## compare (971 lines)

**Order:** `core` → `payload` → `store` → `models` → `versions`. `models` imports `run_check` from `skillgate_ai.gate` at top, as today. `versions` imports `run_models_compare` from `models` and keeps its lazy `compare_git` imports. `compare_git` keeps its top-level `from skillgate_ai.compare import (…)` through the shim. This is safe because no compare submodule imports `compare_git` at module level. Only its lazy `run_check` import is repointed (see Patch seams).

| Symbol | New module |
|---|---|
| `MAX_ARMS`, `MIN_ARMS`, `DEFAULT_MAX_SPEND_USD`, `ALLOWED_COMPARE_HARNESS`, `CompareError`, `CompareArmSpec`, `CompareResult`, `arm_label_defaults`, `parse_arm_spec`, `parse_arm_file`, `_resolved_arm_model`, `_blank`, `_as_int`, `_as_float`, `_arm_ids`, `arm_id_for_index`, `validate_compare_plan`, `_resolve_compare_case_ids`, `checks_for_case_ids` | `core` |
| `_usage_for_task_ids`, `_dry_run_payload`, `_skill_pack_hash_from_report`, `_usage_from_report`, `_task_map`, `_build_cases`, `scrub_compare_payload`, `scrub_customer_compare_payload`, `_subtitle_for_arm`, `_plan_subtitle`, `_case_ids_from_report`, `_arm_stats_from_report` | `payload` |
| `find_compare`, `find_compare_anywhere`, `list_compares`, `list_compares_merged`, `strip_compare_list_meta` | `store` |
| `_append_compare_failure`, `run_models_compare`, `_run_models_compare` | `models` |
| `_history_report`, `preflight_versions_compare`, `_git_ref_picker_suggestions`, `_versions_dry_run_payload`, `harness_from_history`, `_normalize_compare_harness`, `run_versions_compare`, `_run_versions_compare` | `versions` |

**Shim:** re-exports all of the above, plus the pass-through `run_check`, imported from `skillgate_ai.compare.models` for compatibility. Its docstring says that patching `skillgate_ai.compare.run_check` does nothing.

**Over 100 lines:**
- `_run_models_compare` (143), in `models.py`:
  - `_run_arm(spec, *, runner, pack, root, run_checks, job_control) -> tuple[str, Any, float]`: L503-529. It covers `run_id`, `set_current_run`, `create_control`, the `try/finally drop_control`, the duration, and raising `CompareError` with exit code 2.
  - `_live_arm_row(spec, report, *, run_id, duration_sec, active_case_ids) -> tuple[dict, dict | None]`: L541-565. It returns the row and `usage`; the caller adds to `spent`.
  - `_models_payload(pack, *, compare_id, pack_fp, pack_case_ids, status, arm_rows, active_case_ids, max_spend_usd, spent, stopped_reason) -> dict`: L582-599.
  - The lazy `from skillgate_ai.report import report_to_dict` and the fingerprint-drift check stay in the loop body.
  - `runner = run_check_fn or run_check` stays in `_run_models_compare`, because it is the seam.
- `_run_versions_compare` (113), in `versions.py`:
  - `_rerun_arms(pack, run_ids) -> list[CompareArmSpec]`: L842-864, including the "Could not load run configs" error.
  - `_history_arm_rows(run_ids, reports, case_ids) -> list[dict]`: L884-904.
  - `_versions_payload(pack, *, compare_id, fingerprint, case_ids, arm_rows) -> dict`: L905-917.

`_versions_dry_run_payload` (79) moves verbatim.

**Cycles:** `compare` → `gate` → `engine` and `harness`; nothing below `gate` imports `compare`. `compare_control` lazily imports `find_compare_anywhere` from the shim; keep it that way.

## engine (1293 lines)

**Order:** `models` → `adherence` → `verdict` → `task` → `run`. It imports `harness` through the shim at top, as today (`Harness`, `HarnessResult`, `_write_selection`, `cannot_run_message`, `is_live_harness`, `usage_limit_message`). The lazy imports of `case_pack`, `harness` (`claude_native_skills_enabled`, `AUTH_CLI_LOGIN`), `workspace_outputs`, `metrics`, `usage` and `judge_context` move with their code and keep their targets.

| Symbol | New module |
|---|---|
| `SKIP_FAILURE`, `KILL_FAILURE`, `TaskReport`, `TaskProgress`, `EvalProgress`, `SuiteReport` | `models` |
| `_extras_all_passed`, `_extras_from_log`, `_extras_from_text`, `_extras_from_source`, `_is_builtin_quality_reason`, `_NON_WORDING_FAIL`, `_wording_only_builtin_reason`, `stabilize_adherence_review` | `adherence` |
| `_outcome_judge_outputs`, `_resolve_task_spec`, `_score_rows`, `_run_outcome_judge`, `_apply_mismatch`, `CORRECTLY_SKIPPED`, `_no_trigger_skipped_judge`, `_live_verdict`, `_why_expected_output`, `_maybe_explain_fail` | `verdict` |
| `task_timeout_sec`, `env_task_timeout_sec`, `_seed_skill_selection`, `_run_task`, `_skipped_report`, `_spans_from_transcript` | `task` (imports `breadcrumb_task`, `span` from `observability`) |
| `run_eval`, `_suite_passed`, `_resolve_path`, `_reference_twin`, `_resolve_pack_stamp`, `_emit_progress`, `_eval_progress` | `run` (imports `open_sandbox` from `sandbox`) |

**Shim:** re-exports all of the above and nothing else. In particular, not `breadcrumb_task` or `open_sandbox`, so a stale `setattr(engine, …)` raises.

**Over 100 lines:**
- `_run_task` (267). The `breadcrumb_task` calls, the `ended` flag, `try/finally` and the `with span(...)` blocks stay in `_run_task`. Extract into `task.py`:
  - `_missing_golden_report(task, skill_root) -> TaskReport | None`: L870-887, keeping the lazy `case_pack` import. The caller sets `ended = True` before returning a non-`None` result.
  - `_stage_workspace(task, skills, harness, sandbox, *, root, suite_dir, skill_root) -> None`: L888-921. Covers input copies, `prepare_workspace` with the lazy `claude_native_skills_enabled` import, trigger mode, and the seeded selection.
  - `_raise_if_run_blocked(result) -> None`: L938-953.
  - `_task_usage(control, result) -> dict | None`: L963-971.
  - `_judge_task(task, *, artifacts, result, scores, skills, harness, judge, skill_root, spans, steps, errors, had_path, file_baseline) -> tuple[bool | None, list[str], Any, bool]`: L984-1033. It returns `(passed, failures, judged, review)` and computes `det_passed`, `det_failures` and `trigger_passed` the same way.
  - `_combined_usage(task_usage, judged, result, run_config) -> dict | None`: L1034-1053, keeping the lazy `usage` and `harness.AUTH_CLI_LOGIN` imports.
  - `_task_advice(task, scores, skills, result, *, reference, sibling_prompts, judged)`: L1054-1069.
- `run_eval` (164), in `run.py`:
  - `_load_eval_inputs(suite_path, spec, project_root, skill_override, strict_ingest) -> tuple[SuiteSpec, Path, list[Skill], list[str | Path]]`: L373-390.
  - `_fill_killed(reports, spec) -> None`: L464-469.
  - `_sliced_report(...) -> SuiteReport`: L471-488.
  - `open_sandbox(...)` stays in `run_eval`'s loop, because it is the seam.

`stabilize_adherence_review` (95), `_run_outcome_judge` (87), `_eval_progress` (78) and `_live_verdict` (60) move verbatim.

**Cycles:** `gate` → `engine` → `harness`; `harness` never imports `engine`. `report` imports `engine` at top; `engine` never imports `report` at module level.

## harness (2032 lines)

**Order:** `base` → `messages` → `transcripts` → `bins` → `selection` → `commands` → `prompts` → `auth` → `login` → `agents` → `resolve`. Calls to a seam from another submodule go through the module object: `bins._resolve_*_bin`, `auth._cursor_ready` / `_codex_ready` / `_claude_ready`, `selection._write_selection` / `_parse_selected` / `_read_selection` / `_resolve_trigger_evidence`. From the grep there are about 35 such call sites, in `agents` (CursorAgentHarness L224-252, CodexCliHarness L610-655, ClaudeCodeHarness L715-756), `resolve` (L779-831), `auth` (L1008-1333), `login` (L1444-1452) and `prompts` (L1703).

| Symbol | New module |
|---|---|
| `AUTH_API_KEY`, `AUTH_CLI_LOGIN`, `AUTH_NONE`, `LOGIN_AGENTS`, `LOGIN_TIMEOUT_SEC`, `LOGIN_TIMEOUT_ENV`, `_login_timeout_sec`, `_AGENT_INSTALL`, `HarnessResult`, `harness_usage`, `Harness`, `_STOP`, `tokenize`, `rank_skills`, `select_skill_from_descriptions`, `description_fits_request`, `LIVE_HARNESS_NAMES`, `is_live_harness`, `CODEX_CHATGPT_DEFAULT`, `_CODEX_REJECTED_MODEL`, `_CODEX_SUPPORTED_MODELS` | `base` |
| `_MODEL_ACCESS_ERROR`, `_claude_model_access_error`, `_claude_model_access_message`, `_CLAUDE_MODEL_ACCESS_HINT`, `_codex_rejected_chatgpt_model`, `_codex_rejected_model`, `codex_chatgpt_model_hint`, `_AUTH_FAILURE_RE`, `USAGE_LIMIT_MESSAGE`, `MODEL_UNAVAILABLE_MESSAGE`, `_USAGE_LIMIT_RE`, `_MODEL_UNAVAILABLE_RE`, `usage_limit_message`, `model_unavailable_message`, `cannot_run_message`, `_raise_if_cannot_run`, `auth_failure_message`, `_raise_if_auth_failed` | `messages` |
| `_claude_used_model`, `_busiest_model_usage`, `_codex_used_model`, `_jsonl_spans`, `_jsonl_transcript`, `_codex_transcript`, `_cursor_transcript` | `transcripts` |
| `_resolve_agent_bin`, `_executable_path`, `_looks_like_bin_path`, `_resolve_codex_bin`, `_resolve_claude_bin`, `_pinned_has_agent_entry` | `bins` |
| `_SKILL_FILE_RE`, `_write_selection`, `_MISSING`, `_read_selection`, `_parse_selected`, `_skill_tool_name_from_args`, `_infer_from_skill_tool`, `_skill_load_path`, `_resolve_trigger_evidence`, `_parse_skill_json`, `_skill_for_selection`, `_parse_read_paths`, `_parse_read_paths_from_spans`, `_collect_read_paths`, `_infer_from_reads`, `_skill_name_from_path` | `selection` |
| `_cursor_exec_command`, `_codex_model_flag`, `_codex_exec_command`, `_CLAUDE_PREAMBLE`, `_CLAUDE_SYSTEM_PREAMBLE`, `_CLAUDE_WORKSPACE_TOOLS`, `_claude_code_exec_command`, `_SKILL_WALK_SKIP`, `_SKILL_WALK_MAX_DEPTH`, `_toml_basic_string`, `_codex_user_skill_roots`, `_skill_markdown_files`, `_codex_user_skill_config_override`, `_claude_sandbox_env`, `_sandbox_run` | `commands` |
| `_workspace_trigger_mode`, `_trigger_mode_prompt`, `_claude_trigger_mode_prompt`, `_claude_discover_prompt`, `_claude_skill_paths`, `_claude_prompt`, `claude_native_skills_enabled`, `claude_config_isolation_enabled`, `_agent_prompt`, `_cursor_discover_prompt`, `_cursor_prompt` | `prompts` |
| `_codex_auth_key`, `_CODEX_LOGIN_STATUS_TIMEOUT_SEC`, `_codex_ready`, `_codex_login_status_authenticated`, `_probe_codex_login_status`, `_codex_session_ok`, `_CURSOR_LOGIN_STATUS_TIMEOUT_SEC`, `_cursor_login_status_authenticated`, `_probe_cursor_login_status`, `_cursor_session_ok`, `_cursor_ready`, `_CLAUDE_LOGIN_STATUS_TIMEOUT_SEC`, `_claude_login_status_authenticated`, `_probe_claude_login_status`, `_claude_session_ok`, `_claude_ready`, `cursor_auth_kind`, `codex_auth_kind`, `claude_auth_kind`, `_display_status`, `normalize_login_agent`, `harness_auth_status`, `format_harness_status` | `auth` |
| `_terminate_process_group`, `_run_inherited`, `run_official_login` | `login` |
| `CursorAgentHarness`, `CodexCliHarness`, `ClaudeCodeHarness` | `agents` |
| `harness_is_startable`, `_named_harness`, `resolve_harness`, `_LIVE_HARNESS_KINDS`, `_AGENT_PRIORITY`, `_agent_candidates`, `startable_agent_kinds`, `has_startable_agent`, `live_harness_or_error`, `auto_live_harness_name` | `resolve` |

**Shim:** re-exports all of the above. No stdlib names.

**Over 100 lines:** none. Today's largest are `CodexCliHarness.run` (69), `_infer_from_skill_tool` (68), `ClaudeCodeHarness.run` (66), `run_official_login` (62), `_cursor_prompt` (56) and `_codex_exec_command` (55). All move verbatim.

**Cycles:** these modules import `harness` at top: `advice`, `eval_config`, `judge`, `report`, `gate` and `engine`. These import it lazily: `config`, `scorers`, `api`, `fixture_bind` and `cli`. Among `harness`'s top-level dependencies (`config`, `errors`, `ingest`, `sandbox`, `scorers`, `spans`, `usage`), none imports `harness` at top. Keep it that way: `config` → `harness` and `scorers` → `harness` stay lazy.

## cli (1282 lines) + cli_pack (506)

`ruff`'s isort (`I`) sorts imports alphabetically, so import order cannot control command order. Command order lives in one explicit table in `cli/tree.py`. Command functions are defined **without** decorators in `cmd_*` modules and registered by calling the decorators: `app.command("check")(check_pack)`. That is equivalent, because Typer's decorator returns the function unchanged. Copy each decorator's arguments verbatim.

**Order:** `base` → `cmd_*` → `pack_skill` / `pack_history` / `pack_case` / `pack_judge` → `pack_commands` → `tree`. `cmd_*` and `pack_*` modules may import from `base` at top. `pack_*` keep today's lazy `from skillgate_ai.cli import …` inside their register functions and helpers. `__init__.py` binds every re-export **before** calling `register_all()`, because `cli_compare` and `pack_*` read `_boot`, `_resolve_pack_arg`, `_bind_key_env`, `_emit_json` and `console` through the shim at registration time.

| Symbol | New module |
|---|---|
| `app`, `console`, `_emit_json`, `_boot`, `_version_callback`, `_main` (keeps `@app.callback()`), `_HARNESS_HELP`, `_SANDBOX_HELP`, `_KEY_ENV_HELP`, `_VERBOSE_HELP`, `_parse_targets`, `_bind_key_env`, `_stdin_is_tty`, `_read_omitted_key`, `_resolve_pack_arg` | `base` |
| `keys_app`, `examples_app`, `judge_app`, `judge_provider_app`, `checks_app`, `case_app`, plus their `add_typer` calls in today's order (keys, examples, judge, judge→provider, checks, case) | `base` |
| `version`, `_print_agent_status`, `_login_targets` (calls `base._stdin_is_tty()`), `login`, `doctor`, `ingest` | `cmd_agents` |
| `_present_check`, `_verbose_scoring_lines`, `_run_gate`, `check_pack`, `run_suite` (imports `run_check` from `gate`) | `cmd_gate` |
| `deploy`, `sync`, `connect`, `helper`, `list_assets` | `cmd_deploy` |
| `keys_set`, `keys_clear`, `keys_list` | `cmd_keys` |
| `init_cmd`, `new_cmd`, `example_cmd`, `examples_list_cmd`, `examples_install_cmd` | `cmd_scaffold` |
| `checks_show_cmd`, `judge_show`, `judge_reset`, `judge_add_question_cmd`, `case_add_cmd`, `judge_provider_show`, `judge_provider_set`, `_run_judge_test`, `judge_test`, `judge_provider_test` | `cmd_judge` |
| `ui_cmd` | `cmd_ui` |
| `register_all` (new) | `tree` |
| `_output_optional_flag`; `register_case_list`, `register_case_remove`, `register_case_edit`, `register_case_import`, `register_case_bind` | `pack_case` |
| `register_skill_app` (creates `skill_app` and calls `add_typer`, returns it), `register_import_command`, `register_skill_write`, `register_skill_paste` | `pack_skill` |
| `register_history_app` (creates `history_app`, calls `add_typer`, registers the `invoke_without_command` callback with its nested `_print_history_rows` / `_print_skill_versions`, returns `history_app`), `register_history_show`, module-level `_find_history_row`, `_print_history_run` | `pack_history` |
| `register_judge_remove_question`, `register_judge_set_question` | `pack_judge` |
| `register_pack_commands(app, case_app, judge_app)`: calls, in order, `register_skill_app` → `register_import_command` → `register_skill_write` → `register_skill_paste` → `register_history_app` → `register_history_show` → `register_case_list` → `register_case_remove` → `register_case_edit` → `register_case_import` → `register_case_bind` → `register_judge_remove_question` → `register_judge_set_question` | `pack_commands` |

**`tree.register_all()`** registers in exactly this order, which mirrors today's file order:
1. `app`: `version`, `login`, `doctor`, `ingest`, `"check"`, `"run"`, `deploy`, `sync`, `connect`, `helper`, `"list"`
2. `keys_app`: `"set"`, `"clear"`, `"list"`
3. `app`: `"init"`, `"new"`, `"example"`
4. `examples_app`: `"list"`, `"install"`
5. `checks_app`: `"show"`
6. `judge_app`: `"show"`, `"reset"`, `"add-question"`
7. `case_app`: `"add"`
8. `judge_provider_app`: `"show"`, `"set"`
9. `judge_app`: `"test"`
10. `judge_provider_app`: `"test"`
11. `app`: `"ui"`
12. `register_pack_commands(app, case_app, judge_app)`
13. `register_compare_commands(app, key_env_help=_KEY_ENV_HELP)`

**Shims:**
- `cli/__init__.py` re-exports every symbol in the table except `register_all` (which it imports and calls once as its last statement). It also re-exports `register_pack_commands` (from `skillgate_ai.cli.pack_commands`) and `register_compare_commands` (from `skillgate_ai.cli_compare`); both are module attributes today.
- `cli/__main__.py` contains `from skillgate_ai.cli import app` and then `app()`. This replaces the old `if __name__ == "__main__"` guard.
- `cli_pack.py` contains only `from skillgate_ai.cli.pack_case import _output_optional_flag as _output_optional_flag` and `from skillgate_ai.cli.pack_commands import register_pack_commands as register_pack_commands`.

**Over 100 lines:**
- `_run_gate` (131), in `cmd_gate.py`:
  - `_exit_with_error(exc, *, machine: bool) -> NoReturn`: the three identical blocks at L319-329, L334-344 and L365-375. It emits `{"error","hint","exit_code"}` or `console.print(exc.render())`, then `raise typer.Exit(exc.exit_code) from None`.
  - `_tryout_checks(target, case_id, *, machine) -> list`: L309-344, keeping both lazy imports.
  - `_finish_gate(result, *, machine, summary, verbose) -> NoReturn`: L376-417.
  - `machine = json_out or summary == "json"` is computed once at the top of `_run_gate`. It is the same expression all three sites use today.
- `register_pack_commands` (489): split per command as above. Every `register_*` stays ≤ 100 lines.
- `history_show` (about 100): `_find_history_row(run_id, pack) -> tuple[dict, Path | None]` is L250-278. It still raises `SkillGateError(f"No run named {run_id}.")`; the caller keeps the `except`/render/exit. `_print_history_run(row) -> None` is L288-341. Both are module-level and lazily import `console`, `_boot` and `_resolve_pack_arg` from `skillgate_ai.cli`.

`login` (89), `judge_show` (85) and `case_add_cmd` (51) move verbatim.

**Test path edit:** in `tests/test_oss_surface.py`, `test_local_ui_may_exist_without_hosted_names` currently parses `ROOT / "cli.py"`. Change it to collect `_imported_names` over `sorted((ROOT / "cli").rglob("*.py"))` and check the same two assertions against the combined set.

**Cycles:**
- `cli` ↔ `cli_pack`: `cli_pack` is now a leaf shim over `skillgate_ai.cli.pack_*`. The `pack_*` modules import nothing from `skillgate_ai.cli` at module level, so importing `cli_pack` first is safe; it initializes the `cli` package, which imports `pack_commands`, which never imports the shim at top.
- `cli` ↔ `cli_compare`: unchanged. `cli_compare` is imported at top of `tree.py`, so the old E402 bottom import goes away. Its `cli` import is still lazy, inside `register_compare_commands`.
- B008 in `cli/` is covered by the new per-file-ignore line.

---

## Public import inventory (grep of `src/`, `tests/`, `scripts/` at 82e77aa)

The registry in the new test is a superset: every module-scope name plus the pass-throughs. Below are the names that real importers use today.

- **`skillgate_ai.harness`**
  - src, top-level imports: `advice` (`select_skill_from_descriptions`, `tokenize`), `eval_config` (`CODEX_CHATGPT_DEFAULT`), `judge`, `report` (`is_live_harness`), `gate` (`is_live_harness`, `live_harness_or_error`), `engine` (`Harness`, `HarnessResult`, `_write_selection`, `cannot_run_message`, `is_live_harness`, `usage_limit_message`).
  - src, lazy imports: `config` (`has_startable_agent`, `startable_agent_kinds`, `auto_live_harness_name`), `scorers` (`description_fits_request`), `fixture_bind` (`is_live_harness`), `api` (`harness_auth_status`, `ClaudeCodeHarness`, `CodexCliHarness`, `CursorAgentHarness`, `normalize_login_agent`, `run_official_login`), `cli` (`format_harness_status`, `harness_auth_status`, `normalize_login_agent`, `AUTH_CLI_LOGIN`, `claude_auth_kind`, `cursor_auth_kind`, `run_official_login`), `engine` (`claude_native_skills_enabled`, `AUTH_CLI_LOGIN`).
  - tests: `AUTH_API_KEY`, `AUTH_CLI_LOGIN`, `AUTH_NONE`, `ClaudeCodeHarness`, `CodexCliHarness`, `CursorAgentHarness`, `HarnessResult`, `_MISSING`, `_claude_code_exec_command`, `_claude_login_status_authenticated`, `_codex_exec_command`, `_codex_login_status_authenticated`, `_codex_model_flag`, `_codex_rejected_model`, `_codex_used_model`, `_cursor_discover_prompt`, `_cursor_exec_command`, `_cursor_login_status_authenticated`, `_infer_from_skill_tool`, `_jsonl_transcript`, `_login_timeout_sec`, `_read_selection`, `_resolve_agent_bin`, `_resolve_trigger_evidence`, `_run_inherited`, `auth_failure_message`, `auto_live_harness_name`, `claude_auth_kind`, `claude_config_isolation_enabled`, `claude_native_skills_enabled`, `codex_auth_kind`, `codex_chatgpt_model_hint`, `cursor_auth_kind`, `description_fits_request`, `harness_auth_status`, `harness_is_startable`, `has_startable_agent`, `is_live_harness`, `live_harness_or_error`, `resolve_harness`, `run_official_login`, `select_skill_from_descriptions`. Patched seams are in the seam table.
- **`skillgate_ai.engine`**
  - src, top-level: `gate` (`EvalProgress`, `SuiteReport`, `run_eval`), `report` (`EvalProgress`, `SuiteReport`, `TaskProgress`, `TaskReport`).
  - tests: `SuiteReport`, `TaskReport`, `EvalProgress`, `TaskProgress`, `run_eval`, `_live_verdict`, `_maybe_explain_fail`, `stabilize_adherence_review`, `_run_task`, `_seed_skill_selection`, `_why_expected_output`.
  - `test_engine` module attributes: `KILL_FAILURE`, `SKIP_FAILURE`, `_apply_mismatch`, `_eval_progress`, `_resolve_pack_stamp`, `_resolve_path`, `_suite_passed`, `env_task_timeout_sec`, `task_timeout_sec`, plus the names above.
- **`skillgate_ai.cli`**
  - src, lazy: `cli_compare` (`_bind_key_env`, `_boot`, `_emit_json`, `_resolve_pack_arg`, `console`), `cli_pack` (`_boot`, `_resolve_pack_arg`, `console`, `_emit_json`).
  - pyproject: `app`.
  - tests: `app` (about 25 files, including `integration/_support.py` and subprocess strings in `test_optional_extras.py`), `_emit_json` (`test_check_cli`).
- **`skillgate_ai.cli_pack`**: `register_pack_commands`, imported by `cli`.
- **`skillgate_ai.case_pack`**
  - src: `api_evals` (`CASES_REL`, `PIN_NEEDS_EXPECTED_HINT`, `checks_from_pack`, `dataset_view`, `load_case_pack`, `pack_judge_dict`; lazy `CasePack`, `save_case_pack`), `api_intake` (`CASES_REL`), `api_payloads` (`skill_has_dataset`), `case_import` (`PIN_NEEDS_EXPECTED`, `PackCase`, `_inline_input_text`, `_skill_name`, `cases_path`, `expected_without_target_warning`, `load_case_pack`, `pin_checks`), `pack_edit` (`expected_without_target_warning`, `load_case_pack`, `pin_case_ids`, `pin_checks`, `save_case_pack`, `save_pack_judge`), `scaffold` (`CasePack`, `PackCase`, `load_case_pack`, `save_case_pack`), `local_ui/api` (`CasePack`, `dataset_view`, `save_case_pack`), `workspace_outputs` (`read_capped_text`, `sniff_output_bytes`).
  - src, lazy: `scorers` (`sniff_output_bytes`), `ingest` (`load_case_pack`), `suite` (`expand_from_pack`), `fixture_bind` (`trust_suite_for_skill`), `engine` (`actual_output_state`, `case_for_task`, `golden_state`, `load_case_pack`, `MISSING_GOLDEN_REASON`, `task_missing_golden`).
  - tests: `CaseGolden`, `CaseInput`, `CasePack`, `ExtraQuestion`, `JudgeBlock`, `MISSING_GOLDEN_REASON`, `PIN_NEEDS_EXPECTED`, `PackCase`, `_persist_golden`, `actual_output_state`, `checks_from_pack`, `dataset_view`, `expand_from_pack`, `golden_state`, `load_case_pack`, `pack_judge_dict`, `pin_checks`, `read_capped_text`, `reset_pack_judge`, `save_case_pack`, `save_pack_judge`, `skill_has_dataset`, `sniff_output_bytes`, `suite_from_checks`, `suite_from_pack`, `task_missing_golden`, `trust_suite_for_skill` (also `tests/helpers.py`).
- **`skillgate_ai.judge_openai`**
  - src: `judge_providers/jev.py` and `clef.py` at top (`DEFAULT_TIMEOUT_SEC`, `_answers_from_decisions_list`, `_normalize_answers`, `_path_is_recorded`, `_state_text`); `judge_setup` lazy (`DEFAULT_MODEL`, `DEFAULT_BASE_URL`).
  - tests: `DEFAULT_BASE_URL`, `DEFAULT_MODEL`, `DISPLAY_NAME`, `DecisionsBackend`, `GATEWAY_DECISIONS_MODEL`, `IMAGE_MAX_BYTES`, `OUT_OF_CREDITS`, `OutcomeJudge`, `WHY_OUTPUT_CHARS`, `_artifacts_without_bodies`, `_state_text`, `collect_images`, `make_openai_judge`, `ping_openai_backend`, `redact_secrets`.
- **`skillgate_ai.compare`**
  - src: `api_compare` (`CompareArmSpec`, `CompareError`, `arm_id_for_index`, `arm_label_defaults`, `find_compare`, `find_compare_anywhere`, `list_compares_merged`, `parse_arm_spec`, `preflight_versions_compare`, `run_models_compare`, `run_versions_compare`, `scrub_customer_compare_payload`, `strip_compare_list_meta`), `compare_git` (`CompareArmSpec`, `CompareError`, `CompareResult`, `_arm_ids`, `_build_cases`, `_task_map`, `_usage_from_report`; lazy `run_check`), `compare_format` (`scrub_compare_payload`), `compare_control` lazy (`find_compare_anywhere`), `cli_compare` lazy (`CompareError`, `arm_id_for_index`, `parse_arm_file`, `parse_arm_spec`, `run_models_compare`, `scrub_compare_payload`, `scrub_customer_compare_payload`, `validate_compare_plan`, `preflight_versions_compare`, `run_versions_compare`, `find_compare`, `find_compare_anywhere`, `list_compares_merged`, `strip_compare_list_meta`).
  - tests: `CompareError`, `arm_label_defaults`, `parse_arm_spec`, `run_models_compare`, `run_versions_compare`, `scrub_compare_payload`, `scrub_customer_compare_payload`.
- **File-path readers:** `tests/test_oss_surface.py:114` (`cli.py`), `tests/test_decision_judges_only.py:22` (`judge_openai.py`), `scripts/extract-from-skillgate-ai.sh` (out of scope).

## New test: `tests/test_public_imports.py`

```python
"""Import and CLI surface of the split modules (docs/specs/split-giant-files.md).

REGISTRY is every module-scope name on main at 82e77aa. Shims must re-export all of
them, unchanged. CLI_SURFACE_SHA256 pins every command, option, default and help string.
"""

from __future__ import annotations

import ast
import hashlib
import importlib
import inspect
import pkgutil
import tomllib
from pathlib import Path

import click
import pytest
from typer.main import get_command

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "skillgate_ai"

REGISTRY: dict[str, tuple[str, ...]] = {
    "skillgate_ai.harness": (
        "AUTH_API_KEY",
        "AUTH_CLI_LOGIN",
        "AUTH_NONE",
        "LOGIN_AGENTS",
        "LOGIN_TIMEOUT_SEC",
        "LOGIN_TIMEOUT_ENV",
        "_login_timeout_sec",
        "_AGENT_INSTALL",
        "HarnessResult",
        "harness_usage",
        "Harness",
        "_STOP",
        "tokenize",
        "rank_skills",
        "select_skill_from_descriptions",
        "description_fits_request",
        "LIVE_HARNESS_NAMES",
        "is_live_harness",
        "CursorAgentHarness",
        "_cursor_exec_command",
        "CODEX_CHATGPT_DEFAULT",
        "_CODEX_REJECTED_MODEL",
        "_CODEX_SUPPORTED_MODELS",
        "_codex_model_flag",
        "_codex_exec_command",
        "_CLAUDE_PREAMBLE",
        "_CLAUDE_SYSTEM_PREAMBLE",
        "_CLAUDE_WORKSPACE_TOOLS",
        "_claude_code_exec_command",
        "_claude_used_model",
        "_busiest_model_usage",
        "_codex_used_model",
        "_MODEL_ACCESS_ERROR",
        "_claude_model_access_error",
        "_claude_model_access_message",
        "_CLAUDE_MODEL_ACCESS_HINT",
        "_jsonl_spans",
        "_jsonl_transcript",
        "_codex_transcript",
        "_cursor_transcript",
        "_codex_rejected_chatgpt_model",
        "_codex_rejected_model",
        "codex_chatgpt_model_hint",
        "CodexCliHarness",
        "ClaudeCodeHarness",
        "harness_is_startable",
        "_named_harness",
        "resolve_harness",
        "_LIVE_HARNESS_KINDS",
        "_AGENT_PRIORITY",
        "_agent_candidates",
        "startable_agent_kinds",
        "has_startable_agent",
        "live_harness_or_error",
        "auto_live_harness_name",
        "_codex_auth_key",
        "_SKILL_WALK_SKIP",
        "_SKILL_WALK_MAX_DEPTH",
        "_toml_basic_string",
        "_codex_user_skill_roots",
        "_skill_markdown_files",
        "_codex_user_skill_config_override",
        "_CODEX_LOGIN_STATUS_TIMEOUT_SEC",
        "_codex_ready",
        "_codex_login_status_authenticated",
        "_probe_codex_login_status",
        "_codex_session_ok",
        "_CURSOR_LOGIN_STATUS_TIMEOUT_SEC",
        "_AUTH_FAILURE_RE",
        "USAGE_LIMIT_MESSAGE",
        "MODEL_UNAVAILABLE_MESSAGE",
        "_sandbox_run",
        "_USAGE_LIMIT_RE",
        "_MODEL_UNAVAILABLE_RE",
        "_SKILL_FILE_RE",
        "usage_limit_message",
        "model_unavailable_message",
        "cannot_run_message",
        "_raise_if_cannot_run",
        "auth_failure_message",
        "_raise_if_auth_failed",
        "_cursor_login_status_authenticated",
        "_probe_cursor_login_status",
        "_cursor_session_ok",
        "_cursor_ready",
        "_CLAUDE_LOGIN_STATUS_TIMEOUT_SEC",
        "_claude_login_status_authenticated",
        "_probe_claude_login_status",
        "_claude_session_ok",
        "_claude_ready",
        "cursor_auth_kind",
        "codex_auth_kind",
        "claude_auth_kind",
        "_display_status",
        "normalize_login_agent",
        "harness_auth_status",
        "format_harness_status",
        "_terminate_process_group",
        "_run_inherited",
        "run_official_login",
        "_resolve_agent_bin",
        "_executable_path",
        "_looks_like_bin_path",
        "_resolve_codex_bin",
        "_resolve_claude_bin",
        "_pinned_has_agent_entry",
        "_workspace_trigger_mode",
        "_trigger_mode_prompt",
        "_claude_trigger_mode_prompt",
        "_claude_discover_prompt",
        "_claude_skill_paths",
        "_claude_prompt",
        "claude_native_skills_enabled",
        "claude_config_isolation_enabled",
        "_claude_sandbox_env",
        "_agent_prompt",
        "_cursor_discover_prompt",
        "_cursor_prompt",
        "_write_selection",
        "_MISSING",
        "_read_selection",
        "_parse_selected",
        "_skill_tool_name_from_args",
        "_infer_from_skill_tool",
        "_skill_load_path",
        "_resolve_trigger_evidence",
        "_parse_skill_json",
        "_skill_for_selection",
        "_parse_read_paths",
        "_parse_read_paths_from_spans",
        "_collect_read_paths",
        "_infer_from_reads",
        "_skill_name_from_path",
    ),
    "skillgate_ai.engine": (
        "SKIP_FAILURE",
        "KILL_FAILURE",
        "_extras_all_passed",
        "_extras_from_log",
        "_extras_from_text",
        "_extras_from_source",
        "_is_builtin_quality_reason",
        "_NON_WORDING_FAIL",
        "_wording_only_builtin_reason",
        "stabilize_adherence_review",
        "_suite_passed",
        "TaskReport",
        "TaskProgress",
        "EvalProgress",
        "SuiteReport",
        "run_eval",
        "task_timeout_sec",
        "env_task_timeout_sec",
        "_outcome_judge_outputs",
        "_resolve_task_spec",
        "_score_rows",
        "_run_outcome_judge",
        "_apply_mismatch",
        "CORRECTLY_SKIPPED",
        "_no_trigger_skipped_judge",
        "_live_verdict",
        "_seed_skill_selection",
        "_why_expected_output",
        "_maybe_explain_fail",
        "_run_task",
        "_skipped_report",
        "_resolve_path",
        "_reference_twin",
        "_resolve_pack_stamp",
        "_spans_from_transcript",
        "_emit_progress",
        "_eval_progress",
    ),
    "skillgate_ai.cli": (
        "app",
        "console",
        "_emit_json",
        "_boot",
        "_version_callback",
        "_main",
        "version",
        "_print_agent_status",
        "_login_targets",
        "login",
        "doctor",
        "ingest",
        "_present_check",
        "_verbose_scoring_lines",
        "_parse_targets",
        "_bind_key_env",
        "_stdin_is_tty",
        "_read_omitted_key",
        "_run_gate",
        "_HARNESS_HELP",
        "_SANDBOX_HELP",
        "_KEY_ENV_HELP",
        "check_pack",
        "run_suite",
        "deploy",
        "sync",
        "connect",
        "helper",
        "list_assets",
        "keys_app",
        "keys_set",
        "keys_clear",
        "keys_list",
        "init_cmd",
        "new_cmd",
        "example_cmd",
        "examples_app",
        "examples_list_cmd",
        "examples_install_cmd",
        "judge_app",
        "judge_provider_app",
        "checks_app",
        "_resolve_pack_arg",
        "checks_show_cmd",
        "judge_show",
        "judge_reset",
        "judge_add_question_cmd",
        "case_app",
        "case_add_cmd",
        "judge_provider_show",
        "judge_provider_set",
        "_run_judge_test",
        "_VERBOSE_HELP",
        "judge_test",
        "judge_provider_test",
        "ui_cmd",
    ),
    "skillgate_ai.cli_pack": ("_output_optional_flag", "register_pack_commands"),
    "skillgate_ai.case_pack": (
        "CASES_REL",
        "PIN_NEEDS_EXPECTED",
        "PIN_NEEDS_EXPECTED_HINT",
        "NO_TRIGGER_OUTPUT_WARNING",
        "EXPECTED_WITHOUT_TARGET",
        "PACK_FINGERPRINT_FIELDS",
        "_CASE_ID_RE",
        "_JSONISH_RE",
        "CaseFileCopy",
        "CaseInput",
        "CaseGolden",
        "PackCase",
        "CasePack",
        "TrustSuite",
        "_reject_missing_seed_cases",
        "_reject_removed_seed_cases",
        "pack_judge_dict",
        "save_pack_judge",
        "reset_pack_judge",
        "expected_without_target_warning",
        "cases_path",
        "load_case_pack",
        "save_case_pack",
        "pack_fingerprint",
        "suite_fingerprint",
        "suite_from_pack",
        "checks_from_pack",
        "skill_has_dataset",
        "dataset_view",
        "_preview_file",
        "pin_checks",
        "pin_case_ids",
        "trust_suite_for_skill",
        "suite_from_checks",
        "expand_from_pack",
        "checks_fingerprint",
        "_OPTIONAL_OUTPUT_NOTE",
        "golden_state",
        "actual_output_state",
        "case_for_task",
        "_dump_pack",
        "_validate_pack_on_disk",
        "MISSING_GOLDEN_REASON",
        "no_trigger_output_warning",
        "task_missing_golden",
        "_skill_name",
        "_file_copies",
        "_inline_input_text",
        "_case_from_check",
        "_file_content",
        "_persist_input_files",
        "_disk_golden",
        "_persist_golden",
        "_project_root_for_skill",
        "_bundled_suite_trust",
        "_template_trust",
    ),
    "skillgate_ai.judge_openai": (
        "DEFAULT_MODEL",
        "GATEWAY_DECISIONS_MODEL",
        "DEFAULT_TIMEOUT_SEC",
        "WHY_TIMEOUT_SEC",
        "WHY_MAX_OUTPUT_TOKENS",
        "WHY_OUTPUT_CHARS",
        "TRANSCRIPT_TAIL_CHARS",
        "DISPLAY_NAME",
        "GATEWAY_DISPLAY_NAME",
        "CHOSEN_DISPLAY_NAME",
        "_decisions_model",
        "JudgeBackend",
        "_OpenAIPosted",
        "_tail",
        "_cell_entry",
        "_user_content",
        "_state_text",
        "_artifacts_without_bodies",
        "_expected_outcome_text",
        "_text_blob",
        "_path_is_recorded",
        "_path_not_available_cell",
        "_finished_answers",
        "_answer_row",
        "_normalize_answers",
        "_answers_from_decisions_list",
        "_lift_decision_answer",
        "_annotate_payload_too_large",
        "DecisionsBackend",
        "OutcomeJudge",
        "_scoring_endpoint",
        "_sum_judge_usage",
        "_as_path",
        "ping_openai_backend",
        "make_openai_judge",
    ),
    "skillgate_ai.compare": (
        "MAX_ARMS",
        "MIN_ARMS",
        "DEFAULT_MAX_SPEND_USD",
        "ALLOWED_COMPARE_HARNESS",
        "CompareError",
        "CompareArmSpec",
        "CompareResult",
        "arm_label_defaults",
        "parse_arm_spec",
        "parse_arm_file",
        "_resolved_arm_model",
        "_blank",
        "_as_int",
        "_as_float",
        "_arm_ids",
        "arm_id_for_index",
        "validate_compare_plan",
        "_resolve_compare_case_ids",
        "checks_for_case_ids",
        "_usage_for_task_ids",
        "_dry_run_payload",
        "_skill_pack_hash_from_report",
        "_usage_from_report",
        "_task_map",
        "_build_cases",
        "scrub_compare_payload",
        "scrub_customer_compare_payload",
        "_subtitle_for_arm",
        "_plan_subtitle",
        "_case_ids_from_report",
        "_arm_stats_from_report",
        "_append_compare_failure",
        "run_models_compare",
        "_run_models_compare",
        "_history_report",
        "preflight_versions_compare",
        "_git_ref_picker_suggestions",
        "_versions_dry_run_payload",
        "harness_from_history",
        "_normalize_compare_harness",
        "run_versions_compare",
        "_run_versions_compare",
        "find_compare",
        "find_compare_anywhere",
        "list_compares",
        "list_compares_merged",
        "strip_compare_list_meta",
    ),
}

# Names a module re-exports from elsewhere (identity is not checked against the module).
PASS_THROUGH: dict[str, tuple[str, ...]] = {
    "skillgate_ai.case_pack": (
        "GOLDEN_TAIL_CHARS",
        "ExtraQuestion",
        "JudgeBlock",
        "read_capped_text",
        "sniff_output_bytes",
    ),
    "skillgate_ai.judge_openai": (
        "DEFAULT_BASE_URL",
        "OUT_OF_CREDITS",
        "IMAGE_MAX_BYTES",
        "IMAGE_MAX_COUNT",
        "collect_images",
        "redact_secrets",
        "user_message_for_status",
    ),
    "skillgate_ai.compare": ("run_check",),
    "skillgate_ai.cli": ("register_compare_commands", "register_pack_commands"),
}

JUDGE_OPENAI_ALL = (
    "DISPLAY_NAME",
    "GATEWAY_DISPLAY_NAME",
    "IMAGE_MAX_BYTES",
    "IMAGE_MAX_COUNT",
    "OUT_OF_CREDITS",
    "WHY_OUTPUT_CHARS",
    "DecisionsBackend",
    "OutcomeJudge",
    "collect_images",
    "make_openai_judge",
    "redact_secrets",
    "user_message_for_status",
)

# Step 1 records the observed order on main; any later change is a regression.
TOP_COMMANDS = (
    "version",
    "login",
    "doctor",
    "ingest",
    "check",
    "run",
    "deploy",
    "sync",
    "connect",
    "helper",
    "list",
    "init",
    "new",
    "example",
    "ui",
    "import",
    "keys",
    "examples",
    "judge",
    "checks",
    "case",
    "skill",
    "history",
    "compare",
)
SUB_COMMANDS: dict[str, tuple[str, ...]] = {
    "keys": ("set", "clear", "list"),
    "examples": ("list", "install"),
    "judge": (
        "show",
        "reset",
        "add-question",
        "test",
        "remove-question",
        "set-question",
        "provider",
    ),
    "judge provider": ("show", "set", "test"),
    "checks": ("show",),
    "case": ("add", "list", "remove", "edit", "import", "bind"),
    "skill": ("write", "paste"),
    "history": ("show",),
    "compare": ("models", "versions", "show", "cancel", "list"),
}
CLI_SURFACE_SHA256 = "<fill in step 1 from main>"

_ALL = [(m, n) for m, names in REGISTRY.items() for n in names]
_ALL += [(m, n) for m, names in PASS_THROUGH.items() for n in names]


@pytest.mark.parametrize(("module", "name"), _ALL)
def test_symbol_importable(module: str, name: str) -> None:
    assert hasattr(importlib.import_module(module), name), f"{module}.{name} missing"


def test_defined_symbols_belong_to_their_module() -> None:
    for module, names in REGISTRY.items():
        mod = importlib.import_module(module)
        for name in names:
            obj = getattr(mod, name)
            if inspect.isfunction(obj) or inspect.isclass(obj):
                owner = obj.__module__
                assert owner == module or owner.startswith(module + "."), (module, name, owner)


def test_judge_openai_all_unchanged() -> None:
    mod = importlib.import_module("skillgate_ai.judge_openai")
    assert sorted(mod.__all__) == sorted(JUDGE_OPENAI_ALL)


def test_no_submodule_shadows_a_symbol() -> None:
    for module, names in REGISTRY.items():
        path = getattr(importlib.import_module(module), "__path__", None)
        if path is None:
            continue
        subs = {info.name for info in pkgutil.iter_modules(path)}
        assert not subs & (set(names) | set(PASS_THROUGH.get(module, ()))), module


def test_shims_hold_no_code() -> None:
    for module in REGISTRY:
        pkg = SRC / module.split(".")[1] / "__init__.py"
        if not pkg.is_file():
            continue
        for node in ast.parse(pkg.read_text(encoding="utf-8")).body:
            assert not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)), (
                f"{pkg}: {node.name}"
            )


def test_entry_points_unchanged() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["scripts"] == {
        "skillgate-ai": "skillgate_ai.cli:app",
        "skillgate": "skillgate_ai.cli:app",
    }


def _root() -> click.Group:
    from skillgate_ai.cli import app

    cmd = get_command(app)
    assert isinstance(cmd, click.Group)
    return cmd


def test_cli_command_order() -> None:
    root = _root()
    assert tuple(root.commands) == TOP_COMMANDS
    for path, expected in SUB_COMMANDS.items():
        node: click.Command = root
        for part in path.split():
            assert isinstance(node, click.Group)
            node = node.commands[part]
        assert isinstance(node, click.Group)
        assert tuple(node.commands) == expected, path


def _surface(cmd: click.Command, path: str, rows: list[str]) -> None:
    rows.append(f"{path}|help={cmd.help!r}|short={cmd.short_help!r}|hidden={cmd.hidden}")
    for p in cmd.params:
        rows.append(
            f"{path}|{p.name}|{p.opts}|{p.secondary_opts}|type={p.type.name}|req={p.required}"
            f"|default={p.default!r}|multiple={p.multiple}|flag={getattr(p, 'is_flag', None)}"
            f"|help={getattr(p, 'help', None)!r}"
        )
    if isinstance(cmd, click.Group):
        for name, sub in cmd.commands.items():
            _surface(sub, f"{path} {name}", rows)


def test_cli_surface_digest() -> None:
    rows: list[str] = []
    _surface(_root(), "skillgate", rows)
    blob = "\n".join(rows)
    assert " at 0x" not in blob, "unstable repr in CLI surface"
    digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    assert digest == CLI_SURFACE_SHA256, blob
```

**Notes for step 1:**
- The `_root()` and `cli_pack` imports run against the flat files; `test_no_submodule_shadows_a_symbol` and `test_shims_hold_no_code` skip modules that are not packages yet.
- Fill in `CLI_SURFACE_SHA256` from the observed value: run the test once, read the digest from a temporary print, then hard-code it.
- If `TOP_COMMANDS` or `SUB_COMMANDS` differ from what main produces, change only those literals and list the change under **Spec deviations**.
- From then on, any change to the CLI surface fails this test.

## Risks and how this spec handles them
- **Silent no-op monkeypatches.** Every seam is listed above. The shims do not re-export stdlib or helper names, so a stale string target fails with `AttributeError`. The acceptance greps confirm that no stale targets remain.
- **Command order and help.** Registration lives in one ordered table (`cli/tree.py`). `test_cli_command_order` and `test_cli_surface_digest` pin it.
- **Partially built package imports.** No submodule imports its own `__init__`. Lazy imports that reach the `cli` shim during registration run only after every re-export is bound (`register_all()` is last).
- **Import cycles:**
  - `engine` → `harness` is one-way.
  - `case_pack` is reached only lazily from `engine`.
  - `compare` → `gate` → `engine`/`harness`; `compare_git` → `compare` stays one-way at module level.
  - `judge_providers.{jev,clef}` → `judge_openai` stays one-way, and `judge_providers/__init__.py` is empty.
  - `cli` ↔ `cli_pack` and `cli` ↔ `cli_compare` are broken by lazy imports inside register functions, exactly as today.
- **mypy.** The override list is rewritten in place to the `.*` form and keeps 21 entries. `engine` is not overridden and must type-check as moved.
- **`__file__` / `__name__`.** The six modules have no `__file__`, `getLogger(__name__)` or `importlib.resources` use. The only one is `cli.py`'s `if __name__ == "__main__"`, which is replaced by `cli/__main__.py`. With `python -m skillgate_ai.cli`, the program name in help becomes `__main__.py` instead of `cli.py`; the installed `skillgate` entry point is unaffected. Note this in the PR body.

## PR body checklist
- List each step's commit, with the line counts before and after for every new file.
- **Spec deviations**: observed command order or digest notes from step 1, any upward-dependency fixes made with function-local imports, and the `python -m` program-name note.
- **Follow-ups**: `scripts/extract-from-skillgate-ai.sh` still lists the flat paths. Shrinking the mypy overrides for the new subpackages is left for a later PR.
