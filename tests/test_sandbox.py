from __future__ import annotations

import os
import stat
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from skillgate_ai.errors import HarnessError, SandboxError
from skillgate_ai.live import RunControl
from skillgate_ai.sandbox import (
    _LIVE,
    LocalSandbox,
    _sandbox_env,
    running_python,
    with_running_python,
)


class _RecordingSink:
    def __init__(self) -> None:
        self.lines: list[tuple[str, str]] = []
        self.proc: subprocess.Popen[str] | None = None

    def on_line(self, stream: str, text: str) -> None:
        self.lines.append((stream, text))

    def attach_process(self, process: subprocess.Popen[str]) -> None:
        self.proc = process

    def detach_process(self) -> None:
        self.proc = None

    def should_abort(self) -> str | None:
        return None


def test_with_running_python_rewrites_bare_python3() -> None:
    script = "/tmp/agent_entry.py"
    assert with_running_python(["python3", script]) == [sys.executable, script]
    assert with_running_python(["python", script]) == [sys.executable, script]
    assert with_running_python(["ls", "-l"]) == ["ls", "-l"]
    assert with_running_python([]) == []


def test_sandbox_env_allowlist_drops_unlisted_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FOO_TOKEN", "not-for-sandbox")
    env = _sandbox_env(None)
    assert "FOO_TOKEN" not in env


@pytest.mark.parametrize(
    "name,value",
    [
        ("CODEX_HOME", "/tmp/codex-home"),
        ("CLAUDE_CONFIG_DIR", "/tmp/claude-config"),
        ("HTTP_PROXY", "http://127.0.0.1:8080"),
        ("HTTPS_PROXY", "https://127.0.0.1:8443"),
        ("NO_PROXY", "localhost"),
        ("http_proxy", "http://127.0.0.1:8080"),
        ("https_proxy", "https://127.0.0.1:8443"),
        ("no_proxy", "localhost"),
        ("SSL_CERT_FILE", "/etc/ssl/cert.pem"),
        ("SSL_CERT_DIR", "/etc/ssl/certs"),
        ("REQUESTS_CA_BUNDLE", "/etc/ssl/ca-bundle.crt"),
    ],
)
def test_sandbox_env_allowlist_passes_harness_vars(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)
    env = _sandbox_env(None)
    assert env.get(name) == value


def test_sandbox_child_inherits_codex_home_from_pytest_isolation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """conftest ``_isolate_codex_home`` must survive the sandbox allowlist."""
    isolated = str(tmp_path / "pytest-codex-home")
    monkeypatch.setenv("CODEX_HOME", isolated)
    work = tmp_path / "work"
    work.mkdir()
    sandbox = LocalSandbox(work)
    try:
        proc = sandbox.run(
            [
                sys.executable,
                "-c",
                "import os; print(os.environ.get('CODEX_HOME', ''), end='')",
            ],
        )
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout == isolated
    finally:
        sandbox.close()


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


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX sessions")
def test_streaming_child_runs_in_new_session(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    sandbox = LocalSandbox(work)
    sandbox.output_sink = _RecordingSink()
    try:
        proc = sandbox.run(
            [
                sys.executable,
                "-c",
                "import os; print(os.getsid(0), os.getpgrp(), os.getpid())",
            ],
        )
        sid, pgrp, child_pid = map(int, proc.stdout.strip().split())
        assert sid == pgrp == child_pid
        assert sid != os.getsid(0)
        assert pgrp != os.getpgrp()
    finally:
        sandbox.close()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX sessions")
def test_streaming_child_stdin_is_devnull(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    sandbox = LocalSandbox(work)
    sandbox.output_sink = _RecordingSink()
    try:
        proc = sandbox.run(
            [sys.executable, "-c", "import sys; print(repr(sys.stdin.read()))"],
        )
        assert proc.stdout.strip() == "''"
    finally:
        sandbox.close()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX sessions")
def test_nonstreaming_child_stays_in_caller_group(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    sandbox = LocalSandbox(work)
    try:
        proc = sandbox.run(
            [
                sys.executable,
                "-c",
                "import os; print(os.getsid(0), os.getpgrp(), os.getpid())",
            ],
        )
        _, pgrp, _ = map(int, proc.stdout.strip().split())
        assert pgrp == os.getpgrp()
    finally:
        sandbox.close()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX sessions")
def test_streaming_child_group_signal_cannot_reach_parent(tmp_path: Path) -> None:
    wrapper = textwrap.dedent(
        f"""
        import os, sys, signal
        from pathlib import Path
        from skillgate_ai.sandbox import LocalSandbox

        class _Sink:
            def on_line(self, *_a): pass
            def attach_process(self, *_a): pass
            def detach_process(self): pass
            def should_abort(self): return None

        work = Path({str(tmp_path)!r}) / "inner"
        work.mkdir(exist_ok=True)
        sandbox = LocalSandbox(work)
        sandbox.output_sink = _Sink()
        try:
            sandbox.run(
                [{sys.executable!r}, "-c",
                 "import os, signal, time; "
                 "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                 "os.killpg(0, signal.SIGTERM); print('sent')"],
                timeout=5,
            )
        finally:
            sandbox.close()
        print("survived", flush=True)
        """
    )
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
    proc = subprocess.run(
        [sys.executable, "-c", wrapper],
        capture_output=True,
        text=True,
        env=env,
        timeout=15,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "survived" in proc.stdout


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX sessions")
def test_streaming_timeout_kills_process_group(tmp_path: Path) -> None:
    pid_file = tmp_path / "gc.pid"
    work = tmp_path / "work"
    work.mkdir()
    sandbox = LocalSandbox(work)
    sink = _RecordingSink()
    sandbox.output_sink = sink
    pid_path = str(pid_file)
    script = textwrap.dedent(
        f"""
        import os, sys, time
        from subprocess import Popen
        gp = Popen([sys.executable, "-c", "import time; time.sleep(120)"])
        open({pid_path!r}, "w").write(str(gp.pid))
        time.sleep(120)
        """
    )
    try:
        with pytest.raises(HarnessError):
            sandbox.run([sys.executable, "-c", script], timeout=1)
    finally:
        sandbox.close()
    grandchild_pid = int(pid_file.read_text())
    gone = False
    for _ in range(30):
        try:
            os.kill(grandchild_pid, 0)
        except ProcessLookupError:
            gone = True
            break
        time.sleep(0.1)
    assert gone


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX sessions")
def test_run_control_kill_terminates_process_group(tmp_path: Path) -> None:
    pid_file = tmp_path / "gc.pid"
    work = tmp_path / "work"
    work.mkdir()
    sandbox = LocalSandbox(work)
    control = RunControl("t")
    control.begin_task("x")
    sandbox.output_sink = control
    pid_path = str(pid_file)
    script = textwrap.dedent(
        f"""
        import os, sys, time
        from subprocess import Popen
        gp = Popen([sys.executable, "-c", "import time; time.sleep(120)"])
        open({pid_path!r}, "w").write(str(gp.pid))
        time.sleep(120)
        """
    )

    import threading

    err: list[BaseException] = []

    def run() -> None:
        try:
            sandbox.run([sys.executable, "-c", script], timeout=120)
        except BaseException as exc:  # noqa: BLE001
            err.append(exc)

    thread = threading.Thread(target=run)
    thread.start()
    deadline = time.monotonic() + 5.0
    while not pid_file.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert pid_file.exists()
    control.request_kill()
    thread.join(timeout=5.0)
    sandbox.close()
    grandchild_pid = int(pid_file.read_text())
    gone = False
    for _ in range(30):
        try:
            os.kill(grandchild_pid, 0)
        except ProcessLookupError:
            gone = True
            break
        time.sleep(0.1)
    assert gone


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX sessions")
def test_streaming_registers_and_clears_live_group(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()

    class _LiveSink(_RecordingSink):
        def attach_process(self, process: subprocess.Popen[str]) -> None:
            super().attach_process(process)
            assert process in _LIVE

    sandbox = LocalSandbox(work)
    sandbox.output_sink = _LiveSink()
    try:
        sandbox.run([sys.executable, "-c", "print('hi')"], timeout=5)
        assert not _LIVE
    finally:
        sandbox.close()
