# Spec: slim core deps + delete QA/release/dogfood dump tests

Branch: `cursor/slim-deps-qa-cleanup` off `origin/main` @ `44cff6b`. Package `skillgate-ai` stays at `0.7.17`.

## 1. Summary

Two independent changes, landed in this order:

**Task A: test cleanup.** Delete 23 one-off QA, release and dogfood test files (≈9,200 lines, ≈380 tests). Most of what they test is already covered by the permanent suites. Three modules are not: `span_facts.py` (677 lines), `wording_facts.py` (338 lines) and `run_lock.py` (67 lines). No permanent test imports them. A few other behaviours (docker sandbox preflight, Claude rate-limit event rendering, the `with_model` alias, capped reads, the pandoc warning, cost parsing) are also tested only by these files. **42 named tests are copied verbatim into permanent files before anything is deleted** (§2.2). Everything else is dropped.

**Task B: slim core deps.** Core `[project.dependencies]` goes from 14 packages to 7:
- FastAPI, uvicorn and python-multipart move to a `ui` extra.
- pypdf, python-docx, openpyxl and reportlab move to a `docs` extra.
- `all` is the union of both, and `dev` includes `all`, so every existing `pip install -e ".[dev]"` keeps working unchanged.

Today three core-path modules import these packages at top level, so a core-only install could not even run `skillgate --help`:
- `cli.py` imports `api_payloads.py`, which imports `fastapi` at top level.
- `engine.py` imports `scorers.py`, which imports `pypdf` at top level.
- `gate.py`, `pack.py` and `local_ui/api.py` import `demo_files.py`, which imports `reportlab` at top level.

These imports become lazy. When a feature that needs an extra is used without it, it raises `MissingExtraError` with this exact message:

```
Missing optional dependency for {feature}. Install with: pip install 'skillgate-ai[{extra}]'
```

Design decisions, each based on the current code:

| Decision | Why (code fact) |
|---|---|
| `MissingExtraError.exit_code = 2` | `gate.run_check` (`gate.py:310-351`) records any `SkillGateError` whose `exit_code != 2` as a **failed, gate-moving** run in history. A missing dependency means "cannot run", not a quality failure. This also matches the CLI contract (0 pass, 1 fail, 2 cannot run). |
| `MissingExtraError(SkillGateError, ImportError)` | Every CLI `except SkillGateError` already renders it. Code that catches `ImportError` still works. |
| Name the extra `ui`, never `server` | `tests/test_dockerfile.py::test_dockerfile_is_cli_not_serve` asserts `"serve" not in Dockerfile.lower()`. |
| Print with `markup=False` wherever this message can reach Rich | Rich reads `[ui]` and `[docs]` as style tags and silently strips them, so the user would see `pip install 'skillgate-ai'`. |
| In `scorers.py`, put the lazy import **outside** the existing `try/except Exception` | `_pdf_pages` and `_pdf_text` swallow every exception and return `None`. Inside the `try`, a missing pypdf would become "is not a readable PDF", a silently wrong score. |
| Leave `document_text.py` unchanged | Its imports are already lazy. `extract_document_text` (L25-32) is best-effort and wraps them in `except Exception: return None`. A missing `docs` extra means the decision model gets no extracted text. That is intended, and a test locks it in. |
| In `checks_show.py`, use a guarded `try/except` fallback for `Request`, not `TYPE_CHECKING` | `skillgate checks show` is a core command that imports this module. The nested FastAPI routes in `register_check_routes` look up the string annotation `"Request"` in module globals (because of `from __future__ import annotations`). The real class must still be a module global when FastAPI is installed. |
| In `api_payloads.py`, use `TYPE_CHECKING` for `Request` and a lazy `HTTPException` | `Request` only annotates `state_of`, which is not a route. `HTTPException` is used only in `fail()`, and only FastAPI routes call `fail()`, so the `ui` extra is always present there. |
| Docker image installs core + `docs`, not `ui` | The image is the check CLI. Real pdf packs need PDF scoring, and the image never serves the UI. |
| CI `gate` job stays core-only | It already runs `pip install -e .`, so it becomes the real core-only smoke test. |
| GitHub Action installs `skillgate-ai[docs]=={version}` | Without this, PDF scoring in the Action would break from the next release. For older releases pip only warns about the unknown extra. |

Known limitation (out of scope, needs a follow-up): a pack with PDF expectations and no `docs` extra fails at **score** time, after the agent has already run. The run is recorded as not scored (exit 2), not as a failure. A preflight check in `gate.run_check` would change behaviour, so it is not part of this spec.


## 2. Files to delete

### 2.1 Delete table

The **Ported tests** column lists tests that are copied into a permanent file (§2.2) **before** their source file is deleted. Every other test in the file is covered by the files in **Coverage elsewhere**.

| Path | Reason | Coverage elsewhere | Ported tests (→ §2.2) |
|---|---|---|---|
| `tests/test_qa_local_flow.py` | One-off local-UI walkthrough (import → list → open → run → deploy) from a QA pass. | `test_pack.py` (copy_skill_pack, goldens), `test_api_local.py` (import/list/open/run via FastAPI), `test_deploy_gate.py`, `test_deploy.py`, `test_local_ui.py` (UI copy), `integration/test_pack_flow.py` | none |
| `tests/test_qa_hn_setup.py` | Two first-time-user repros: compare dry-run hint, and `judge provider show` when unset. | `test_compare_dry_run_and_cases.py`, `test_compare_cli.py`, `test_judge_cli.py` | none |
| `tests/test_qa_cli_fixes.py` | Must-fix list from one full QA pass: JSON scrub, seed lock, CLI gaps, friendly errors. | `test_api_local.py` (`scrub_browser_payload`), `test_case_pack_cli.py` (seed lock, `case add --force`, empty prompt), `test_cli_pack.py` (case/pin/import/`skill write`), `test_check_cli.py` (`--case`, unknown case), `test_history.py`, `test_friendly_errors.py`, `test_keys.py`, `test_judge_cli.py` (add/remove question) | none |
| `tests/test_qa_56_round7.py` | Round-7 repro for deterministic c4 log extras, plus a README wording check. | `test_docs.py` (README), `test_engine.py` and `integration/test_check_gate.py` (timeout = not scored) | `test_c4_three_logs_same_deterministic_stop_extra`, `test_c4_two_real_refunds_still_fail_stop_extra` → `test_span_facts.py` |
| `tests/test_qa_56_round6.py` | Round-6 repro: honest-hedge extras and timeout history rows. | `test_decision_judges_only.py`, `test_judge_spec.py` (verdict, judge-only extras), `test_history.py`, `test_engine.py` (`timeout_harness_error`), `integration/test_check_gate.py` | `test_c8_two_refunds_stays_red` → `test_span_facts.py` |
| `tests/test_qa_56_round5.py` | Round-5 repro: an agent timeout is cannot-run and never dumps the prompt. | `test_engine.py` (timeout → `HarnessError` exit 2), `integration/test_check_gate.py` (exit 2, not scored), `test_friendly_errors.py`, `test_sandbox.py` | none |
| `tests/test_qa_56_round4.py` | Round-4 repro on the ticket-deflector c3–c8 calls-log fixtures. | `test_jev_extra_questions.py`, `test_judge_spec.py`, `test_workspace_outputs.py`, `test_local_ui.py` | `test_http_200_is_not_success_when_status_failed`, `test_c3_pending_hedge_from_calls_log_passes`, `test_c8_two_refunds_from_calls_log_still_fail` → `test_span_facts.py` |
| `tests/test_qa_56_round3.py` | Round-3 repro: example trigger fit, the cannot-use-model path, skill-folder reads as trigger evidence, pass-lock unsure. | `test_no_trigger_selection.py`, `test_example_datasets.py`, `test_engine.py` (cannot use model, usage limit), `test_harness_agents.py`, `test_claude_native_skills.py`, `test_judge_spec.py`, `test_local_ui.py` | `test_c4_more_than_once_from_the_log_fails` → `test_span_facts.py` |
| `tests/test_qa_56_retest.py` | Retest of round 2: trigger prompts, log-fact polarity, usage limit, adherence unsure. | `test_no_trigger_selection.py`, `test_engine.py` (usage limit), `test_judge_spec.py`, `test_report.py`, `test_local_ui.py` | `test_more_than_once_log_fact_uses_question_polarity`, `test_at_most_once_file_read_is_computed_from_the_log`, `test_computable_file_read_check_is_not_sent_to_the_judge`, `test_answer_no_if_more_than_once_keeps_no_duplicate_polarity` → `test_span_facts.py` |
| `tests/test_qa_56_followup.py` | Follow-up repro: description-based trigger, judge evidence, log-fact kinds, question-id validation. | `test_no_trigger_selection.py`, `test_judge_context.py`, `test_jev_extra_questions.py` and `test_judge_spec.py` (id validation), `test_checks_show.py` (source label) | none (the copied retest tests exercise log-fact kinds) |
| `tests/test_qa_079_fixes.py` | 0.7.9 QA must-fix list across the CLI, keys, judge provider and ingest. | `test_history.py`, `test_cli_pack.py` (import of an existing skill), `test_keys.py`, `test_harness_auth.py`, `test_judge_cli.py`, `test_judge_providers.py`, `test_judge_setup.py`, `test_case_pack_cli.py`, `test_case_skill_mismatch.py`, `test_check_cli.py` (missing pack → exit 2), `test_examples_cli.py`, `test_golden_run.py` | none |
| `tests/test_qa_0712_wording.py` | 0.7.12 wording-rule repros on the q13 fixture. | `test_checks_show.py` (wording check CLI), `test_decision_judges_only.py`, `test_judge_setup.py`, `test_docs.py` | 10 wording tests → `test_wording_facts.py`; `test_already_running_check_exits_2` → `test_run_lock.py` |
| `tests/test_qa_0711_fixes.py` | 0.7.11 low-confidence/review repros on the q10 fixtures. Four other dump files import helpers from it. | `test_judge_spec.py` (low-confidence verdicts), `test_report.py` (unsure/review status), `test_deploy_gate.py` (review does not unlock deploy), `test_history.py`, `test_golden_run.py` (example goldens) | 8 span-facts tests plus helpers `_load`, `_spec_from_fixture`, `_rescore`, `_shell_span` → `test_span_facts.py` |
| `tests/test_qa_0710_fixes.py` | 0.7.10 repros: JEV retry, low-confidence re-ask, scoring error → exit 2. | `test_jev_extra_questions.py`, `test_http_retry.py`, `integration/test_judge_retry.py`, `test_judge_providers.py`, `test_judge.py`, `test_judge_openai.py`, `test_history.py` | none. `test_tests_do_not_use_the_real_home_dir` is a test-hygiene meta-check and is dropped on purpose, because `conftest.py` is on the do-not-touch list. |
| `tests/test_qa_06_fixes.py` | 0.6 QA must-fix list: persist, docker sandbox, keys, run lock, deploy, case add. | `test_history.py`, `test_jev_extra_questions.py`, `test_harness_agents.py`, `test_keys.py`, `test_deploy.py`, `test_deploy_gate.py`, `test_case_pack_cli.py`, `test_examples_cli.py`, `test_scaffold.py`, `test_report.py`, `test_api_local.py` (catalog) | `test_docker_sandbox_fails_before_run_when_image_missing`, `test_docker_sandbox_fails_clearly_when_daemon_down` → `test_sandbox.py`; `test_run_lock_unwritable_is_not_fatal`, `test_cli_one_run_at_a_time` → `test_run_lock.py` |
| `tests/test_release_072_round3.py` | 0.7.2 round-3 release repros: compare harness defaults, trigger mode, codex skills dir. | `test_compare_git.py`, `test_compare_versions.py`, `test_harness_agents.py` (trigger mode and prompt), `test_harness_auth.py` (codex home, skills disable), `test_claude_native_skills.py` | none |
| `tests/test_release_072.py` | 0.7.2 release checklist: event rendering, evidence rules, workspace capture, auth, version pin. | `test_judge_bank.py`, `test_judge_spec.py`, `test_workspace_outputs.py`, `test_harness_agents.py`, `test_harness_auth.py`, `test_judge_cli.py`, `test_judge_providers.py`, `test_check_cli.py`, `test_docs.py::test_package_and_docs_pin_078` (version) | `test_render_drops_claude_rate_limit_and_system_events` → `test_usage_combine.py` |
| `tests/test_release_061_round3.py` | 0.6.1 round-3 release repros: pnpm bundle, sdist install, compare dry-run, hidden docker option. | `test_packaging_ui.py` (bundle, pnpm), CI `web-build` job (sdist/wheel install), `test_compare_dry_run_and_cases.py`, `test_compare_models.py`, `test_history.py`, `test_check_cli.py` | none |
| `tests/test_release_061_round2.py` | 0.6.1 round-2 release repros: workspace init, keys copy, compare versions. | `test_cli_pack.py`, `test_check_cli.py`, `test_keys.py`, `test_api_local.py` (settings keys), `test_judge_setup.py`, `test_eval_config.py`, `test_compare_versions.py`, `test_compare_git.py`, `test_compare_cli.py` | none |
| `tests/test_release_061_fixes.py` | 0.6.1 release must-fix list: compare limits and cancel, keys labels, nested import. | `test_compare_models.py`, `test_compare_versions.py`, `test_compare_cli.py`, `test_api_compare.py` (cancel), `test_keys.py`, `test_local_ui.py`, `test_cli_pack.py`, `test_judge_cli.py` | none |
| `tests/test_dogfood_v7.py` | Dogfood round-7 repros: command-run parsing, model aliases, compatible ping, caps. | `test_judge_context.py` and `test_judge_dogfood_v5.py` (command runs), `test_harness_auth.py` (used model), `test_gate.py` (resolved model), `test_compare_models.py`, `test_judge_openai.py` (responses fallback), `test_sandbox.py` (secret env strip), `test_golden_run.py` | `test_with_model_keeps_requested_alias`, `test_with_model_promotes_stamped_alias_when_requested_missing` → `test_eval_config.py`; `test_saved_artifact_body_is_not_capped_at_8kb`, `test_judge_and_golden_reads_stay_capped` → `test_workspace_outputs.py` |
| `tests/test_dogfood_v6.py` | Dogfood round-6 repros: harness defaults, cursor/codex login, usage cost, 429 retry. | `test_gate.py`, `test_harness_auth.py`, `test_harness_agents.py`, `test_eval_config.py`, `test_judge_spec.py`, `test_usage_combine.py`, `test_judge_openai.py` and `test_http_retry.py` (429), `test_judge.py` | none |
| `tests/test_dogfood_fixes.py` | First dogfood round of repros: description trigger, demo fixtures, outputs, cost parsing. | `test_no_trigger_selection.py`, `test_skill_sample_files.py` (`prepare_pack_fixtures`), `test_workspace_outputs.py`, `test_ingest.py`, `test_usage_combine.py`, `test_engine.py` (answer_contains) | `test_wrong_description_fails_trigger_even_if_selected` → `test_no_trigger_selection.py`; `test_ingest_warns_when_pandoc_missing` → `test_ingest.py`; `test_parse_claude_result_total_cost_usd` → `test_usage_combine.py` |

Also delete `tests/fixtures/judge_072/` (`commit_subject_length.json`, `no_useeffect_fetch.json`). Only `test_release_072.py` reads it; grep for `judge_072` again before deleting.

Keep:
- `tests/fixtures/q10/`, used by the copied span-facts tests.
- `tests/fixtures/q13/`, used by the copied q13 wording test.
- `tests/test_judge_dogfood_v5.py`. It has "dogfood" in its name but is **not** on the delete list.

### 2.2 Port list (exact)

Rules for every port:
- Copy the test body **verbatim**, together with every module-private helper, constant, fixture and autouse fixture it references.
- Never import from a file listed in §2.1. Today `test_qa_56_retest.py`, `test_qa_56_round3.py`, `test_qa_56_round4.py` and `test_qa_0712_wording.py` import helpers from `test_qa_0711_fixes.py`, and `test_qa_56_round6.py` imports from `test_qa_56_round4.py`.
- If two source files define a helper with the same name but different bodies, rename the later one with a suffix (for example `_outputs_r4`).
- Copy the autouse fixture `_never_touch_real_home` (`test_qa_0711_fixes.py:33-39`) into each **new** file.
- Wrap long string literals with implicit concatenation so their values don't change. Only add a ruff per-file-ignore for a new file if a literal truly cannot be split. If you do, it replaces the `test_qa_0712_wording.py` entry one-for-one.

| Destination | Tests (source file) |
|---|---|
| **new** `tests/test_span_facts.py` | From `test_qa_0711_fixes.py`: helpers `_load`, `_spec_from_fixture`, `_rescore`, `_shell_span` and `FIXTURES` (q10); tests `test_c8_single_refund_log_fact_overrides_judge_no`, `test_c8_rep3_single_refund_also_passes_duplicate_check`, `test_duplicate_refund_from_the_log_still_fails`, `test_synthetic_duplicate_refund_fails_without_the_judge`, `test_duplicate_check_without_a_log_still_uses_the_judge`, `test_tool_return_fact_uses_span_result_not_the_judge`, `test_missing_tool_result_falls_back_to_the_judge`, `test_called_check_is_scored_from_the_log`. From `test_qa_56_retest.py`: the 4 tests named in §2.1. From `test_qa_56_round3.py`: `test_c4_more_than_once_from_the_log_fails`. From `test_qa_56_round4.py`: the 3 tests in §2.1, plus `C3_ASK`, `C3_HEDGE`, `_call`, `_extra_spec` and `_outputs` as needed. From `test_qa_56_round6.py`: `test_c8_two_refunds_stays_red`. From `test_qa_56_round7.py`: the 2 tests in §2.1. **Total: 19.** |
| **new** `tests/test_wording_facts.py` | From `test_qa_0712_wording.py`: `test_judge_yes_cannot_override_banned_wording`, `test_negation_does_not_trip_banned_wording`, `test_quoting_the_user_does_not_trip_banned_wording`, `test_required_wording_missing_fails_from_text`, `test_required_wording_present_passes`, `test_example_skills_do_not_compile_wording_rules`, `test_bullet_list_of_phrases_is_parsed_not_garbled`, `test_one_phrase_per_line_polarity_apostrophe_and_negation`, `test_passing_text_check_is_not_overridden_by_judge`, `test_q13_pending_submitted_full_refund_is_red_from_4b`. Also `_spec_from_fixture` (copied from 0711) and any 0712 helpers. **Total: 10.** |
| **new** `tests/test_run_lock.py` | `test_run_lock_unwritable_is_not_fatal` and `test_cli_one_run_at_a_time` (from `test_qa_06_fixes.py:372`); `test_already_running_check_exits_2` (from `test_qa_0712_wording.py:672`). **Total: 3.** |
| `tests/test_sandbox.py` (append) | `test_docker_sandbox_fails_before_run_when_image_missing`, `test_docker_sandbox_fails_clearly_when_daemon_down` (from `test_qa_06_fixes.py:240`) |
| `tests/test_usage_combine.py` (append) | `test_render_drops_claude_rate_limit_and_system_events` (from `test_release_072.py:93`), `test_parse_claude_result_total_cost_usd` (from `test_dogfood_fixes.py`) |
| `tests/test_eval_config.py` (append) | `test_with_model_keeps_requested_alias`, `test_with_model_promotes_stamped_alias_when_requested_missing` (from `test_dogfood_v7.py:283, 347`) |
| `tests/test_workspace_outputs.py` (append) | `test_saved_artifact_body_is_not_capped_at_8kb`, `test_judge_and_golden_reads_stay_capped` (from `test_dogfood_v7.py:539, 553`) |
| `tests/test_ingest.py` (append) | `test_ingest_warns_when_pandoc_missing` (from `test_dogfood_fixes.py:76`) |
| `tests/test_no_trigger_selection.py` (append) | `test_wrong_description_fails_trigger_even_if_selected` (from `test_dogfood_fixes.py`) |

**42 tests in total.** Each must pass against unmodified `src/` before its source file is deleted.

### 2.3 pyproject edit for Task A

Delete `"tests/test_qa_0712_wording.py" = ["E501"]` (`pyproject.toml:116`). Keep the `tests/test_local_ui.py` line and the comment above it.


## 3. `pyproject.toml`: exact blocks

```toml
dependencies = [
  "typer>=0.12",
  "rich>=13.7",
  "pyyaml>=6.0",
  "pydantic>=2.7",
  "httpx>=0.27",
  "tenacity>=8.2",
  "python-dotenv>=1.0",
]

[project.optional-dependencies]
# Local React UI + loopback API (`skillgate ui`).
ui = [
  "fastapi>=0.115",
  "uvicorn>=0.30",
  "python-multipart>=0.0.9",
]
# PDF page/text scoring, demo PDF generation, PDF/Word/Excel text for the decision model.
docs = [
  "pypdf>=4.2",
  "python-docx>=1.1",
  "openpyxl>=3.1",
  "reportlab>=4.2",
]
all = [
  "skillgate-ai[ui,docs]",
]
dev = [
  "skillgate-ai[all]",
  "pytest>=8.2",
  "pytest-timeout>=2.3",
  "ruff>=0.5",
  "mypy>=1.10",
  "pre-commit>=4.0",
]
```

Notes:
- Self-referencing extras need pip ≥ 21.2.
- Because `dev` includes `all`, nothing that runs `pip install -e ".[dev]"` needs to change: the `lint`, `test`, `integration` and `oss-surface` CI jobs, `AGENTS.md`, `CONTRIBUTING.md` and `docs/ui.md`. `mypy src` still sees FastAPI.
- Do not change `version`, `[project.scripts]`, `[tool.*]` or package-data.


## 4. New module `src/skillgate_ai/extras.py`

```python
"""Optional dependency extras. Core installs stay slim; features name their extra."""

from __future__ import annotations

import importlib
from types import ModuleType
from typing import Final

from skillgate_ai.errors import SkillGateError

EXTRA_MESSAGE: Final = (
    "Missing optional dependency for {feature}. Install with: pip install 'skillgate-ai[{extra}]'"
)

UI_FEATURE: Final = "the local UI (skillgate ui)"
PDF_SCORING_FEATURE: Final = "PDF scoring"
DEMO_PDF_FEATURE: Final = "demo PDF generation"

# Import names probed by require_extra (not pip names).
EXTRA_MODULES: Final[dict[str, tuple[str, ...]]] = {
    "ui": ("fastapi", "uvicorn"),
    "docs": ("pypdf", "docx", "openpyxl", "reportlab"),
    "all": ("fastapi", "uvicorn", "pypdf", "docx", "openpyxl", "reportlab"),
}


class MissingExtraError(SkillGateError, ImportError):
    """A feature needs an optional extra that is not installed. Cannot run, not a fail."""

    exit_code = 2

    def __init__(self, feature: str, extra: str) -> None:
        self.feature = feature
        self.extra = extra
        super().__init__(EXTRA_MESSAGE.format(feature=feature, extra=extra))


def import_extra(module: str, *, extra: str, feature: str) -> ModuleType:
    """Import one optional module or raise MissingExtraError naming the extra."""
    try:
        return importlib.import_module(module)
    except ImportError as exc:
        raise MissingExtraError(feature, extra) from exc


def require_extra(extra: str, *, feature: str) -> None:
    """Raise MissingExtraError unless every probe module of `extra` imports."""
    if extra not in EXTRA_MODULES:
        raise ValueError(f"Unknown extra {extra!r}")
    for module in EXTRA_MODULES[extra]:
        import_extra(module, extra=extra, feature=feature)
```

Contract:
- `str(err)` and `err.render()` are byte-identical to the exact message. There is no hint.
- `err` is both an `ImportError` and a `SkillGateError`, and `exit_code == 2`.
- Use the `ui` extra for every FastAPI, starlette or uvicorn site, and `docs` for every pypdf or reportlab site.

Module-level guards use this pattern (ruff-clean, no E402). Import `MissingExtraError` and `UI_FEATURE` from `skillgate_ai.extras` above the guarded block:

```python
try:
    from fastapi import FastAPI
except ModuleNotFoundError as exc:
    raise MissingExtraError(UI_FEATURE, "ui") from exc
```


## 5. Lazy-import checklist

| File | Symbol(s) today | Extra | Change | Error trigger |
|---|---|---|---|---|
| `api_payloads.py` (core path, via `cli.py:15`, `gate.py:72`, `compare.py:356`, `history.py:181`) | L11 `from fastapi import HTTPException, Request` | `ui` | Delete L11. Add `if TYPE_CHECKING: from fastapi import Request`. Make `from fastapi import HTTPException` the first line inside `fail()` (L63-68). | None on the core path; `fail()` only runs inside routes. |
| `checks_show.py` (core path, via `cli.py:928`) | L9 `from fastapi import Request` | `ui` | `try: from fastapi import Request` / `except ModuleNotFoundError: Request = Any  # type: ignore[assignment,misc]`, with a comment that core `checks show` needs no web stack. | None; routes register only through the guarded `api.create_app`. |
| `scorers.py` (core path, via `engine.py:35`, `advice.py:15`, `harness.py:27`, `judge_context.py:14`) | L10 `from pypdf import PdfReader`; used at L341 and L348 | `docs` | Delete L10. In `_pdf_pages` and `_pdf_text`, put `pdf_reader = import_extra("pypdf", extra="docs", feature=PDF_SCORING_FEATURE).PdfReader` **before** `try:`. | `min_pages`/`max_pages`/`pdf_pages`, or `contains` on a `.pdf`, with pypdf missing → exit 2 via `gate.run_check`. |
| `demo_files.py` (core path, via `gate.py:17`, `pack.py:23`, `local_ui/api.py:26`) | L7-8 reportlab imports | `docs` | Delete L7-8. At the top of `write_pdf`, load `canvas` from `reportlab.pdfgen.canvas` and `letter` from `reportlab.lib.pagesizes`, both through `import_extra(..., extra="docs", feature=DEMO_PDF_FEATURE)`. | `write_pdf` only runs when a demo fixture is missing (`ensure_demo_pdfs` L37-41) or for `generate_sample_bytes` on a `.pdf` (`skill write --generate`, UI generate). The committed `skills/pdf/evals/fixtures/*.pdf` mean `example pdf` → `check` never calls it. |
| `document_text.py` | L52, L61, L70 (already lazy) | `docs` | **No change.** | None; returns `None` through `except Exception`. |
| `server.py` | L11-13 fastapi/starlette | `ui` | §4 guard. Replace L155 `import uvicorn` with `uvicorn = import_extra("uvicorn", extra="ui", feature=UI_FEATURE)`. | Importing `server`; `serve_ui` without uvicorn (raises before the port check). |
| `api.py` | L10-12 | `ui` | §4 guard. | Importing it, or calling `create_app`. |
| `local_guard.py` | L7-9 starlette | `ui` | §4 guard. | Importing it. |
| `api_compare.py` L9, `api_evals.py` L7, `api_runs.py` L9, `api_shims.py` L7, `api_skills.py` L9-10 | fastapi (evals/skills also need python-multipart) | `ui` | §4 guard on each. | Direct import. Normally unreachable, because `api.py` fails first. |
| `cli.py` `ui_cmd` | L1236 lazy `from skillgate_ai.server import serve_ui` | `ui` | Before L1236: `try: require_extra("ui", feature=UI_FEATURE)` / `except MissingExtraError as exc: console.print(exc.render(), markup=False); raise typer.Exit(exc.exit_code) from None`. Import `MissingExtraError`, `UI_FEATURE` and `require_extra` lazily in the function. | `skillgate ui` without `ui` → exit 2 + message. |
| `cli.py` print sites | L234, L237 (`_present_check`), L394, L397 (`check` error branch), L1258 (`ui_cmd`) | n/a | Add `markup=False`. A grep confirmed no error string uses Rich markup today. | Keeps `[docs]` and `[ui]` visible. |
| `cli_pack.py` | L113 `console.print(message)` in `skill write` | n/a | Add `markup=False`. | `skill write --generate --path evals/fixtures/x.pdf` without `docs`. |
| `skills/pdf/scripts/*`, `src/skillgate_ai/examples/**` | pypdf/reportlab in bundled skill scripts | n/a | **No change.** This is skill code run by the agent, not package code. | n/a |
| python-multipart | only through FastAPI `File`/`Form`/`UploadFile` | `ui` | Covered by the `ui` extra. Not probed, because its import name differs across versions (`multipart` vs `python_multipart`). | FastAPI raises at route registration. |


## 6. Implementation order

Make one commit per step. Each step must be green before the next on `pytest -q -m "not integration" && pytest -q -m integration tests/integration && ruff check && ruff format --check && mypy src`.

**Task A: tests only, no `src/` edits**

1. **Baseline coverage.** Install `coverage` ad hoc (not in `pyproject.toml`). Run `coverage run -m pytest -q -m "not integration"` and `coverage report --include='src/skillgate_ai/*' > /tmp/cov_before.txt`.
2. **Copy tests.** Add the 42 tests from §2.2 and confirm they pass against unmodified `src/`.
3. **Delete.** Remove the 23 files and `tests/fixtures/judge_072/`. Run `grep -rn "judge_072\|test_qa_\|test_release_0\|test_dogfood_" tests src pyproject.toml .github`; the only hit should be the pyproject ignore line. Remove that line.
4. **Coverage check.** Re-run step 1 into `/tmp/cov_after.txt`. No module may drop more than **5 percentage points**. If one does, copy the missing test from `git show 44cff6b:tests/<file>` into the matching permanent file.

**Task B: optional extras**

5. Add `extras.py` and the §7.2 contract tests (1–4).
6. Core-path imports: `api_payloads`, `checks_show`, `scorers`, `demo_files`. Add tests 5–8.
7. UI guards: `server`, `api`, `local_guard`, `api_*`. Add tests 9–11 and 13.
8. CLI changes: `ui_cmd` `require_extra` and the six `markup=False` sites. Add tests 12 and 19.
9. Docs-extra tests 14–18, 20 and 21.
10. Replace the `pyproject.toml` blocks (§3). In a fresh venv, check that `pip install -e ".[dev]"` brings in fastapi, pypdf and reportlab. Add test 22.
11. Dockerfile (§6.1) and test 23. Run `docker build --target runtime .` plus the three `docker run` lines from the `docker` CI job.
12. CI (§6.2).
13. GitHub Action: in `scripts/skillgate_action.py` L76, change `[f"skillgate-ai=={version}"]` to `[f"skillgate-ai[docs]=={version}"]`. Update the expected value in `tests/test_action.py::test_explicit_version_is_passed_to_pip_install` to `["skillgate-ai[docs]==0.7.9"]`.
14. Docs (§6.3) and test 24.
15. Local core-only smoke test. In a venv with only `pip install .`:
    - `--help`, `example pdf`, `ingest` and `checks show path_efficiency` work.
    - A keyless `check` exits 2.
    - `ui --no-browser` exits 2 and prints `pip install 'skillgate-ai[ui]'`.

### 6.1 Dockerfile (replace lines 14-17)

```dockerfile
# Install core deps + the docs extra (PDF scoring, demo PDFs) first; cached when only src changes.
# No ui extra: this image is the check CLI.
RUN --mount=type=bind,source=pyproject.toml,target=/tmp/pyproject.toml \
    --mount=type=cache,target=/root/.cache/pip \
    python -c "import tomllib, pathlib, subprocess; p=tomllib.loads(pathlib.Path('/tmp/pyproject.toml').read_text())['project']; deps=p['dependencies']+p['optional-dependencies']['docs']; subprocess.check_call(['pip','install','--upgrade','pip']); subprocess.check_call(['pip','install','--no-compile',*deps])"
```

Leave `pip install --no-deps --no-compile .` unchanged. The Dockerfile must not contain "serve", "server" or `ui` as an extra name.

### 6.2 `.github/workflows/gate.yml`

- `lint`, `test`, `integration`, `oss-surface`: no change.
- `gate` stays core-only. After `pip install -e .`, add:
  ```yaml
      - name: core install pulls no ui/docs extras
        run: |
          python - <<'EOF'
          import importlib.util, sys
          mods = ("fastapi", "starlette", "uvicorn", "pypdf", "docx", "openpyxl", "reportlab")
          found = [m for m in mods if importlib.util.find_spec(m)]
          sys.exit(f"core install pulled extras: {found}" if found else 0)
          EOF
      - run: skillgate --help
      - run: skillgate checks show path_efficiency
  ```
  After "keyless check exits 2", add:
  ```yaml
      - name: ui without the ui extra exits 2 with the install hint
        run: |
          set +e
          out=$(skillgate ui --no-browser 2>&1); code=$?
          set -e
          echo "$out"
          test "$code" -eq 2
          echo "$out" | grep -F "pip install 'skillgate-ai[ui]'"
  ```
- `web-build`: change `/tmp/wheelenv/bin/pip install dist/skillgate_ai-*.whl` to `/tmp/wheelenv/bin/pip install "$(ls dist/skillgate_ai-*.whl)[ui]"`.
- `docker`: no YAML change; the image now has `docs`.
- `release.yml` and `skillgate-action.yml`: no change.

### 6.3 Docs

- **README.md.** Add an `### Optional extras` section after the Quickstart paragraph and before "The same steps in the local UI". It has a three-row table:

  | Install | Adds | Needed for |
  |---|---|---|
  | `pip install 'skillgate-ai[ui]'` | FastAPI, uvicorn, python-multipart | `skillgate ui` |
  | `pip install 'skillgate-ai[docs]'` | pypdf, python-docx, openpyxl, reportlab | PDF checks, demo PDFs, document text for the decision model |
  | `pip install 'skillgate-ai[all]'` | both | everything |

  Add a line quoting the missing-extra message (exit 2). In the local-UI snippet, put `pip install 'skillgate-ai[ui]'` before `skillgate ui`. Keep every existing `pip install skillgate-ai`, `skillgate-ai==0.7.17` and `0.7.12` string, because `test_docs.py` asserts them.
- **docs/quickstart.md.** Add the same table under `## Install`. Extend the "the pdf example needs `pypdf`" line to mention `[docs]`. Keep both pins before `## Keys`.
- **docs/ui.md.** Add: "From PyPI: `pip install 'skillgate-ai[ui]'`. `pip install -e \".[dev]\"` already includes it."
- **CHANGELOG.md**, under `## Unreleased`, cover:
  - core deps cut to 7, with new `ui`/`docs`/`all` extras;
  - the exact missing-extra message and exit 2;
  - the Docker image ships `docs`, and the Action installs `[docs]`;
  - 23 dump test files removed, with 42 tests copied into permanent files.
- `AGENTS.md`, `CONTRIBUTING.md`: no change.


## 7. Acceptance criteria

### 7.1 Checklist

- [ ] The 23 files and `tests/fixtures/judge_072/` are gone. `q10/`, `q13/` and `test_judge_dogfood_v5.py` remain.
- [ ] All 42 tests from §2.2 exist under their names, pass, and import nothing from a deleted file.
- [ ] The `test_qa_0712_wording.py` ignore is gone and `ruff check` is clean.
- [ ] The coverage diff is in the PR body, and no module drops more than 5 points.
- [ ] `[project.dependencies]` lists exactly the 7 core packages, the extras match §3 exactly, and `version = "0.7.17"`.
- [ ] `extras.py` matches §4, and the message is byte-exact.
- [ ] Every §5 row is done. `grep -rnE "^(from|import) (fastapi|starlette|uvicorn|pypdf|reportlab|docx|openpyxl)" src/skillgate_ai` matches only lines inside `try:` guards, and nothing in `scorers.py`, `demo_files.py` or `api_payloads.py`.
- [ ] Core-only install (CI `gate` job and step 15):
  - `--help`, `example pdf`, `ingest` and `checks show` work.
  - A keyless `check` exits 2.
  - `ui` exits 2 and prints `pip install 'skillgate-ai[ui]'` with the brackets intact.
- [ ] The `web-build` job serves the UI from the wheel after `[ui]` is installed.
- [ ] The Docker image builds and the `docker` job is green. The image contains pypdf and reportlab, and no fastapi.
- [ ] The full test suite, ruff, ruff format and mypy are green on `.[dev]`, and `test_docs.py` passes unchanged.

### 7.2 New tests: `tests/test_optional_extras.py`

Shared helper: `_run_without(blocked, code, tmp_path)` runs `sys.executable -c <BLOCKER + code> <comma-joined names>`, with `HOME=tmp_path` and `PYTHONPATH=src`. The prelude puts a finder at the front of `sys.meta_path` that raises `ModuleNotFoundError` for the listed top-level names. Two constant sets:
- `UI_MODULES = ("fastapi", "starlette", "uvicorn", "multipart", "python_multipart")`
- `DOCS_MODULES = ("pypdf", "docx", "openpyxl", "reportlab")`

| # | Function | Blocks | Asserts |
|---|---|---|---|
| 1 | `test_missing_extra_error_contract` | none | Is both `ImportError` and `SkillGateError`; `exit_code == 2`; `render() == str()`; `hint is None` |
| 2 | `test_missing_extra_message_is_exact` | none | Exact string for `("PDF scoring", "docs")` |
| 3 | `test_require_extra_passes_when_installed` | none | `require_extra("all", ...)` returns `None` |
| 4 | `test_require_extra_unknown_extra_raises_value_error` | none | `ValueError` |
| 5 | `test_import_extra_wraps_import_error` | fastapi | Raises `MissingExtraError` with `__cause__` a `ModuleNotFoundError` |
| 6 | `test_core_cli_imports_without_ui_or_docs_extras` | UI+DOCS | `--help` exits 0, and no blocked module is in `sys.modules` |
| 7 | `test_core_modules_import_without_extras` | UI+DOCS | `gate`, `engine`, `scorers`, `demo_files`, `pack`, `api_payloads`, `checks_show`, `compare`, `history`, `judge_context`, `document_text`, `local_ui.api` and `local_ui.server` all import |
| 8 | `test_checks_show_cli_runs_without_ui_extra` | UI | `checks show path_efficiency` exits 0 |
| 9 | `test_server_import_without_ui_extra_raises_friendly_error` | UI | Exact `[ui]` message |
| 10 | `test_create_app_without_ui_extra_raises_friendly_error` | UI | `MissingExtraError` with `[ui]` |
| 11 | `test_serve_ui_without_uvicorn_raises_friendly_error` | uvicorn | Raises before binding |
| 12 | `test_ui_command_without_ui_extra_exits_2_with_install_hint` | UI | Exit 2; output contains `pip install 'skillgate-ai[ui]'` with brackets |
| 13 | `test_ui_modules_each_raise_friendly_error_without_fastapi` | UI | Parametrised over `api`, `api_compare`, `api_evals`, `api_runs`, `api_shims`, `api_skills`, `local_guard`, `server`: each has `extra == "ui"` |
| 14 | `test_pdf_page_scoring_without_docs_extra_raises_friendly_error` | DOCS | `FileExpect(min_pages=1)` gives `feature == "PDF scoring"`, `extra == "docs"` |
| 15 | `test_pdf_contains_scoring_without_docs_extra_raises_friendly_error` | DOCS | `RubricCheck(contains=...)` on a `.pdf` raises |
| 16 | `test_non_pdf_scoring_needs_no_docs_extra` | DOCS | `.txt` with `contains` passes |
| 17 | `test_write_pdf_without_docs_extra_raises_friendly_error` | DOCS | `feature == "demo PDF generation"` |
| 18 | `test_ensure_demo_pdfs_with_prebuilt_fixtures_needs_no_reportlab` | DOCS | Prebuilt fixtures are left untouched |
| 19 | `test_check_error_keeps_extra_brackets_visible` | none | With `cli.run_check` monkeypatched to return a `MissingExtraError` result, the `check` output contains `'skillgate-ai[docs]'` and exits 2 |
| 20 | `test_document_text_extracts_pdf_docx_xlsx_with_docs_extra` | none | `importorskip` each library; extracted text from all three formats contains the written string |
| 21 | `test_document_text_returns_none_without_docs_extra` | DOCS | A `%PDF` file returns `None` and raises nothing |
| 22 | `test_pyproject_core_dependencies_are_slim` | none | `tomllib` checks of the §3 sets |
| 23 | `test_dockerfile_installs_docs_extra_not_ui` | none | Contains `['optional-dependencies']['docs']`; no `'ui'`, `[ui]`, `fastapi` or `[all]` |
| 24 | `test_readme_and_quickstart_document_extras` | none | All three install lines are present |

No test is marked `slow` or `integration`.


## 8. DO-NOT-TOUCH

- **No file splitting or moves.** `api_payloads.py` stays one file. Do not extract `scrub_browser_payload`.
- **No logic changes beyond import gating.** The only allowed `src/` edits are:
  - the §5 import moves and guards;
  - the six `markup=False` additions;
  - `extras.py`;
  - the `ui_cmd` `require_extra` block.

  Specifically, add no preflight in `gate.run_check`, make no edit to `document_text.py`, and change no try/except bodies, defaults, messages or exit codes elsewhere.
- **Tests to leave untouched:** `tests/integration/*`, `test_engine.py`, `conftest.py`, `helpers.py`, `test_judge_dogfood_v5.py`, `test_docs.py`, `test_dockerfile.py`. The only permanent tests you may edit are the §2.2 append targets and one expected list in `test_action.py`.
- **No version bump.** `0.7.17` stays everywhere, and all existing pin strings stay.
- **No change to:** `[tool.mypy*]`, `[tool.pytest*]`, `[project.scripts]`, package-data, `release.yml`, `skillgate-action.yml`, `action.yml`, `compose.yaml`, `.dockerignore`, `.pre-commit-config.yaml`, `skills/**`, `src/skillgate_ai/examples/**`, `local_ui/static/**`, `web/**`, `src/skillgate_build.py`.
- **Naming:** never call an extra `server`, and never put "serve" or "server" in the Dockerfile.
- **Coverage tools:** don't add `coverage` or `pytest-cov` to `pyproject.toml`.
- Leave the untracked `.spec-prompt-slim-deps.txt` alone, and don't commit it.

