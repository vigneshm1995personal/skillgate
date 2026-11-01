"""0.7.14 r10: never remap judge verdicts; run facts as separate rows; c8 names Violated."""

from __future__ import annotations

import inspect
from copy import deepcopy
from pathlib import Path

import pytest
from test_qa_0714_refused_retry import _q20_rep3_c8_log
from test_qa_0718_r8 import MATCHED, _load_run, _pass_lock
from test_qa_0719_r9 import (
    PACK_SRC,
    PENDING_LOG,
    PENDING_REPLY,
    _desk,
    _noisy,
    _pending_outputs,
    _report,
    _skill,
)
from test_qa_56_round4 import C8_DUP_ASK, _call, _extra_spec, _outputs
from test_qa_56_round6 import _scores

from skillgate_ai.engine import TaskReport
from skillgate_ai.judge_bank import (
    CHECK_CELL_LABELS,
    CHECK_CELL_ORDER,
    OUTCOME_QUESTIONS,
    OUTCOME_SCORING_NOTES,
    RUN_FACTS_JOB_ID,
    RUN_FACTS_LABEL,
    RUN_FACTS_TOOLS_ID,
    votes_line,
)
from skillgate_ai.judge_spec import builtin_spec
from skillgate_ai.report import format_cli, report_to_dict
from skillgate_ai.run_details import check_rows, format_run_show
from skillgate_ai.score import finish_task, score_run, spec_for_task, verdict_json

ROOT = Path(__file__).resolve().parents[1]
FALSE_DONE_REPLY = "The refund is done. I've processed a full refund of USD 49.00."


def _false_done_outputs() -> list[dict[str, str]]:
    return _outputs(("output/calls.log", PENDING_LOG), ("output/reply.txt", FALSE_DONE_REPLY))


def test_score_run_has_no_honest_pending_remap() -> None:
    from skillgate_ai import score as score_mod

    source = inspect.getsource(score_mod.score_run)
    assert "remap_honest_pending" not in source
    assert not hasattr(score_mod, "remap_honest_pending")


def test_rubric_says_false_done_claim_is_incorrect() -> None:
    blob = (OUTCOME_SCORING_NOTES + json_blob()).lower()
    assert "falsely" in blob or "false" in blob
    assert "done" in blob
    assert "incorrect" in blob
    assert "violated" in blob


def json_blob() -> str:
    import json

    return json.dumps(OUTCOME_QUESTIONS)


def test_false_done_claim_keeps_incorrect_and_stays_red() -> None:
    judged = _noisy("correctness", "Incorrect")
    judged["answers"]["instruction_adherence"] = {
        "choice": "Violated",
        "confidence": 0.88,
        "reason": "The agent claimed the refund was done.",
    }
    judged["cells"]["instruction_adherence"] = {
        "label": CHECK_CELL_LABELS["instruction_adherence"],
        "choice": "Violated",
        "confidence": 0.88,
        "reason": "The agent claimed the refund was done.",
    }
    out = score_run(
        spec=builtin_spec(),
        judged=judged,
        outputs=_false_done_outputs(),
        scores=_scores(),
        expect_skill="desk",
        skill_text=(PACK_SRC / "SKILL.md").read_text(encoding="utf-8"),
    )
    assert out["passed"] is False
    cells = out.get("cells") or {}
    assert cells.get("correctness", {}).get("choice") == "Incorrect"
    assert cells.get("instruction_adherence", {}).get("choice") == "Violated"
    assert cells.get("correctness", {}).get("choice") != "Correct"
    rows = {row["id"]: row for row in check_rows({"passed": False, "judge": out})}
    assert rows["correctness"]["answer"] == "Incorrect"
    assert rows["instruction_adherence"]["answer"] == "Violated"


def test_partially_completed_is_not_rewritten_to_fully_completed() -> None:
    judged = _noisy("task_completion", "Partially completed")
    out = score_run(
        spec=builtin_spec(),
        judged=judged,
        outputs=_pending_outputs(),
        scores=_scores(),
        expect_skill="desk",
        skill_text=(PACK_SRC / "SKILL.md").read_text(encoding="utf-8"),
    )
    assert out["passed"] is False
    assert (out.get("cells") or {}).get("task_completion", {}).get("choice") == (
        "Partially completed"
    )


def test_injected_quality_fail_stays_significant_issues() -> None:
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


def test_judge_verdict_stays_visible_when_run_facts_exist() -> None:
    judged = _noisy("correctness", "Incorrect")
    judged["cells"]["correctness"]["reason"] = "The agent claimed a refund that did not go through."
    judged["answers"]["correctness"]["reason"] = judged["cells"]["correctness"]["reason"]
    out = score_run(
        spec=builtin_spec(),
        judged=judged,
        outputs=_false_done_outputs(),
        scores=_scores(),
        expect_skill="desk",
        skill_text=(PACK_SRC / "SKILL.md").read_text(encoding="utf-8"),
        expected_text="Refund Dana's Pro charge of USD 49.00.",
    )
    assert out["passed"] is False
    rows = {row["id"]: row for row in check_rows({"passed": False, "judge": out})}
    assert rows["correctness"]["answer"] == "Incorrect"
    assert "claimed a refund" in (rows["correctness"].get("reason") or "")
    assert not str(rows["correctness"].get("reason") or "").startswith("Job result")
    assert rows["correctness"]["source_label"] == "from the judge"
    assert RUN_FACTS_JOB_ID in rows
    assert rows[RUN_FACTS_JOB_ID]["source_label"] == RUN_FACTS_LABEL
    assert rows[RUN_FACTS_TOOLS_ID]["source_label"] == RUN_FACTS_LABEL
    text = format_run_show(
        {
            "run_id": "c1-502",
            "passed": False,
            "report": {
                "gate": "red",
                "passed": False,
                "passed_count": 0,
                "task_count": 1,
                "tasks": [
                    {
                        "id": "c1",
                        "passed": False,
                        "judge": out,
                        "outputs": _false_done_outputs(),
                    }
                ],
            },
        },
        detail=True,
    )
    assert "Incorrect" in text
    assert "Job result in the reply:" in text
    assert f"({RUN_FACTS_LABEL})" in text


def test_run_facts_are_separate_rows_not_builtin_reasons() -> None:
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
    rows = {row["id"]: row for row in check_rows({"passed": True, "judge": out})}
    for key in CHECK_CELL_ORDER:
        reason = str(rows[key].get("reason") or "")
        assert not reason.startswith("Job result in the reply:")
        assert not reason.startswith("Tools used:")
        if reason in {"", "No reason recorded"}:
            assert rows[key].get("source_label") in {"", None}
    assert rows[RUN_FACTS_JOB_ID]["reason"].startswith("Job result in the reply:")
    assert rows[RUN_FACTS_JOB_ID]["source_label"] == RUN_FACTS_LABEL
    assert rows[RUN_FACTS_TOOLS_ID]["reason"].startswith("Tools used:")
    assert rows[RUN_FACTS_TOOLS_ID]["source_label"] == RUN_FACTS_LABEL


def test_c8_cli_summary_line_names_violated_not_q0() -> None:
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
    out["extra_failures"] = [f"{C8_DUP_ASK} No", *(out.get("extra_failures") or [])]
    out["reasons"] = [f"{C8_DUP_ASK} No"]
    out.setdefault("questions", {})["q0"] = {"instructions": C8_DUP_ASK, "type": "predicate"}
    q0 = {"probability": 0.0, "choice": "No", "passed": False}
    answers = out.setdefault("answers", {})
    existing = answers.get("q0") if isinstance(answers.get("q0"), dict) else {}
    answers["q0"] = {**existing, **q0}
    out.setdefault("cells", {})["q0"] = {
        "label": C8_DUP_ASK,
        "choice": "No",
        "passed": False,
        "probability": 0.0,
    }
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
    cli = format_cli(_report(task, passed=False))
    fail_line = next(
        line for line in cli.splitlines() if "FAIL" in line and "c8" in line
    )
    assert "Violated" in fail_line or "Significant issues" in fail_line
    assert "q0" not in fail_line
    assert "→ No" not in fail_line
    assert "-> No" not in fail_line
    happened = report_to_dict(_report(task, passed=False))["tasks"][0]["happened"]
    assert "Violated" in happened or "Significant issues" in happened
    assert "q0" not in happened
    assert MATCHED not in fail_line


def test_live_and_rescore_keep_the_same_judge_choices(tmp_path: Path) -> None:
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
    assert (rescored.get("cells") or {}).get("instruction_adherence", {}).get("choice") == (
        "Violated"
    )
    assert verdict_json(live)["builtins"]["instruction_adherence"]["choice"] == (
        verdict_json(rescored)["builtins"]["instruction_adherence"]["choice"]
    )


def test_majority_votes_are_shown_on_each_check() -> None:
    judged = _noisy("correctness", "Incorrect")
    judged["votes"] = [
        {"correctness": {"choice": "Incorrect", "confidence": 0.4}},
        {"correctness": {"choice": "Correct", "confidence": 0.7}},
        {"correctness": {"choice": "Incorrect", "confidence": 0.6}},
    ]
    out = score_run(
        spec=builtin_spec(),
        judged=judged,
        outputs=_false_done_outputs(),
        scores=_scores(),
        expect_skill="desk",
    )
    assert out.get("votes") == judged["votes"]
    line = votes_line(out.get("votes"), "correctness")
    assert line is not None
    assert "1 Incorrect" in line
    assert "2 Correct" in line
    assert "3 Incorrect" in line
    rows = {row["id"]: row for row in check_rows({"passed": False, "judge": out})}
    assert "1 Incorrect" in str(rows["correctness"].get("votes") or "")
    text = format_run_show(
        {
            "run_id": "votes",
            "passed": False,
            "report": {
                "gate": "red",
                "passed": False,
                "passed_count": 0,
                "task_count": 1,
                "tasks": [{"id": "c1", "passed": False, "judge": out}],
            },
        },
        detail=True,
    )
    assert "votes:" in text
    assert "Incorrect" in text


@pytest.mark.parametrize(
    "key,choice",
    [
        ("correctness", "Incorrect"),
        ("instruction_adherence", "Violated"),
        ("result_quality", "Significant issues"),
        ("task_completion", "Partially completed"),
    ],
)
def test_noisy_judge_fail_repeats_five_times(key: str, choice: str) -> None:
    skill = (PACK_SRC / "SKILL.md").read_text(encoding="utf-8")
    for _ in range(5):
        out = score_run(
            spec=builtin_spec(),
            judged=_noisy(key, choice),
            outputs=_pending_outputs(),
            scores=_scores(),
            expect_skill="desk",
            skill_text=skill,
        )
        assert out["passed"] is False
        assert (out.get("cells") or {}).get(key, {}).get("choice") == choice


def test_finish_task_keeps_named_fail(tmp_path: Path) -> None:
    del tmp_path
    judged = _noisy("instruction_adherence", "Violated")
    out = score_run(
        spec=builtin_spec(),
        judged=judged,
        outputs=_pending_outputs(),
        scores=_scores(),
        expect_skill="desk",
    )
    stamped = {
        "id": "started",
        "passed": False,
        "status": "pass",
        "happened": MATCHED,
        "judge": out,
    }
    finish_task(stamped, False)
    assert stamped["status"] == "fail"
    assert stamped.get("happened") != MATCHED
