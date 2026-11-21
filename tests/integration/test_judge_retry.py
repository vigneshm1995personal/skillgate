from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from _support import (
    FAKE_KEY,
    DecisionAPI,
    FakeHarness,
    cli,
    history_rows,
    live_check,
    run_rows,
)

pytestmark = pytest.mark.integration


def test_judge_503_then_200_is_retried_and_green(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = FakeHarness(skill="memo")
    _root, pack, api = live_check(monkeypatch, tmp_path, harness, DecisionAPI([503]))
    code, out = cli(["check", str(pack)])
    assert code == 0, out
    assert len(api.urls) == 2
    assert "GREEN" in out
    assert len(harness.calls) == 2
    assert FAKE_KEY not in out
    assert FAKE_KEY not in json.dumps(history_rows(pack))


def test_judge_429_honors_retry_after(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr("skillgate_ai.http_retry.sleep", sleeps.append)
    harness = FakeHarness(skill="memo")
    _root, pack, api = live_check(
        monkeypatch, tmp_path, harness, DecisionAPI([429], retry_after="0")
    )
    code, _out = cli(["check", str(pack)])
    assert code == 0
    assert len(api.urls) == 2
    assert sleeps == [0.0]


def test_judge_transport_error_then_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = FakeHarness(skill="memo")
    _root, pack, api = live_check(
        monkeypatch, tmp_path, harness, DecisionAPI([httpx.ConnectError("boom")])
    )
    code, _out = cli(["check", str(pack)])
    assert code == 0
    assert len(api.urls) == 2


def test_judge_503_exhausted_exit_2_not_scored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = FakeHarness(skill="memo")
    _root, pack, api = live_check(monkeypatch, tmp_path, harness, DecisionAPI(default=503))
    monkeypatch.setenv("SKILLGATE_HTTP_RETRY_ATTEMPTS", "3")
    code, out = cli(["check", str(pack)])
    assert code == 2, out
    assert len(api.urls) == 3
    assert "NOT SCORED  should-trigger-1" in out
    assert run_rows(pack)[-1]["passed"] is None


def test_judge_401_is_not_retried_exit_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    harness = FakeHarness(skill="memo")
    _root, pack, api = live_check(monkeypatch, tmp_path, harness, DecisionAPI(default=401))
    code, _out = cli(["check", str(pack)])
    assert code == 2
    assert len(api.urls) == 1


def test_judge_quota_429_is_not_retried_exit_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = FakeHarness(skill="memo")
    _root, pack, api = live_check(
        monkeypatch, tmp_path, harness, DecisionAPI(default=429, error_code="insufficient_quota")
    )
    code, _out = cli(["check", str(pack)])
    assert code == 2
    assert len(api.urls) == 1
