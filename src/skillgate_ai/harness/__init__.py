"""Agent harnesses: Cursor Agent, Codex CLI, and Claude Code in the sandbox workspace."""

from __future__ import annotations

from skillgate_ai.harness.agents import ClaudeCodeHarness as ClaudeCodeHarness
from skillgate_ai.harness.agents import CodexCliHarness as CodexCliHarness
from skillgate_ai.harness.agents import CursorAgentHarness as CursorAgentHarness
from skillgate_ai.harness.auth import (
    _CLAUDE_LOGIN_STATUS_TIMEOUT_SEC as _CLAUDE_LOGIN_STATUS_TIMEOUT_SEC,
)
from skillgate_ai.harness.auth import (
    _CODEX_LOGIN_STATUS_TIMEOUT_SEC as _CODEX_LOGIN_STATUS_TIMEOUT_SEC,
)
from skillgate_ai.harness.auth import (
    _CURSOR_LOGIN_STATUS_TIMEOUT_SEC as _CURSOR_LOGIN_STATUS_TIMEOUT_SEC,
)
from skillgate_ai.harness.auth import (
    _claude_login_status_authenticated as _claude_login_status_authenticated,
)
from skillgate_ai.harness.auth import _claude_ready as _claude_ready
from skillgate_ai.harness.auth import _claude_session_ok as _claude_session_ok
from skillgate_ai.harness.auth import _codex_auth_key as _codex_auth_key
from skillgate_ai.harness.auth import (
    _codex_login_status_authenticated as _codex_login_status_authenticated,
)
from skillgate_ai.harness.auth import _codex_ready as _codex_ready
from skillgate_ai.harness.auth import _codex_session_ok as _codex_session_ok
from skillgate_ai.harness.auth import (
    _cursor_login_status_authenticated as _cursor_login_status_authenticated,
)
from skillgate_ai.harness.auth import _cursor_ready as _cursor_ready
from skillgate_ai.harness.auth import _cursor_session_ok as _cursor_session_ok
from skillgate_ai.harness.auth import _display_status as _display_status
from skillgate_ai.harness.auth import _probe_claude_login_status as _probe_claude_login_status
from skillgate_ai.harness.auth import _probe_codex_login_status as _probe_codex_login_status
from skillgate_ai.harness.auth import _probe_cursor_login_status as _probe_cursor_login_status
from skillgate_ai.harness.auth import claude_auth_kind as claude_auth_kind
from skillgate_ai.harness.auth import codex_auth_kind as codex_auth_kind
from skillgate_ai.harness.auth import cursor_auth_kind as cursor_auth_kind
from skillgate_ai.harness.auth import format_harness_status as format_harness_status
from skillgate_ai.harness.auth import harness_auth_status as harness_auth_status
from skillgate_ai.harness.auth import normalize_login_agent as normalize_login_agent
from skillgate_ai.harness.base import _AGENT_INSTALL as _AGENT_INSTALL
from skillgate_ai.harness.base import _CODEX_REJECTED_MODEL as _CODEX_REJECTED_MODEL
from skillgate_ai.harness.base import _CODEX_SUPPORTED_MODELS as _CODEX_SUPPORTED_MODELS
from skillgate_ai.harness.base import _STOP as _STOP
from skillgate_ai.harness.base import AUTH_API_KEY as AUTH_API_KEY
from skillgate_ai.harness.base import AUTH_CLI_LOGIN as AUTH_CLI_LOGIN
from skillgate_ai.harness.base import AUTH_NONE as AUTH_NONE
from skillgate_ai.harness.base import CODEX_CHATGPT_DEFAULT as CODEX_CHATGPT_DEFAULT
from skillgate_ai.harness.base import LIVE_HARNESS_NAMES as LIVE_HARNESS_NAMES
from skillgate_ai.harness.base import LOGIN_AGENTS as LOGIN_AGENTS
from skillgate_ai.harness.base import LOGIN_TIMEOUT_ENV as LOGIN_TIMEOUT_ENV
from skillgate_ai.harness.base import LOGIN_TIMEOUT_SEC as LOGIN_TIMEOUT_SEC
from skillgate_ai.harness.base import Harness as Harness
from skillgate_ai.harness.base import HarnessResult as HarnessResult
from skillgate_ai.harness.base import _login_timeout_sec as _login_timeout_sec
from skillgate_ai.harness.base import description_fits_request as description_fits_request
from skillgate_ai.harness.base import harness_usage as harness_usage
from skillgate_ai.harness.base import is_live_harness as is_live_harness
from skillgate_ai.harness.base import rank_skills as rank_skills
from skillgate_ai.harness.base import (
    select_skill_from_descriptions as select_skill_from_descriptions,
)
from skillgate_ai.harness.base import tokenize as tokenize
from skillgate_ai.harness.bins import _executable_path as _executable_path
from skillgate_ai.harness.bins import _looks_like_bin_path as _looks_like_bin_path
from skillgate_ai.harness.bins import _pinned_has_agent_entry as _pinned_has_agent_entry
from skillgate_ai.harness.bins import _resolve_agent_bin as _resolve_agent_bin
from skillgate_ai.harness.bins import _resolve_claude_bin as _resolve_claude_bin
from skillgate_ai.harness.bins import _resolve_codex_bin as _resolve_codex_bin
from skillgate_ai.harness.commands import _CLAUDE_PREAMBLE as _CLAUDE_PREAMBLE
from skillgate_ai.harness.commands import _CLAUDE_SYSTEM_PREAMBLE as _CLAUDE_SYSTEM_PREAMBLE
from skillgate_ai.harness.commands import _CLAUDE_WORKSPACE_TOOLS as _CLAUDE_WORKSPACE_TOOLS
from skillgate_ai.harness.commands import _SKILL_WALK_MAX_DEPTH as _SKILL_WALK_MAX_DEPTH
from skillgate_ai.harness.commands import _SKILL_WALK_SKIP as _SKILL_WALK_SKIP
from skillgate_ai.harness.commands import _claude_code_exec_command as _claude_code_exec_command
from skillgate_ai.harness.commands import _claude_sandbox_env as _claude_sandbox_env
from skillgate_ai.harness.commands import _codex_exec_command as _codex_exec_command
from skillgate_ai.harness.commands import _codex_model_flag as _codex_model_flag
from skillgate_ai.harness.commands import (
    _codex_user_skill_config_override as _codex_user_skill_config_override,
)
from skillgate_ai.harness.commands import _codex_user_skill_roots as _codex_user_skill_roots
from skillgate_ai.harness.commands import _cursor_exec_command as _cursor_exec_command
from skillgate_ai.harness.commands import _sandbox_run as _sandbox_run
from skillgate_ai.harness.commands import _skill_markdown_files as _skill_markdown_files
from skillgate_ai.harness.commands import _toml_basic_string as _toml_basic_string
from skillgate_ai.harness.login import _run_inherited as _run_inherited
from skillgate_ai.harness.login import _terminate_process_group as _terminate_process_group
from skillgate_ai.harness.login import run_official_login as run_official_login
from skillgate_ai.harness.messages import _AUTH_FAILURE_RE as _AUTH_FAILURE_RE
from skillgate_ai.harness.messages import _CLAUDE_MODEL_ACCESS_HINT as _CLAUDE_MODEL_ACCESS_HINT
from skillgate_ai.harness.messages import _MODEL_ACCESS_ERROR as _MODEL_ACCESS_ERROR
from skillgate_ai.harness.messages import _MODEL_UNAVAILABLE_RE as _MODEL_UNAVAILABLE_RE
from skillgate_ai.harness.messages import _USAGE_LIMIT_RE as _USAGE_LIMIT_RE
from skillgate_ai.harness.messages import MODEL_UNAVAILABLE_MESSAGE as MODEL_UNAVAILABLE_MESSAGE
from skillgate_ai.harness.messages import USAGE_LIMIT_MESSAGE as USAGE_LIMIT_MESSAGE
from skillgate_ai.harness.messages import _claude_model_access_error as _claude_model_access_error
from skillgate_ai.harness.messages import (
    _claude_model_access_message as _claude_model_access_message,
)
from skillgate_ai.harness.messages import (
    _codex_rejected_chatgpt_model as _codex_rejected_chatgpt_model,
)
from skillgate_ai.harness.messages import _codex_rejected_model as _codex_rejected_model
from skillgate_ai.harness.messages import _raise_if_auth_failed as _raise_if_auth_failed
from skillgate_ai.harness.messages import _raise_if_cannot_run as _raise_if_cannot_run
from skillgate_ai.harness.messages import auth_failure_message as auth_failure_message
from skillgate_ai.harness.messages import cannot_run_message as cannot_run_message
from skillgate_ai.harness.messages import codex_chatgpt_model_hint as codex_chatgpt_model_hint
from skillgate_ai.harness.messages import model_unavailable_message as model_unavailable_message
from skillgate_ai.harness.messages import usage_limit_message as usage_limit_message
from skillgate_ai.harness.prompts import _agent_prompt as _agent_prompt
from skillgate_ai.harness.prompts import _claude_discover_prompt as _claude_discover_prompt
from skillgate_ai.harness.prompts import _claude_prompt as _claude_prompt
from skillgate_ai.harness.prompts import _claude_skill_paths as _claude_skill_paths
from skillgate_ai.harness.prompts import _claude_trigger_mode_prompt as _claude_trigger_mode_prompt
from skillgate_ai.harness.prompts import _cursor_discover_prompt as _cursor_discover_prompt
from skillgate_ai.harness.prompts import _cursor_prompt as _cursor_prompt
from skillgate_ai.harness.prompts import _trigger_mode_prompt as _trigger_mode_prompt
from skillgate_ai.harness.prompts import _workspace_trigger_mode as _workspace_trigger_mode
from skillgate_ai.harness.prompts import (
    claude_config_isolation_enabled as claude_config_isolation_enabled,
)
from skillgate_ai.harness.prompts import (
    claude_native_skills_enabled as claude_native_skills_enabled,
)
from skillgate_ai.harness.resolve import _AGENT_PRIORITY as _AGENT_PRIORITY
from skillgate_ai.harness.resolve import _LIVE_HARNESS_KINDS as _LIVE_HARNESS_KINDS
from skillgate_ai.harness.resolve import _agent_candidates as _agent_candidates
from skillgate_ai.harness.resolve import _named_harness as _named_harness
from skillgate_ai.harness.resolve import auto_live_harness_name as auto_live_harness_name
from skillgate_ai.harness.resolve import harness_is_startable as harness_is_startable
from skillgate_ai.harness.resolve import has_startable_agent as has_startable_agent
from skillgate_ai.harness.resolve import live_harness_or_error as live_harness_or_error
from skillgate_ai.harness.resolve import resolve_harness as resolve_harness
from skillgate_ai.harness.resolve import startable_agent_kinds as startable_agent_kinds
from skillgate_ai.harness.selection import _MISSING as _MISSING
from skillgate_ai.harness.selection import _SKILL_FILE_RE as _SKILL_FILE_RE
from skillgate_ai.harness.selection import _collect_read_paths as _collect_read_paths
from skillgate_ai.harness.selection import _infer_from_reads as _infer_from_reads
from skillgate_ai.harness.selection import _infer_from_skill_tool as _infer_from_skill_tool
from skillgate_ai.harness.selection import _parse_read_paths as _parse_read_paths
from skillgate_ai.harness.selection import (
    _parse_read_paths_from_spans as _parse_read_paths_from_spans,
)
from skillgate_ai.harness.selection import _parse_selected as _parse_selected
from skillgate_ai.harness.selection import _parse_skill_json as _parse_skill_json
from skillgate_ai.harness.selection import _read_selection as _read_selection
from skillgate_ai.harness.selection import _resolve_trigger_evidence as _resolve_trigger_evidence
from skillgate_ai.harness.selection import _skill_for_selection as _skill_for_selection
from skillgate_ai.harness.selection import _skill_load_path as _skill_load_path
from skillgate_ai.harness.selection import _skill_name_from_path as _skill_name_from_path
from skillgate_ai.harness.selection import _skill_tool_name_from_args as _skill_tool_name_from_args
from skillgate_ai.harness.selection import _write_selection as _write_selection
from skillgate_ai.harness.transcripts import _busiest_model_usage as _busiest_model_usage
from skillgate_ai.harness.transcripts import _claude_used_model as _claude_used_model
from skillgate_ai.harness.transcripts import _codex_transcript as _codex_transcript
from skillgate_ai.harness.transcripts import _codex_used_model as _codex_used_model
from skillgate_ai.harness.transcripts import _cursor_transcript as _cursor_transcript
from skillgate_ai.harness.transcripts import _jsonl_spans as _jsonl_spans
from skillgate_ai.harness.transcripts import _jsonl_transcript as _jsonl_transcript
