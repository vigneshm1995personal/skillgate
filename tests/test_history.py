from __future__ import annotations

from pathlib import Path

from skillgate_ai.history import append_deploy, append_eval, load_deploys, load_history


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


def test_deploy_log_is_not_eval_history(tmp_path: Path) -> None:
    pack = tmp_path / "skill"
    append_eval(
        pack,
        run_id="r1",
        passed=True,
        report={"skill": "pdf", "task_count": 1},
        config={"harness": "demo"},
    )
    append_deploy(pack, target="cursor", status="installed", file_count=3)
    rows = load_history(pack)
    assert len(rows) == 1
    assert rows[0]["run_id"] == "r1"
    assert rows[0].get("kind") != "deploy"
    deploys = load_deploys(pack)
    assert len(deploys) == 1
    assert deploys[0]["target"] == "cursor"
    assert "dest_label" not in deploys[0]
    assert "dest_path" not in deploys[0]
