"""Dogfood v6 regressions: harness env, cursor login, judge unscored, cost."""

from __future__ import annotations

from pathlib import Path

import pytest

from skillgate_ai.engine import _live_verdict
from skillgate_ai.eval_config import stamp_resolved, resolve_eval_config
from skillgate_ai.gate import run_check
from skillgate_ai.harness import (
    CodexCliHarness,
    CursorAgentHarness,
    _cursor_login_status_authenticated,
    _cursor_ready,
    harness_is_startable,
    live_harness_or_error,
)
from skillgate_ai.judge_bank import outcome_verdict
from skillgate_ai.openai_http import post_openai
from skillgate_ai.usage import combine_task_usage, estimate_usage_cost_usd, normalize_judge_api_usage
from skillgate_ai.usage import Usage
from test_judge import _cfg


def test_run_check_uses_skillgate_harness_when_cli_omits_flag(
    monkeypatch: pytest.MonkeyPatch,
    project_root: Path,
    tmp_path: Path,
) -> None:
    import shutil

    from skillgate_ai.demo_files import ensure_demo_pdfs

    dest = tmp_path / "pdf"
    shutil.copytree(project_root / "skills" / "pdf", dest)
    ensure_demo_pdfs(dest / "evals" / "fixtures")
    captured: list[str] = []

    def fake_execute(*, harness: str | None, cfg, **kwargs: object) -> object:
        captured.append((harness if harness is not None else cfg.harness_pref) or "auto")
        from skillgate_ai.gate import CheckResult

        return CheckResult(report=None, exit_code=2, error={"message": "stop"})

    monkeypatch.setattr("skillgate_ai.gate._execute_check", fake_execute)
    monkeypatch.setattr(
        "skillgate_ai.gate.get_llm_config",
        lambda _p: _cfg(harness_pref="codex"),
    )
    monkeypatch.setattr("skillgate_ai.run_lock.project_run_lock", lambda _p: _NoopLock())

    run_check(dest, harness=None, source="test", root=tmp_path)

    assert captured == ["codex"]


class _NoopLock:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *args: object) -> None:
        return None


def test_cursor_ready_without_api_key_when_cli_logged_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("skillgate_ai.harness._cursor_session_ok", lambda _c: True)
    monkeypatch.setattr("skillgate_ai.harness._resolve_agent_bin", lambda _p: "/bin/agent")
    cfg = _cfg(cursor_api_key=None)
    assert _cursor_ready(cfg)
    assert harness_is_startable(CursorAgentHarness(cfg), cfg)


def test_cursor_login_status_parser() -> None:
    assert _cursor_login_status_authenticated(0, "Logged in as user\n", "")
    assert not _cursor_login_status_authenticated(1, "Logged in", "")
    assert not _cursor_login_status_authenticated(0, "Not logged in", "")


def test_auto_includes_cursor_when_session_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("skillgate_ai.harness._resolve_agent_bin", lambda _p: "/bin/agent")
    monkeypatch.setattr("skillgate_ai.harness._cursor_session_ok", lambda _c: True)
    monkeypatch.setattr("skillgate_ai.harness._codex_ready", lambda _c: False)
    cfg = _cfg(cursor_api_key=None)
    harness = live_harness_or_error("auto", cfg)
    assert isinstance(harness, CursorAgentHarness)


def test_codex_run_keeps_login_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: dict[str, str] = {}

    class FakeSandbox:
        workspace = Path("/tmp/ws")

        def run(self, command, *, env=None, timeout=0, cwd=None):
            captured.update(env or {})
            import subprocess

            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("skillgate_ai.harness._codex_ready", lambda _c: True)
    monkeypatch.setattr("skillgate_ai.harness._resolve_codex_bin", lambda _p: "/bin/codex")
    monkeypatch.setattr(
        "skillgate_ai.harness._read_selection",
        lambda _w: "pdf",
    )
    monkeypatch.setattr("skillgate_ai.harness._parse_selected", lambda *a: "pdf")
    monkeypatch.setattr("skillgate_ai.harness._parse_read_paths", lambda _t: [])
    monkeypatch.setattr("skillgate_ai.harness._write_selection", lambda *a: None)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    monkeypatch.delenv("CODEX_HOME", raising=False)
    harness = CodexCliHarness(_cfg(codex_api_key="k"))
    harness.run(FakeSandbox(), "task", [], timeout_sec=5)
    assert "CODEX_HOME" not in captured
    assert captured["CODEX_API_KEY"] == "k"


def test_stamp_resolved_codex_default_model_label() -> None:
    cfg = _cfg(codex_model=None)
    run = stamp_resolved(
        resolve_eval_config(harness_pref="codex", incoming={}, cfg=cfg, source="cli"),
        "codex",
        cfg,
    )
    assert run.model == "gpt-5.6-luna"


def test_judge_pass_lock_partially_supported_passes_major_deviation_fails() -> None:
    base = {
        "task_completion": {"choice": "Fully completed", "confidence": 0.9},
        "correctness": {"choice": "Correct", "confidence": 0.9},
        "result_quality": {"choice": "Clear and complete", "confidence": 0.9},
        "path_efficiency": {"choice": "Efficient", "confidence": 0.9},
    }
    partial = {
        **base,
        "instruction_adherence": {"choice": "Fully followed", "confidence": 0.9},
        "evidence_action_validity": {"choice": "Partially supported", "confidence": 0.9},
    }
    passed, reasons = outcome_verdict(partial)
    assert passed is True
    assert reasons == []

    major = {
        **base,
        "instruction_adherence": {"choice": "Major deviation", "confidence": 0.9},
        "evidence_action_validity": {"choice": "Fully supported", "confidence": 0.9},
    }
    passed, reasons = outcome_verdict(major)
    assert passed is False
    assert any("Followed the rules?" in item for item in reasons)


def test_normalize_judge_api_usage_reads_top_level_completion_tokens() -> None:
    usage = normalize_judge_api_usage(
        {"usage": {"input_tokens": 500}, "completion_tokens": 25, "model": "gpt-6-luna"},
    )
    assert usage is not None
    assert usage["tokens_out"] == 25


def test_estimate_usage_cost_from_tokens() -> None:
    cost = estimate_usage_cost_usd(
        "gpt-6-luna",
        Usage(tokens_in=1_000_000, tokens_out=0),
    )
    assert cost == 0.1


def test_combine_task_usage_estimates_when_api_omits_dollars() -> None:
    merged = combine_task_usage(
        {"tokens_in": 1_000_000, "tokens_out": 0},
        {"usage": {"input_tokens": 500, "output_tokens": 25}, "model": "gpt-6-luna"},
        agent_model="codex-default",
        judge_model="gpt-6-luna",
    )
    assert merged is not None
    assert merged.get("cost_usd") is not None
    assert merged.get("tokens_out") == 25


def test_openai_retries_transient_429(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    class Resp:
        def __init__(self, status: int) -> None:
            self.status_code = status

        def json(self) -> dict:
            return {"error": {"message": "rate limit"}}

    def fake_post(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls < 3:
            return Resp(429)
        return Resp(200)

    monkeypatch.setattr("skillgate_ai.openai_http.time.sleep", lambda _s: None)
    response = post_openai(
        "https://api.openai.com/v1/decisions",
        headers={},
        payload={},
        timeout_sec=1.0,
        post=fake_post,
    )
    assert calls == 3
    assert response.status_code == 200


def test_live_verdict_judge_error_not_counted_as_pass() -> None:
    passed, failures, stamped = _live_verdict(
        {"status": "error", "reason": "HTTP 429"},
        "pdf",
        det_passed=True,
        det_failures=[],
    )
    assert passed is None
    assert stamped is not None
    assert stamped.get("quality_unscored") is True
    assert stamped.get("passed") is None
