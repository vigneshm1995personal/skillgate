from __future__ import annotations

import httpx

from skillgate_ai.errors import HarnessError
from skillgate_ai.harness import _command_allowed, _gateway_complete_response, _parse_run_lines
from tests.test_judge import _cfg


def test_parse_run_lines_keeps_quoted_title() -> None:
    text = (
        "RUN: python3 .skillgate/skills/pdf/scripts/create_pdf.py "
        '--title "Q3 Status" output/status.pdf --body "All systems are go."'
    )
    commands = _parse_run_lines(text)
    assert commands == [
        [
            "python3",
            ".skillgate/skills/pdf/scripts/create_pdf.py",
            "--title",
            "Q3 Status",
            "output/status.pdf",
            "--body",
            "All systems are go.",
        ]
    ]
    assert _command_allowed(commands[0], "pdf")
    assert '"Q3' not in commands[0]
    assert 'Status"' not in commands[0]


def test_byo_llm_429_is_plain_settings_copy(monkeypatch) -> None:
    def fake_post(url, headers=None, json=None, timeout=None):
        del url, headers, json, timeout
        return httpx.Response(429, json={"error": {"message": "rate"}})

    monkeypatch.setattr("skillgate_ai.harness.httpx.post", fake_post)
    try:
        _gateway_complete_response(_cfg(gateway_api_key="gw-test"), "hello", 5)
    except HarnessError as exc:
        blob = f"{exc.message} {exc.hint or ''}"
    else:
        raise AssertionError("expected HarnessError")
    assert "429" not in blob
    assert "BYO LLM" not in blob
    assert "OPENAI_API_KEY" not in blob
    assert "AI_GATEWAY_API_KEY" not in blob
    assert "SKILLGATE_MODEL" not in blob
    assert ".env" not in blob
    assert "Settings" in blob
    assert "rate-limited" in blob.lower() or "out of credit" in blob.lower()
