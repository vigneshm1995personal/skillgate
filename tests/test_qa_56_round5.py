"""QA round 5: F10 agent timeout is cannot-run, never dumps the prompt."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from test_judge import _cfg
from typer.testing import CliRunner

from skillgate_ai.cli import app
from skillgate_ai.errors import HarnessError
from skillgate_ai.gate import CheckResult
from skillgate_ai.harness import CursorAgentHarness
from skillgate_ai.sandbox import LocalSandbox

ROOT = Path(__file__).resolve().parents[1]
PROMPT_LEAK = "SECRET_AGENT_PROMPT_SHOULD_NOT_LEAK"
runner = CliRunner()


@pytest.fixture(autouse=True)
def _never_touch_real_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    monkeypatch.chdir(tmp_path)


class _Sink:
    def on_line(self, stream: str, text: str) -> None:
        del stream, text

    def attach_process(self, process: object) -> None:
        del process

    def detach_process(self) -> None:
        return None

    def should_abort(self) -> str | None:
        return None


def test_agent_timeout_error_is_cannot_run() -> None:
    from skillgate_ai.errors import AGENT_TIMEOUT_MESSAGE, agent_timeout_error

    err = agent_timeout_error(300)
    assert err.exit_code == 2
    assert err.message == AGENT_TIMEOUT_MESSAGE
    assert "cannot run" in err.message.lower()
    assert "300" in (err.hint or "")
    blob = err.render()
    assert PROMPT_LEAK not in blob
    assert "the agent timed out" in blob.lower()


def test_local_sandbox_timeout_is_cannot_run(tmp_path: Path) -> None:
    work = tmp_path / "ws"
    work.mkdir()
    sandbox = LocalSandbox(work)
    try:
        with pytest.raises(HarnessError) as caught:
            sandbox.run(
                ["python3", "-c", f"import time; time.sleep(5); print({PROMPT_LEAK!r})"],
                timeout=1,
            )
    finally:
        sandbox.close()
    err = caught.value
    assert err.exit_code == 2
    assert "cannot run" in err.message.lower()
    assert "timed out" in err.message.lower()
    blob = f"{err.message}\n{err.hint or ''}\n{err!s}"
    assert PROMPT_LEAK not in blob
    assert "time.sleep" not in blob
    assert "python3" not in blob


def test_streaming_sandbox_timeout_is_cannot_run(tmp_path: Path) -> None:
    work = tmp_path / "ws"
    work.mkdir()
    sandbox = LocalSandbox(work)
    sandbox.output_sink = _Sink()
    try:
        with pytest.raises(HarnessError) as caught:
            sandbox.run(
                ["python3", "-c", f"import time; time.sleep(5); print({PROMPT_LEAK!r})"],
                timeout=1,
            )
    finally:
        sandbox.close()
    err = caught.value
    assert err.exit_code == 2
    assert PROMPT_LEAK not in err.render()


def test_harness_timeout_never_prints_the_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _Sandbox:
        def __init__(self, workspace: Path) -> None:
            self.workspace = workspace

        def run(self, command, *, env=None, timeout=0, cwd=None):
            del env, cwd
            raise subprocess.TimeoutExpired(cmd=list(command) + [PROMPT_LEAK], timeout=timeout)

    monkeypatch.setattr("skillgate_ai.harness._cursor_ready", lambda _c: True)
    monkeypatch.setattr("skillgate_ai.harness._resolve_agent_bin", lambda _p: "/bin/agent")
    workspace = tmp_path / "ws"
    workspace.mkdir()
    with pytest.raises(HarnessError) as caught:
        CursorAgentHarness(_cfg(cursor_api_key="cur-test")).run(
            _Sandbox(workspace),  # type: ignore[arg-type]
            PROMPT_LEAK,
            [],
            timeout_sec=300,
        )
    err = caught.value
    assert err.exit_code == 2
    assert "cannot run" in err.message.lower()
    blob = err.render()
    assert PROMPT_LEAK not in blob
    assert "-p" not in blob


def test_check_timeout_json_is_valid_exit_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dest = tmp_path / "pack"
    dest.mkdir()
    (dest / "SKILL.md").write_text("---\nname: pack\n---\n", encoding="utf-8")

    def boom(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd=["agent", "-p", PROMPT_LEAK], timeout=300)

    monkeypatch.setattr("skillgate_ai.cli.run_check", boom)
    result = runner.invoke(app, ["check", str(dest), "--json"])
    out = result.stdout + result.stderr
    assert result.exit_code == 2, out
    payload = json.loads(result.stdout)
    assert payload["exit_code"] == 2
    assert "cannot run" in str(payload.get("error") or "").lower()
    assert "timed out" in str(payload.get("error") or "").lower()
    assert PROMPT_LEAK not in out
    assert result.exception is None or not isinstance(result.exception, subprocess.TimeoutExpired)


def test_run_check_timeout_is_check_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = tmp_path / "pack"
    dest.mkdir()
    (dest / "SKILL.md").write_text("---\nname: pack\n---\n", encoding="utf-8")

    def boom(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd=["agent", "-p", PROMPT_LEAK], timeout=300)

    monkeypatch.setattr("skillgate_ai.cli.run_check", boom)
    result = runner.invoke(app, ["check", str(dest)])
    out = result.stdout + result.stderr
    assert result.exit_code == 2, out
    assert "cannot run" in out.lower()
    assert PROMPT_LEAK not in out


def test_gate_timeout_becomes_cannot_run_result() -> None:
    from skillgate_ai.errors import agent_timeout_error

    err = agent_timeout_error(300)
    result = CheckResult(
        report=None,
        exit_code=err.exit_code,
        error={"message": err.message, "hint": err.hint},
    )
    payload = {"error": result.error["message"], "hint": result.error.get("hint"), "exit_code": result.exit_code}
    dumped = json.dumps(payload)
    assert json.loads(dumped)["exit_code"] == 2
    assert PROMPT_LEAK not in dumped


def test_subprocess_timeouts_are_caught() -> None:
    missing: list[str] = []
    for path in (ROOT / "src" / "skillgate_ai").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "subprocess." not in text:
            continue
        if "timeout=" not in text and "timeout =" not in text:
            continue
        if "TimeoutExpired" not in text:
            missing.append(str(path.relative_to(ROOT)))
    assert missing == []
