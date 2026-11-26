from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from _support import (
    FAKE_KEY,
    DecisionAPI,
    FakeHarness,
    cli,
    cli_json,
    enable_live,
    example_pack,
    history_rows,
    install_decision_api,
    install_harness,
    live_check,
    make_workspace,
    new_pack,
    run_rows,
)

from skillgate_ai.errors import HarnessError

pytestmark = pytest.mark.integration


def test_check_green_exit_0_writes_history(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    harness = FakeHarness(skill="memo")
    root, pack, api = live_check(monkeypatch, tmp_path, harness)
    code, out = cli(["check", str(pack)])
    assert code == 0, out
    assert "GREEN" in out
    assert "PASS  should-trigger-1" in out
    assert "PASS  no-trigger-unrelated" in out
    assert len(harness.calls) == 2
    assert len(api.urls) == 1
    assert api.urls[0].endswith("/decisions")
    rows = run_rows(pack)
    assert len(rows) == 1
    assert rows[0]["passed"] is True
    assert rows[0]["gate"] == "green"
    assert rows[0]["run_id"]
    task_ids = [t["id"] for t in rows[0]["report"]["tasks"]]
    assert task_ids == ["should-trigger-1", "no-trigger-unrelated"]
    assert FAKE_KEY not in json.dumps(history_rows(pack))
    del root


def test_check_red_when_skill_not_triggered_exit_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = FakeHarness(skill=None)
    _root, pack, _api = live_check(monkeypatch, tmp_path, harness)
    code, out = cli(["check", str(pack)])
    assert code == 1, out
    assert "RED" in out
    assert "FAIL  should-trigger-1" in out
    assert "PASS  no-trigger-unrelated" in out
    row = run_rows(pack)[-1]
    assert row["passed"] is False
    assert row["gate"] == "red"
    assert FAKE_KEY not in out


def test_check_json_payload_matches_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = FakeHarness(skill="memo")
    _root, pack, _api = live_check(monkeypatch, tmp_path, harness)
    code, payload = cli_json(["check", str(pack), "--json"])
    assert code == 0
    assert payload["passed"] is True
    assert payload["gate"] == "green"
    assert payload["task_count"] == 2
    assert payload["harness"] == "cursor-agent"
    assert payload["failed_task_ids"] == []
    assert run_rows(pack)[-1]["report"]["passed"] is True


def test_check_expect_fail_red_suite_exits_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = FakeHarness(skill=None)
    _root, pack, _api = live_check(monkeypatch, tmp_path, harness)
    code, out = cli(["check", str(pack), "--expect-fail"])
    assert code == 0, out
    assert "Suite failed as expected (intentional fail)." in out


def test_check_expect_fail_green_suite_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = FakeHarness(skill="memo")
    _root, pack, _api = live_check(monkeypatch, tmp_path, harness)
    code, out = cli(["check", str(pack), "--expect-fail"])
    assert code == 1, out
    assert "Expected this suite to fail, but the gate was green." in out


def test_check_records_workspace_outputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    harness = FakeHarness(
        skill="memo",
        writes={"output/notes.md": "# Notes\nhello integration\n"},
    )
    _root, pack, _api = live_check(monkeypatch, tmp_path, harness)
    code, payload = cli_json(["check", str(pack), "--json"])
    assert code == 0
    task = payload["tasks"][0]
    assert task["id"] == "should-trigger-1"
    row = next(o for o in task["outputs"] if o["path"] == "output/notes.md")
    assert "hello integration" in str(row.get("body"))
    hist_row = run_rows(pack)[-1]["report"]["tasks"][0]["outputs"]
    assert any(o["path"] == "output/notes.md" for o in hist_row)
    assert not (pack / "output").exists()


@pytest.mark.parametrize(
    ("exit_code", "passed", "gate"),
    [(1, False, "red"), (2, None, None)],
)
def test_check_harness_error_is_not_retried(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    exit_code: int,
    passed: bool | None,
    gate: str | None,
) -> None:
    harness = FakeHarness(
        skill="memo",
        raises=HarnessError("agent crashed", exit_code=exit_code),
    )
    _root, pack, api = live_check(monkeypatch, tmp_path, harness)
    code, out = cli(["check", str(pack)])
    assert code == exit_code, out
    assert "agent crashed" in out
    assert len(harness.calls) == 1
    assert api.urls == []
    row = run_rows(pack)[-1]
    assert row["passed"] is passed
    assert row["gate"] == gate
    assert row["error"]["message"] == "agent crashed"


def test_check_agent_timeout_exit_2_hides_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = FakeHarness(
        skill="memo",
        raises=subprocess.TimeoutExpired(["agent", "SECRET-PROMPT-XYZ"], 5),
    )
    _root, pack, _api = live_check(monkeypatch, tmp_path, harness)
    code, out = cli(["check", str(pack)])
    assert code == 2, out
    assert "The agent timed out." in out
    assert "SECRET-PROMPT-XYZ" not in out
    assert run_rows(pack)[-1]["passed"] is None


def test_check_keyless_exit_2_writes_no_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_workspace(monkeypatch, tmp_path)
    pack = new_pack(root)
    code, out = cli(["check", str(pack)])
    assert code == 2, out
    assert "No agent is available" in out
    assert history_rows(pack) == []


def test_check_missing_judge_key_exit_2_agent_never_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_workspace(monkeypatch, tmp_path)
    enable_live(monkeypatch, root, judge_key=False)
    pack = new_pack(root)
    harness = FakeHarness(skill="memo", raises=AssertionError("must not run"))
    install_harness(monkeypatch, harness)
    api = install_decision_api(monkeypatch, DecisionAPI())
    code, out = cli(["check", str(pack)])
    assert code == 2, out
    assert "API key" in out
    assert harness.calls == []
    assert api.urls == []
    assert history_rows(pack) == []


def test_check_no_judge_flag_skips_decision_api_exit_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = FakeHarness(skill="memo")
    _root, pack, api = live_check(monkeypatch, tmp_path, harness)
    code, _out = cli(["check", str(pack), "--no-judge"])
    assert code == 0
    assert api.urls == []


def test_check_single_case_tryout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    harness = FakeHarness(skill="memo")
    _root, pack, _api = live_check(monkeypatch, tmp_path, harness)
    code, _out = cli(["check", str(pack), "--case", "should-trigger-1"])
    assert code == 0
    assert len(harness.calls) == 1
    assert run_rows(pack)[-1]["tryout"] is True


def test_run_command_mirrors_check(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    harness = FakeHarness(skill="memo")
    _root, pack, _api = live_check(monkeypatch, tmp_path, harness)
    code, out = cli(["run", str(pack)])
    assert code == 0, out
    assert "Prefer `skillgate check` for CI." in out
    assert "GREEN" in out


def test_pdf_example_without_outputs_is_red_and_expect_fail_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_workspace(monkeypatch, tmp_path)
    enable_live(monkeypatch, root)
    pack = example_pack(root)
    harness = FakeHarness(skill="pdf")
    install_harness(monkeypatch, harness)
    install_decision_api(monkeypatch, DecisionAPI())
    code, out = cli(["check", str(pack)])
    assert code == 1, out
    assert "RED" in out
    code2, _out2 = cli(["check", str(pack), "--expect-fail"])
    assert code2 == 0
    assert len(harness.calls) == 16


def test_green_check_unlocks_deploy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    harness = FakeHarness(skill="memo")
    _root, pack, _api = live_check(monkeypatch, tmp_path, harness)
    code, _out = cli(["check", str(pack)])
    assert code == 0
    deploy_code, dout = cli(["deploy", str(pack), "--target", "cursor"])
    assert deploy_code == 0, dout
    assert (tmp_path / "cursor-skills" / "memo" / "SKILL.md").is_file()
    assert not (tmp_path / "cursor-skills" / "memo" / "evals").exists()
    assert (pack / "evals" / "deploys.jsonl").is_file()


def test_red_check_blocks_deploy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    harness = FakeHarness(skill=None)
    _root, pack, _api = live_check(monkeypatch, tmp_path, harness)
    code, _out = cli(["check", str(pack)])
    assert code == 1
    deploy_code, _dout = cli(["deploy", str(pack), "--target", "cursor"])
    assert deploy_code == 1
    assert not (tmp_path / "cursor-skills" / "memo").exists()
