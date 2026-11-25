from __future__ import annotations

from pathlib import Path

from skillgate_ai.api_payloads import history_row_to_run


def test_history_row_to_run_marks_tryout_and_gate() -> None:
    skill = Path("/tmp/skills/pdf")
    row = {
        "run_id": "r1",
        "passed": True,
        "tryout": True,
        "gate": "green",
        "ts": "2026-01-01T00:00:00+00:00",
        "report": {"harness": "demo", "task_count": 1, "skill": "pdf", "tryout": True},
    }
    out = history_row_to_run(row, skill)
    assert out["tryout"] is True
    assert out["run_gate"]["decision"] == "pending"
    assert out["skill_path"] == str(skill)
