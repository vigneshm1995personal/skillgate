"""One check at a time per project. File lock so CLI and the local UI share it."""

from __future__ import annotations

from pathlib import Path
from types import TracebackType
from typing import TextIO

from skillgate_ai.errors import SkillGateError

try:
    import fcntl
except ImportError:  # Windows: skip exclusive lock; still refuse a second check in-process via UI.
    fcntl = None

BUSY_MESSAGE = "A check is already running."
BUSY_HINT = "Wait for it to finish, or stop it first."


class project_run_lock:
    """Exclusive flock on ``{root}/.skillgate/run.lock``.

    If the folder is not writable (Docker ``:ro`` /pack, or a non-root image
    cwd), the lock is skipped so ``check`` can still exit 0/1/2.
    """

    def __init__(self, root: str | Path) -> None:
        self.path = Path(root).expanduser().resolve() / ".skillgate" / "run.lock"
        self._fd: TextIO | None = None

    def __enter__(self) -> project_run_lock:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            handle = open(self.path, "a+", encoding="utf-8")
        except OSError:
            return self
        if fcntl is None:
            self._fd = handle
            return self
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close()
            raise SkillGateError(BUSY_MESSAGE, hint=BUSY_HINT) from None
        except OSError:
            handle.close()
            return self
        self._fd = handle
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        del exc_type, exc, tb
        handle = self._fd
        self._fd = None
        if handle is None:
            return
        if fcntl is not None:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        handle.close()
