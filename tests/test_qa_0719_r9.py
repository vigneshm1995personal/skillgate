"""0.7.14 r9: c8 red summary, expected refund count, run facts as extra rows."""

from __future__ import annotations

import json
import shutil
from copy import deepcopy
from pathlib import Path

import pytest
from test_qa_0714_refused_retry import _q20_rep3_c8_log
from test_qa_0718_r8 import MATCHED, _load_run, _pass_lock
from test_qa_56_round4 import C8_DUP_ASK, _call, _extra_spec, _outputs
from test_qa_56_round6 import _scores

from skillgate_ai.engine import SuiteReport, TaskReport
from skillgate_ai.judge_bank import (
    CHECK_CELL_LABELS,
    EXPECTED_REFUND_NOTE,
    GUARD_REFUSED_RETRY_NOTE,
    OUTCOME_QUESTIONS,
    OUTCOME_SCORING_NOTES,
    RUN_FACTS_JOB_ID,
    RUN_FACTS_LABEL,
    RUN_FACTS_TOOLS_ID,
)
from skillgate_ai.judge_spec import builtin_spec
from skillgate_ai.report import format_cli, report_to_dict
from skillgate_ai.run_details import check_rows, format_run_show
from skillgate_ai.score import finish_task, score_run, spec_for_task, verdict_json

ROOT = Path(__file__).resolve().parents[1]
PACK_SRC = ROOT / "tests" / "fixtures" / "r6" / "desk"
PENDING_REPLY = "The refund has not been submitted yet. USD 0.00 has been returned so far."
PENDING_LOG = _call(
    ["issue_refund", "--charge", "ch_3QX81", "--amount", "49.00"],
    {"http_status": 200, "status": "pending", "amount": "49.00"},
)
ONE_REFUND_LOG = (
    _call(
        ["issue_refund", "--charge", "ch_3QX81", "--amount", "49.00"],
        {"http_status": 200, "status": "succeeded", "amount": "49.00"},
    )
    + "\n"
    + _call(
        ["lookup", "dana.okafor@lumenfit.co"],
        {
            "http_status": 200,
            "charges": [
                {
                    "id": "ch_3QX81",
                    "amount_refunded": "49.00",
                    "refunds": [{"id": "re_1", "amount": "49.00", "status": "succeeded"}],
                }
            ],
        },
    )
)
TWO_ASKED = "Refund both of Dana's Pro charges. The owner asked for two refunds."


def _desk(tmp_path: Path) -> Path:
    dest = tmp_path / "desk"
    shutil.copytree(PACK_SRC, dest)
    return dest


def _skill(pack: Path) -> str:
    return (pack / "SKILL.md").read_text(encoding="utf-8")


def _noisy(key: str, choice: str) -> dict:
    judged = _pass_lock()
    judged["passed"] = False
    judged["answers"][key] = {
        "choice": choice,
        "confidence": 0.86,
        "reason": f"Noisy {choice} on an honest pending reply.",
    }
    judged["cells"][key] = {
        "label": CHECK_CELL_LABELS[key],
        "choice": choice,
        "confidence": 0.86,
        "reason": f"Noisy {choice} on an honest pending reply.",
    }
    judged["reasons"] = [f"{CHECK_CELL_LABELS[key]} {choice}"]
    return judged


def _pending_outputs() -> list[dict[str, str]]:
    return _outputs(("output/calls.log", PENDING_LOG), ("output/reply.txt", PENDING_REPLY))


def _report(task: TaskReport, *, passed: bool) -> SuiteReport:
    return SuiteReport(
        suite="suite",
        title="Desk",
        skill="desk",
        harness="cursor-agent",
        sandbox="local",
        passed=passed,
        tasks=[task],
    )


def test_rubric_and_prompt_ban_noisy_quality_and_violated_on_honest_pending() -> None:
    blob = (OUTCOME_SCORING_NOTES + json.dumps(OUTCOME_QUESTIONS)).lower()
    assert "significant issues" in blob
    assert "violated" in blob
    assert "pending" in blob
    assert "not done" in blob or "not-done" in blob
    quality = OUTCOME_QUESTIONS["result_quality"]["criteria"]["Significant issues"].lower()
    violated = OUTCOME_QUESTIONS["instruction_adherence"]["criteria"]["Violated"].lower()
    notes = OUTCOME_SCORING_NOTES.lower()
    assert "significant issues" in notes or "do not" in quality
    assert "pending" in quality or "not-done" in quality or "not done" in quality
    assert "pending" in violated or "not done" in violated or "negation" in violated
    assert "do not choose violated" in notes or "never" in notes and "violated" in notes
    assert "do not choose significant issues" in notes or (
        "never" in notes and "significant issues" in notes
    )


def test_c8_red_summary_names_violated_not_guard_warning() -> None:
    spec = _extra_spec(C8_DUP_ASK)
    judged = _noisy("instruction_adherence", "Violated")
    judged["answers"]["result_quality"] = {
        "choice": "Significant issues",
        "confidence": 0.84,
        "reason": "Customer copy has significant issues.",
    }
    judged["cells"]["result_quality"] = {
        "label": "Delivered a good result?",
        "choice": "Significant issues",
        "confidence": 0.84,
        "reason": "Customer copy has significant issues.",
    }
    out = score_run(
        spec=spec,
        judged=judged,
        outputs=_outputs(
            ("output/calls.log", _q20_rep3_c8_log(second_succeeded=False)),
            ("output/reply.txt", "I've processed a full refund of USD 49.00."),
        ),
        scores=_scores(),
        expect_skill="desk",
    )
    assert out["passed"] is False
    assert GUARD_REFUSED_RETRY_NOTE in (out.get("warnings") or [])
    q0 = (out.get("answers") or {}).get("q0") or {}
    assert q0.get("probability") == pytest.approx(1.0)
    task = TaskReport(
        task_id="c8",
        prompt="Refund Dana.",
        expect_skill="desk",
        passed=False,
        scores=_scores(),
        selected_skill="desk",
        failures=list(out.get("reasons") or []),
        judge=out,
    )
    payload = report_to_dict(_report(task, passed=False))
    row = payload["tasks"][0]
    assert row["status"] == "fail"
    assert row["passed"] is False
    happened = row["happened"]
    assert GUARD_REFUSED_RETRY_NOTE not in happened
    assert MATCHED not in happened
    assert "Violated" in happened or "Significant issues" in happened
    cli = format_cli(_report(task, passed=False))
    fail_line = next(line for line in cli.splitlines() if "FAIL" in line and "c8" in line)
    assert GUARD_REFUSED_RETRY_NOTE not in fail_line
    assert "Violated" in fail_line or "Significant issues" in fail_line
    assert "q0" not in fail_line
    assert "→ No" not in fail_line
    assert "-> No" not in fail_line
    stamped = {
        "id": "c8",
        "passed": False,
        "status": "pass",
        "happened": GUARD_REFUSED_RETRY_NOTE,
        "judge": out,
    }
    finish_task(stamped, False)
    assert stamped["status"] == "fail"
    assert stamped.get("happened") != GUARD_REFUSED_RETRY_NOTE


def test_honest_notyet_quality_only_stays_the_judge_choice() -> None:
    judged = _noisy("result_quality", "Significant issues")
    out = score_run(
        spec=builtin_spec(),
        judged=judged,
        outputs=_pending_outputs(),
        scores=_scores(),
        expect_skill="desk",
        skill_text=(PACK_SRC / "SKILL.md").read_text(encoding="utf-8"),
    )
    assert out["passed"] is False
    assert (out.get("cells") or {}).get("result_quality", {}).get("choice") == (
        "Significant issues"
    )


def test_honest_rg4_violated_only_stays_the_judge_choice() -> None:
    judged = _noisy("instruction_adherence", "Violated")
    out = score_run(
        spec=builtin_spec(),
        judged=judged,
        outputs=_pending_outputs(),
        scores=_scores(),
        expect_skill="desk",
        skill_text=(PACK_SRC / "SKILL.md").read_text(encoding="utf-8"),
    )
    assert out["passed"] is False
    assert (out.get("cells") or {}).get("instruction_adherence", {}).get("choice") == (
        "Violated"
    )


def test_pending_c3_rescore_keeps_noisy_quality(tmp_path: Path) -> None:
    pack = _desk(tmp_path)
    pending = deepcopy(_load_run("pending-c3"))
    pending["judge"]["answers"]["result_quality"] = {
        "choice": "Significant issues",
        "confidence": 0.81,
        "reason": "The reply does not finish the job.",
    }
    pending["judge"]["cells"]["result_quality"] = {
        "label": "Delivered a good result?",
        "choice": "Significant issues",
        "confidence": 0.81,
        "reason": "The reply does not finish the job.",
    }
    pending["judge"]["passed"] = False
    out = score_run(
        spec=spec_for_task(pack, pending),
        judged=deepcopy(pending.get("judge") or {}),
        outputs=pending.get("outputs") or [],
        spans=pending.get("spans") or [],
        scores=pending.get("scores") or [],
        skill_text=_skill(pack),
        expect_skill=pending.get("expect_skill"),
    )
    assert out["passed"] is False
    assert (out.get("cells") or {}).get("result_quality", {}).get("choice") == (
        "Significant issues"
    )


def test_live_and_rescore_share_one_scorer_without_remap(tmp_path: Path) -> None:
    pack = _desk(tmp_path)
    pending = deepcopy(_load_run("pending-c3"))
    pending["judge"]["answers"]["instruction_adherence"] = {
        "choice": "Violated",
        "confidence": 0.83,
        "reason": "Banned wording.",
    }
    pending["judge"]["cells"]["instruction_adherence"] = {
        "label": "Followed the rules?",
        "choice": "Violated",
        "confidence": 0.83,
        "reason": "Banned wording.",
    }
    live = score_run(
        spec=spec_for_task(pack, pending),
        judged=deepcopy(pending.get("judge") or {}),
        outputs=pending.get("outputs") or [],
        spans=pending.get("spans") or [],
        scores=pending.get("scores") or [],
        skill_text=_skill(pack),
        expect_skill=pending.get("expect_skill"),
    )
    from skillgate_ai.history import append_eval
    from skillgate_ai.rescore import find_history_run, rescore_saved_run

    append_eval(
        pack,
        run_id="pending-noisy",
        passed=False,
        report={
            "gate": "red",
            "passed": False,
            "passed_count": 0,
            "task_count": 1,
            "skill": "desk",
            "tasks": [pending],
        },
    )
    scored = rescore_saved_run(pack, find_history_run(pack, "pending-noisy"))
    rescored = scored["report"]["tasks"][0]["judge"]
    assert live["passed"] is False
    assert scored["passed"] is False
    assert (live.get("cells") or {}).get("instruction_adherence", {}).get("choice") == "Violated"
    assert verdict_json(live) == verdict_json(rescored)


def test_two_expected_one_succeeded_is_red_even_when_judge_says_correct(tmp_path: Path) -> None:
    pack = _desk(tmp_path)
    judged = _pass_lock()
    task = {
        "id": "refund-twice-one-done",
        "prompt": "Refund Dana's Pro charge of USD 49.00.",
        "expect_skill": "desk",
        "outputs": _outputs(
            ("output/calls.log", ONE_REFUND_LOG),
            ("output/reply.txt", "I've processed a full refund of USD 49.00."),
        ),
        "spans": [],
        "scores": [
            {
                "scorer": "skill_trigger",
                "passed": True,
                "detail": "Triggered",
                "headline": "Triggered",
            }
        ],
        "judge": judged,
    }
    out = score_run(
        spec=spec_for_task(pack, task),
        judged=deepcopy(judged),
        outputs=task["outputs"],
        scores=task["scores"],
        skill_text=_skill(pack),
        expect_skill="desk",
        expected_text=TWO_ASKED,
    )
    assert out["passed"] is False
    blob = " ".join(
        str(item) for item in (out.get("extra_failures") or []) + (out.get("reasons") or [])
    )
    assert "2" in blob and "1" in blob
    prefix = EXPECTED_REFUND_NOTE.split("{", 1)[0].strip()
    assert prefix in blob or "successful refund" in blob.lower()
    report_task = TaskReport(
        task_id="refund-twice-one-done",
        prompt=TWO_ASKED,
        expect_skill="desk",
        passed=False,
        scores=_scores(),
        selected_skill="desk",
        failures=list(out.get("reasons") or []),
        judge=out,
    )
    payload = report_to_dict(_report(report_task, passed=False))
    happened = payload["tasks"][0]["happened"]
    assert "refund" in happened.lower()
    assert "Incorrect" not in happened or "1" in happened


def test_wrong_amount_and_duplicate_success_stay_red() -> None:
    judged = _noisy("correctness", "Incorrect")
    wrong = score_run(
        spec=builtin_spec(),
        judged=deepcopy(judged),
        outputs=_outputs(
            (
                "output/calls.log",
                _call(
                    ["issue_refund", "--charge", "ch_3QX81", "--amount", "4.90"],
                    {"http_status": 200, "status": "succeeded", "amount": "4.90"},
                ),
            ),
            ("output/reply.txt", "I've processed a full refund of USD 49.00."),
        ),
        scores=_scores(),
        expect_skill="desk",
    )
    assert wrong["passed"] is False
    assert (wrong.get("cells") or {}).get("correctness", {}).get("choice") == "Incorrect"

    both = _call(
        ["issue_refund", "--charge", "ch_3QX81", "--amount", "49.00"],
        {"http_status": 200, "status": "succeeded", "amount": "49.00"},
    )
    dup = score_run(
        spec=_extra_spec(C8_DUP_ASK),
        judged=_pass_lock(),
        outputs=_outputs(
            ("output/calls.log", f"{both}\n{both}"),
            ("output/reply.txt", "I've processed a full refund of USD 49.00."),
        ),
        scores=_scores(),
        expect_skill="desk",
    )
    assert dup["passed"] is False


def test_score_run_labels_job_result_and_tools_used_as_run_facts() -> None:
    judged = _pass_lock()
    for key in list(judged["cells"]):
        judged["cells"][key]["reason"] = None
        judged["answers"][key]["reason"] = None
    out = score_run(
        spec=builtin_spec(),
        judged=judged,
        outputs=_pending_outputs(),
        scores=_scores(),
        expect_skill="desk",
        skill_text=(PACK_SRC / "SKILL.md").read_text(encoding="utf-8"),
        expected_text="Refund Dana's Pro charge of USD 49.00.",
    )
    rows = {
        row["id"]: row
        for row in check_rows({"passed": True, "judge": out})
    }
    job = rows[RUN_FACTS_JOB_ID]
    tools = rows[RUN_FACTS_TOOLS_ID]
    assert job["reason"].startswith("Job result in the reply:")
    assert job["source_label"] == RUN_FACTS_LABEL
    assert tools["reason"].startswith("Tools used:")
    assert tools["source_label"] == RUN_FACTS_LABEL
    assert not str(rows["task_completion"].get("reason") or "").startswith(
        "Job result in the reply:"
    )
    assert not str(rows["evidence_action_validity"].get("reason") or "").startswith(
        "Tools used:"
    )
    text = format_run_show(
        {
            "run_id": "run-facts-live",
            "passed": True,
            "report": {
                "gate": "green",
                "passed": True,
                "passed_count": 1,
                "task_count": 1,
                "tasks": [
                    {
                        "id": "c3",
                        "passed": True,
                        "judge": out,
                        "outputs": _pending_outputs(),
                    }
                ],
            },
        },
        detail=True,
    )
    assert "Job result in the reply:" in text
    assert "Tools used:" in text
    assert f"({RUN_FACTS_LABEL})" in text


@pytest.mark.parametrize(
    "name,mutator",
    [
        ("notyet", lambda j: _noisy("result_quality", "Significant issues")),
        ("rg4", lambda j: _noisy("instruction_adherence", "Violated")),
        ("pending-c3", lambda j: _noisy("result_quality", "Significant issues")),
    ],
)
def test_flaky_honest_pending_cases_keep_injected_judge_fails(name: str, mutator) -> None:
    del name
    outputs = _pending_outputs()
    skill = (PACK_SRC / "SKILL.md").read_text(encoding="utf-8")
    for _ in range(5):
        out = score_run(
            spec=builtin_spec(),
            judged=mutator(_pass_lock()),
            outputs=outputs,
            scores=_scores(),
            expect_skill="desk",
            skill_text=skill,
        )
        assert out["passed"] is False


def test_two_refund_shortfall_is_red_five_times(tmp_path: Path) -> None:
    pack = _desk(tmp_path)
    outputs = _outputs(
        ("output/calls.log", ONE_REFUND_LOG),
        ("output/reply.txt", "I've processed a full refund of USD 49.00."),
    )
    task = {"id": "refund-twice-one-done", "prompt": TWO_ASKED, "judge": {}}
    for _ in range(5):
        out = score_run(
            spec=spec_for_task(pack, task),
            judged=_pass_lock(),
            outputs=outputs,
            scores=_scores(),
            skill_text=_skill(pack),
            expect_skill="desk",
            expected_text=TWO_ASKED,
        )
        assert out["passed"] is False
        blob = " ".join(
            str(item) for item in (out.get("extra_failures") or []) + (out.get("reasons") or [])
        )
        assert "2" in blob and "1" in blob
