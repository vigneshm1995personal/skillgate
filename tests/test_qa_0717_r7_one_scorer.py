"""0.7.14 r7: one scorer for live check and rescore; no wording override."""

from __future__ import annotations

import inspect
import json
import shutil
from copy import deepcopy
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skillgate_ai import engine, rescore
from skillgate_ai.cli import app
from skillgate_ai.history import append_eval, load_history
from skillgate_ai.judge_bank import (
    CHECK_CELL_ORDER,
    NO_REASON_RECORDED,
    OUTCOME_QUESTIONS,
    OUTCOME_SCORING_NOTES,
    RUN_FACTS_TOOLS_ID,
    UNSURE_REVIEW,
    WORDING_OVERRIDE_NOTE,
    is_built_reason,
)
from skillgate_ai.rescore import find_history_run, rescore_saved_run
from skillgate_ai.run_details import check_rows, format_run_show
from skillgate_ai.score import drop_assembled_reasons, score_run, spec_for_task, verdict_json

ROOT = Path(__file__).resolve().parents[1]
PACK_SRC = ROOT / "tests" / "fixtures" / "r6" / "desk"
R6_RUNS = ROOT / "tests" / "fixtures" / "r6" / "runs"
R7_RUNS = ROOT / "tests" / "fixtures" / "r7" / "runs"
runner = CliRunner()

R6_CASES = (
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
    for folder in (R6_RUNS, R7_RUNS):
        path = folder / f"{name}.json"
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    raise FileNotFoundError(name)


def _pack_with_history(tmp_path: Path, *names: str) -> Path:
    dest = tmp_path / "desk"
    if dest.exists():
        shutil.rmtree(dest)
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


def _live_score(pack: Path, task: dict) -> dict:
    spec = spec_for_task(pack, task)
    skill = pack / "SKILL.md"
    return score_run(
        spec=spec,
        judged=deepcopy(task.get("judge") or {}),
        outputs=task.get("outputs") or [],
        spans=task.get("spans") or [],
        scores=task.get("scores") or [],
        skill_text=skill.read_text(encoding="utf-8") if skill.is_file() else None,
        expect_skill=task.get("expect_skill"),
    )


def test_live_check_and_rescore_call_the_same_scorer() -> None:
    live_src = inspect.getsource(engine._run_task)
    rescore_src = inspect.getsource(rescore.rescore_saved_run)
    assert "score_run(" in live_src
    assert "score_run(" in rescore_src
    assert "stabilize_adherence_review(" not in live_src
    assert "_live_verdict(" not in live_src
    assert "_restamp_why" not in rescore_src
    from skillgate_ai.score import apply_gate

    gate_src = inspect.getsource(apply_gate)
    assert "WORDING_OVERRIDE_NOTE" not in gate_src
    assert "honest_negation" not in gate_src


@pytest.mark.parametrize("name", (*R6_CASES, "pending-c3"))
def test_live_score_run_matches_rescore_verdict_json(tmp_path: Path, name: str) -> None:
    pack = _pack_with_history(tmp_path, name)
    row = find_history_run(pack, name)
    assert row is not None
    task = row["report"]["tasks"][0]
    live = _live_score(pack, task)
    scored = rescore_saved_run(pack, deepcopy(row))
    rescored = scored["report"]["tasks"][0]["judge"]
    assert verdict_json(live) == verdict_json(rescored)


def test_incorrect_stays_red_with_passing_extras_and_no_override(tmp_path: Path) -> None:
    pack = _pack_with_history(tmp_path, "refund-twice-one-done")
    row = find_history_run(pack, "refund-twice-one-done")
    task = row["report"]["tasks"][0]
    live = _live_score(pack, task)
    assert live["passed"] is False
    assert WORDING_OVERRIDE_NOTE not in (live.get("warnings") or [])
    cells = live.get("cells") or {}
    assert cells["correctness"]["choice"] == "Incorrect"
    scored = rescore_saved_run(pack, deepcopy(row))
    rescored = scored["report"]["tasks"][0]
    assert rescored["passed"] is False
    assert WORDING_OVERRIDE_NOTE not in ((rescored.get("judge") or {}).get("warnings") or [])


def test_timeout_then_success_double_is_red_on_both_paths(tmp_path: Path) -> None:
    pack = _pack_with_history(tmp_path, "timeout-success-double")
    row = find_history_run(pack, "timeout-success-double")
    live = _live_score(pack, row["report"]["tasks"][0])
    scored = rescore_saved_run(pack, deepcopy(row))
    assert live["passed"] is False
    assert scored["passed"] is False
    assert scored["report"]["tasks"][0]["passed"] is False
    q0 = (live.get("answers") or {}).get("q0") or {}
    assert q0.get("probability") == pytest.approx(0.0)


def test_honest_rg4_greens_from_judge_choices_without_override(tmp_path: Path) -> None:
    pack = _pack_with_history(tmp_path, "rg4-negation")
    row = find_history_run(pack, "rg4-negation")
    live = _live_score(pack, row["report"]["tasks"][0])
    scored = rescore_saved_run(pack, deepcopy(row))
    task = scored["report"]["tasks"][0]
    assert live["passed"] is True
    assert task["passed"] is True
    cells = (task.get("judge") or {}).get("cells") or {}
    assert cells["correctness"]["choice"] == "Correct"
    assert cells["instruction_adherence"]["choice"] == "Fully followed"
    assert cells["result_quality"]["choice"] == "Clear and complete"
    warnings = (task.get("judge") or {}).get("warnings") or []
    assert WORDING_OVERRIDE_NOTE not in warnings
    assert WORDING_OVERRIDE_NOTE not in (live.get("warnings") or [])
    result = _rescore_cli(pack, "rg4-negation")
    assert result.exit_code == 0
    assert WORDING_OVERRIDE_NOTE not in result.stdout


def test_honest_pending_c3_greens_on_judge_pass_lock(tmp_path: Path) -> None:
    pack = _pack_with_history(tmp_path, "pending-c3")
    row = find_history_run(pack, "pending-c3")
    live = _live_score(pack, row["report"]["tasks"][0])
    scored = rescore_saved_run(pack, deepcopy(row))
    task = scored["report"]["tasks"][0]
    assert live["passed"] is True
    assert task["passed"] is True
    cells = (task.get("judge") or {}).get("cells") or {}
    assert cells["correctness"]["choice"] == "Correct"
    assert cells["task_completion"]["choice"] == "Fully completed"
    q1 = ((task.get("judge") or {}).get("answers") or {}).get("q1") or {}
    assert q1.get("probability") == pytest.approx(1.0)
    assert WORDING_OVERRIDE_NOTE not in ((task.get("judge") or {}).get("warnings") or [])


def test_rubric_says_honest_pending_is_correct() -> None:
    blob = OUTCOME_SCORING_NOTES + json.dumps(OUTCOME_QUESTIONS)
    assert "not submitted yet" in blob.lower()
    assert "pending" in blob.lower()
    correct = OUTCOME_QUESTIONS["correctness"]["criteria"]["Correct"]
    followed = OUTCOME_QUESTIONS["instruction_adherence"]["criteria"]["Fully followed"]
    done = OUTCOME_QUESTIONS["task_completion"]["criteria"]["Fully completed"]
    quality = OUTCOME_QUESTIONS["result_quality"]["criteria"]["Clear and complete"]
    assert "pending" in correct.lower() or "not submitted yet" in correct.lower()
    assert "pending" in followed.lower() or "not submitted yet" in followed.lower()
    assert "pending" in done.lower() or "not submitted yet" in done.lower()
    assert "pending" in quality.lower() or "not submitted yet" in quality.lower()


def test_assembled_reasons_are_run_facts_not_from_the_judge() -> None:
    cells = {
        "correctness": {
            "label": "Got it right?",
            "choice": "Incorrect",
            "reason": "Facts in the reply: I've processed a full refund of USD 49.00.",
        },
        "task_completion": {
            "label": "Got the job done?",
            "choice": "Partially completed",
            "reason": "Job expected: Refund both of Dana's Pro charges.",
        },
        "instruction_adherence": {
            "label": "Followed the rules?",
            "choice": "Fully followed",
            "reason": "Listed skill rule: Never issue a duplicate refund.",
        },
        "evidence_action_validity": {
            "label": "Used the right evidence/actions?",
            "choice": "Fully supported",
            "reason": "Tools used: lookup, issue_refund",
        },
        "result_quality": {
            "label": "Delivered a good result?",
            "choice": "Significant issues",
            "reason": "Customer-facing reply: The refund has not been submitted yet.",
        },
    }
    answers = {key: dict(row) for key, row in cells.items()}
    drop_assembled_reasons(cells, answers)
    task = {
        "passed": False,
        "status": "fail",
        "judge": {"passed": False, "cells": cells, "answers": answers},
    }
    rows = {row["id"]: row for row in check_rows(task)}
    for key in CHECK_CELL_ORDER:
        assert not is_built_reason(cells[key].get("reason"))
        assert rows[key]["source_label"] != "run facts"
        if rows[key]["reason"] == NO_REASON_RECORDED:
            assert rows[key].get("source_label") in {"", None}
    assert rows[RUN_FACTS_TOOLS_ID]["reason"].startswith("Tools used:")
    assert rows[RUN_FACTS_TOOLS_ID]["source_label"] == "run facts"
    text = format_run_show(
        {
            "run_id": "assembled",
            "passed": False,
            "report": {
                "gate": "red",
                "passed": False,
                "passed_count": 0,
                "task_count": 1,
                "tasks": [task],
            },
        },
        detail=True,
    )
    assert "Tools used:" in text
    assert "(run facts)" in text


def test_judge_written_reason_is_kept() -> None:
    written = "Only one of the two refunds went through."
    cells = {"correctness": {"label": "Got it right?", "choice": "Incorrect", "reason": written}}
    answers = {"correctness": {"choice": "Incorrect", "reason": written}}
    drop_assembled_reasons(cells, answers)
    assert cells["correctness"]["reason"] == written
    rows = {row["id"]: row for row in check_rows({"passed": False, "judge": {"cells": cells, "answers": answers}})}
    assert rows["correctness"]["reason"] == written


def test_rescore_cli_adds_a_history_row(tmp_path: Path) -> None:
    pack = _pack_with_history(tmp_path, "refund-twice-one-done")
    before = load_history(pack, limit=0)
    assert len(before) == 1
    result = _rescore_cli(pack, "refund-twice-one-done")
    assert result.exit_code == 1
    after = load_history(pack, limit=0)
    assert len(after) == 2
    ids = [str(row.get("run_id") or "") for row in after]
    assert "refund-twice-one-done" in ids
    added = [row for row in after if row.get("run_id") != "refund-twice-one-done"]
    assert len(added) == 1
    assert added[0].get("passed") is False


def test_red_rescore_json_has_no_unsure(tmp_path: Path) -> None:
    pack = _pack_with_history(tmp_path, "refund-twice-one-done")
    result = _rescore_cli(pack, "refund-twice-one-done", "--json")
    payload = _json_payload(result)
    assert payload["passed"] is False
    blob = json.dumps(payload)
    assert UNSURE_REVIEW not in blob
    task = payload["report"]["tasks"][0]
    assert task.get("status") == "fail"
    warnings = (task.get("judge") or {}).get("warnings") or []
    assert UNSURE_REVIEW not in warnings
