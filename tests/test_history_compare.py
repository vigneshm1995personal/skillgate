from __future__ import annotations

from pathlib import Path

from skillgate_ai.history import append_compare, load_compares, load_history


def test_append_compare_and_load_isolated_from_eval_runs(tmp_path: Path) -> None:
    pack = tmp_path / "skill"
    pack.mkdir()
    dest = append_compare(
        pack,
        row={"compare_id": "cmp-1", "status": "done", "skill": "skill", "arms": []},
    )
    assert dest is not None
    compares = load_compares(pack)
    assert len(compares) == 1
    assert compares[0]["compare_id"] == "cmp-1"
    assert load_history(pack) == []
