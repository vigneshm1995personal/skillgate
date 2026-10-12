from __future__ import annotations

from pathlib import Path

import pytest

from skillgate_ai.errors import SuiteError
from skillgate_ai.judge_bank import (
    CHECK_CELL_ORDER,
    SOFT_CELL_ORDER,
    decisions_questions,
    outcome_verdict,
)
from skillgate_ai.judge_spec import (
    MAX_QUESTIONS,
    builtin_spec,
    coerce_extra_answer,
    extra_question_passed,
    resolve_judge_spec,
    spec_decisions_questions,
    spec_verdict,
)


def _pass_answers() -> dict:
    return {
        "task_completion": {"choice": "Fully completed", "confidence": 0.9},
        "correctness": {"choice": "Correct", "confidence": 0.9},
        "instruction_adherence": {"choice": "Fully followed", "confidence": 0.9},
        "evidence_action_validity": {"choice": "Fully supported", "confidence": 0.9},
        "result_quality": {"choice": "Clear and complete", "confidence": 0.9},
        "path_efficiency": {"choice": "Efficient", "confidence": 0.9},
    }


def test_pack_without_judge_is_six_builtin_questions() -> None:
    spec = resolve_judge_spec()
    assert [q.id for q in spec.questions] == list(CHECK_CELL_ORDER) + list(SOFT_CELL_ORDER)
    assert all(q.builtin for q in spec.questions)
    assert spec_decisions_questions(spec) == decisions_questions(include_path=True)


def test_extras_append_after_builtins() -> None:
    spec = resolve_judge_spec(
        pack={
            "extra_questions": [
                {
                    "id": "numbers_match",
                    "type": "predicate",
                    "ask": "Do the totals match?",
                    "on_fail": "block",
                    "pass_if": {"gte": 0.8},
                }
            ]
        }
    )
    names = [q.id for q in spec.questions]
    assert names[:6] == list(CHECK_CELL_ORDER) + list(SOFT_CELL_ORDER)
    assert names[-1] == "numbers_match"
    payload = spec_decisions_questions(spec)
    assert [row["name"] for row in payload] == names
    assert payload[-1]["type"] == "predicate"


def test_reserved_id_is_a_suite_error() -> None:
    with pytest.raises(SuiteError) as caught:
        resolve_judge_spec(
            pack={
                "extra_questions": [
                    {
                        "id": "correctness",
                        "type": "choice",
                        "ask": "Got it right?",
                        "choices": [{"value": "Yes", "pass": True}],
                    }
                ]
            }
        )
    assert caught.value.exit_code == 2
    assert "`correctness` is a Skill Gate question" in caught.value.message
    assert "Fail vs warn" in caught.value.message


def test_on_fail_warn_does_not_fail_that_builtin() -> None:
    spec = resolve_judge_spec(pack={"on_fail": {"result_quality": "warn"}})
    answers = _pass_answers()
    answers["result_quality"] = {"choice": "Poor", "confidence": 0.9}
    passed, reasons, warnings = spec_verdict(spec, answers, supports_confidence=True)
    assert passed is True
    assert reasons == []
    assert any("good result" in item.lower() or "Poor" in item for item in warnings)

    answers["correctness"] = {"choice": "Incorrect", "confidence": 0.9}
    passed, reasons, _ = spec_verdict(spec, answers, supports_confidence=True)
    assert passed is False
    assert reasons


def test_per_case_extras_append_for_that_case_only() -> None:
    pack = {
        "extra_questions": [
            {
                "id": "pack_extra",
                "type": "predicate",
                "ask": "Pack-wide?",
                "pass_if": {"gte": 0.8},
            }
        ]
    }
    case = {
        "extra_questions": [
            {
                "id": "currency_usd",
                "type": "choice",
                "ask": "Is the currency USD?",
                "choices": [
                    {"value": "Yes", "description": "USD", "pass": True},
                    {"value": "No", "description": "Other", "pass": False},
                ],
            }
        ]
    }
    other = resolve_judge_spec(pack=pack)
    this = resolve_judge_spec(pack=pack, case=case)
    assert [q.id for q in other.questions][-1] == "pack_extra"
    assert "currency_usd" not in [q.id for q in other.questions]
    assert [q.id for q in this.questions][-2:] == ["pack_extra", "currency_usd"]


def test_project_extras_then_pack_extras() -> None:
    spec = resolve_judge_spec(
        project={
            "extra_questions": [
                {"id": "project_q", "type": "predicate", "ask": "Project?", "pass_if": {"gte": 0.5}}
            ]
        },
        pack={
            "extra_questions": [
                {"id": "pack_q", "type": "predicate", "ask": "Pack?", "pass_if": {"gte": 0.5}}
            ]
        },
    )
    ids = [q.id for q in spec.questions]
    assert ids[-2:] == ["project_q", "pack_q"]


def test_twenty_question_cap() -> None:
    extras = [
        {
            "id": f"extra_{i}",
            "type": "predicate",
            "ask": f"Q{i}?",
            "pass_if": {"gte": 0.5},
        }
        for i in range(1, 16)
    ]
    with pytest.raises(SuiteError) as caught:
        resolve_judge_spec(pack={"extra_questions": extras})
    assert "at most 20" in caught.value.message
    assert str(MAX_QUESTIONS) in caught.value.message or "20" in caught.value.message


def test_extra_fail_blocks_when_on_fail_block() -> None:
    spec = resolve_judge_spec(
        pack={
            "extra_questions": [
                {
                    "id": "numbers_match",
                    "type": "predicate",
                    "ask": "Do the totals match?",
                    "on_fail": "block",
                    "pass_if": {"gte": 0.8},
                }
            ]
        }
    )
    answers = _pass_answers()
    answers["numbers_match"] = {"probability": 0.2}
    passed, reasons, _ = spec_verdict(spec, answers)
    assert passed is False
    assert any("totals match" in item.lower() or "numbers_match" in item for item in reasons)


def test_low_confidence_only_when_provider_supports_it() -> None:
    spec = builtin_spec()
    answers = _pass_answers()
    answers["task_completion"] = {"choice": "Fully completed"}
    passed, _, warnings = spec_verdict(spec, answers, supports_confidence=True)
    assert passed is True
    assert warnings == ["The judge wasn't very sure about this one."]
    passed, _, warnings = spec_verdict(spec, answers, supports_confidence=False)
    assert passed is True
    assert warnings == []


def test_builtin_verdict_matches_today_for_empty_spec() -> None:
    spec = builtin_spec()
    answers = _pass_answers()
    passed, reasons, _ = spec_verdict(spec, answers)
    expected_ok, expected_reasons = outcome_verdict(answers)
    assert passed is expected_ok
    assert reasons == expected_reasons


def test_skipped_extras_do_not_fail_the_check() -> None:
    spec = resolve_judge_spec(
        pack={
            "extra_questions": [
                {
                    "id": "numbers_match",
                    "type": "predicate",
                    "ask": "Totals match?",
                    "on_fail": "block",
                    "pass_if": {"gte": 0.8},
                }
            ]
        }
    )
    passed, reasons, _ = spec_verdict(spec, _pass_answers(), skipped=["numbers_match"])
    assert passed is True
    assert reasons == []


def test_score_extra_decisions_payload_includes_levels() -> None:
    spec = resolve_judge_spec(
        pack={
            "extra_questions": [
                {
                    "id": "quality_score",
                    "type": "score",
                    "ask": "How complete is the result?",
                    "on_fail": "block",
                    "pass_if": {"gte": 0.7},
                }
            ]
        }
    )
    extra = next(row for row in spec_decisions_questions(spec) if row["name"] == "quality_score")
    assert extra["type"] == "score"
    assert isinstance(extra.get("levels"), list)
    assert len(extra["levels"]) >= 2
    assert all(isinstance(item, dict) and str(item.get("label") or "").strip() for item in extra["levels"])


def test_numeric_score_extra_passes_after_coerce() -> None:
    spec = resolve_judge_spec(
        pack={
            "extra_questions": [
                {
                    "id": "quality_score",
                    "type": "score",
                    "ask": "How complete is the result?",
                    "on_fail": "block",
                    "pass_if": {"gte": 0.7},
                }
            ]
        }
    )
    coerced = coerce_extra_answer(0.9, kind="score")
    ok, detail = extra_question_passed(spec.extras[0], coerced)
    assert ok is True
    assert detail is None
    answers = _pass_answers()
    answers["quality_score"] = coerced
    passed, reasons, _ = spec_verdict(spec, answers)
    assert passed is True
    assert reasons == []


def test_unknown_type_is_plain() -> None:
    with pytest.raises(SuiteError) as caught:
        resolve_judge_spec(
            pack={
                "extra_questions": [
                    {"id": "ranked", "type": "ranking", "ask": "Rank these"}
                ]
            }
        )
    assert "Yes/No, pick one, or score" in caught.value.message


def test_seed_cases_cannot_be_removed_once_saved(tmp_path: Path) -> None:
    from skillgate_ai.case_pack import CasePack, PackCase, save_case_pack
    from skillgate_ai.errors import SuiteError
    from skillgate_ai.pack_schema import SEED_CASE_IDS

    dest = tmp_path / "pdf"
    dest.mkdir()
    (dest / "SKILL.md").write_text("---\nname: pdf\ndescription: d\n---\n# pdf\n", encoding="utf-8")
    first = CasePack(
        schema_version=1,
        skill="pdf",
        cases=[
            PackCase(id=case_id, status="pinned", prompt=case_id)
            for case_id in sorted(SEED_CASE_IDS["pdf"])
        ],
    )
    save_case_pack(dest, first)
    with pytest.raises(SuiteError) as caught:
        save_case_pack(
            dest,
            CasePack(
                schema_version=1,
                skill="pdf",
                cases=[PackCase(id="extract-hello", status="pinned", prompt="Extract hello")],
            ),
        )
    assert caught.value.exit_code == 2
    assert "original checks stay" in caught.value.message.lower()
    assert "seed checks cannot be removed" not in caught.value.message.lower()


def test_dump_seed_pack_omits_empty_judge(tmp_path: Path) -> None:
    from skillgate_ai.case_pack import CasePack, PackCase, save_case_pack

    dest = tmp_path / "notes"
    dest.mkdir()
    (dest / "SKILL.md").write_text("---\nname: notes\ndescription: d\n---\n# notes\n", encoding="utf-8")
    pack = CasePack(
        schema_version=1,
        skill="notes",
        cases=[
            PackCase(id="extract-hello", status="pinned", prompt="Extract hello"),
        ],
    )
    path = save_case_pack(dest, pack)
    text = path.read_text(encoding="utf-8")
    assert "judge:" not in text
