"""Harness-neutral token and cost usage parsed from live harness output.

Every harness funnels its machine-readable usage through this module so the
Gate panel, run snapshots, and suite totals all read one `Usage` shape:
`tokens_in`, `tokens_out`, `tokens_total`, `cost_usd` (nullable). A harness
that reports tokens but no dollars leaves `cost_usd` null until
`estimate_usage_cost_usd` fills it from a known model price table.

Codex `exec --json` prints one JSON object per line. The event carrying real
token counts is `turn.completed`:

    {"type":"turn.completed","usage":{"input_tokens":18102,
     "cached_input_tokens":11136,"output_tokens":210,...}}

Cursor Agent `--output-format stream-json` prints one JSON event per line. The
final `result` event carries camelCase usage (no cost):

    {"type":"result","subtype":"success","is_error":false,"result":"pong",
     "usage":{"inputTokens":10146,"outputTokens":101,
              "cacheReadTokens":4736,"cacheWriteTokens":0}}

Anthropic messages and OpenAI-compatible chat completions carry `usage` in the
response JSON (`input_tokens`/`output_tokens` or
`prompt_tokens`/`completion_tokens`) — the same parser reads both.

`parse_usage_line` is deliberately permissive: along with those events it
understands the Codex session `event_msg`/`token_count` shape, the
`token_usage_record` shape, and any object whose `usage`/`total_token_usage`
carries a recognized token key. Lines without usage return None.

`render_stream_line` turns Codex and Cursor JSONL rows into short human lines
for the live tail and the selection transcript; it returns unrecognized input
unchanged.

Re-export shim. Code lives in the submodules listed below. Patching a name on this
shim does not affect code inside the package; patch the submodule that defines it.
"""

from __future__ import annotations

from skillgate_ai.usage.cost import _add_float as _add_float
from skillgate_ai.usage.cost import _add_int as _add_int
from skillgate_ai.usage.cost import _normalize_model_id as _normalize_model_id
from skillgate_ai.usage.cost import combine_task_usage as combine_task_usage
from skillgate_ai.usage.cost import estimate_usage_cost_usd as estimate_usage_cost_usd
from skillgate_ai.usage.cost import normalize_judge_api_usage as normalize_judge_api_usage
from skillgate_ai.usage.model import _CODEX_BOOKKEEPING as _CODEX_BOOKKEEPING
from skillgate_ai.usage.model import _COST_KEYS as _COST_KEYS
from skillgate_ai.usage.model import _CURSOR_BOOKKEEPING as _CURSOR_BOOKKEEPING
from skillgate_ai.usage.model import _IN_KEYS as _IN_KEYS
from skillgate_ai.usage.model import _MODEL_USD_PER_MILLION as _MODEL_USD_PER_MILLION
from skillgate_ai.usage.model import _NON_CONTENT_EVENTS as _NON_CONTENT_EVENTS
from skillgate_ai.usage.model import _OUT_KEYS as _OUT_KEYS
from skillgate_ai.usage.model import _TOTAL_KEYS as _TOTAL_KEYS
from skillgate_ai.usage.model import SUBSCRIPTION_COST_LABEL as SUBSCRIPTION_COST_LABEL
from skillgate_ai.usage.model import Usage as Usage
from skillgate_ai.usage.parse import _Num as _Num
from skillgate_ai.usage.parse import _number_field as _number_field
from skillgate_ai.usage.parse import _pick as _pick
from skillgate_ai.usage.parse import _usage_from_tokens as _usage_from_tokens
from skillgate_ai.usage.parse import _usage_objects as _usage_objects
from skillgate_ai.usage.parse import merge_usage as merge_usage
from skillgate_ai.usage.parse import parse_usage_line as parse_usage_line
from skillgate_ai.usage.parse import usage_from_event as usage_from_event
from skillgate_ai.usage.parse import usage_from_mapping as usage_from_mapping
from skillgate_ai.usage.stream import _CURSOR_ARG_KEYS as _CURSOR_ARG_KEYS
from skillgate_ai.usage.stream import _claude_tool_command as _claude_tool_command
from skillgate_ai.usage.stream import _claude_tool_result_text as _claude_tool_result_text
from skillgate_ai.usage.stream import _cursor_tool_args as _cursor_tool_args
from skillgate_ai.usage.stream import _render_claude_tool_results as _render_claude_tool_results
from skillgate_ai.usage.stream import _render_codex_item as _render_codex_item
from skillgate_ai.usage.stream import _render_cursor_assistant as _render_cursor_assistant
from skillgate_ai.usage.stream import _render_cursor_thinking as _render_cursor_thinking
from skillgate_ai.usage.stream import _render_cursor_tool_call as _render_cursor_tool_call
from skillgate_ai.usage.stream import is_non_content_stream_line as is_non_content_stream_line
from skillgate_ai.usage.stream import render_stream_line as render_stream_line
