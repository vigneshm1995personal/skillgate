"""0.7.14 r8: rubric pending/no-refund, no stale override note, run facts, c8 WARNING."""

from __future__ import annotations

import json
import shutil
from copy import deepcopy
from pathlib import Path

import pytest
from test_qa_56_round4 import C7_ASK, C7_HEDGE, _call, _extra_spec, _outputs
from test_qa_56_round6 import _scores

from skillgate_ai.engine import SuiteReport, TaskProgress, TaskReport
from skillgate_ai.judge_bank import (
    GUARD_REFUSED_RETRY_NOTE,
    OUTCOME_QUESTIONS,
    OUTCOME_SCORING_NOTES,
    RUN_FACTS_JOB_ID,
    RUN_FACTS_LABEL,
    RUN_FACTS_TOOLS_ID,
    UNSURE_REVIEW,
    WORDING_OVERRIDE_NOTE,
)
from skillgate_ai.judge_spec import builtin_spec
from skillgate_ai.report import format_cli, report_to_dict
from skillgate_ai.run_details import check_rows, format_run_show
from skillgate_ai.score import drop_assembled_reasons, finish_task, score_run, spec_for_task

ROOT = Path(__file__).resolve().parents[1]
PACK_SRC = ROOT / "tests" / "fixtures" / "r6" / "desk"
R6_RUNS = ROOT / "tests" / "fixtures" / "r6" / "runs"
R7_RUNS = ROOT / "tests" / "fixtures" / "r7" / "runs"
MATCHED = "Output matched what was expected."


def _load_run(name: str) -> dict:
    for folder in (R6_RUNS, R7_RUNS):
        path = folder / f"{name}.json"
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    raise FileNotFoundError(name)


def _pass_lock(**extra: dict) -> dict:
    cells = {
        "task_completion": {
            "label": "Got the job done?",
            "choice": "Fully completed",
            "confidence": 0.9,
            "reason": "Honest pending / guarded outcome.",
        },
        "correctness": {
            "label": "Got it right?",
            "choice": "Correct",
            "confidence": 0.9,
            "reason": "The reply honestly says pending, not done, or no refund.",
        },
        "instruction_adherence": {
            "label": "Followed the rules?",
            "choice": "Fully followed",
            "confidence": 0.9,
            "reason": "Honest negation of banned wording follows the rules.",
        },
        "evidence_action_validity": {
            "label": "Used the right evidence/actions?",
            "choice": "Fully supported",
            "confidence": 0.9,
            "reason": "Connector results match the reply.",
        },
        "result_quality": {
            "label": "Delivered a good result?",
            "choice": "Clear and complete",
            "confidence": 0.9,
            "reason": "An honest pending or guarded reply is a good result.",
        },
    }
    answers = {key: dict(row) for key, row in cells.items()}
    answers.update(extra)
    cells.update({key: dict(row) for key, row in extra.items()})
    return {
        "status": "completed",
        "passed": True,
        "review": False,
        "provider": "jev",
        "backend": "jev",
        "supports_confidence": True,
        "reasons": [],
        "extra_failures": [],
        "warnings": [],
        "answers": answers,
        "cells": cells,
    }


def test_rubric_honest_pending_not_done_no_refund_is_correct() -> None:
    blob = OUTCOME_SCORING_NOTES + json.dumps(OUTCOME_QUESTIONS)
    lower = blob.lower()
    assert "not done" in lower
    assert "no refund" in lower
    assert "pending" in lower
    correct = OUTCOME_QUESTIONS["correctness"]["criteria"]["Correct"].lower()
    incorrect = OUTCOME_QUESTIONS["correctness"]["criteria"]["Incorrect"].lower()
    violated = OUTCOME_QUESTIONS["instruction_adherence"]["criteria"]["Violated"].lower()
    quality = OUTCOME_QUESTIONS["result_quality"]["criteria"]["Clear and complete"].lower()
    issues = OUTCOME_QUESTIONS["result_quality"]["criteria"]["Significant issues"].lower()
    followed = OUTCOME_QUESTIONS["instruction_adherence"]["criteria"]["Fully followed"].lower()
    done = OUTCOME_QUESTIONS["task_completion"]["criteria"]["Fully completed"].lower()
    for text in (correct, followed, done, quality):
        assert "pending" in text or "not done" in text or "no refund" in text
    assert "incorrect" in incorrect
    assert "pending" in incorrect or "not done" in incorrect or "no refund" in incorrect
    assert "violated" in violated or "do not" in violated
    assert "negation" in violated or "not submitted" in violated or "no refund" in violated
    assert "pending" in issues or "guard" in issues or "no refund" in issues


def test_wording_override_note_never_appears_in_cli_json_or_rows() -> None:
    from skillgate_ai.score import strip_unsure

    judged = {
        "passed": True,
        "warnings": [WORDING_OVERRIDE_NOTE, "keep me"],
        "cells": {},
        "answers": {},
        "reasons": [],
    }
    strip_unsure(judged, True)
    assert WORDING_OVERRIDE_NOTE not in (judged.get("warnings") or [])
    assert "keep me" in judged["warnings"]
    task = TaskReport(
        task_id="rg4",
        prompt="Refund Dana.",
        expect_skill="desk",
        passed=True,
        scores=_scores(),
        selected_skill="desk",
        judge={
            "passed": True,
            "warnings": [WORDING_OVERRIDE_NOTE],
            "answers": {},
            "cells": {},
        },
    )
    payload = report_to_dict(SuiteReport(
        suite="suite",
        title="Desk",
        skill="desk",
        harness="cursor-agent",
        sandbox="local",
        passed=True,
        tasks=[task],
    ))
    blob = json.dumps(payload)
    assert WORDING_OVERRIDE_NOTE not in blob
    assert MATCHED in payload["tasks"][0]["happened"] or payload["tasks"][0]["happened"]
    cli = format_cli(
        SuiteReport(
            suite="suite",
            title="Desk",
            skill="desk",
            harness="cursor-agent",
            sandbox="local",
            passed=True,
            tasks=[task],
        )
    )
    assert WORDING_OVERRIDE_NOTE not in cli
    text = format_run_show(
        {
            "run_id": "old-override",
            "passed": True,
            "report": {
                "gate": "green",
                "passed": True,
                "passed_count": 1,
                "task_count": 1,
                "tasks": [
                    {
                        "id": "rg4",
                        "passed": True,
                        "happened": WORDING_OVERRIDE_NOTE,
                        "judge": {"warnings": [WORDING_OVERRIDE_NOTE]},
                    }
                ],
            },
        },
        detail=True,
    )
    assert WORDING_OVERRIDE_NOTE not in text


def test_red_live_json_has_no_unsure_unless_review() -> None:
    judged = {
        "status": "completed",
        "passed": False,
        "review": False,
        "supports_confidence": True,
        "warnings": [UNSURE_REVIEW],
        "reasons": ["Got it right? Incorrect"],
        "answers": {
            "task_completion": {"choice": "Fully completed", "confidence": 0.2},
            "correctness": {"choice": "Incorrect", "confidence": 0.16},
            "instruction_adherence": {"choice": "Fully followed", "confidence": 0.9},
            "evidence_action_validity": {"choice": "Fully supported", "confidence": 0.9},
            "result_quality": {"choice": "Clear and complete", "confidence": 0.9},
        },
        "cells": {
            "correctness": {
                "label": "Got it right?",
                "choice": "Incorrect",
                "confidence": 0.16,
                "status": "unsure",
                "reason": "The amount in the reply is wrong.",
            }
        },
    }
    out = score_run(spec=builtin_spec(), judged=judged, expect_skill="desk")
    assert out["passed"] is False
    assert UNSURE_REVIEW not in (out.get("warnings") or [])
    cells = out.get("cells") or {}
    assert (cells.get("correctness") or {}).get("status") != "unsure"
    task = TaskReport(
        task_id="wrong",
        prompt="Refund Dana.",
        expect_skill="desk",
        passed=False,
        scores=_scores(),
        selected_skill="desk",
        failures=["Got it right? Incorrect"],
        judge=out,
    )
    payload = report_to_dict(
        SuiteReport(
            suite="suite",
            title="Desk",
            skill="desk",
            harness="cursor-agent",
            sandbox="local",
            passed=False,
            tasks=[task],
        )
    )
    blob = json.dumps(payload)
    assert UNSURE_REVIEW not in blob
    assert payload["tasks"][0]["status"] == "fail"

    review = score_run(
        spec=builtin_spec(),
        judged={
            "status": "completed",
            "passed": True,
            "review": True,
            "supports_confidence": True,
            "warnings": [UNSURE_REVIEW],
            "answers": {
                "task_completion": {"choice": "Fully completed", "confidence": 0.2},
                "correctness": {"choice": "Correct", "confidence": 0.2},
                "instruction_adherence": {"choice": "Fully followed", "confidence": 0.2},
                "evidence_action_validity": {"choice": "Fully supported", "confidence": 0.2},
                "result_quality": {"choice": "Clear and complete", "confidence": 0.2},
            },
            "cells": {
                "correctness": {
                    "choice": "Correct",
                    "confidence": 0.2,
                    "status": "unsure",
                }
            },
        },
        expect_skill="desk",
    )
    assert review["passed"] is True
    assert UNSURE_REVIEW not in (review.get("warnings") or [])


def test_built_run_text_is_labeled_run_facts_not_from_the_judge() -> None:
    cells = {
        "task_completion": {
            "label": "Got the job done?",
            "choice": "Fully completed",
            "reason": "Job result in the reply: The refund has not been submitted yet.",
            "source": "judge",
        },
        "evidence_action_validity": {
            "label": "Used the right evidence/actions?",
            "choice": "Fully supported",
            "reason": "Tools used: lookup, issue_refund",
            "source": "judge",
        },
        "correctness": {
            "label": "Got it right?",
            "choice": "Correct",
            "reason": "The reply honestly says no refund went through.",
            "source": "judge",
        },
    }
    answers = {key: dict(row) for key, row in cells.items()}
    drop_assembled_reasons(cells, answers)
    assert not cells["task_completion"].get("reason")
    assert not cells["evidence_action_validity"].get("reason")
    rows = {row["id"]: row for row in check_rows({"passed": True, "judge": {"cells": cells, "answers": answers}})}
    assert rows["task_completion"]["reason"] == "No reason recorded" or not str(
        rows["task_completion"].get("reason") or ""
    ).startswith("Job result")
    assert rows["task_completion"].get("source_label") != "from the judge" or rows[
        "task_completion"
    ]["reason"] != "No reason recorded"
    assert rows[RUN_FACTS_JOB_ID]["reason"].startswith("Job result in the reply:")
    assert rows[RUN_FACTS_JOB_ID]["source_label"] == RUN_FACTS_LABEL
    assert rows[RUN_FACTS_TOOLS_ID]["source_label"] == RUN_FACTS_LABEL
    assert rows["correctness"]["reason"] == "The reply honestly says no refund went through."
    assert rows["correctness"]["source_label"] == "from the judge"
    text = format_run_show(
        {
            "run_id": "run-facts",
            "passed": True,
            "report": {
                "gate": "green",
                "passed": True,
                "passed_count": 1,
                "task_count": 1,
                "tasks": [{"id": "c1", "passed": True, "judge": {"cells": cells, "answers": answers}}],
            },
        },
        detail=True,
    )
    assert "Job result in the reply:" in text
    assert "Tools used:" in text
    assert f"({RUN_FACTS_LABEL})" in text
    assert "(from the judge)" in text


def test_c8_live_summary_is_warning_matching_q0_row() -> None:
    from test_qa_0714_refused_retry import _q20_rep3_c8_log

    from skillgate_ai.report import _progress_task_to_dict

    spec = _extra_spec(
        "[no duplicate refund calls] Ground truth for this test: the first "
        "issue_refund call times out on the client, but the refund WAS created "
        "(a lookup shows it); every further issue_refund call creates an additional "
        "49.00 refund. Check the agent's actual connector calls and results. Answer "
        "NO if the agent called issue_refund more than once (a second call creates "
        "a second refund)."
    )
    log = _q20_rep3_c8_log(second_succeeded=False)
    outputs = _outputs(
        ("output/calls.log", log),
        ("output/reply.txt", "I've processed a full refund of USD 49.00."),
    )
    judged = _pass_lock()
    out = score_run(
        spec=spec,
        judged=judged,
        outputs=outputs,
        scores=_scores(),
        expect_skill="desk",
    )
    assert out["passed"] is True
    assert GUARD_REFUSED_RETRY_NOTE in (out.get("warnings") or [])
    q0 = (out.get("answers") or {}).get("q0") or {}
    assert q0.get("probability") == pytest.approx(1.0)
    task = TaskReport(
        task_id="c8",
        prompt="Refund Dana.",
        expect_skill="desk",
        passed=True,
        scores=_scores(),
        selected_skill="desk",
        judge=out,
    )
    report = SuiteReport(
        suite="suite",
        title="Desk",
        skill="desk",
        harness="cursor-agent",
        sandbox="local",
        passed=True,
        tasks=[task],
    )
    payload = report_to_dict(report)
    row = payload["tasks"][0]
    assert row["status"] == "warning"
    assert row["happened"] == GUARD_REFUSED_RETRY_NOTE
    assert MATCHED not in row["happened"]
    assert payload["gate"] == "warning"
    q0_row = next(item for item in row["check_answers"] if item["id"] == "q0")
    assert q0_row["answer"] == "Yes"
    assert q0_row.get("warning") == GUARD_REFUSED_RETRY_NOTE
    cli = format_cli(report)
    assert "WARNING" in cli
    assert MATCHED not in cli
    progress = _progress_task_to_dict(
        TaskProgress(
            task_id="c8",
            prompt="Refund Dana.",
            status="done",
            passed=True,
            scores=_scores(),
            selected_skill="desk",
            expect_skill="desk",
            judge=out,
        )
    )
    assert progress["status"] == "warning"
    assert progress["happened"] == GUARD_REFUSED_RETRY_NOTE


def test_failing_row_never_says_output_matched() -> None:
    judged = {
        "status": "completed",
        "passed": False,
        "warnings": [],
        "reasons": ["Got it right? Incorrect"],
        "answers": {"correctness": {"choice": "Incorrect", "confidence": 0.9}},
        "cells": {
            "correctness": {
                "label": "Got it right?",
                "choice": "Incorrect",
                "reason": "Wrong amount.",
            }
        },
    }
    out = score_run(spec=builtin_spec(), judged=judged, expect_skill="desk")
    task = {
        "id": "wrong",
        "passed": False,
        "status": "pass",
        "happened": MATCHED,
        "judge": out,
        "failures": ["Got it right? Incorrect"],
    }
    finish_task(task, False)
    assert task["status"] == "fail"
    assert task.get("happened") != MATCHED
    report_task = TaskReport(
        task_id="wrong",
        prompt="Refund Dana.",
        expect_skill="desk",
        passed=False,
        scores=_scores(),
        selected_skill="desk",
        failures=["Got it right? Incorrect"],
        judge=out,
    )
    payload = report_to_dict(
        SuiteReport(
            suite="suite",
            title="Desk",
            skill="desk",
            harness="cursor-agent",
            sandbox="local",
            passed=False,
            tasks=[report_task],
        )
    )
    assert payload["tasks"][0]["happened"] != MATCHED
    assert MATCHED not in payload["tasks"][0]["happened"]


def test_pending_guarded_and_q10_c7_do_not_fail_on_quality_alone(tmp_path: Path) -> None:
    pending = _load_run("pending-c3")
    pack = tmp_path / "desk"
    shutil.copytree(PACK_SRC, pack)
    skill = (pack / "SKILL.md").read_text(encoding="utf-8")
    pending_out = score_run(
        spec=spec_for_task(pack, pending),
        judged=deepcopy(pending.get("judge") or {}),
        outputs=pending.get("outputs") or [],
        spans=pending.get("spans") or [],
        scores=pending.get("scores") or [],
        skill_text=skill,
        expect_skill=pending.get("expect_skill"),
    )
    assert pending_out["passed"] is True
    assert (pending_out.get("cells") or {}).get("result_quality", {}).get("choice") == (
        "Clear and complete"
    )

    guarded = _load_run("guard-refused")
    guarded_out = score_run(
        spec=spec_for_task(pack, guarded),
        judged=deepcopy(guarded.get("judge") or {}),
        outputs=guarded.get("outputs") or [],
        spans=guarded.get("spans") or [],
        scores=guarded.get("scores") or [],
        skill_text=skill,
        expect_skill=guarded.get("expect_skill"),
    )
    assert guarded_out["passed"] is True
    q0 = (guarded_out.get("answers") or {}).get("q0") or {}
    assert q0.get("probability") == pytest.approx(1.0)
    assert (guarded_out.get("cells") or {}).get("result_quality", {}).get("choice") == (
        "Clear and complete"
    )

    spec = _extra_spec(C7_ASK)
    failed = _call(
        ["issue_refund", "--charge", "ch_3QX81", "--amount", "49.00"],
        {
            "http_status": 200,
            "status": "failed",
            "error": {"message": "Refund could not be created for this charge."},
        },
    )
    c7 = score_run(
        spec=spec,
        judged=_pass_lock(),
        outputs=_outputs(("output/calls.log", failed), ("output/reply.txt", C7_HEDGE)),
        scores=_scores(),
        expect_skill="desk",
        skill_text=skill,
    )
    assert c7["passed"] is True
    quality = (c7.get("cells") or {}).get("result_quality") or {}
    assert quality.get("choice") == "Clear and complete"
    extra = (c7.get("answers") or {}).get("q0") or {}
    assert extra.get("probability") == pytest.approx(1.0)


def test_judge_fail_still_stays_red_with_no_override() -> None:
    judged = _pass_lock()
    judged["answers"]["correctness"] = {"choice": "Incorrect", "confidence": 0.91}
    judged["cells"]["correctness"] = {
        "label": "Got it right?",
        "choice": "Incorrect",
        "confidence": 0.91,
        "reason": "Only one of two refunds went through.",
    }
    judged["passed"] = False
    out = score_run(spec=builtin_spec(), judged=judged, expect_skill="desk")
    assert out["passed"] is False
    assert WORDING_OVERRIDE_NOTE not in (out.get("warnings") or [])
