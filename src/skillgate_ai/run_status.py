"""Disk-backed run status for MCP/UI polls across process restarts."""

from __future__ import annotations

import contextlib
import json
import os
import re
import socket
import tempfile
import threading
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from skillgate_ai.errors import SkillGateError
from skillgate_ai.history import history_dir

RUN_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")

STATUS_VERSION = 1
RUNS_DIRNAME = "runs"
HEARTBEAT_INTERVAL_SEC = 10.0
ORPHAN_HEARTBEAT_SEC = 60.0

ORPHAN_MESSAGE = (
    "This check stopped when the Skill Gate process running it exited "
    "(pid {pid} on {host}). No result was saved."
)


def runs_dir(pack_root: str | Path) -> Path:
    dest = history_dir(pack_root) / RUNS_DIRNAME
    dest.mkdir(parents=True, exist_ok=True)
    gitignore = dest / ".gitignore"
    if not gitignore.is_file():
        with contextlib.suppress(OSError):
            gitignore.write_text("*\n", encoding="utf-8")
    return dest


def assert_valid_run_id(run_id: str) -> str:
    text = (run_id or "").strip()
    if not RUN_ID_RE.fullmatch(text):
        raise SkillGateError("Invalid run id.")
    return text


def status_path(pack_root: str | Path, run_id: str) -> Path:
    safe = assert_valid_run_id(run_id)
    base = runs_dir(pack_root).resolve()
    path = (base / f"{safe}.json").resolve()
    if path.parent != base:
        raise SkillGateError("Invalid run id.")
    try:
        path.relative_to(base)
    except ValueError as exc:
        raise SkillGateError("Invalid run id.") from exc
    return path


def _iso_now() -> str:
    return datetime.now(UTC).astimezone().isoformat()


def _owner() -> Mapping[str, Any]:
    return {"pid": os.getpid(), "hostname": socket.gethostname()}


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=True, indent=2) + "\n"
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix=f".{path.stem}-", suffix=".json")
    closed = False
    try:
        os.write(fd, text.encode("utf-8"))
        os.close(fd)
        closed = True
        os.replace(tmp_path, path)
    finally:
        if not closed:
            os.close(fd)
        leftover = Path(tmp_path)
        if leftover.is_file() and leftover != path:
            leftover.unlink(missing_ok=True)


def persist_run_status(
    pack_root: str | Path,
    run_id: str,
    record: dict[str, Any],
    *,
    meta: Mapping[str, Any] | None = None,
) -> None:
    """Best-effort status snapshot without the report body."""
    slim = {key: record.get(key) for key in record if key != "report"}
    payload: dict[str, Any] = {
        "version": STATUS_VERSION,
        "run_id": run_id,
        "updated_at": _iso_now(),
        "heartbeat_at": _iso_now(),
        "owner": _owner(),
        "record": slim,
    }
    if meta:
        payload["meta"] = dict(meta)
    try:
        _atomic_write_json(status_path(pack_root, run_id), payload)
    except OSError:
        return


def touch_heartbeat(pack_root: str | Path, run_id: str) -> None:
    path = status_path(pack_root, run_id)
    if not path.is_file():
        return
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(raw, dict):
        return
    if raw.get("status") == "orphaned":
        return
    record_obj = raw.get("record")
    record = record_obj if isinstance(record_obj, dict) else {}
    if str(record.get("status") or raw.get("status")) not in ("running", "started"):
        return
    raw["heartbeat_at"] = _iso_now()
    raw["owner"] = _owner()
    try:
        _atomic_write_json(path, raw)
    except OSError:
        return


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _heartbeat_stale(heartbeat_at: str | None) -> bool:
    if not heartbeat_at:
        return True
    try:
        when = datetime.fromisoformat(heartbeat_at)
    except ValueError:
        return True
    age = (datetime.now(UTC).astimezone() - when).total_seconds()
    return age > ORPHAN_HEARTBEAT_SEC


def _apply_orphan(payload: Mapping[str, Any], path: Path) -> Mapping[str, Any]:
    record_obj = payload.get("record")
    record = record_obj if isinstance(record_obj, dict) else {}
    status = str(record.get("status") or payload.get("status") or "running")
    if status not in ("running", "started"):
        return dict(payload)
    owner_obj = payload.get("owner")
    owner = owner_obj if isinstance(owner_obj, dict) else {}
    pid = int(owner.get("pid") or 0)
    host = str(owner.get("hostname") or "")
    local = host == socket.gethostname()
    dead = local and not _pid_alive(pid)
    stale = _heartbeat_stale(str(payload.get("heartbeat_at") or ""))
    if not dead and not stale:
        return dict(payload)
    message = ORPHAN_MESSAGE.format(pid=pid or "?", host=host or "?")
    out = dict(payload)
    next_record = dict(record)
    next_record.update(
        {
            "status": "orphaned",
            "passed": None,
            "gate_decision": "pending",
            "error": {"message": message},
        }
    )
    out["record"] = next_record
    out["status"] = "orphaned"
    out["orphan_reason"] = message
    with contextlib.suppress(OSError):
        _atomic_write_json(path, out)
    return out


def read_run_status(path: Path) -> Mapping[str, Any] | None:
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            return None
        payload = json.loads(text)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return _apply_orphan(payload, path)


def record_from_status(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    record = payload.get("record") if isinstance(payload.get("record"), dict) else None
    if record is None:
        return None
    return dict(record)


def start_heartbeat(
    pack_root: str | Path,
    run_id: str,
    *,
    stop: threading.Event,
) -> threading.Thread:
    def loop() -> None:
        while not stop.wait(HEARTBEAT_INTERVAL_SEC):
            touch_heartbeat(pack_root, run_id)

    thread = threading.Thread(
        target=loop,
        name=f"skillgate-run-heartbeat-{run_id}",
        daemon=True,
    )
    thread.start()
    return thread


def find_status_file(root: Path, run_id: str) -> tuple[Mapping[str, Any], Path] | None:
    from skillgate_ai.catalog import catalog_entries
    from skillgate_ai.paths import is_skill_pack

    try:
        assert_valid_run_id(run_id)
    except SkillGateError:
        return None
    candidates: list[Path] = []
    for entry in catalog_entries(root):
        candidates.append(Path(entry["absolute"]))
    if is_skill_pack(root):
        candidates.append(root)
    for pack in candidates:
        path = status_path(pack, run_id)
        payload = read_run_status(path)
        if payload is not None:
            return payload, pack
    return None
