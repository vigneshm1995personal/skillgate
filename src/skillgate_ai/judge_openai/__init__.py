"""Direct-answer scoring. Chat and Responses completion models are refused."""

from __future__ import annotations

from skillgate_ai.judge_images import IMAGE_MAX_BYTES, IMAGE_MAX_COUNT, collect_images
from skillgate_ai.judge_openai.backend import CHOSEN_DISPLAY_NAME as CHOSEN_DISPLAY_NAME
from skillgate_ai.judge_openai.backend import DEFAULT_MODEL as DEFAULT_MODEL
from skillgate_ai.judge_openai.backend import DEFAULT_TIMEOUT_SEC as DEFAULT_TIMEOUT_SEC
from skillgate_ai.judge_openai.backend import DISPLAY_NAME as DISPLAY_NAME
from skillgate_ai.judge_openai.backend import GATEWAY_DECISIONS_MODEL as GATEWAY_DECISIONS_MODEL
from skillgate_ai.judge_openai.backend import GATEWAY_DISPLAY_NAME as GATEWAY_DISPLAY_NAME
from skillgate_ai.judge_openai.backend import TRANSCRIPT_TAIL_CHARS as TRANSCRIPT_TAIL_CHARS
from skillgate_ai.judge_openai.backend import WHY_MAX_OUTPUT_TOKENS as WHY_MAX_OUTPUT_TOKENS
from skillgate_ai.judge_openai.backend import WHY_OUTPUT_CHARS as WHY_OUTPUT_CHARS
from skillgate_ai.judge_openai.backend import WHY_TIMEOUT_SEC as WHY_TIMEOUT_SEC
from skillgate_ai.judge_openai.backend import JudgeBackend as JudgeBackend
from skillgate_ai.judge_openai.backend import _decisions_model as _decisions_model
from skillgate_ai.judge_openai.backend import _OpenAIPosted as _OpenAIPosted
from skillgate_ai.judge_openai.decisions import DecisionsBackend as DecisionsBackend
from skillgate_ai.judge_openai.decisions import make_openai_judge as make_openai_judge
from skillgate_ai.judge_openai.decisions import ping_openai_backend as ping_openai_backend
from skillgate_ai.judge_openai.outcome import OutcomeJudge as OutcomeJudge
from skillgate_ai.judge_openai.outcome import _as_path as _as_path
from skillgate_ai.judge_openai.outcome import _scoring_endpoint as _scoring_endpoint
from skillgate_ai.judge_openai.outcome import _sum_judge_usage as _sum_judge_usage
from skillgate_ai.judge_openai.payload import (
    _annotate_payload_too_large as _annotate_payload_too_large,
)
from skillgate_ai.judge_openai.payload import _answer_row as _answer_row
from skillgate_ai.judge_openai.payload import (
    _answers_from_decisions_list as _answers_from_decisions_list,
)
from skillgate_ai.judge_openai.payload import _artifacts_without_bodies as _artifacts_without_bodies
from skillgate_ai.judge_openai.payload import _cell_entry as _cell_entry
from skillgate_ai.judge_openai.payload import _expected_outcome_text as _expected_outcome_text
from skillgate_ai.judge_openai.payload import _finished_answers as _finished_answers
from skillgate_ai.judge_openai.payload import _lift_decision_answer as _lift_decision_answer
from skillgate_ai.judge_openai.payload import _normalize_answers as _normalize_answers
from skillgate_ai.judge_openai.payload import _path_is_recorded as _path_is_recorded
from skillgate_ai.judge_openai.payload import _path_not_available_cell as _path_not_available_cell
from skillgate_ai.judge_openai.payload import _state_text as _state_text
from skillgate_ai.judge_openai.payload import _tail as _tail
from skillgate_ai.judge_openai.payload import _text_blob as _text_blob
from skillgate_ai.judge_openai.payload import _user_content as _user_content
from skillgate_ai.openai_http import DEFAULT_BASE_URL as DEFAULT_BASE_URL
from skillgate_ai.openai_http import OUT_OF_CREDITS as OUT_OF_CREDITS
from skillgate_ai.openai_http import redact_secrets as redact_secrets
from skillgate_ai.openai_http import user_message_for_status as user_message_for_status

__all__ = [
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
]
