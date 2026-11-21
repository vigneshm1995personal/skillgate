from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from _support import history_rows

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        shutil.which("skillgate", path=str(Path(sys.executable).parent)) is None,
        reason="skillgate entry point not installed in this venv",
    ),
]

SKILLGATE = shutil.which("skillgate", path=str(Path(sys.executable).parent))


def _env(tmp_path: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if v}
    env["SKILLGATE_ROOT"] = str(tmp_path / "ws")
    env["HOME"] = str(tmp_path / "home")
    env["CODEX_HOME"] = str(tmp_path / "codex-home")
    env["SKILLGATE_MODE"] = "local"
    env["NO_COLOR"] = "1"
    env["PATH"] = f"{Path(sys.executable).parent}{os.pathsep}/usr/bin{os.pathsep}/bin"
    Path(env["HOME"]).mkdir(parents=True, exist_ok=True)
    Path(env["CODEX_HOME"]).mkdir(parents=True, exist_ok=True)
    return env


def _run(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    ws = tmp_path / "ws"
    ws.mkdir(parents=True, exist_ok=True)
    assert SKILLGATE is not None
    return subprocess.run(
        [SKILLGATE, *args],
        env=_env(tmp_path),
        cwd=ws,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_subprocess_example_ingest_keyless_check_exits_2(tmp_path: Path) -> None:
    pack = tmp_path / "ws" / "skills" / "pdf"
    proc = _run(tmp_path, "example", "pdf", "--dest", str(pack))
    assert proc.returncode == 0, proc.stdout
    assert "Wrote" in proc.stdout
    proc = _run(tmp_path, "ingest", str(pack))
    assert proc.returncode == 0, proc.stdout
    assert "OK  pdf" in proc.stdout
    before = len(history_rows(pack))
    proc = _run(tmp_path, "check", str(pack))
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "No agent is available" in proc.stdout + proc.stderr
    assert len(history_rows(pack)) == before


def test_subprocess_check_missing_pack_exits_2(tmp_path: Path) -> None:
    proc = _run(tmp_path, "check", str(tmp_path / "ws" / "nope"))
    assert proc.returncode == 2
    assert "Not a skill pack or suite" in proc.stdout + proc.stderr


def test_subprocess_check_json_keyless_emits_error_object(tmp_path: Path) -> None:
    pack = tmp_path / "ws" / "skills" / "pdf"
    _run(tmp_path, "example", "pdf", "--dest", str(pack))
    proc = _run(tmp_path, "check", str(pack), "--json")
    assert proc.returncode == 2
    payload = json.loads(proc.stdout)
    assert payload["exit_code"] == 2
    assert "No agent is available" in payload["error"]


def test_subprocess_expect_fail_does_not_mask_exit_2(tmp_path: Path) -> None:
    pack = tmp_path / "ws" / "skills" / "pdf-sabotaged"
    _run(tmp_path, "example", "pdf-sabotaged", "--dest", str(pack))
    proc = _run(tmp_path, "check", str(pack), "--expect-fail")
    assert proc.returncode == 2
