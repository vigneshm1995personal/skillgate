"""Cancel in-flight compare jobs (CLI, API, and UI share pack-local flags)."""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from skillgate_ai.live import get_control

_COMPARE_ID_RE = re.compile(r"^[a-f0-9]{12}$", re.IGNORECASE)

_LOCK = threading.Lock()
_CONTROLS: dict[str, "CompareControl"] = {}


def _cancel_path(root: Path, compare_id: str) -> Path:
    return root.expanduser().resolve() / ".skillgate" / "cancel" / compare_id


def is_compare_id_format(compare_id: str) -> bool:
    return bool(_COMPARE_ID_RE.match((compare_id or "").strip()))


def _write_cancel_flag(root: Path, compare_id: str) -> None:
    path = _cancel_path(root, compare_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("1", encoding="utf-8")


def _kill_compare_run(control: CompareControl) -> None:
    with control._run_lock:
        run_id = control._current_run_id
    if run_id:
        run_control = get_control(run_id)
        if run_control is not None:
            run_control.request_kill()


def request_cancel_compare(root: Path, compare_id: str) -> bool:
    """Signal cancel. Returns True if cancel was accepted."""
    root = root.expanduser().resolve()
    cid = compare_id.strip()
    if not is_compare_id_format(cid):
        return False
    with _LOCK:
        control = _CONTROLS.get(cid)
    if control is not None:
        control._event.set()
        _write_cancel_flag(root, cid)
        _kill_compare_run(control)
        return True
    _write_cancel_flag(root, cid)
    return True


def is_compare_cancelled(root: Path, compare_id: str) -> bool:
    if _cancel_path(root, compare_id).is_file():
        return True
    with _LOCK:
        control = _CONTROLS.get(compare_id)
    return bool(control and control._event.is_set())


def clear_compare_cancel(root: Path, compare_id: str) -> None:
    path = _cancel_path(root, compare_id)
    if path.is_file():
        path.unlink()
    with _LOCK:
        _CONTROLS.pop(compare_id, None)


@dataclass
class CompareControl:
    compare_id: str
    root: Path
    skill: str = ""
    mode: str = ""
    _event: threading.Event = field(default_factory=threading.Event)
    _current_run_id: str | None = None
    _run_lock: threading.Lock = field(default_factory=threading.Lock)

    def request_cancel(self) -> None:
        self._event.set()
        _write_cancel_flag(self.root, self.compare_id)
        _kill_compare_run(self)

    def cancelled(self) -> bool:
        return self._event.is_set() or _cancel_path(self.root, self.compare_id).is_file()

    def set_current_run(self, run_id: str | None) -> None:
        with self._run_lock:
            self._current_run_id = run_id


def create_compare_control(
    root: Path,
    compare_id: str,
    *,
    skill: str = "",
    mode: str = "",
) -> CompareControl:
    clear_compare_cancel(root, compare_id)
    control = CompareControl(compare_id=compare_id, root=root, skill=skill, mode=mode)
    with _LOCK:
        _CONTROLS[compare_id] = control
    return control


def get_compare_control(compare_id: str) -> CompareControl | None:
    with _LOCK:
        return _CONTROLS.get(compare_id)


def list_inflight_compares(root: Path) -> list[dict[str, Any]]:
    """In-process compares for this project root (CLI list / cancel hints)."""
    root = root.expanduser().resolve()
    rows: list[dict[str, Any]] = []
    with _LOCK:
        for control in _CONTROLS.values():
            if control.root.resolve() != root or control.cancelled():
                continue
            rows.append(
                {
                    "compare_id": control.compare_id,
                    "mode": control.mode or "models",
                    "skill": control.skill,
                    "status": "running",
                }
            )
    return rows
