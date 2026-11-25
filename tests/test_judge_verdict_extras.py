from __future__ import annotations

from skillgate_ai.judge_spec import JudgeQuestion, JudgeSpec
from skillgate_ai.judge_spec.verdict import (
    coerce_extra_answer,
    extra_block_failures,
    extra_question_passed,
    low_confidence_for_spec,
)


def test_extra_question_predicate_requires_probability() -> None:
    question = JudgeQuestion(
        id="q1",
        type="predicate",
        ask="Did it work?",
        on_fail="block",
    )
    ok, detail = extra_question_passed(question, {"probability": 0.95})
    assert ok is True
    ok2, detail2 = extra_question_passed(question, {"probability": 0.1})
    assert ok2 is False
    assert detail2


def test_extra_question_score_checks_threshold() -> None:
    question = JudgeQuestion(
        id="q2",
        type="score",
        ask="Quality?",
        on_fail="block",
        pass_if={"gte": 0.8},
    )
    ok, _ = extra_question_passed(question, {"score": 0.9})
    assert ok is True
    fail, detail = extra_question_passed(question, {"score": 0.2})
    assert fail is False
    assert detail


def test_extra_block_failures_collects_blocking_predicates() -> None:
    spec = JudgeSpec(
        questions=(JudgeQuestion(id="q1", type="predicate", ask="Works?", on_fail="block"),)
    )
    failures = extra_block_failures(spec, {"q1": {"probability": 0.1}})
    assert failures


def test_low_confidence_for_spec_warns_on_weak_choice() -> None:
    spec = JudgeSpec(
        questions=(
            JudgeQuestion(
                id="task_completion",
                type="choice",
                ask="Completed?",
                on_fail="block",
                builtin=True,
                choices=({"value": "fully completed", "pass": True},),
            ),
        )
    )
    warnings = low_confidence_for_spec(
        spec,
        {"task_completion": {"choice": "fully completed", "confidence": 0.2}},
        min_confidence=0.8,
    )
    assert warnings


def test_coerce_extra_answer_wraps_scalar_predicate() -> None:
    wrapped = coerce_extra_answer(0.9, kind="predicate")
    assert isinstance(wrapped, dict)
    assert wrapped.get("probability") == 0.9
