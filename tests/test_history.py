from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from skillgate_ai.history import append_eval, latest_eval, load_history


def test_append_and_load(tmp_path: Path) -> None:
    pack = tmp_path / "skill"
    (pack / "evals" / "history").mkdir(parents=True)
    dest = append_eval(
        pack,
        run_id="abc123",
        passed=True,
        report={"suite": "demo", "passed": True},
        config={"harness": "demo"},
    )
    assert dest is not None
    rows = load_history(pack)
    assert len(rows) == 1
    assert rows[0]["run_id"] == "abc123"
    assert rows[0]["passed"] is True
    assert rows[0]["gate"] == "green"


def test_history_filename_uses_local_date(tmp_path: Path, monkeypatch) -> None:
    pack = tmp_path / "skill"
    (pack / "evals" / "history").mkdir(parents=True)
    local = datetime(2026, 10, 10, 21, 0, tzinfo=timezone(timedelta(hours=-4)))

    monkeypatch.setattr("skillgate_ai.history._local_now", lambda: local)
    dest = append_eval(pack, run_id="local-date", passed=True)
    assert dest is not None
    assert dest.name == "20261010.jsonl"
    rows = load_history(pack)
    assert rows[0]["ts"].startswith("2026-10-10T21:00:00")


def test_latest_eval_orders_by_ts_not_filename(tmp_path: Path) -> None:
    pack = tmp_path / "skill"
    hist = pack / "evals" / "history"
    hist.mkdir(parents=True)
    (hist / "20261011.jsonl").write_text(
        '{"ts":"2026-10-11T01:00:00+00:00","run_id":"old-utc","passed":true,"gate":"green"}\n',
        encoding="utf-8",
    )
    (hist / "20261010.jsonl").write_text(
        '{"ts":"2026-10-11T01:30:00+00:00","run_id":"new-local","passed":false,"gate":"red"}\n',
        encoding="utf-8",
    )
    rows = load_history(pack)
    assert [row["run_id"] for row in rows] == ["old-utc", "new-local"]
    row = latest_eval(pack)
    assert row is not None
    assert row["run_id"] == "new-local"
    assert row["passed"] is False


def test_skip_on_unwritable(tmp_path: Path, monkeypatch) -> None:
    pack = tmp_path / "ro"
    pack.mkdir()
    # Force OSError on mkdir by pointing at a file path as history parent
    (pack / "evals").write_text("not a dir", encoding="utf-8")
    dest = append_eval(pack, run_id="x", passed=False)
    assert dest is None
    assert load_history(pack) == []
