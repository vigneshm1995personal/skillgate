from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from conftest import enable_cursor_agent, plain_text
from typer.testing import CliRunner

from skillgate_ai.cli import app
from skillgate_ai.harness import HarnessResult
from skillgate_ai.scorers import TriggerEvidence

FAKE_KEY = "sk-test-integration-not-real"
NO_TRIGGER_MARKER = "FastAPI"

PASS_ANSWERS: list[dict[str, Any]] = [
    {"name": "task_completion", "choice": "Fully completed", "confidence": 0.95},
    {"name": "correctness", "choice": "Correct", "confidence": 0.95},
    {"name": "instruction_adherence", "choice": "Fully followed", "confidence": 0.95},
    {"name": "evidence_action_validity", "choice": "Fully supported", "confidence": 0.95},
    {"name": "result_quality", "choice": "Clear and complete", "confidence": 0.95},
    {"name": "path_efficiency", "choice": "Efficient", "confidence": 0.95},
]

runner = CliRunner()


def cli(argv: list[str]) -> tuple[int, str]:
    result = runner.invoke(app, argv)
    if result.exception is not None and not isinstance(result.exception, SystemExit):
        raise result.exception
    return result.exit_code, plain_text(result.stdout + result.stderr)


def cli_json(argv: list[str]) -> tuple[int, dict[str, Any]]:
    result = runner.invoke(app, argv)
    if result.exception is not None and not isinstance(result.exception, SystemExit):
        raise result.exception
    payload: dict[str, Any] = {}
    if result.stdout.strip():
        payload = json.loads(result.stdout)
    return result.exit_code, payload


def make_workspace(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    root = tmp_path / "ws"
    root.mkdir()
    monkeypatch.setenv("SKILLGATE_ROOT", str(root))
    monkeypatch.setenv("SKILLGATE_CURSOR_SKILLS", str(tmp_path / "cursor-skills"))
    monkeypatch.setenv("SKILLGATE_CODEX_SKILLS", str(tmp_path / "codex-skills"))
    monkeypatch.setenv("SKILLGATE_CLAUDE_SKILLS", str(tmp_path / "claude-skills"))
    monkeypatch.delenv("SKILLGATE_TASK_TIMEOUT_SEC", raising=False)
    monkeypatch.delenv("SKILLGATE_HTTP_RETRY_ATTEMPTS", raising=False)
    monkeypatch.chdir(root)
    return root


def enable_live(monkeypatch: pytest.MonkeyPatch, root: Path, *, judge_key: bool = True) -> None:
    enable_cursor_agent(monkeypatch, root)
    monkeypatch.setenv("SKILLGATE_JUDGE", "openai")
    if judge_key:
        monkeypatch.setenv("SKILLGATE_OPENAI_API_KEY", FAKE_KEY)


def new_pack(root: Path, name: str = "memo") -> Path:
    code, out = cli(["new", name])
    assert code == 0, out
    return root / "skills" / name


def example_pack(root: Path, name: str = "pdf") -> Path:
    dest = root / "skills" / name
    code, out = cli(["example", name, "--dest", str(dest)])
    assert code == 0, out
    return dest


class FakeHarness:
    name = "cursor-agent"
    supported_models: tuple[str, ...] = ()

    def __init__(
        self,
        *,
        skill: str | None,
        writes: dict[str, str] | None = None,
        raises: BaseException | None = None,
    ) -> None:
        self.skill = skill
        self.writes = writes or {}
        self.raises = raises
        self.calls: list[str] = []

    def run(
        self,
        sandbox: object,
        prompt: str,
        skills: object,
        timeout_sec: int,
    ) -> HarnessResult:
        del skills, timeout_sec
        self.calls.append(prompt)
        if self.raises is not None:
            raise self.raises
        selected = None if NO_TRIGGER_MARKER in prompt else self.skill
        workspace = getattr(sandbox, "workspace", None)
        if selected is not None and workspace is not None:
            for rel, body in self.writes.items():
                path = Path(workspace) / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(body, encoding="utf-8")
        return HarnessResult(
            trigger=TriggerEvidence(selected_skill=selected),
            transcript=f"fake agent ran: {prompt}",
            returncode=0,
        )


def install_harness(monkeypatch: pytest.MonkeyPatch, harness: FakeHarness) -> None:
    monkeypatch.setattr("skillgate_ai.gate.live_harness_or_error", lambda *_a, **_k: harness)


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        payload: object,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self.text = ""

    def json(self) -> object:
        return self._payload


class DecisionAPI:
    def __init__(
        self,
        script: list[int | BaseException] | None = None,
        *,
        default: int = 200,
        error_code: str | None = None,
        retry_after: str | None = None,
    ) -> None:
        self.script = list(script or [])
        self.urls: list[str] = []
        self.default = default
        self.error_code = error_code
        self.retry_after = retry_after

    def __call__(
        self,
        url: object,
        headers: object = None,
        json: object = None,
        timeout: object = None,
    ) -> FakeResponse:
        del headers, json, timeout
        self.urls.append(str(url))
        if self.script:
            step = self.script.pop(0)
            if isinstance(step, BaseException):
                raise step
        else:
            step = self.default
        if step == 200:
            return FakeResponse(200, {"answers": PASS_ANSWERS, "model": "decision-test"})
        err: dict[str, object] = {"message": f"upstream {step} {FAKE_KEY}"}
        if self.error_code is not None:
            err["code"] = self.error_code
        hdr = {"Retry-After": self.retry_after} if self.retry_after is not None else {}
        return FakeResponse(step, {"error": err}, hdr)


def install_decision_api(monkeypatch: pytest.MonkeyPatch, api: DecisionAPI) -> DecisionAPI:
    monkeypatch.setattr("skillgate_ai.openai_http.httpx.post", api)
    return api


def history_rows(pack: Path) -> list[dict[str, Any]]:
    hist = pack / "evals" / "history"
    if not hist.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(hist.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def run_rows(pack: Path) -> list[dict[str, Any]]:
    return [row for row in history_rows(pack) if row.get("kind") == "run"]


def live_check(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    harness: FakeHarness,
    api: DecisionAPI | None = None,
) -> tuple[Path, Path, DecisionAPI]:
    root = make_workspace(monkeypatch, tmp_path)
    enable_live(monkeypatch, root)
    pack = new_pack(root)
    install_harness(monkeypatch, harness)
    installed = install_decision_api(monkeypatch, api or DecisionAPI())
    return root, pack, installed
