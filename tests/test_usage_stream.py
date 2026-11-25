from __future__ import annotations

from skillgate_ai.usage.stream import is_non_content_stream_line, render_stream_line


def test_is_non_content_stream_line_rate_limit() -> None:
    assert is_non_content_stream_line('{"type":"rate_limit_event","n":1}') is True
    assert is_non_content_stream_line('{"type":"ping"}') is True
    assert is_non_content_stream_line('{"type":"assistant","message":{}}') is False
    assert is_non_content_stream_line("plain text") is False
    assert is_non_content_stream_line("{bad json") is False


def test_render_stream_line_drops_rate_limit_and_ping() -> None:
    assert render_stream_line('{"type":"rate_limit_event"}') is None
    assert render_stream_line('{"type":"ping"}') is None
    assert render_stream_line('{"type":"hook_started"}') is None


def test_render_stream_line_codex_agent_message() -> None:
    line = '{"type":"item.completed","item":{"type":"agent_message","text":"hello from agent"}}'
    assert render_stream_line(line) == "hello from agent"


def test_render_stream_line_codex_command() -> None:
    line = '{"type":"item.completed","item":{"type":"command_execution","command":"pytest -q"}}'
    assert render_stream_line(line) == "$ pytest -q"


def test_render_stream_line_codex_file_change() -> None:
    line = (
        '{"type":"item.completed","item":{"type":"file_change",'
        '"changes":[{"path":"a.py"},{"path":"b.py"}]}}'
    )
    assert render_stream_line(line) == "changed a.py, b.py"


def test_render_stream_line_cursor_assistant_text() -> None:
    line = '{"type":"assistant","message":{"content":[{"type":"text","text":"hi there"}]}}'
    assert render_stream_line(line) == "hi there"


def test_render_stream_line_cursor_tool_call() -> None:
    line = (
        '{"type":"tool_call","subtype":"started","tool_call":'
        '{"bashToolCall":{"args":{"command":"make test"}}}}'
    )
    assert render_stream_line(line) == "$ bash make test"


def test_render_stream_line_cursor_tool_call_completed_is_dropped() -> None:
    line = '{"type":"tool_call","subtype":"completed","tool_call":{}}'
    assert render_stream_line(line) is None


def test_render_stream_line_error_envelope() -> None:
    assert render_stream_line('{"type":"error","message":"boom"}') == "error: boom"


def test_render_stream_line_non_json_passthrough() -> None:
    assert render_stream_line("  raw line  ") == "  raw line  "


def test_render_stream_line_bookkeeping_dropped() -> None:
    assert render_stream_line('{"type":"thread.started"}') is None
    assert render_stream_line('{"type":"system","subtype":"init"}') is None


def test_render_stream_line_event_msg_token_count_dropped() -> None:
    line = '{"type":"event_msg","payload":{"type":"token_count","n":3}}'
    assert render_stream_line(line) is None


def test_render_stream_line_thinking_text() -> None:
    assert render_stream_line('{"type":"thinking","text":"planning"}') == "planning"


def test_render_stream_line_claude_tool_results() -> None:
    line = (
        '{"type":"user","message":{"content":[{"type":"tool_result","content":"pytest passed"}]}}'
    )
    assert render_stream_line(line) == "pytest passed"


def test_render_stream_line_codex_reasoning_item() -> None:
    line = '{"type":"item.completed","item":{"type":"reasoning","text":"chain"}}'
    assert render_stream_line(line) == "chain"


def test_render_stream_line_passthrough_unknown_json_kind() -> None:
    line = '{"type":"custom_debug","payload":1}'
    assert render_stream_line(line) == line
