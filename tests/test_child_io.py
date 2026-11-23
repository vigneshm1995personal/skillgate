from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from skillgate_ai.child_io import isolated_kwargs, kill_group

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX sessions")


def test_isolated_kwargs_posix() -> None:
    assert isolated_kwargs() == {
        "stdin": subprocess.DEVNULL,
        "close_fds": True,
        "start_new_session": True,
    }


def test_signal_group_kills_grandchild(tmp_path: Path) -> None:
    pid_file = tmp_path / "gc.pid"
    pid_path = str(pid_file)
    script = f"""
import os, time, sys
from subprocess import Popen
gp = Popen([sys.executable, "-c", "import time; time.sleep(120)"])
open({pid_path!r}, "w").write(str(gp.pid))
time.sleep(120)
"""
    proc = subprocess.Popen(
        [sys.executable, "-c", script],
        **isolated_kwargs(),
    )
    deadline = time.monotonic() + 5.0
    while not pid_file.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert pid_file.exists(), "grandchild pid file not written"
    grandchild_pid = int(pid_file.read_text())
    kill_group(proc)
    assert proc.wait(5) is not None
    gone = False
    for _ in range(30):
        try:
            os.kill(grandchild_pid, 0)
        except ProcessLookupError:
            gone = True
            break
        time.sleep(0.1)
    assert gone, "grandchild still alive after kill_group"


def test_signal_group_noop_after_exit() -> None:
    proc = subprocess.Popen([sys.executable, "-c", "pass"], **isolated_kwargs())
    proc.wait()
    kill_group(proc)
