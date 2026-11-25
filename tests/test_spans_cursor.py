from __future__ import annotations

import json

from skillgate_ai.spans import attr_map, make_span, spans_from_jsonl


def test_make_span_attr_types() -> None:
    span = make_span(
        name="tool.bash",
        trace_id="abcd",
        attributes={"flag": True, "count": 2, "ratio": 0.5, "label": "x"},
    )
    attrs = attr_map(span)
    assert attrs.get("flag") == "true" or attrs.get("flag") is True


def test_spans_from_jsonl_cursor_read_tool_call() -> None:
    line = json.dumps(
        {
            "type": "tool_call",
            "subtype": "started",
            "tool_call": {
                "readToolCall": {"args": {"path": "/tmp/foo.txt"}},
            },
        }
    )
    spans = spans_from_jsonl(line)
    names = {span["name"] for span in spans}
    assert any(name.startswith("tool.") for name in names)


def test_spans_from_jsonl_codex_item_completed() -> None:
    line = json.dumps(
        {
            "type": "item.completed",
            "item": {
                "type": "file_change",
                "changes": [{"path": "output/a.txt"}],
            },
        }
    )
    spans = spans_from_jsonl(line)
    assert spans
