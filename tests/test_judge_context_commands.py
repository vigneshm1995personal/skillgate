from __future__ import annotations

from skillgate_ai.judge_context import parse_command_runs


def test_parse_command_runs_codex_command_execution() -> None:
    transcript = (
        '{"type":"item.completed","item":{"type":"command_execution",'
        '"command":"pytest -q","aggregated_output":"3 passed"}}\n'
    )
    runs = parse_command_runs(transcript)
    assert runs
    assert "pytest" in runs[0]["command"]
    assert "passed" in (runs[0].get("output") or "")


def test_parse_command_runs_plain_pytest_line() -> None:
    transcript = "======================== 2 passed in 0.1s ========================\n"
    runs = parse_command_runs(transcript)
    assert runs and "passed" in runs[0]["output"].lower()
