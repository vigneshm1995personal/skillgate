"""Deterministic tool-call assertions. Outrank the judge.

Re-export shim. Code lives in the submodules listed below. Patching a name on this
shim does not affect code inside the package; patch the submodule that defines it.
"""

from __future__ import annotations

from skillgate_ai.tool_checks.aliases import ToolCall as ToolCall
from skillgate_ai.tool_checks.aliases import _pattern_forms as _pattern_forms
from skillgate_ai.tool_checks.aliases import _shell_rule_aliases as _shell_rule_aliases
from skillgate_ai.tool_checks.aliases import matches_pattern as matches_pattern
from skillgate_ai.tool_checks.aliases import normalize_tool_name as normalize_tool_name
from skillgate_ai.tool_checks.aliases import tool_aliases as tool_aliases
from skillgate_ai.tool_checks.assertions import _args_match as _args_match
from skillgate_ai.tool_checks.assertions import _count_matching as _count_matching
from skillgate_ai.tool_checks.assertions import _fmt_args as _fmt_args
from skillgate_ai.tool_checks.assertions import _get_path as _get_path
from skillgate_ai.tool_checks.assertions import _match_expected as _match_expected
from skillgate_ai.tool_checks.assertions import _matching_calls as _matching_calls
from skillgate_ai.tool_checks.assertions import _score_assertions as _score_assertions
from skillgate_ai.tool_checks.collect import _args_from_row as _args_from_row
from skillgate_ai.tool_checks.collect import _args_from_span as _args_from_span
from skillgate_ai.tool_checks.collect import _command_stem as _command_stem
from skillgate_ai.tool_checks.collect import _declared_shell_calls as _declared_shell_calls
from skillgate_ai.tool_checks.collect import _name_from_argv as _name_from_argv
from skillgate_ai.tool_checks.collect import _name_from_row as _name_from_row
from skillgate_ai.tool_checks.collect import _safe_calls_log_path as _safe_calls_log_path
from skillgate_ai.tool_checks.collect import _shell_rule_calls as _shell_rule_calls
from skillgate_ai.tool_checks.collect import _shell_segments as _shell_segments
from skillgate_ai.tool_checks.collect import collect_tool_calls as collect_tool_calls
from skillgate_ai.tool_checks.consequential import _alias_segments as _alias_segments
from skillgate_ai.tool_checks.consequential import (
    _allow_consequential_hint as _allow_consequential_hint,
)
from skillgate_ai.tool_checks.consequential import _allowed_consequential as _allowed_consequential
from skillgate_ai.tool_checks.consequential import (
    _consequential_display_name as _consequential_display_name,
)
from skillgate_ai.tool_checks.consequential import _score_consequential as _score_consequential
from skillgate_ai.tool_checks.consequential import is_consequential as is_consequential
from skillgate_ai.tool_checks.rules import _ENV_PREFIX as _ENV_PREFIX
from skillgate_ai.tool_checks.rules import _INTERPRETERS as _INTERPRETERS
from skillgate_ai.tool_checks.rules import _READ_VERBS as _READ_VERBS
from skillgate_ai.tool_checks.rules import _SAFE_TOOLS as _SAFE_TOOLS
from skillgate_ai.tool_checks.rules import _SEP as _SEP
from skillgate_ai.tool_checks.rules import _SHELL_RULES as _SHELL_RULES
from skillgate_ai.tool_checks.rules import _SHELL_TOOLS as _SHELL_TOOLS
from skillgate_ai.tool_checks.rules import _SUDO_PREFIX as _SUDO_PREFIX
from skillgate_ai.tool_checks.rules import TOOL_CHECK_SCORERS as TOOL_CHECK_SCORERS
from skillgate_ai.tool_checks.scoring import score_tool_checks as score_tool_checks
from skillgate_ai.tool_checks.scoring import tool_check_failures as tool_check_failures
