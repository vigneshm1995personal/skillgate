from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

from skillgate_ai.errors import SandboxError
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


def test_sandbox_env_allowlist_drops_github_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "gh_secret_value")
    env = _sandbox_env(None)
    assert "GITHUB_TOKEN" not in env


def test_sandbox_env_includes_extra_and_python_flags() -> None:
    env = _sandbox_env({"CUSTOM_FLAG": "1"})
    assert env["CUSTOM_FLAG"] == "1"
    assert env["PYTHONDONTWRITEBYTECODE"] == "1"
    assert env["PYTHONUNBUFFERED"] == "1"


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


def test_sandbox_runs_agent_entry_with_running_interpreter(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    script = work / "agent_entry.py"
    script.write_text("import sys; print(sys.executable, end='')\n", encoding="utf-8")
    sandbox = LocalSandbox(work)
    try:
        proc = sandbox.run(["python3", str(script)])
        assert proc.returncode == 0, proc.stderr
        assert Path(proc.stdout).resolve() == Path(sys.executable).resolve()
    finally:
        sandbox.close()


def test_docker_sandbox_fails_before_run_when_image_missing(monkeypatch) -> None:
    from skillgate_ai.sandbox import DockerSandbox

    monkeypatch.setattr("skillgate_ai.sandbox.shutil.which", lambda _name: "/usr/bin/docker")

    def fake_run(cmd, **_kwargs):
        del _kwargs
        if cmd[:3] == ["docker", "image", "inspect"] or (
            len(cmd) >= 3 and cmd[0] == "docker" and "inspect" in cmd
        ):

            class Proc:
                returncode = 1
                stdout = ""
                stderr = "Error: No such image: skillgate-sandbox:v0"

            return Proc()

        class Info:
            returncode = 0
            stdout = ""
            stderr = ""

        return Info()

    monkeypatch.setattr("skillgate_ai.sandbox.subprocess.run", fake_run)
    with pytest.raises(SandboxError, match="not installed|not found|image") as caught:
        DockerSandbox("skillgate-sandbox:v0")
    blob = f"{caught.value.message} {caught.value.hint or ''}".lower()
    assert "125" not in blob
    assert "sandbox local" in blob or "--sandbox local" in blob


def test_docker_sandbox_fails_clearly_when_daemon_down(monkeypatch) -> None:
    from skillgate_ai.sandbox import DockerSandbox

    monkeypatch.setattr("skillgate_ai.sandbox.shutil.which", lambda _name: "/usr/bin/docker")

    def fake_run(cmd, **_kwargs):
        del cmd, _kwargs

        class Proc:
            returncode = 1
            stdout = ""
            stderr = "Cannot connect to the Docker daemon. Is the docker daemon running?"

        return Proc()

    monkeypatch.setattr("skillgate_ai.sandbox.subprocess.run", fake_run)
    with pytest.raises(SandboxError, match="Docker") as caught:
        DockerSandbox("skillgate-sandbox:v0")
    blob = f"{caught.value.message} {caught.value.hint or ''}".lower()
    assert "125" not in blob
    assert "daemon" in blob or "reach docker" in blob or "start docker" in blob
