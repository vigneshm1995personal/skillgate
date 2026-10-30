"""QA follow-up on PR #56: sabotaged packs stay red; adherence gets rules+evidence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import plain_text
from test_judge_openai import FakePost, FakeResponse, _judge, _score, decisions_payload
from typer.testing import CliRunner

from skillgate_ai.case_pack import load_case_pack
from skillgate_ai.cli import app
from skillgate_ai.engine import SuiteReport, TaskReport, _live_verdict
from skillgate_ai.ingest import ingest_skill
from skillgate_ai.judge_bank import OUTCOME_QUESTIONS, OUTCOME_SCORING_NOTES
from skillgate_ai.judge_spec import (
    JudgeQuestion,
    JudgeSpec,
    builtin_questions,
    parse_extra_question,
)
from skillgate_ai.report import format_cli, report_to_dict
from skillgate_ai.scorers import TriggerEvidence, score_skill_trigger
from skillgate_ai.span_facts import LOG_FACT_KINDS, log_fact_kind
from skillgate_ai.suite import TaskSpec

ROOT = Path(__file__).resolve().parents[1]
runner = CliRunner()


@pytest.fixture(autouse=True)
def _never_touch_real_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    monkeypatch.chdir(tmp_path)


def _pdf_task(skill: str, prompt: str, *, expect: str | None) -> TaskSpec:
    return TaskSpec(
        id="extract-hello",
        prompt=prompt,
        expect_skill=expect,
        scorers=[],
    )


def test_meal_planner_description_fails_trigger_even_when_selected() -> None:
    skill = ingest_skill(ROOT / "skills" / "pdf-sabotaged")
    task = _pdf_task(
        skill.name,
        "Extract the text from hello.pdf and save it to output/extracted.txt",
        expect=skill.name,
    )
    score = score_skill_trigger(
        task,
        TriggerEvidence(selected_skill=skill.name, read_paths=[], transcript=""),
        skills=[skill],
    )
    assert score.passed is False
    assert "description" in score.detail.lower()


def test_pdf_description_still_triggers_on_pdf_prompt() -> None:
    skill = ingest_skill(ROOT / "skills" / "pdf")
    task = _pdf_task(
        skill.name,
        "Extract the text from hello.pdf and save it to output/extracted.txt",
        expect=skill.name,
    )
    score = score_skill_trigger(
        task,
        TriggerEvidence(selected_skill=skill.name, read_paths=[], transcript=""),
        skills=[skill],
    )
    assert score.passed is True


def test_example_trigger_prompts_keep_good_packs_and_fail_sabotaged() -> None:
    good = ingest_skill(ROOT / "skills" / "pdf")
    bad = ingest_skill(ROOT / "skills" / "pdf-sabotaged")
    pack = load_case_pack(ROOT / "skills" / "pdf-sabotaged")
    assert pack is not None
    for case in pack.cases:
        if not case.should_trigger:
            continue
        task = _pdf_task(bad.name, case.prompt, expect=bad.name)
        missed = score_skill_trigger(
            task,
            TriggerEvidence(selected_skill=bad.name, read_paths=[], transcript=""),
            skills=[bad],
        )
        kept = score_skill_trigger(
            _pdf_task(good.name, case.prompt, expect=good.name),
            TriggerEvidence(selected_skill=good.name, read_paths=[], transcript=""),
            skills=[good],
        )
        assert missed.passed is False, case.id
        assert kept.passed is True, case.id


def test_trigger_miss_cannot_pass_or_review_even_if_judge_is_green() -> None:
    passed, failures, judged = _live_verdict(
        {
            "status": "completed",
            "passed": True,
            "review": True,
            "reasons": [],
            "warnings": ["unsure, needs review"],
        },
        "pdf-sabotaged",
        det_passed=True,
        det_failures=[],
        trigger_passed=False,
    )
    assert passed is False
    assert judged is not None
    assert judged.get("passed") is False
    assert any("trigger" in item.lower() or "description" in item.lower() for item in failures)


def test_followed_the_rules_sends_skill_rules_and_scorer_evidence() -> None:
    post = FakePost([FakeResponse(200, decisions_payload(confidence=0.91))])
    judged = _score(
        _judge(post),
        scores=[
            {
                "scorer": "skill_trigger",
                "passed": True,
                "headline": "Skill triggered",
                "detail": "Triggered `pdf`",
            },
            {
                "scorer": "task_completion",
                "passed": True,
                "headline": "Task completed",
                "detail": "All expected outputs present",
            },
        ],
        skill_instructions=(
            "OUTCOME notes\n\n--- SKILL.md ---\n"
            "description: Process PDF files — extract text.\n"
            "Prefer bundled scripts over ad-hoc code."
        ),
        expected_outcome="Hello Skill Gate",
    )
    assert judged["status"] == "completed"
    payload = post.calls[0]["json"]
    questions = payload["questions"]
    if isinstance(questions, list):
        adherence = next(item for item in questions if item.get("name") == "instruction_adherence")
        blob = json.dumps(adherence).lower()
    else:
        blob = json.dumps(questions["instruction_adherence"]).lower()
    assert "process pdf" in blob or "bundled scripts" in blob
    assert "skill_trigger" in blob or "triggered" in blob
    assert "hello skill gate" in blob
    notes = (
        str(OUTCOME_QUESTIONS["instruction_adherence"]["criteria"]["Fully followed"])
        + "\n"
        + OUTCOME_SCORING_NOTES
    ).lower()
    assert "listed" in notes and "rule" in notes
    assert "do not hedge" in notes or "do not split" in notes


def test_custom_check_source_is_log_or_judge_in_cli_json() -> None:
    task = TaskReport(
        task_id="write-note",
        prompt="Write the note.",
        expect_skill="note-once",
        passed=True,
        scores=[],
        selected_skill="note-once",
        judge={
            "status": "completed",
            "passed": True,
            "cells": {
                "no_duplicate_read": {
                    "label": "Did the agent read status.txt at most once?",
                    "choice": "Yes",
                    "probability": 1.0,
                    "source": "log",
                }
            },
            "answers": {
                "no_duplicate_read": {"probability": 1.0, "source": "log"},
            },
            "questions": {
                "no_duplicate_read": {
                    "type": "predicate",
                    "instructions": "Did the agent read status.txt at most once?",
                }
            },
        },
    )
    report = SuiteReport(
        suite="suite",
        title="Notes",
        skill="note-once",
        harness="cursor-agent",
        sandbox="local",
        passed=True,
        tasks=[task],
    )
    cli = format_cli(report)
    payload = report_to_dict(report)
    assert "from the log" in cli.lower()
    extra = payload["tasks"][0]["check_answers"][-1]
    assert extra["source"] == "log"
    assert payload["tasks"][0]["judge"]["cells"]["no_duplicate_read"]["source"] == "log"
    assert "noul" not in json.dumps(payload["tasks"][0]["judge"]["answers"])


def test_log_fact_wording_is_documented() -> None:
    assert log_fact_kind("Answer NO if the agent called issue_refund more than once.") == "count"
    assert log_fact_kind("Did the agent call lookup_order?") == "called"
    assert log_fact_kind("Did issue_refund return success?") == "return"
    assert log_fact_kind("Did the customer reply yes?") is None
    assert set(LOG_FACT_KINDS) == {"count", "called", "return"}


def test_public_predicate_answer_drops_noul() -> None:
    spec = JudgeSpec(
        questions=tuple(
            builtin_questions()
            + [
                JudgeQuestion(
                    id="no_dup",
                    type="predicate",
                    ask="Answer NO if the agent called issue_refund more than once.",
                )
            ]
        )
    )
    payload = decisions_payload(confidence=0.91)
    payload["answers"].append(
        {"type": "noul", "name": "no_dup", "noul": 0.92, "probability": 0.92}
    )
    judged = _score(_judge(FakePost([FakeResponse(200, payload)])), spec=spec)
    answer = judged["answers"]["no_dup"]
    assert answer.get("probability") == 0.92
    assert "noul" not in answer
    assert answer.get("type") != "noul"
    assert judged["cells"]["no_dup"].get("source") == "judge"


def test_invalid_question_id_is_rejected_and_not_saved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = tmp_path / "notes"
    dest.mkdir()
    (dest / "SKILL.md").write_text(
        "---\nname: notes\ndescription: Take notes.\n---\n# notes\n",
        encoding="utf-8",
    )
    (dest / "evals" / "cases.yaml").parent.mkdir(parents=True)
    (dest / "evals" / "cases.yaml").write_text(
        "schema: 1\nskill: notes\ncases:\n"
        "  - id: write-note\n    status: pinned\n    prompt: Write a note.\n"
        "    should_trigger: true\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        [
            "judge",
            "add-question",
            str(dest),
            "--ask",
            "Did the agent read status.txt at most once?",
            "--id",
            "no-duplicate-read",
        ],
    )
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code == 2, out
    assert "underscore" in out.lower()
    assert "not added" in out.lower()
    pack = load_case_pack(dest)
    extras = pack.judge.extra_questions if pack and pack.judge else []
    assert extras == []

    missing = runner.invoke(app, ["check", str(dest), "--id", "no-duplicate-read"])
    missing_out = plain_text(missing.stdout + missing.stderr)
    assert missing.exit_code != 0
    assert "no check named" in missing_out.lower()
    assert "no-duplicate-read" in missing_out


def test_hyphenated_id_parse_error_names_the_fix() -> None:
    with pytest.raises(Exception) as exc:
        parse_extra_question(
            {
                "id": "no-duplicate-read",
                "type": "predicate",
                "ask": "Did the agent read status.txt at most once?",
            }
        )
    hint = str(getattr(exc.value, "hint", "") or "")
    text = f"{exc.value}\n{hint}".lower()
    assert "underscore" in text
    assert "no_duplicate_read" in text
