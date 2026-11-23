from __future__ import annotations

import shutil
import sys
import threading
from pathlib import Path

import pytest

from skillgate_ai.demo_files import ensure_demo_pdfs
from skillgate_ai.engine import SuiteReport, TaskReport
from skillgate_ai.errors import SkillGateError
from skillgate_ai.live import reset_controls
from skillgate_ai.run_registry import RunBusyError, RunRegistry, RunRequest, resolve_harness
from skillgate_ai.scorers import Score

ROOT = Path(__file__).resolve().parents[1]

UI_SEED_KEYS = [
    "id",
    "status",
    "passed",
    "gate",
    "gate_decision",
    "skill",
    "skill_path",
    "harness",
    "tryout",
    "completed_count",
    "task_count",
    "current_task_id",
    "error",
    "report",
    "config",
    "model",
    "timeout_sec",
    "temperature",
    "reasoning_effort",
]


@pytest.fixture(autouse=True)
def _reset_live() -> None:
    reset_controls()


def _pdf_pack(tmp_path: Path) -> Path:
    dest = tmp_path / "skills" / "pdf"
    shutil.copytree(ROOT / "skills" / "pdf", dest)
    ensure_demo_pdfs(dest / "evals" / "fixtures")
    return dest


def _fake_suite(dest: Path) -> SuiteReport:
    task = TaskReport(
        task_id="should-trigger-1",
        prompt="demo",
        expect_skill="pdf",
        passed=True,
        scores=[
            Score(
                scorer="skill_trigger",
                passed=True,
                detail="Triggered `pdf`",
                expected="pdf",
                actual="pdf",
            )
        ],
        selected_skill="pdf",
        judge={"status": "skip", "provider": "skip", "passed": None},
    )
    return SuiteReport(
        suite="pdf-pack",
        title="Dataset",
        skill="pdf",
        harness="cursor-agent",
        sandbox="local",
        passed=True,
        tasks=[task],
        skill_path=str(dest),
        config={"judge": {"provider": "skip", "display_name": "Checks"}},
    )


def test_start_returns_id_and_running_seed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from conftest import enable_cursor_agent

    enable_cursor_agent(monkeypatch, tmp_path)
    pack = _pdf_pack(tmp_path)
    monkeypatch.setattr("skillgate_ai.gate.live_harness_or_error", lambda *_a, **_k: object())
    monkeypatch.setattr(
        "skillgate_ai.gate.run_eval",
        lambda *_a, **_k: _fake_suite(pack),
    )
    reg = RunRegistry(tmp_path)
    out = reg.start(
        RunRequest(skill_path=pack, source="test", no_judge=True),
    )
    assert out["status"] == "running"
    assert len(out["id"]) == 12
    reg.join(out["id"], timeout=30.0)


def test_seed_record_keys_match_ui_seed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from conftest import enable_cursor_agent

    enable_cursor_agent(monkeypatch, tmp_path)
    pack = _pdf_pack(tmp_path)
    monkeypatch.setattr("skillgate_ai.gate.run_eval", lambda *_a, **_k: _fake_suite(pack))
    reg = RunRegistry(tmp_path)
    out = reg.start(RunRequest(skill_path=pack, no_judge=True))
    record = reg.get(out["id"])
    assert record is not None
    assert list(record.keys()) == UI_SEED_KEYS
    reg.join(out["id"], timeout=30.0)


def test_worker_finishes_done_with_mocked_run_eval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from conftest import enable_cursor_agent

    enable_cursor_agent(monkeypatch, tmp_path)
    pack = _pdf_pack(tmp_path)
    monkeypatch.setattr("skillgate_ai.gate.run_eval", lambda *_a, **_k: _fake_suite(pack))
    reg = RunRegistry(tmp_path)
    run_id = reg.start(RunRequest(skill_path=pack, no_judge=True))["id"]
    assert reg.join(run_id, timeout=30.0)
    done = reg.get(run_id)
    assert done is not None
    assert done["status"] == "done"
    assert done["passed"] is True


def test_worker_records_error_on_exception(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from conftest import enable_cursor_agent

    enable_cursor_agent(monkeypatch, tmp_path)
    pack = _pdf_pack(tmp_path)

    def boom(*_a, **_k):
        raise SkillGateError("worker boom")

    monkeypatch.setattr("skillgate_ai.run_registry.run_check", boom)
    reg = RunRegistry(tmp_path)
    run_id = reg.start(RunRequest(skill_path=pack))["id"]
    assert reg.join(run_id, timeout=30.0)
    record = reg.get(run_id)
    assert record is not None
    assert record["status"] == "error"
    assert record["error"]["message"] == "worker boom"


def test_busy_raises_run_busy_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from conftest import enable_cursor_agent

    enable_cursor_agent(monkeypatch, tmp_path)
    pack = _pdf_pack(tmp_path)
    reg = RunRegistry(tmp_path)
    reg.runs["stuck"] = {"id": "stuck", "status": "running"}
    with pytest.raises(RunBusyError):
        reg.start(RunRequest(skill_path=pack))


def test_injected_busy_predicate_is_used(tmp_path: Path) -> None:
    pack = _pdf_pack(tmp_path)
    flag = {"busy": True}

    def busy() -> bool:
        return flag["busy"]

    reg = RunRegistry(tmp_path, busy=busy)
    with pytest.raises(RunBusyError):
        reg.start(RunRequest(skill_path=pack))
    flag["busy"] = False


def test_injected_shared_lock_does_not_deadlock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from conftest import enable_cursor_agent

    enable_cursor_agent(monkeypatch, tmp_path)
    pack = _pdf_pack(tmp_path)
    lock = threading.Lock()
    monkeypatch.setattr(
        "skillgate_ai.gate.run_eval",
        lambda *_a, **_k: _fake_suite(pack),
    )

    def busy() -> bool:
        with lock:
            return False

    reg = RunRegistry(tmp_path, lock=lock, busy=busy)
    run_id = reg.start(RunRequest(skill_path=pack, no_judge=True))["id"]
    assert reg.join(run_id, timeout=30.0)


def test_kill_and_skip_return_false_for_unknown_run() -> None:
    reg = RunRegistry(Path("/tmp"))
    assert reg.kill("nope") is False
    assert reg.skip("nope") is False


def test_kill_requests_control_on_live_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from conftest import enable_cursor_agent

    from skillgate_ai.live import get_control

    enable_cursor_agent(monkeypatch, tmp_path)
    pack = _pdf_pack(tmp_path)
    event = threading.Event()

    def slow_eval(*_a, **_k):
        event.wait(timeout=30.0)
        return _fake_suite(pack)

    monkeypatch.setattr("skillgate_ai.gate.run_eval", slow_eval)
    reg = RunRegistry(tmp_path)
    run_id = reg.start(RunRequest(skill_path=pack, no_judge=True))["id"]
    assert reg.kill(run_id) is True
    control = get_control(run_id)
    assert control is not None
    event.set()
    reg.join(run_id, timeout=30.0)


def test_get_returns_deep_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from conftest import enable_cursor_agent

    enable_cursor_agent(monkeypatch, tmp_path)
    pack = _pdf_pack(tmp_path)
    reg = RunRegistry(tmp_path)
    run_id = reg.start(RunRequest(skill_path=pack))["id"]
    a = reg.get(run_id)
    b = reg.get(run_id)
    assert a is not None and b is not None
    assert a == b
    a["status"] = "mutated"
    c = reg.get(run_id)
    assert c is not None
    assert c["status"] == "running"


def test_resolve_harness_pref_wins_over_requested() -> None:
    assert resolve_harness({"harness_pref": "codex"}, "claude") == "codex"
    assert resolve_harness({}, "claude") == "claude"
    assert resolve_harness({}, "") == "auto"


def test_registry_imports_without_fastapi(tmp_path: Path) -> None:
    import subprocess

    code = (
        "import sys\n"
        "class B:\n"
        "    def find_spec(self, n, p=None, t=None):\n"
        "        if n == 'fastapi' or n.startswith('fastapi.'):\n"
        "            raise ModuleNotFoundError('blocked')\n"
        "        return None\n"
        "sys.meta_path.insert(0, B())\n"
        "import skillgate_ai.run_registry as rr\n"
        "print('ok' if hasattr(rr, 'RunRegistry') else 'no')\n"
    )
    import os
    import site

    py_path = os.pathsep.join([str(ROOT / "src"), site.getusersitepackages()])
    env = {**os.environ, "PYTHONPATH": py_path}
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert "ok" in proc.stdout
