from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from test_run_registry import UI_SEED_KEYS, _fake_suite, _pdf_pack

from skillgate_ai.run_registry import RunRegistry, RunRequest
from skillgate_ai.run_status import read_run_status, record_from_status, runs_dir, status_path


def test_status_json_written_on_start_and_finish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from conftest import enable_cursor_agent

    enable_cursor_agent(monkeypatch, tmp_path)
    pack = _pdf_pack(tmp_path)
    monkeypatch.setattr("skillgate_ai.gate.run_eval", lambda *_a, **_k: _fake_suite(pack))
    reg = RunRegistry(tmp_path)
    run_id = reg.start(RunRequest(skill_path=pack, no_judge=True))["id"]
    path = status_path(pack, run_id)
    assert path.is_file()
    payload = read_run_status(path)
    assert payload is not None
    record = record_from_status(payload)
    assert record is not None
    assert record["status"] == "running"
    assert reg.join(run_id, timeout=30.0)
    payload2 = read_run_status(path)
    assert payload2 is not None
    assert record_from_status(payload2)["status"] == "done"


def test_fresh_registry_reads_persisted_running_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import threading

    from conftest import enable_cursor_agent

    enable_cursor_agent(monkeypatch, tmp_path)
    pack = _pdf_pack(tmp_path)
    gate = threading.Event()

    def slow_eval(*_a, **_k):
        gate.wait(timeout=30.0)
        return _fake_suite(pack)

    monkeypatch.setattr("skillgate_ai.gate.run_eval", slow_eval)
    reg = RunRegistry(tmp_path)
    run_id = reg.start(RunRequest(skill_path=pack, no_judge=True))["id"]
    reg2 = RunRegistry(tmp_path)
    assert reg2.get(run_id) is None
    payload = read_run_status(status_path(pack, run_id))
    assert payload is not None
    record = record_from_status(payload)
    assert record is not None
    assert record["status"] == "running"
    assert set(UI_SEED_KEYS) - {"report"} <= set(record.keys())
    assert "report" not in record
    gate.set()
    reg.join(run_id, timeout=30.0)


def test_dead_owner_reported_orphaned(tmp_path: Path) -> None:
    pack = _pdf_pack(tmp_path)
    run_id = "deadrun12"
    path = status_path(pack, run_id)
    payload = {
        "version": 1,
        "run_id": run_id,
        "heartbeat_at": "2020-01-01T00:00:00+00:00",
        "owner": {"pid": 999999999, "hostname": os.uname().nodename},
        "record": {
            "id": run_id,
            "status": "running",
            "skill_path": str(pack),
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    out = read_run_status(path)
    assert out is not None
    record = record_from_status(out)
    assert record is not None
    assert record["status"] == "orphaned"
    assert "Skill Gate process" in (record.get("error") or {}).get("message", "")


def test_atomic_write_never_partial_json(tmp_path: Path) -> None:
    pack = _pdf_pack(tmp_path)
    dest = runs_dir(pack) / "partial.json"
    dest.write_text("{", encoding="utf-8")
    assert read_run_status(dest) is None
