from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from skillgate_ai.harness import DemoHarness
from skillgate_ai.ingest import Skill
from skillgate_ai.sandbox import (
    LocalSandbox,
    _sandbox_env,
    running_python,
    with_running_python,
)


def test_with_running_python_rewrites_bare_python3() -> None:
    script = "/tmp/agent_entry.py"
    assert with_running_python(["python3", script]) == [sys.executable, script]
    assert with_running_python(["python", script]) == [sys.executable, script]
    assert with_running_python(["ls", "-l"]) == ["ls", "-l"]
    assert with_running_python([]) == []


def test_sandbox_env_puts_running_interpreter_first_on_path(tmp_path: Path) -> None:
    fake = str(tmp_path / "bin")
    env = _sandbox_env({"PATH": fake})
    first = env["PATH"].split(os.pathsep)[0]
    assert first == str(Path(running_python()).resolve().parent)
    assert fake in env["PATH"].split(os.pathsep)


def test_local_sandbox_python3_uses_running_interpreter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_py = fake_bin / "python3"
    fake_py.write_text("#!/bin/sh\necho FAKE-PYTHON\n", encoding="utf-8")
    fake_py.chmod(fake_py.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", str(fake_bin) + os.pathsep + os.environ.get("PATH", ""))
    work = tmp_path / "work"
    work.mkdir()
    sandbox = LocalSandbox(work)
    try:
        proc = sandbox.run(["python3", "-c", "import sys; print(sys.executable, end='')"])
        assert proc.returncode == 0, proc.stderr
        assert "FAKE-PYTHON" not in (proc.stdout or "")
        assert Path(proc.stdout).resolve() == Path(sys.executable).resolve()
    finally:
        sandbox.close()


def test_demo_harness_runs_bundled_script_with_running_interpreter(tmp_path: Path) -> None:
    selected = tmp_path / ".skillgate" / "skills" / "notes" / "scripts"
    selected.mkdir(parents=True)
    (selected / "agent_entry.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / ".skillgate" / "selected.json").write_text(
        '{"skill": "notes"}', encoding="utf-8"
    )
    recorded: list[list[str]] = []

    class Capture:
        workspace = tmp_path

        def run(self, command, **kwargs):
            recorded.append(list(command))
            return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    skill = Skill(
        path=tmp_path / ".skillgate" / "skills" / "notes",
        name="notes",
        description="Write notes.",
        body="",
    )
    result = DemoHarness().run(Capture(), "write notes", [skill], timeout_sec=10)
    assert recorded, result.transcript
    assert recorded[0][0] == sys.executable
    assert recorded[0][1].endswith("agent_entry.py")
    assert result.returncode == 0
