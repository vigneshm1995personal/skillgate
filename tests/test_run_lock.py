"""Run-lock behaviour (ported from QA dumps)."""

from __future__ import annotations

from pathlib import Path

import pytest

def test_run_lock_unwritable_is_not_fatal(tmp_path: Path, monkeypatch) -> None:
    from skillgate_ai.run_lock import project_run_lock

    lock = project_run_lock(tmp_path)

    def boom(*_args, **_kwargs):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr("builtins.open", boom)
    with lock:
        pass


def test_cli_one_run_at_a_time(tmp_path: Path) -> None:
    import subprocess
    import sys
    import textwrap

    from skillgate_ai.run_lock import project_run_lock

    with project_run_lock(tmp_path):
        code = textwrap.dedent(
            f"""
            from pathlib import Path
            from skillgate_ai.errors import SkillGateError
            from skillgate_ai.run_lock import project_run_lock
            try:
                with project_run_lock(Path({str(tmp_path)!r})):
                    print("GOT")
            except SkillGateError as exc:
                print(exc.message)
                raise SystemExit(2)
            """
        )
        proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            check=False,
        )
        blob = proc.stdout + proc.stderr
        assert proc.returncode == 2, blob
        assert "already running" in blob.lower()


def test_already_running_check_exits_2(tmp_path: Path) -> None:
    from skillgate_ai.errors import SkillGateError
    from skillgate_ai.run_lock import BUSY_MESSAGE, project_run_lock

    with (
        project_run_lock(tmp_path),
        pytest.raises(SkillGateError) as caught,
        project_run_lock(tmp_path),
    ):
        raise AssertionError("second check should not start")
    assert caught.value.message == BUSY_MESSAGE
    assert caught.value.exit_code == 2
