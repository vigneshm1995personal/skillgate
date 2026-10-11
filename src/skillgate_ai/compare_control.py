"""Cancel in-flight compare jobs (CLI, API, and UI share pack-local flags)."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path

from skillgate_ai.live import get_control

_LOCK = threading.Lock()
_CONTROLS: dict[str, "CompareControl"] = {}


def _cancel_path(root: Path, compare_id: str) -> Path:
    return root.expanduser().resolve() / ".skillgate" / "cancel" / compare_id


def request_cancel_compare(root: Path, compare_id: str) -> bool:
    """Signal cancel. Returns True if the compare id was known or flag was written."""
    root = root.expanduser().resolve()
    path = _cancel_path(root, compare_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("1", encoding="utf-8")
    with _LOCK:
        control = _CONTROLS.get(compare_id)
    if control is not None:
        control.request_cancel()
        return True
    return path.is_file()


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
    _event: threading.Event = field(default_factory=threading.Event)
    _current_run_id: str | None = None
    _run_lock: threading.Lock = field(default_factory=threading.Lock)

    def request_cancel(self) -> None:
        self._event.set()
        request_cancel_compare(self.root, self.compare_id)
        with self._run_lock:
            run_id = self._current_run_id
        if run_id:
            control = get_control(run_id)
            if control is not None:
                control.request_kill()

    def cancelled(self) -> bool:
        return self._event.is_set() or _cancel_path(self.root, self.compare_id).is_file()

    def set_current_run(self, run_id: str | None) -> None:
        with self._run_lock:
            self._current_run_id = run_id


def create_compare_control(root: Path, compare_id: str) -> CompareControl:
    clear_compare_cancel(root, compare_id)
    control = CompareControl(compare_id=compare_id, root=root)
    with _LOCK:
        _CONTROLS[compare_id] = control
    return control


def get_compare_control(compare_id: str) -> CompareControl | None:
    with _LOCK:
        return _CONTROLS.get(compare_id)
