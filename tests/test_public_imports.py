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
        "AUTH_API_KEY", "AUTH_CLI_LOGIN", "AUTH_NONE", "LOGIN_AGENTS", "LOGIN_TIMEOUT_SEC",
        "LOGIN_TIMEOUT_ENV", "_login_timeout_sec", "_AGENT_INSTALL", "HarnessResult",
        "harness_usage", "Harness", "_STOP", "tokenize", "rank_skills",
        "select_skill_from_descriptions", "description_fits_request", "LIVE_HARNESS_NAMES",
        "is_live_harness", "CursorAgentHarness", "_cursor_exec_command", "CODEX_CHATGPT_DEFAULT",
        "_CODEX_REJECTED_MODEL", "_CODEX_SUPPORTED_MODELS", "_codex_model_flag",
        "_codex_exec_command", "_CLAUDE_PREAMBLE", "_CLAUDE_SYSTEM_PREAMBLE",
        "_CLAUDE_WORKSPACE_TOOLS", "_claude_code_exec_command", "_claude_used_model",
        "_busiest_model_usage", "_codex_used_model", "_MODEL_ACCESS_ERROR",
        "_claude_model_access_error", "_claude_model_access_message",
        "_CLAUDE_MODEL_ACCESS_HINT", "_jsonl_spans", "_jsonl_transcript", "_codex_transcript",
        "_cursor_transcript", "_codex_rejected_chatgpt_model", "_codex_rejected_model",
        "codex_chatgpt_model_hint", "CodexCliHarness", "ClaudeCodeHarness",
        "harness_is_startable", "_named_harness", "resolve_harness", "_LIVE_HARNESS_KINDS",
        "_AGENT_PRIORITY", "_agent_candidates", "startable_agent_kinds", "has_startable_agent",
        "live_harness_or_error", "auto_live_harness_name", "_codex_auth_key",
        "_SKILL_WALK_SKIP", "_SKILL_WALK_MAX_DEPTH", "_toml_basic_string",
        "_codex_user_skill_roots", "_skill_markdown_files", "_codex_user_skill_config_override",
        "_CODEX_LOGIN_STATUS_TIMEOUT_SEC", "_codex_ready", "_codex_login_status_authenticated",
        "_probe_codex_login_status", "_codex_session_ok", "_CURSOR_LOGIN_STATUS_TIMEOUT_SEC",
        "_AUTH_FAILURE_RE", "USAGE_LIMIT_MESSAGE", "MODEL_UNAVAILABLE_MESSAGE", "_sandbox_run",
        "_USAGE_LIMIT_RE", "_MODEL_UNAVAILABLE_RE", "_SKILL_FILE_RE", "usage_limit_message",
        "model_unavailable_message", "cannot_run_message", "_raise_if_cannot_run",
        "auth_failure_message", "_raise_if_auth_failed", "_cursor_login_status_authenticated",
        "_probe_cursor_login_status", "_cursor_session_ok", "_cursor_ready",
        "_CLAUDE_LOGIN_STATUS_TIMEOUT_SEC", "_claude_login_status_authenticated",
        "_probe_claude_login_status", "_claude_session_ok", "_claude_ready", "cursor_auth_kind",
        "codex_auth_kind", "claude_auth_kind", "_display_status", "normalize_login_agent",
        "harness_auth_status", "format_harness_status", "_terminate_process_group",
        "_run_inherited", "run_official_login", "_resolve_agent_bin", "_executable_path",
        "_looks_like_bin_path", "_resolve_codex_bin", "_resolve_claude_bin",
        "_pinned_has_agent_entry", "_workspace_trigger_mode", "_trigger_mode_prompt",
        "_claude_trigger_mode_prompt", "_claude_discover_prompt", "_claude_skill_paths",
        "_claude_prompt", "claude_native_skills_enabled", "claude_config_isolation_enabled",
        "_claude_sandbox_env", "_agent_prompt", "_cursor_discover_prompt", "_cursor_prompt",
        "_write_selection", "_MISSING", "_read_selection", "_parse_selected",
        "_skill_tool_name_from_args", "_infer_from_skill_tool", "_skill_load_path",
        "_resolve_trigger_evidence", "_parse_skill_json", "_skill_for_selection",
        "_parse_read_paths", "_parse_read_paths_from_spans", "_collect_read_paths",
        "_infer_from_reads", "_skill_name_from_path",
    ),
    "skillgate_ai.engine": (
        "SKIP_FAILURE", "KILL_FAILURE", "_extras_all_passed", "_extras_from_log",
        "_extras_from_text", "_extras_from_source", "_is_builtin_quality_reason",
        "_NON_WORDING_FAIL", "_wording_only_builtin_reason", "stabilize_adherence_review",
        "_suite_passed", "TaskReport", "TaskProgress", "EvalProgress", "SuiteReport", "run_eval",
        "task_timeout_sec", "env_task_timeout_sec", "_outcome_judge_outputs",
        "_resolve_task_spec", "_score_rows", "_run_outcome_judge", "_apply_mismatch",
        "CORRECTLY_SKIPPED", "_no_trigger_skipped_judge", "_live_verdict",
        "_seed_skill_selection", "_why_expected_output", "_maybe_explain_fail", "_run_task",
        "_skipped_report", "_resolve_path", "_reference_twin", "_resolve_pack_stamp",
        "_spans_from_transcript", "_emit_progress", "_eval_progress",
    ),
    "skillgate_ai.cli": (
        "app", "console", "_emit_json", "_boot", "_version_callback", "_main", "version",
        "_print_agent_status", "_login_targets", "login", "doctor", "ingest", "_present_check",
        "_verbose_scoring_lines", "_parse_targets", "_bind_key_env", "_stdin_is_tty",
        "_read_omitted_key", "_run_gate", "_HARNESS_HELP", "_SANDBOX_HELP", "_KEY_ENV_HELP",
        "check_pack", "run_suite", "deploy", "sync", "connect", "helper", "list_assets",
        "keys_app", "keys_set", "keys_clear", "keys_list", "init_cmd", "new_cmd", "example_cmd",
        "examples_app", "examples_list_cmd", "examples_install_cmd", "judge_app",
        "judge_provider_app", "checks_app", "_resolve_pack_arg", "checks_show_cmd", "judge_show",
        "judge_reset", "judge_add_question_cmd", "case_app", "case_add_cmd",
        "judge_provider_show", "judge_provider_set", "_run_judge_test", "_VERBOSE_HELP",
        "judge_test", "judge_provider_test", "ui_cmd",
    ),
    "skillgate_ai.cli_pack": ("_output_optional_flag", "register_pack_commands"),
    "skillgate_ai.case_pack": (
        "CASES_REL", "PIN_NEEDS_EXPECTED", "PIN_NEEDS_EXPECTED_HINT", "NO_TRIGGER_OUTPUT_WARNING",
        "EXPECTED_WITHOUT_TARGET", "PACK_FINGERPRINT_FIELDS", "_CASE_ID_RE", "_JSONISH_RE",
        "CaseFileCopy", "CaseInput", "CaseGolden", "PackCase", "CasePack", "TrustSuite",
        "_reject_missing_seed_cases", "_reject_removed_seed_cases", "pack_judge_dict",
        "save_pack_judge", "reset_pack_judge", "expected_without_target_warning", "cases_path",
        "load_case_pack", "save_case_pack", "pack_fingerprint", "suite_fingerprint",
        "suite_from_pack", "checks_from_pack", "skill_has_dataset", "dataset_view",
        "_preview_file", "pin_checks", "pin_case_ids", "trust_suite_for_skill",
        "suite_from_checks", "expand_from_pack", "checks_fingerprint", "_OPTIONAL_OUTPUT_NOTE",
        "golden_state", "actual_output_state", "case_for_task", "_dump_pack",
        "_validate_pack_on_disk", "MISSING_GOLDEN_REASON", "no_trigger_output_warning",
        "task_missing_golden", "_skill_name", "_file_copies", "_inline_input_text",
        "_case_from_check", "_file_content", "_persist_input_files", "_disk_golden",
        "_persist_golden", "_project_root_for_skill", "_bundled_suite_trust", "_template_trust",
    ),
    "skillgate_ai.judge_openai": (
        "DEFAULT_MODEL", "GATEWAY_DECISIONS_MODEL", "DEFAULT_TIMEOUT_SEC", "WHY_TIMEOUT_SEC",
        "WHY_MAX_OUTPUT_TOKENS", "WHY_OUTPUT_CHARS", "TRANSCRIPT_TAIL_CHARS", "DISPLAY_NAME",
        "GATEWAY_DISPLAY_NAME", "CHOSEN_DISPLAY_NAME", "_decisions_model", "JudgeBackend",
        "_OpenAIPosted", "_tail", "_cell_entry", "_user_content", "_state_text",
        "_artifacts_without_bodies", "_expected_outcome_text", "_text_blob", "_path_is_recorded",
        "_path_not_available_cell", "_finished_answers", "_answer_row", "_normalize_answers",
        "_answers_from_decisions_list", "_lift_decision_answer", "_annotate_payload_too_large",
        "DecisionsBackend", "OutcomeJudge", "_scoring_endpoint", "_sum_judge_usage", "_as_path",
        "ping_openai_backend", "make_openai_judge",
    ),
    "skillgate_ai.compare": (
        "MAX_ARMS", "MIN_ARMS", "DEFAULT_MAX_SPEND_USD", "ALLOWED_COMPARE_HARNESS",
        "CompareError", "CompareArmSpec", "CompareResult", "arm_label_defaults",
        "parse_arm_spec", "parse_arm_file", "_resolved_arm_model", "_blank", "_as_int",
        "_as_float", "_arm_ids", "arm_id_for_index", "validate_compare_plan",
        "_resolve_compare_case_ids", "checks_for_case_ids", "_usage_for_task_ids",
        "_dry_run_payload", "_skill_pack_hash_from_report", "_usage_from_report", "_task_map",
        "_build_cases", "scrub_compare_payload", "scrub_customer_compare_payload",
        "_subtitle_for_arm", "_plan_subtitle", "_case_ids_from_report", "_arm_stats_from_report",
        "_append_compare_failure", "run_models_compare", "_run_models_compare",
        "_history_report", "preflight_versions_compare", "_git_ref_picker_suggestions",
        "_versions_dry_run_payload", "harness_from_history", "_normalize_compare_harness",
        "run_versions_compare", "_run_versions_compare", "find_compare",
        "find_compare_anywhere", "list_compares", "list_compares_merged",
        "strip_compare_list_meta",
    ),
}

# Names a module re-exports from elsewhere (identity is not checked against the module).
PASS_THROUGH: dict[str, tuple[str, ...]] = {
    "skillgate_ai.case_pack": (
        "GOLDEN_TAIL_CHARS", "ExtraQuestion", "JudgeBlock", "read_capped_text",
        "sniff_output_bytes",
    ),
    "skillgate_ai.judge_openai": (
        "DEFAULT_BASE_URL", "OUT_OF_CREDITS", "IMAGE_MAX_BYTES", "IMAGE_MAX_COUNT",
        "collect_images", "redact_secrets", "user_message_for_status",
    ),
    "skillgate_ai.compare": ("run_check",),
    "skillgate_ai.cli": ("register_compare_commands", "register_pack_commands"),
}

JUDGE_OPENAI_ALL = (
    "DISPLAY_NAME", "GATEWAY_DISPLAY_NAME", "IMAGE_MAX_BYTES", "IMAGE_MAX_COUNT",
    "OUT_OF_CREDITS", "WHY_OUTPUT_CHARS", "DecisionsBackend", "OutcomeJudge",
    "collect_images", "make_openai_judge", "redact_secrets", "user_message_for_status",
)

# Step 1 records the observed order on main; any later change is a regression.
TOP_COMMANDS = (
    "version", "login", "doctor", "ingest", "check", "run", "deploy", "sync", "connect",
    "helper", "list", "init", "new", "example", "ui", "import",
    "keys", "examples", "judge", "checks", "case", "skill", "history", "compare",
)
SUB_COMMANDS: dict[str, tuple[str, ...]] = {
    "keys": ("set", "clear", "list"),
    "examples": ("list", "install"),
    "judge": ("show", "reset", "add-question", "test", "remove-question", "set-question", "provider"),
    "judge provider": ("show", "set", "test"),
    "checks": ("show",),
    "case": ("add", "list", "remove", "edit", "import", "bind"),
    "skill": ("write", "paste"),
    "history": ("show",),
    "compare": ("models", "versions", "show", "cancel", "list"),
}
CLI_SURFACE_SHA256 = (
    "130695a069e5de6f6ceb528f0502b7ca701b64135a481f2123140e7cf42483a1"
)

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
                if owner == "conftest":
                    # autouse harness session stubs in tests/conftest.py
                    continue
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
    assert hasattr(cmd, "commands")
    return cmd  # TyperGroup (not a click.Group subclass in current typer)


def test_cli_command_order() -> None:
    root = _root()
    assert tuple(root.commands) == TOP_COMMANDS
    for path, expected in SUB_COMMANDS.items():
        node: click.Command = root
        for part in path.split():
            assert hasattr(node, "commands")
            node = node.commands[part]
        assert hasattr(node, "commands")
        assert tuple(node.commands) == expected, path


def _surface(cmd: click.Command, path: str, rows: list[str]) -> None:
    rows.append(f"{path}|help={cmd.help!r}|short={cmd.short_help!r}|hidden={cmd.hidden}")
    for p in cmd.params:
        ptype = getattr(p, "param_type_name", None) or getattr(
            getattr(p, "type", None), "name", type(p).__name__
        )
        rows.append(
            f"{path}|{p.name}|{p.opts}|{p.secondary_opts}|type={ptype}|req={p.required}"
            f"|default={p.default!r}|multiple={p.multiple}|flag={getattr(p, 'is_flag', None)}"
            f"|help={getattr(p, 'help', None)!r}"
        )
    if hasattr(cmd, "commands"):
        for name, sub in cmd.commands.items():
            _surface(sub, f"{path} {name}", rows)


def test_cli_surface_digest() -> None:
    rows: list[str] = []
    _surface(_root(), "skillgate", rows)
    blob = "\n".join(rows)
    assert " at 0x" not in blob, "unstable repr in CLI surface"
    digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    assert digest == CLI_SURFACE_SHA256, blob
