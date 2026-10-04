from __future__ import annotations

from pathlib import Path

from skillgate_ai.history import append_eval, load_history


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


def test_skip_on_unwritable(tmp_path: Path, monkeypatch) -> None:
    pack = tmp_path / "ro"
    pack.mkdir()
    # Force OSError on mkdir by pointing at a file path as history parent
    (pack / "evals").write_text("not a dir", encoding="utf-8")
    dest = append_eval(pack, run_id="x", passed=False)
    assert dest is None
    assert load_history(pack) == []
