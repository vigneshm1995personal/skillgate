from __future__ import annotations

from skillgate_ai.usage.stream import is_non_content_stream_line, render_stream_line


def test_is_non_content_stream_line_rate_limit() -> None:
    assert is_non_content_stream_line('{"type":"ping"}') is True
    assert is_non_content_stream_line("plain") is False


def test_render_stream_line_parses_codex_item() -> None:
    line = '{"type":"item","item":{"type":"text","text":"hello"}}'
    out = render_stream_line(line)
    assert out is None or "hello" in out
