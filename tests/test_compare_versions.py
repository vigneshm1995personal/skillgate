from __future__ import annotations

from pathlib import Path

import pytest

from skillgate_ai.compare import CompareError, run_versions_compare
from skillgate_ai.compare.versions import harness_from_history, preflight_versions_compare
from skillgate_ai.history import append_eval


def _pack(tmp_path: Path) -> Path:
    pack = tmp_path / "pdf"
    src = Path(__file__).resolve().parents[1] / "skills" / "pdf"
    import shutil

    shutil.copytree(src, pack)
    return pack


def test_harness_from_history_uses_latest_eval(tmp_path: Path) -> None:
    pack = _pack(tmp_path)
    append_eval(
        pack,
        run_id="run-a",
        passed=True,
        report={"tasks": []},
        config={"harness": "codex"},
    )
    assert harness_from_history(pack) == "codex"


def test_preflight_versions_compare_requires_two_distinct_runs(tmp_path: Path) -> None:
    pack = _pack(tmp_path)
    for rid in ("run-a", "run-b"):
        append_eval(
            pack,
            run_id=rid,
            passed=True,
            report={"pack_fingerprint": "fp", "pack_case_ids": [], "tasks": []},
        )
    preflight_versions_compare(pack, run_ids=["run-a", "run-b"])
    with pytest.raises(CompareError, match="different"):
        preflight_versions_compare(pack, run_ids=["run-a", "run-a"])


def test_versions_dry_run_payload(tmp_path: Path) -> None:
    pack = _pack(tmp_path)
    fp = "fp"
    for rid in ("run-a", "run-b"):
        append_eval(
            pack,
            run_id=rid,
            passed=True,
            report={"pack_fingerprint": fp, "pack_case_ids": ["c1"], "tasks": []},
        )
    result = run_versions_compare(
        pack,
        run_ids=["run-a", "run-b"],
        root=tmp_path,
        dry_run=True,
    )
    assert result.exit_code == 0
    assert result.payload["status"] == "dry_run"
    assert len(result.payload.get("arms") or []) == 2


def test_versions_rejects_same_run_twice(tmp_path: Path) -> None:
    pack = _pack(tmp_path)
    fp = "fp"
    append_eval(
        pack,
        run_id="run-a",
        passed=True,
        report={
            "pack_fingerprint": fp,
            "pack_case_ids": ["c1"],
            "tasks": [{"id": "c1", "passed": True}],
        },
    )
    with pytest.raises(CompareError, match="different"):
        run_versions_compare(pack, run_ids=["run-a", "run-a"], root=tmp_path)


def test_versions_history_matrix(tmp_path: Path) -> None:
    pack = _pack(tmp_path)
    fp = "same-fp"
    append_eval(
        pack,
        run_id="run-a",
        passed=True,
        report={
            "skill": "pdf",
            "pack_fingerprint": fp,
            "pack_case_ids": ["c1", "c2"],
            "tasks": [
                {"id": "c1", "passed": True, "usage": {"tokens_total": 10}},
                {"id": "c2", "passed": False, "usage": {"tokens_total": 20}},
            ],
            "usage": {"tokens_total": 30, "cost_usd": 0.1},
        },
        config={"label": "Arm A", "harness": "codex"},
    )
    append_eval(
        pack,
        run_id="run-b",
        passed=False,
        report={
            "skill": "pdf",
            "pack_fingerprint": fp,
            "pack_case_ids": ["c1", "c2"],
            "tasks": [
                {"id": "c1", "passed": True, "usage": {"tokens_total": 11}},
                {"id": "c2", "passed": True, "usage": {"tokens_total": 21}},
            ],
            "usage": {"tokens_total": 32, "cost_usd": 0.2},
        },
        config={"label": "Arm B", "harness": "cursor-agent"},
    )
    result = run_versions_compare(
        pack,
        run_ids=["run-a", "run-b"],
        root=tmp_path,
    )
    assert result.exit_code == 0
    assert result.payload["mode"] == "versions"
    assert result.payload["cases"][1]["disagreement"] is True
    assert len(result.payload["arms"]) == 2


def test_versions_history_includes_skill_pack_hash_from_skill_path(tmp_path: Path) -> None:
    pack = _pack(tmp_path)
    fp = "same-fp"
    append_eval(
        pack,
        run_id="run-a",
        passed=True,
        report={
            "pack_fingerprint": fp,
            "pack_case_ids": ["c1"],
            "skill_path": str(pack),
            "tasks": [{"id": "c1", "passed": True}],
        },
    )
    append_eval(
        pack,
        run_id="run-b",
        passed=True,
        report={
            "pack_fingerprint": fp,
            "pack_case_ids": ["c1"],
            "skill_path": str(pack),
            "tasks": [{"id": "c1", "passed": True}],
        },
    )
    from skillgate_ai.pack import skill_pack_hash

    expected = skill_pack_hash(pack)
    result = run_versions_compare(pack, run_ids=["run-a", "run-b"], root=tmp_path)
    for arm in result.payload["arms"]:
        assert arm.get("skill_pack_hash") == expected


def test_versions_fingerprint_mismatch(tmp_path: Path) -> None:
    pack = _pack(tmp_path)
    append_eval(
        pack,
        run_id="run-a",
        passed=True,
        report={"pack_fingerprint": "a", "tasks": [], "pack_case_ids": []},
    )
    append_eval(
        pack,
        run_id="run-b",
        passed=True,
        report={"pack_fingerprint": "b", "tasks": [], "pack_case_ids": []},
    )
    with pytest.raises(CompareError) as exc:
        run_versions_compare(pack, run_ids=["run-a", "run-b"], root=tmp_path)
    assert exc.value.exit_code == 1
