from __future__ import annotations

from pathlib import Path

from skillgate_ai.cli.history_format import (
    _print_history_rows,
    _print_history_run,
    _print_skill_versions,
)


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


def test_print_history_rows_marks_fail_and_review(monkeypatch) -> None:
    printed: list[str] = []

    class FakeConsole:
        def print(self, text: str, **kwargs: object) -> None:
            printed.append(text)

    monkeypatch.setattr("skillgate_ai.cli.console", FakeConsole())
    _print_history_rows(
        [
            {
                "run_id": "bad",
                "passed": False,
                "report": {"passed_count": 0, "task_count": 2, "scored_by": "x"},
            },
            {
                "run_id": "rev",
                "passed": True,
                "report": {
                    "gate": "needs review",
                    "passed_count": 1,
                    "task_count": 1,
                    "scored_by": "openai decisions api",
                    "config": {},
                },
            },
        ]
    )
    blob = "\n".join(printed)
    assert "fail" in blob
    assert "review" in blob


def test_print_skill_versions_empty(tmp_path: Path, monkeypatch) -> None:
    printed: list[str] = []

    class FakeConsole:
        def print(self, text: str, **kwargs: object) -> None:
            printed.append(text)

    monkeypatch.setattr("skillgate_ai.cli.console", FakeConsole())
    monkeypatch.setattr("skillgate_ai.compare_git.list_skill_git_versions", lambda _p: [])
    _print_skill_versions(tmp_path / "pack")
    assert any("No versions" in line for line in printed)


def test_print_history_run_with_tasks(tmp_path: Path, monkeypatch) -> None:
    printed: list[str] = []

    class FakeConsole:
        def print(self, text: str, **kwargs: object) -> None:
            printed.append(text)

    monkeypatch.setattr("skillgate_ai.cli.console", FakeConsole())
    _print_history_run(
        {
            "run_id": "r3",
            "passed": True,
            "report": {
                "tasks": [{"id": "t1", "passed": True, "duration_sec": 1.2}],
                "harness": "cursor-agent",
            },
        }
    )
    assert any("t1" in line for line in printed)
