"""Spawn flags for external CLI children: no inherited stdin, own session.

Under `skillgate mcp`, fd 0/1 are the JSON-RPC pipes. A child that inherits
fd 0 can steal requests or flip O_NONBLOCK on the shared pipe; a child in our
process group can signal the server. Every harness / probe spawn uses these.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
from typing import Any

POSIX = sys.platform != "win32"


def isolated_kwargs() -> dict[str, Any]:
    """stdin=DEVNULL, close_fds, and (POSIX) a new session / process group."""
    kwargs: dict[str, Any] = {"stdin": subprocess.DEVNULL, "close_fds": True}
    if POSIX:
        kwargs["start_new_session"] = True
    return kwargs


def signal_group(proc: subprocess.Popen[Any], sig: int) -> None:
    """Signal the child's whole group (it is a session leader); fall back to the pid."""
    if proc.poll() is not None:
        return
    if POSIX:
        try:
            os.killpg(proc.pid, sig)
            return
        except (ProcessLookupError, PermissionError, OSError):
            pass
    with contextlib.suppress(ProcessLookupError, OSError):
        proc.send_signal(sig)


def kill_group(proc: subprocess.Popen[Any]) -> None:
    signal_group(proc, signal.SIGKILL if POSIX else signal.SIGTERM)
