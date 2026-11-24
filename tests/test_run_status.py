from __future__ import annotations

import json
import os
import socket
from pathlib import Path

import pytest
from test_run_registry import UI_SEED_KEYS, _fake_suite, _pdf_pack

from skillgate_ai.errors import SkillGateError
from skillgate_ai.run_registry import RunRegistry, RunRequest
from skillgate_ai.run_status import (
    _atomic_write_json,
    _iso_now,
    assert_valid_run_id,
    read_run_status,
    record_from_status,
    status_path,
)


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


def test_live_pid_fresh_heartbeat_not_orphaned(tmp_path: Path) -> None:
    pack = _pdf_pack(tmp_path)
    run_id = "liverun001"
    path = status_path(pack, run_id)
    payload = {
        "version": 1,
        "run_id": run_id,
        "heartbeat_at": _iso_now(),
        "owner": {"pid": os.getpid(), "hostname": socket.gethostname()},
        "record": {"id": run_id, "status": "running", "skill_path": str(pack)},
    }
    _atomic_write_json(path, payload)
    out = read_run_status(path)
    assert out is not None
    record = record_from_status(out)
    assert record is not None
    assert record["status"] == "running"


def test_dead_pid_fresh_heartbeat_orphaned(tmp_path: Path) -> None:
    pack = _pdf_pack(tmp_path)
    run_id = "deadpidr01"
    path = status_path(pack, run_id)
    payload = {
        "version": 1,
        "run_id": run_id,
        "heartbeat_at": _iso_now(),
        "owner": {"pid": 999999999, "hostname": socket.gethostname()},
        "record": {"id": run_id, "status": "running", "skill_path": str(pack)},
    }
    _atomic_write_json(path, payload)
    out = read_run_status(path)
    assert out is not None
    record = record_from_status(out)
    assert record is not None
    assert record["status"] == "orphaned"


def test_stale_heartbeat_orphans_even_when_pid_alive(tmp_path: Path) -> None:
    pack = _pdf_pack(tmp_path)
    run_id = "stalehb0001"
    path = status_path(pack, run_id)
    payload = {
        "version": 1,
        "run_id": run_id,
        "heartbeat_at": "2020-01-01T00:00:00+00:00",
        "owner": {"pid": os.getpid(), "hostname": socket.gethostname()},
        "record": {"id": run_id, "status": "running", "skill_path": str(pack)},
    }
    _atomic_write_json(path, payload)
    out = read_run_status(path)
    assert out is not None
    record = record_from_status(out)
    assert record is not None
    assert record["status"] == "orphaned"


def test_invalid_run_id_rejected_for_status_path(tmp_path: Path) -> None:
    pack = _pdf_pack(tmp_path)
    for bad in ("/etc/passwd", "../secret", "..", "a/b", ""):
        with pytest.raises(SkillGateError, match="Invalid run id"):
            status_path(pack, bad)


def test_read_run_status_rejects_corrupt_json(tmp_path: Path) -> None:
    pack = _pdf_pack(tmp_path)
    safe_path = status_path(pack, "partial00001")
    safe_path.write_text("{", encoding="utf-8")
    assert read_run_status(safe_path) is None


def test_atomic_write_keeps_old_file_on_replace_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pack = _pdf_pack(tmp_path)
    path = status_path(pack, "atomic00001")
    original = {
        "version": 1,
        "run_id": "atomic00001",
        "record": {"status": "done", "id": "atomic00001"},
    }
    _atomic_write_json(path, original)

    def broken_replace(*_a, **_k) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr("skillgate_ai.run_status.os.replace", broken_replace)
    with pytest.raises(OSError, match="replace failed"):
        _atomic_write_json(path, {**original, "record": {"status": "error", "id": "atomic00001"}})
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk == original
    leftovers = [p for p in path.parent.iterdir() if p.name.startswith(f".{path.stem}-")]
    assert not leftovers


def test_assert_valid_run_id_accepts_uuid_style() -> None:
    assert assert_valid_run_id("deadbeefcafe") == "deadbeefcafe"
