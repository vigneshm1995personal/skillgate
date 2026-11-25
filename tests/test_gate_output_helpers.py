from __future__ import annotations

from types import SimpleNamespace

from skillgate_ai.cli.gate_output import _print_auth_diagnostics, _verbose_scoring_lines


def test_verbose_scoring_lines_includes_upstream_notes() -> None:
    task = SimpleNamespace(
        task_id="t1",
        judge={"upstream": "Judge noted a gap."},
    )
    report = SimpleNamespace(tasks=[task])
    assert _verbose_scoring_lines(report) == ["  t1: Judge noted a gap."]


def test_verbose_scoring_lines_skips_missing_upstream() -> None:
    task = SimpleNamespace(task_id="t1", judge={})
    report = SimpleNamespace(tasks=[task])
    assert _verbose_scoring_lines(report) == []


def test_print_auth_diagnostics_renders_tail(capsys) -> None:
    diag = {
        "harness": "codex",
        "exit_code": 2,
        "stderr_tail": "auth failed",
        "env_presence": {"OPENAI_API_KEY": True},
        "command_summary": ["agent", "run"],
    }
    _print_auth_diagnostics(diag)
    out = capsys.readouterr().out
    assert "Auth diagnostics:" in out
    assert "codex" in out
    assert "auth failed" in out
    assert "OPENAI_API_KEY" in out
