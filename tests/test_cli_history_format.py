from __future__ import annotations

from pathlib import Path

from skillgate_ai.cli.history_format import _print_history_rows, _print_history_run


def test_print_history_rows_empty_message(capsys) -> None:

    _print_history_rows([])
    out = capsys.readouterr().out
    assert "No runs yet" in out


def test_print_history_rows_renders_pass_and_tryout(monkeypatch) -> None:
    printed: list[str] = []

    class FakeConsole:
        def print(self, text: str, **kwargs: object) -> None:
            printed.append(text)

    monkeypatch.setattr("skillgate_ai.cli.console", FakeConsole())
    rows = [
        {
            "run_id": "r1",
            "passed": True,
            "tryout": True,
            "ts": "2026-01-02T00:00:00+00:00",
            "report": {
                "gate": "green",
                "scored_by": "Scored by the judge",
                "passed_count": 1,
                "task_count": 1,
                "config": {"judge": {"display_name": "Judge"}},
            },
        }
    ]
    _print_history_rows(rows)
    line = printed[-1]
    assert "r1" in line
    assert "tryout" in line
    assert "pass" in line.lower()


def test_print_history_run_without_report(tmp_path: Path, monkeypatch) -> None:
    printed: list[str] = []

    class FakeConsole:
        def print(self, text: str, **kwargs: object) -> None:
            printed.append(text)

    monkeypatch.setattr("skillgate_ai.cli.console", FakeConsole())
    _print_history_run({"run_id": "r2", "passed": None, "error": {"message": "cannot run"}})
    assert any("r2" in line for line in printed)
