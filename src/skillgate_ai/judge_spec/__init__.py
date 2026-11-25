"""Resolve built-in + extra judge questions. No HTTP.

Re-export shim. Code lives in the submodules listed below. Patching a name on this
shim does not affect code inside the package; patch the submodule that defines it.
"""

from __future__ import annotations

from skillgate_ai.judge_spec.model import CAP_MESSAGE as CAP_MESSAGE
from skillgate_ai.judge_spec.model import MAX_EXTRAS as MAX_EXTRAS
from skillgate_ai.judge_spec.model import MAX_QUESTIONS as MAX_QUESTIONS
from skillgate_ai.judge_spec.model import QUESTION_ID_RE as QUESTION_ID_RE
from skillgate_ai.judge_spec.model import RESERVED_ID_MESSAGE as RESERVED_ID_MESSAGE
from skillgate_ai.judge_spec.model import RESERVED_IDS as RESERVED_IDS
from skillgate_ai.judge_spec.model import TYPE_ALIASES as TYPE_ALIASES
from skillgate_ai.judge_spec.model import TYPE_MESSAGE as TYPE_MESSAGE
from skillgate_ai.judge_spec.model import JudgeQuestion as JudgeQuestion
from skillgate_ai.judge_spec.model import JudgeSpec as JudgeSpec
from skillgate_ai.judge_spec.model import _on_fail_value as _on_fail_value
from skillgate_ai.judge_spec.model import builtin_questions as builtin_questions
from skillgate_ai.judge_spec.model import builtin_spec as builtin_spec
from skillgate_ai.judge_spec.parse import _extra_list as _extra_list
from skillgate_ai.judge_spec.parse import _parse_choices as _parse_choices
from skillgate_ai.judge_spec.parse import _parse_levels as _parse_levels
from skillgate_ai.judge_spec.parse import parse_extra_question as parse_extra_question
from skillgate_ai.judge_spec.parse import resolve_judge_spec as resolve_judge_spec
from skillgate_ai.judge_spec.schema import _extra_schema_property as _extra_schema_property
from skillgate_ai.judge_spec.schema import judge_block_to_dict as judge_block_to_dict
from skillgate_ai.judge_spec.schema import spec_decisions_questions as spec_decisions_questions
from skillgate_ai.judge_spec.schema import spec_structured_schema as spec_structured_schema
from skillgate_ai.judge_spec.verdict import _NOT_APPLICABLE as _NOT_APPLICABLE
from skillgate_ai.judge_spec.verdict import _choice_passes as _choice_passes
from skillgate_ai.judge_spec.verdict import _extract_choice_value as _extract_choice_value
from skillgate_ai.judge_spec.verdict import _extract_probability as _extract_probability
from skillgate_ai.judge_spec.verdict import _extract_score as _extract_score
from skillgate_ai.judge_spec.verdict import _gte as _gte
from skillgate_ai.judge_spec.verdict import _is_not_applicable as _is_not_applicable
from skillgate_ai.judge_spec.verdict import _pass_levels as _pass_levels
from skillgate_ai.judge_spec.verdict import _reason_key as _reason_key
from skillgate_ai.judge_spec.verdict import _unusable_or_fail as _unusable_or_fail
from skillgate_ai.judge_spec.verdict import coerce_extra_answer as coerce_extra_answer
from skillgate_ai.judge_spec.verdict import extra_block_failure_map as extra_block_failure_map
from skillgate_ai.judge_spec.verdict import extra_block_failures as extra_block_failures
from skillgate_ai.judge_spec.verdict import extra_question_passed as extra_question_passed
from skillgate_ai.judge_spec.verdict import low_confidence_for_spec as low_confidence_for_spec
from skillgate_ai.judge_spec.verdict import spec_verdict as spec_verdict
