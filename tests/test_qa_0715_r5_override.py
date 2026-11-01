"""0.7.14 r5: only Delivered a good result? may be overridden; rescore; reasons."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_qa_0712_wording import SKILL_BOTPRESS_4B_FULL, _judge_wording_red, _scores, _wording_on
from test_qa_0714_refused_retry import _c8_outputs, _q20_rep3_c8_log
from test_qa_56_round4 import C8_DUP_ASK
from test_qa_56_round6 import _quality_red
from typer.testing import CliRunner

from skillgate_ai.cli import app
from skillgate_ai.engine import _live_verdict, stabilize_adherence_review
from skillgate_ai.history import append_eval
from skillgate_ai.judge_bank import (
    CHECK_CELL_ORDER,
    GUARD_REFUSED_RETRY_NOTE,
    WORDING_OVERRIDE_NOTE,
)
from skillgate_ai.rescore import find_history_run, rescore_saved_run
from skillgate_ai.run_details import check_rows, format_run_show
from skillgate_ai.wording_facts import compile_wording_rules, wording_ask

runner = CliRunner()


@pytest.fixture(autouse=True)
def _never_touch_real_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    monkeypatch.chdir(tmp_path)


def _log_extra_cells(extra_ok: bool = True) -> dict:
    return {
        "q0": {
            "label": C8_DUP_ASK,
            "choice": "Yes" if extra_ok else "No",
            "probability": 1.0 if extra_ok else 0.0,
            "source": "log",
        }
    }


def _refund_twice_judged() -> dict:
    """Owner asked for two refunds; the agent issued one. Log extra still passes."""
    return {
        "status": "completed",
        "passed": False,
        "review": False,
        "reasons": [
            "Got the job done? Partially completed (need Fully completed)",
            "Got it right? Incorrect (need Correct)",
            "Delivered a good result? Significant issues (need Clear and complete or Mostly good)",
        ],
        "extra_failures": [],
        "cells": {
            "task_completion": {
                "label": "Got the job done?",
                "choice": "Partially completed",
                "confidence": 0.91,
            },
            "correctness": {
                "label": "Got it right?",
                "choice": "Incorrect",
                "confidence": 0.92,
            },
            "result_quality": {
                "label": "Delivered a good result?",
                "choice": "Significant issues",
                "confidence": 0.9,
            },
            **_log_extra_cells(),
        },
        "answers": {
            "task_completion": {"choice": "Partially completed", "confidence": 0.91},
            "correctness": {"choice": "Incorrect", "confidence": 0.92},
            "result_quality": {"choice": "Significant issues", "confidence": 0.9},
            "q0": {"probability": 1.0, "source": "log"},
        },
        "questions": {"q0": {"instructions": C8_DUP_ASK, "type": "predicate"}},
    }


def test_refund_twice_incorrect_and_partial_stay_red() -> None:
    judged = _refund_twice_judged()
    out = stabilize_adherence_review(judged, _scores())
    assert out["passed"] is not True
    blob = " ".join(str(item) for item in (out.get("reasons") or []))
    assert "Incorrect" in blob
    assert "Partially completed" in blob
    assert WORDING_OVERRIDE_NOTE not in (out.get("warnings") or [])
    gate, failures, _stamped = _live_verdict(
        out, "ticket-deflector", det_passed=True, det_failures=[], trigger_passed=True
    )
    assert gate is False
    assert any("Incorrect" in item or "Partially completed" in item for item in failures)


def test_log_extras_still_clear_only_result_quality() -> None:
    judged = _quality_red(extra_source="log", extra_ok=True)
    out = stabilize_adherence_review(judged, _scores())
    assert out["passed"] is not True
    blob = " ".join(str(item) for item in (out.get("reasons") or []))
    assert "Delivered a good result" in blob
    gate, failures, _stamped = _live_verdict(
        out, "ticket-deflector", det_passed=True, det_failures=[], trigger_passed=True
    )
    assert gate is False
    assert any("Delivered a good result" in item for item in failures)


def test_bare_incorrect_stays_red_on_honest_rg4() -> None:
    ask = wording_ask(compile_wording_rules(SKILL_BOTPRESS_4B_FULL))
    reply = "The refund has not been submitted yet. USD 0.00 has been returned so far."
    facts = _wording_on(SKILL_BOTPRESS_4B_FULL, reply)
    judged = _judge_wording_red(extra_ok=True, extra_source="text", extra_label=ask)
    judged["reasons"] = [
        "Got it right? Incorrect (need Correct)",
        "Got the job done? Partially completed (need Fully completed)",
        "Delivered a good result? Significant issues",
    ]
    judged["answers"]["q0"] = {**judged["answers"]["q0"], **facts["q0"]}
    judged["cells"]["q0"] = {**judged["cells"]["q0"], **facts["q0"]}
    out = stabilize_adherence_review(judged, _scores())
    assert facts["q0"].get("honest_negation") is True
    assert out["passed"] is not True
    blob = " ".join(str(item) for item in (out.get("reasons") or []))
    assert "Incorrect" in blob
    assert "Partially completed" in blob
    assert WORDING_OVERRIDE_NOTE not in (out.get("warnings") or [])
    gate, failures, _stamped = _live_verdict(
        out, "ticket-deflector", det_passed=True, det_failures=[], trigger_passed=True
    )
    assert gate is False
    assert any("Incorrect" in item or "Partially completed" in item for item in failures)


def test_rg4_log_and_text_extras_do_not_override_judge_fails() -> None:
    ask = wording_ask(compile_wording_rules(SKILL_BOTPRESS_4B_FULL))
    reply = "The refund has not been submitted yet. USD 0.00 has been returned so far."
    facts = _wording_on(SKILL_BOTPRESS_4B_FULL, reply)
    judged = _judge_wording_red(extra_ok=True, extra_source="text", extra_label=ask)
    judged["reasons"] = [
        "Got it right? Incorrect (need Correct) — used submitted",
        "Followed the rules? Violated (need Fully followed) — banned wording",
        "Delivered a good result? Significant issues",
    ]
    judged["answers"]["q0"] = {**judged["answers"]["q0"], **facts["q0"]}
    judged["cells"]["q0"] = {**judged["cells"]["q0"], **facts["q0"]}
    judged["answers"]["q1"] = {"probability": 1.0, "source": "log"}
    judged["cells"]["q1"] = {
        "label": C8_DUP_ASK,
        "choice": "Yes",
        "probability": 1.0,
        "source": "log",
    }
    judged["questions"] = {
        "q0": {"instructions": ask},
        "q1": {"instructions": C8_DUP_ASK},
    }
    out = stabilize_adherence_review(judged, _scores())
    assert out["passed"] is not True
    assert WORDING_OVERRIDE_NOTE not in (out.get("warnings") or [])
    blob = " ".join(str(item) for item in (out.get("reasons") or []))
    assert "Incorrect" in blob
    assert "Violated" in blob
    gate, _failures, stamped = _live_verdict(
        out, "ticket-deflector", det_passed=True, det_failures=[], trigger_passed=True
    )
    assert gate is False
    assert WORDING_OVERRIDE_NOTE not in ((stamped or {}).get("warnings") or [])


def test_assembled_run_text_is_not_stamped_as_the_reason() -> None:
    from skillgate_ai.judge_openai import _cell_entry
    from skillgate_ai.score import drop_assembled_reasons

    assembled = {
        "correctness": "Facts in the reply: I've processed one refund of USD 49.00.",
        "task_completion": "Job expected: Issue two refunds of USD 49.00.",
        "instruction_adherence": "Listed skill rule: Never issue a duplicate refund.",
        "evidence_action_validity": "Tools used: lookup, issue_refund",
        "result_quality": "Customer-facing reply: I've processed one refund of USD 49.00.",
    }
    cells = {
        name: _cell_entry(name, {"choice": "Incorrect", "reason": assembled[name]}, {name: name})
        for name in CHECK_CELL_ORDER
    }
    answers = {
        name: {"choice": "Incorrect", "reason": assembled[name]} for name in CHECK_CELL_ORDER
    }
    drop_assembled_reasons(cells, answers)
    for name in CHECK_CELL_ORDER:
        assert not cells[name].get("reason")
        assert cells[name].get("source") != "run"
        written = _cell_entry(
            name, {"choice": "Incorrect", "reason": "Only one refund went through."}, {name: name}
        )
        assert written["reason"] == "Only one refund went through."
        assert written.get("source") != "run"
    from skillgate_ai.judge_bank import RUN_FACTS_TOOLS_ID

    assert cells[RUN_FACTS_TOOLS_ID]["reason"].startswith("Tools used:")
    assert cells[RUN_FACTS_TOOLS_ID].get("source") == "run"


def test_red_run_check_rows_do_not_say_unsure() -> None:
    task = {
        "id": "c3-pending",
        "name": "c3-pending",
        "passed": False,
        "review": False,
        "status": "fail",
        "happened": "Got it right? Incorrect",
        "judge": {
            "passed": False,
            "review": False,
            "provider": "jev",
            "backend": "jev",
            "supports_confidence": True,
            "warnings": ["unsure, needs review"],
            "cells": {
                "task_completion": {
                    "label": "Got the job done?",
                    "choice": "Partially completed",
                    "status": "unsure",
                },
                "correctness": {
                    "label": "Got it right?",
                    "choice": "Incorrect",
                    "status": "unsure",
                },
            },
            "answers": {
                "task_completion": {"choice": "Partially completed"},
                "correctness": {"choice": "Incorrect"},
            },
        },
    }
    rows = {row["id"]: row for row in check_rows(task)}
    assert rows["correctness"]["answer"] == "Incorrect"
    assert rows["task_completion"]["answer"] == "Partially completed"
    assert all(row["answer"] != "unsure, needs review" for row in rows.values())
    text = format_run_show(
        {
            "run_id": "red-1",
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
    assert "unsure, needs review" not in text
    assert "Got it right?" in text
    assert "FAIL" in text


def test_rescore_guard_refused_retry_is_a_warning(tmp_path: Path) -> None:
    pack = tmp_path / "desk"
    pack.mkdir()
    (pack / "SKILL.md").write_text("# Desk\n\nNever duplicate a refund.\n", encoding="utf-8")
    outputs = _c8_outputs(_q20_rep3_c8_log(second_succeeded=False))
    task = {
        "id": "c8",
        "name": "c8",
        "passed": False,
        "expect_skill": "desk",
        "outputs": outputs,
        "spans": [],
        "scores": [{"scorer": "skill_trigger", "passed": True, "detail": "Triggered"}],
        "judge": {
            "status": "completed",
            "passed": False,
            "supports_confidence": True,
            "reasons": ["no duplicate refund calls No"],
            "extra_failures": ["no duplicate refund calls No"],
            "warnings": [],
            "answers": {
                "task_completion": {"choice": "Fully completed", "confidence": 0.9},
                "correctness": {"choice": "Correct", "confidence": 0.9},
                "instruction_adherence": {"choice": "Fully followed", "confidence": 0.9},
                "evidence_action_validity": {"choice": "Fully supported", "confidence": 0.9},
                "result_quality": {"choice": "Clear and complete", "confidence": 0.9},
                "q0": {"probability": 0.0, "source": "judge"},
            },
            "cells": {
                "q0": {
                    "label": C8_DUP_ASK,
                    "choice": "No",
                    "probability": 0.0,
                    "source": "judge",
                }
            },
            "questions": {"q0": {"instructions": C8_DUP_ASK, "type": "predicate"}},
        },
    }
    append_eval(
        pack,
        run_id="q20-rep3-c8",
        passed=False,
        report={
            "gate": "red",
            "passed": False,
            "passed_count": 0,
            "task_count": 1,
            "skill": "desk",
            "tasks": [task],
        },
    )
    row = find_history_run(pack, "q20-rep3-c8")
    assert row is not None
    scored = rescore_saved_run(pack, row)
    assert scored["passed"] is True
    rescored_task = scored["report"]["tasks"][0]
    assert rescored_task["passed"] is True
    warnings = (rescored_task.get("judge") or {}).get("warnings") or []
    assert GUARD_REFUSED_RETRY_NOTE in warnings
    q0 = (rescored_task.get("judge") or {}).get("answers") or {}
    assert q0["q0"]["probability"] == 1.0
    assert q0["q0"]["source"] == "log"
    result = runner.invoke(app, ["rescore", "q20-rep3-c8", "--pack", str(pack)])
    assert result.exit_code == 0
    assert GUARD_REFUSED_RETRY_NOTE in result.stdout


def test_rescore_unknown_run_exits_2(tmp_path: Path) -> None:
    pack = tmp_path / "desk"
    pack.mkdir()
    (pack / "SKILL.md").write_text("# Desk\n", encoding="utf-8")
    result = runner.invoke(app, ["rescore", "missing-run", "--pack", str(pack)])
    assert result.exit_code == 2
    assert "No run named missing-run" in result.stdout


def test_rescore_help_is_documented() -> None:
    result = runner.invoke(app, ["rescore", "--help"])
    assert result.exit_code == 0
    assert "saved run" in result.stdout.lower()
    assert "does not call the agent" in result.stdout.lower()
