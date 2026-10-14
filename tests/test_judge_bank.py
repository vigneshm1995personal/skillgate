from __future__ import annotations

from skillgate_ai.judge_bank import (
    CHECK_CELL_ORDER,
    LOW_CONFIDENCE_WARNING,
    PASS_LOCK,
    UNUSABLE_ANSWER,
    canonical_choice,
    decisions_questions,
    low_confidence_warnings,
    outcome_verdict,
    structured_output_schema,
    unusable_answers,
)


def _pass_answers(**overrides: object) -> dict:
    answers = {
        "task_completion": {"choice": "Fully completed", "confidence": 0.9},
        "correctness": {"choice": "Correct", "confidence": 0.9},
        "instruction_adherence": {"choice": "Fully followed", "confidence": 0.9},
        "evidence_action_validity": {"choice": "Fully supported", "confidence": 0.9},
        "result_quality": {"choice": "Clear and complete", "confidence": 0.9},
        "path_efficiency": {"choice": "Efficient", "confidence": 0.9},
    }
    answers.update(overrides)
    return answers


def test_pass_lock_table() -> None:
    passed, reasons = outcome_verdict(_pass_answers())
    assert passed is True
    assert reasons == []

    passed, reasons = outcome_verdict(_pass_answers(correctness={"choice": "Incorrect"}))
    assert passed is False
    assert any("Got it right?" in item for item in reasons)

    passed, reasons = outcome_verdict(
        _pass_answers(path_efficiency={"choice": "Wasteful", "confidence": 0.99})
    )
    assert passed is True
    assert reasons == []

    passed, reasons = outcome_verdict(
        _pass_answers(result_quality={"choice": "Mostly good", "confidence": 0.8})
    )
    assert passed is True

    passed, reasons = outcome_verdict(
        _pass_answers(evidence_action_validity={"choice": "N/A", "confidence": 0.8})
    )
    assert passed is True

    passed, reasons = outcome_verdict(
        _pass_answers(instruction_adherence={"choice": "Minor deviation", "confidence": 0.8})
    )
    assert passed is True
    assert reasons == []

    passed, reasons = outcome_verdict(
        _pass_answers(correctness={"choice": "Mostly correct", "confidence": 0.8})
    )
    assert passed is True

    passed, reasons = outcome_verdict(
        _pass_answers(
            evidence_action_validity={"choice": "Partially supported", "confidence": 0.8}
        )
    )
    assert passed is True

    passed, reasons = outcome_verdict(
        _pass_answers(
            instruction_adherence={"choice": "Major deviation", "confidence": 0.8}
        )
    )
    assert passed is True


def test_missing_or_unknown_choice_fails_closed() -> None:
    answers = _pass_answers()
    del answers["correctness"]
    passed, reasons = outcome_verdict(answers)
    assert passed is False
    assert reasons == [UNUSABLE_ANSWER]
    assert unusable_answers(answers) is True

    passed, reasons = outcome_verdict(_pass_answers(correctness={"choice": "Pretty good"}))
    assert passed is False
    assert reasons == [UNUSABLE_ANSWER]


def test_case_insensitive_canonical_choice() -> None:
    assert canonical_choice("correctness", "correct") == "Correct"
    assert canonical_choice("correctness", "  CORRECT  ") == "Correct"
    assert canonical_choice("correctness", "nope") is None


def test_low_confidence_keeps_pass_and_warns() -> None:
    answers = _pass_answers(correctness={"choice": "Correct", "confidence": 0.2})
    passed, reasons = outcome_verdict(answers)
    assert passed is True
    assert reasons == []
    assert low_confidence_warnings(answers) == [LOW_CONFIDENCE_WARNING]


def test_missing_confidence_warns_on_decisions_only() -> None:
    answers = _pass_answers(correctness={"choice": "Correct"})
    answers["correctness"].pop("confidence", None)
    assert outcome_verdict(answers)[0] is True
    assert low_confidence_warnings(answers, expect_confidence=True) == [LOW_CONFIDENCE_WARNING]
    assert low_confidence_warnings(answers, expect_confidence=False) == []


def test_low_confidence_does_not_warn_on_fail() -> None:
    answers = _pass_answers(correctness={"choice": "Incorrect", "confidence": 0.1})
    assert outcome_verdict(answers)[0] is False
    assert low_confidence_warnings(answers) == []


def test_path_is_not_in_pass_lock() -> None:
    assert "path_efficiency" not in PASS_LOCK
    assert set(PASS_LOCK) == set(CHECK_CELL_ORDER)


def test_decisions_questions_omit_path_when_asked() -> None:
    questions = decisions_questions(include_path=False)
    names = [item["name"] for item in questions]
    assert "path_efficiency" not in names
    assert names == list(CHECK_CELL_ORDER)
    schema = structured_output_schema(include_path=False)
    assert "path_efficiency" not in schema["properties"]
    assert set(schema["required"]) == set(CHECK_CELL_ORDER)


def test_decisions_questions_and_schema_match_bank() -> None:
    questions = decisions_questions()
    names = [item["name"] for item in questions]
    assert names[:5] == list(CHECK_CELL_ORDER)
    assert "path_efficiency" in names
    assert all(item["type"] == "choice" for item in questions)
    task = next(item for item in questions if item["name"] == "task_completion")
    assert set(task.keys()) == {"type", "name", "instructions", "choices"}
    assert task["instructions"] == "Got the job done? Pick exactly one."
    assert [row["value"] for row in task["choices"]] == [
        "Fully completed",
        "Partially completed",
        "Not completed",
    ]
    path_q = next(item for item in questions if item["name"] == "path_efficiency")
    assert "path.steps" not in path_q["instructions"]
    assert "Pick exactly one." in path_q["instructions"]
    for item in questions:
        if item["name"] in CHECK_CELL_ORDER:
            assert item["instructions"].endswith("Pick exactly one.")
    schema = structured_output_schema()
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
    assert schema["properties"]["correctness"]["enum"][0] == "Correct"
