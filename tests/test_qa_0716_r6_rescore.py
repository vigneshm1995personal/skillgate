"""0.7.14 r6: live-path rescore against a real pack, from saved-run fixtures."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skillgate_ai.cli import app
from skillgate_ai.history import append_eval
from skillgate_ai.judge_bank import (
    GUARD_REFUSED_RETRY_NOTE,
    NO_REASON_RECORDED,
    UNSURE_REVIEW,
    WORDING_OVERRIDE_NOTE,
)
from skillgate_ai.rescore import find_history_run, rescore_saved_run
from skillgate_ai.run_details import check_rows, format_run_show

ROOT = Path(__file__).resolve().parents[1]
PACK_SRC = ROOT / "tests" / "fixtures" / "r6" / "desk"
RUNS = ROOT / "tests" / "fixtures" / "r6" / "runs"
runner = CliRunner()

CASES = (
    "refund-twice-one-done",
    "timeout-success-double",
    "guard-refused",
    "both-succeeded",
    "rg4-negation",
    "wrong-amount",
)


@pytest.fixture(autouse=True)
def _never_touch_real_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    monkeypatch.chdir(tmp_path)


def _load_run(name: str) -> dict:
    return json.loads((RUNS / f"{name}.json").read_text(encoding="utf-8"))


def _pack_with_history(tmp_path: Path, *names: str) -> Path:
    dest = tmp_path / "desk"
    shutil.copytree(PACK_SRC, dest)
    for name in names:
        task = _load_run(name)
        append_eval(
            dest,
            run_id=name,
            passed=task.get("passed"),
            report={
                "gate": "green" if task.get("passed") else "red",
                "passed": task.get("passed"),
                "passed_count": 1 if task.get("passed") else 0,
                "task_count": 1,
                "skill": "desk",
                "tasks": [task],
            },
        )
    return dest


def _rescore_cli(pack: Path, run_id: str, *extra: str):
    return runner.invoke(app, ["rescore", run_id, "--pack", str(pack), *extra])


def _json_payload(result) -> dict:
    text = result.stdout.strip()
    start = text.find("{")
    assert start >= 0, result.stdout
    return json.loads(text[start:])


def _task(scored: dict) -> dict:
    return scored["report"]["tasks"][0]


def _dup_row(task: dict) -> dict:
    rows = {row["id"]: row for row in check_rows(task)}
    assert "q0" in rows
    return rows["q0"]


def test_fixtures_cover_the_six_live_cases() -> None:
    assert {path.stem for path in RUNS.glob("*.json")} == set(CASES)
    for name in CASES:
        blob = _load_run(name)
        assert blob["outputs"], name
        assert any(item.get("path", "").endswith("calls.log") for item in blob["outputs"]), name
        assert any(item.get("path", "").endswith("reply.txt") for item in blob["outputs"]), name
        assert blob["judge"]["supports_confidence"] is True, name


def test_rescore_refund_twice_one_done_stays_red(tmp_path: Path) -> None:
    pack = _pack_with_history(tmp_path, "refund-twice-one-done")
    scored = rescore_saved_run(pack, find_history_run(pack, "refund-twice-one-done"))
    task = _task(scored)
    assert scored["passed"] is False
    assert scored.get("gate") == "red"
    assert task["passed"] is False
    assert task.get("status") == "fail"
    blob = " ".join(str(item) for item in (task.get("failures") or []))
    cells = (task.get("judge") or {}).get("cells") or {}
    assert cells["correctness"]["choice"] == "Incorrect"
    assert cells["task_completion"]["choice"] == "Partially completed"
    assert "Incorrect" in blob or cells["correctness"]["choice"] == "Incorrect"
    assert WORDING_OVERRIDE_NOTE not in ((task.get("judge") or {}).get("warnings") or [])
    result = _rescore_cli(pack, "refund-twice-one-done")
    assert result.exit_code == 1
    assert "FAIL" in result.stdout
    assert "Got it right?" in result.stdout
    assert "Got the job done?" in result.stdout


def test_rescore_timeout_then_success_is_a_double_refund_red(tmp_path: Path) -> None:
    pack = _pack_with_history(tmp_path, "timeout-success-double")
    scored = rescore_saved_run(pack, find_history_run(pack, "timeout-success-double"))
    task = _task(scored)
    assert scored["passed"] is False
    assert task["passed"] is False
    assert task.get("status") == "fail"
    row = _dup_row(task)
    assert row["passed"] is False
    assert row.get("score") == pytest.approx(0.0)
    q0 = ((task.get("judge") or {}).get("answers") or {}).get("q0") or {}
    assert q0.get("probability") == pytest.approx(0.0)
    result = _rescore_cli(pack, "timeout-success-double")
    assert result.exit_code == 1
    assert "FAIL" in result.stdout
    assert "0.00" in result.stdout or "0.0" in result.stdout


def test_rescore_guard_refused_is_warning_not_pass(tmp_path: Path) -> None:
    pack = _pack_with_history(tmp_path, "guard-refused")
    scored = rescore_saved_run(pack, find_history_run(pack, "guard-refused"))
    task = _task(scored)
    assert scored["passed"] is True
    assert task["passed"] is True
    assert task.get("status") != "fail"
    assert scored.get("status") != "fail"
    warnings = (task.get("judge") or {}).get("warnings") or []
    assert GUARD_REFUSED_RETRY_NOTE in warnings
    assert UNSURE_REVIEW not in json.dumps(scored)
    row = _dup_row(task)
    assert row.get("warning") == GUARD_REFUSED_RETRY_NOTE
    assert row["passed"] is not False
    assert row.get("score") == pytest.approx(1.0)
    listed = {item["id"]: item for item in task.get("check_answers") or []}
    assert listed["q0"]["score"] == pytest.approx(1.0)
    assert listed["q0"]["passed"] is not False
    result = _rescore_cli(pack, "guard-refused")
    assert result.exit_code == 0
    assert "WARNING" in result.stdout
    assert GUARD_REFUSED_RETRY_NOTE in result.stdout
    json_result = _rescore_cli(pack, "guard-refused", "--json")
    payload = _json_payload(json_result)
    assert payload["passed"] is True
    json_task = payload["report"]["tasks"][0]
    assert json_task.get("status") != "fail"
    assert json_task["passed"] is True
    json_q0 = next(item for item in json_task["check_answers"] if item["id"] == "q0")
    assert json_q0["score"] == pytest.approx(1.0)
    assert json_q0.get("warning") == GUARD_REFUSED_RETRY_NOTE


def test_rescore_both_succeeded_is_red(tmp_path: Path) -> None:
    pack = _pack_with_history(tmp_path, "both-succeeded")
    scored = rescore_saved_run(pack, find_history_run(pack, "both-succeeded"))
    task = _task(scored)
    assert scored["passed"] is False
    assert task["passed"] is False
    row = _dup_row(task)
    assert row["passed"] is False
    assert row.get("score") == pytest.approx(0.0)
    result = _rescore_cli(pack, "both-succeeded")
    assert result.exit_code == 1


def test_rescore_rg4_negation_greens_from_judge_choices(tmp_path: Path) -> None:
    pack = _pack_with_history(tmp_path, "rg4-negation")
    scored = rescore_saved_run(pack, find_history_run(pack, "rg4-negation"))
    task = _task(scored)
    assert scored["passed"] is True
    assert task["passed"] is True
    warnings = (task.get("judge") or {}).get("warnings") or []
    assert WORDING_OVERRIDE_NOTE not in warnings
    assert UNSURE_REVIEW not in json.dumps(scored)
    cells = (task.get("judge") or {}).get("cells") or {}
    assert cells["correctness"]["choice"] == "Correct"
    assert cells["instruction_adherence"]["choice"] == "Fully followed"
    assert cells["result_quality"]["choice"] == "Clear and complete"
    reasons = " ".join(str(item) for item in ((task.get("judge") or {}).get("reasons") or []))
    assert "Incorrect" not in reasons
    assert "Violated" not in reasons
    assert "Partially completed" not in reasons
    result = _rescore_cli(pack, "rg4-negation")
    assert result.exit_code == 0
    assert WORDING_OVERRIDE_NOTE not in result.stdout


def test_rescore_wrong_amount_stays_red(tmp_path: Path) -> None:
    pack = _pack_with_history(tmp_path, "wrong-amount")
    scored = rescore_saved_run(pack, find_history_run(pack, "wrong-amount"))
    task = _task(scored)
    assert scored["passed"] is False
    assert task["passed"] is False
    assert task.get("status") == "fail"
    cells = (task.get("judge") or {}).get("cells") or {}
    assert cells["correctness"]["choice"] == "Incorrect"
    result = _rescore_cli(pack, "wrong-amount")
    assert result.exit_code == 1
    assert "FAIL" in result.stdout
    assert "Got it right?" in result.stdout


def test_rescore_cli_json_and_rows_agree_and_keep_jev_reasons(tmp_path: Path) -> None:
    pack = _pack_with_history(tmp_path, *CASES)
    for name in CASES:
        scored = rescore_saved_run(pack, find_history_run(pack, name))
        task = _task(scored)
        if task.get("passed") is True:
            assert task.get("status") != "fail", name
            assert scored.get("passed") is True
            assert UNSURE_REVIEW not in json.dumps(scored), name
        if task.get("passed") is False:
            assert scored.get("passed") is False
            assert task.get("status") == "fail", name
        rows = {row["id"]: row for row in check_rows(task)}
        listed = {item["id"]: item for item in task.get("check_answers") or []}
        for key in ("task_completion", "correctness", "result_quality"):
            if key not in rows:
                continue
            assert rows[key]["reason"] != NO_REASON_RECORDED, f"{name}:{key}"
            if key in listed:
                assert listed[key]["reason"] == rows[key]["reason"]
                if rows[key].get("score") is not None and listed[key].get("score") is not None:
                    assert listed[key]["score"] == pytest.approx(rows[key]["score"])
                assert listed[key]["passed"] == rows[key]["passed"]
        text = format_run_show(scored, detail=True)
        if task.get("passed") is True:
            assert UNSURE_REVIEW not in text, name
        json_result = _rescore_cli(pack, name, "--json")
        payload = _json_payload(json_result)
        json_task = payload["report"]["tasks"][0]
        assert json_task["passed"] == task["passed"], name
        assert (payload["passed"] is True) == (task["passed"] is True), name
        if json_task.get("passed") is True:
            assert json_task.get("status") != "fail", name
        if json_task.get("passed") is False:
            assert json_task.get("status") == "fail", name
            assert payload.get("passed") is False
