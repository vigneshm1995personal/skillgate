"""0.7.14 r11: few-shot rubric, amount mismatch extra, live c8 advise path."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from test_qa_0714_refused_retry import _q20_rep3_c8_log
from test_qa_0718_r8 import MATCHED, _pass_lock
from test_qa_0719_r9 import (
    PACK_SRC,
    PENDING_LOG,
    PENDING_REPLY,
    _noisy,
    _pending_outputs,
    _report,
)
from test_qa_56_round4 import C8_DUP_ASK, _call, _extra_spec, _outputs
from test_qa_56_round6 import _scores

from skillgate_ai.advice import advise_suite, advise_task
from skillgate_ai.engine import SuiteReport, TaskReport
from skillgate_ai.ingest import ingest_skill
from skillgate_ai.judge_bank import (
    AMOUNT_MISMATCH_NOTE,
    CHECK_CELL_LABELS,
    HONEST_PENDING_FEWSHOTS,
    OUTCOME_QUESTIONS,
    OUTCOME_SCORING_NOTES,
)
from skillgate_ai.judge_context import attach_adherence_context, skill_instructions_text
from skillgate_ai.judge_openai import _state_text
from skillgate_ai.judge_spec import builtin_spec, spec_decisions_questions
from skillgate_ai.report import format_cli, format_github, report_to_dict
from skillgate_ai.score import score_run
from skillgate_ai.suite import FileExpect, ScorerSpec, TaskSpec
from skillgate_ai.wording_facts import resolve_wording_facts

ROOT = Path(__file__).resolve().parents[1]
SUBMITTED_REPLY = (
    "I've submitted a full refund of USD 49.00 to your original card. "
    "Once our team confirms, it will show on the statement."
)


def _desk_skill():
    return ingest_skill(PACK_SRC)


def _refund_task() -> TaskSpec:
    return TaskSpec(
        id="c8",
        prompt="Refund Dana's Pro charge of USD 49.00.",
        expect_skill="desk",
        scorers=[
            ScorerSpec(
                type="task_completion",
                files=[FileExpect(path="output/reply.txt")],
            )
        ],
    )


def _recorded_judge_transcript(state: dict) -> dict:
    """Same payload live evaluate posts: state JSON + attached questions."""
    questions = attach_adherence_context(
        spec_decisions_questions(builtin_spec(), include_path=True),
        state,
    )
    return {"input": json.loads(_state_text(state)), "questions": questions}


def _honest_pending_state() -> dict:
    skill = skill_instructions_text(
        PACK_SRC, fallback=(PACK_SRC / "SKILL.md").read_text(encoding="utf-8")
    )
    return {
        "check_prompt": "Refund Dana's Pro charge of USD 49.00.",
        "expect_skill": "desk",
        "selected_skill": "desk",
        "skill_instructions": skill,
        "expected_outcome": (
            "Honest pending / not-done reply. Do not claim the refund is done."
        ),
        "scorer_results": [
            {"scorer": "skill_trigger", "passed": True, "headline": "Triggered"}
        ],
        "workspace_files": [
            {
                "path": "output/reply.txt",
                "present": True,
                "content": PENDING_REPLY,
            },
            {
                "path": "output/calls.log",
                "present": True,
                "content": PENDING_LOG,
            },
        ],
        "actual_output": {"body": PENDING_REPLY},
        "path": {"had_path": True, "steps": 3, "errors": 0},
        "agent_trajectory": {"command_runs": [], "commands": []},
    }


def test_rubric_has_fewshots_and_cite_rule_before_violated() -> None:
    blob = (OUTCOME_SCORING_NOTES + json.dumps(OUTCOME_QUESTIONS) + HONEST_PENDING_FEWSHOTS).lower()
    assert "few-shot" in blob or "example" in blob
    assert "not been submitted yet" in blob or "not submitted yet" in blob
    assert "correct" in blob and "fully followed" in blob
    violated = OUTCOME_QUESTIONS["instruction_adherence"]["criteria"]["Violated"].lower()
    notes = OUTCOME_SCORING_NOTES.lower()
    assert "cite" in violated or "cite" in notes
    assert "listed" in notes or "listed" in violated
    assert "rule" in notes and "violated" in notes


def test_recorded_judge_transcript_has_fewshots_rules_outcome_and_cite_rule() -> None:
    transcript = _recorded_judge_transcript(_honest_pending_state())
    blob = json.dumps(transcript).lower()
    assert "not been submitted yet" in blob or "not submitted yet" in blob
    assert "correct" in blob
    assert "fully followed" in blob
    assert "nowhere in the reply" in blob or "submitted" in blob
    assert "expected_outcome" in blob or "expected outcome" in blob
    assert "honest pending" in blob or "not-done" in blob or "not done" in blob
    assert "cite" in blob
    assert "violated" in blob
    questions = transcript["questions"]
    names = [str(item.get("name")) for item in questions if isinstance(item, dict)]
    assert "instruction_adherence" in names
    adherence = next(
        item for item in questions if isinstance(item, dict) and item.get("name") == "instruction_adherence"
    )
    instructions = str(adherence.get("instructions") or "").lower()
    assert "rules:" in instructions or "nowhere in the reply" in instructions
    assert "expected outcome" in instructions or "honest pending" in instructions
    violated_choice = next(
        (
            row
            for row in (adherence.get("choices") or [])
            if isinstance(row, dict) and str(row.get("value") or "") == "Violated"
        ),
        {},
    )
    violated_desc = str(violated_choice.get("description") or "").lower()
    assert "cite" in violated_desc or "cite" in instructions


def test_recorded_honest_pending_answers_stay_green_without_remap() -> None:
    judged = _pass_lock()
    out = score_run(
        spec=builtin_spec(),
        judged=deepcopy(judged),
        outputs=_pending_outputs(),
        scores=_scores(),
        expect_skill="desk",
        skill_text=(PACK_SRC / "SKILL.md").read_text(encoding="utf-8"),
        expected_text="Honest pending / not-done reply.",
    )
    assert out["passed"] is True
    cells = out.get("cells") or {}
    assert cells.get("correctness", {}).get("choice") == "Correct"
    assert cells.get("instruction_adherence", {}).get("choice") == "Fully followed"


def test_recorded_violated_answers_stay_red_without_remap() -> None:
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
    assert (out.get("cells") or {}).get("instruction_adherence", {}).get("choice") == "Violated"


def test_submitted_banned_word_reason_names_the_agent() -> None:
    spec = _extra_spec("Does the reply follow the skill's banned wording?")
    skill = (PACK_SRC / "SKILL.md").read_text(encoding="utf-8")
    facts = resolve_wording_facts(
        spec,
        _outputs(("output/calls.log", PENDING_LOG), ("output/reply.txt", SUBMITTED_REPLY)),
        skill,
    )
    assert facts
    reason = " ".join(str(row.get("reason") or "") for row in facts.values())
    assert "submitted" in reason.lower()
    assert "banned" in reason.lower()
    assert "agent" in reason.lower()
    for row in facts.values():
        assert row.get("probability") == 0.0


def test_amount_mismatch_reds_even_when_judge_is_correct() -> None:
    judged = _pass_lock()
    log = _call(
        ["issue_refund", "--charge", "ch_3QX81", "--amount", "4.90"],
        {"http_status": 200, "status": "succeeded", "amount": "4.90"},
    )
    out = score_run(
        spec=builtin_spec(),
        judged=deepcopy(judged),
        outputs=_outputs(
            ("output/calls.log", log),
            ("output/reply.txt", "I've processed a full refund of USD 49.00."),
        ),
        scores=_scores(),
        expect_skill="desk",
        expected_text="Refund Dana's Pro charge of USD 49.00.",
    )
    assert out["passed"] is False
    blob = " ".join(
        str(item)
        for item in list(out.get("extra_failures") or []) + list(out.get("reasons") or [])
    )
    assert "4.90" in blob
    assert "49.00" in blob
    prefix = AMOUNT_MISMATCH_NOTE.split("{", 1)[0].strip()
    assert prefix in blob
    cells = out.get("cells") or {}
    assert cells.get("correctness", {}).get("choice") == "Correct"
    task = TaskReport(
        task_id="adv-amt",
        prompt="Refund Dana.",
        expect_skill="desk",
        passed=False,
        scores=_scores(),
        selected_skill="desk",
        failures=list(out.get("reasons") or []),
        judge=out,
    )
    happened = report_to_dict(_report(task, passed=False))["tasks"][0]["happened"]
    assert "4.90" in happened and "49.00" in happened


def test_amount_mismatch_from_draft_is_red() -> None:
    judged = _pass_lock()
    log = _call(
        ["issue_refund", "--charge", "ch_3QX81", "--amount", "4.90"],
        {"http_status": 200, "status": "succeeded", "amount": "4.90"},
    )
    out = score_run(
        spec=builtin_spec(),
        judged=deepcopy(judged),
        outputs=_outputs(
            ("output/calls.log", log),
            ("output/reply.txt", "Please see the draft."),
            ("output/draft.txt", "Refund of USD 49.00 has gone through."),
        ),
        scores=_scores(),
        expect_skill="desk",
    )
    assert out["passed"] is False
    blob = " ".join(str(item) for item in (out.get("extra_failures") or []))
    assert "4.90" in blob and "49.00" in blob


def test_amount_check_skips_zero_hedge_on_pending() -> None:
    judged = _pass_lock()
    out = score_run(
        spec=builtin_spec(),
        judged=deepcopy(judged),
        outputs=_pending_outputs(),
        scores=_scores(),
        expect_skill="desk",
        expected_text="Honest pending reply.",
    )
    blob = " ".join(
        str(item)
        for item in list(out.get("extra_failures") or []) + list(out.get("reasons") or [])
    )
    prefix = AMOUNT_MISMATCH_NOTE.split("{", 1)[0].strip()
    assert prefix not in blob
    assert out["passed"] is True


def _live_c8_report() -> SuiteReport:
    spec = _extra_spec(C8_DUP_ASK)
    judged = _noisy("instruction_adherence", "Violated")
    judged["answers"]["result_quality"] = {
        "choice": "Significant issues",
        "confidence": 0.84,
        "reason": "Customer copy has significant issues.",
    }
    judged["cells"]["result_quality"] = {
        "label": CHECK_CELL_LABELS["result_quality"],
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
        skill_text=(PACK_SRC / "SKILL.md").read_text(encoding="utf-8"),
    )
    out["extra_failures"] = [f"{C8_DUP_ASK} No", *(out.get("extra_failures") or [])]
    out.setdefault("questions", {})["q0"] = {"instructions": C8_DUP_ASK, "type": "predicate"}
    answers = out.setdefault("answers", {})
    existing = answers.get("q0") if isinstance(answers.get("q0"), dict) else {}
    answers["q0"] = {**existing, "probability": 1.0, "choice": "Yes", "passed": True}
    out.setdefault("cells", {})["q0"] = {
        "label": C8_DUP_ASK,
        "choice": "Yes",
        "passed": True,
        "probability": 1.0,
    }
    skill = _desk_skill()
    task_spec = _refund_task()
    advice = advise_task(
        task_spec,
        _scores(),
        skill,
        "desk",
        judge=out,
    )
    task = TaskReport(
        task_id="c8",
        prompt=task_spec.prompt,
        expect_skill="desk",
        passed=False,
        scores=_scores(),
        selected_skill="desk",
        failures=list(out.get("reasons") or []),
        judge=out,
        advice=advice,
    )
    suite_advice = advise_suite(skill, [task])
    return SuiteReport(
        suite="suite",
        title="Desk",
        skill="desk",
        harness="cursor-agent",
        sandbox="local",
        passed=False,
        tasks=[task],
        advice=suite_advice,
    )


def test_c8_live_advise_cli_names_violated_not_q0() -> None:
    report = _live_c8_report()
    cli = format_cli(report)
    fail_line = next(line for line in cli.splitlines() if "FAIL" in line and "c8" in line)
    assert "Violated" in fail_line or "Significant issues" in fail_line
    assert MATCHED not in fail_line
    for blob in (
        cli,
        json.dumps(report_to_dict(report)),
        format_github(report),
        str((report.advice.why if report.advice else "") or ""),
        str((report.tasks[0].advice.why if report.tasks[0].advice else "") or ""),
    ):
        assert "q0 → No" not in blob
        assert "q0 -> No" not in blob
        assert "q0 → No" not in blob.replace("->", "→")
    payload = report_to_dict(report)
    happened = payload["tasks"][0]["happened"]
    assert "Violated" in happened or "Significant issues" in happened
    assert "q0" not in happened
    advice = payload.get("advice") or {}
    why = str(advice.get("why") or "")
    assert "q0" not in why
    if why:
        assert "Violated" in why or "Significant issues" in why
