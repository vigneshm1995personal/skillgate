"""QA retest on PR #56: trigger fit, log-fact polarity, quota, adherence review."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_judge_openai import FakePost, FakeResponse, _judge, _score, decisions_payload
from test_qa_0711_fixes import _shell_span

from skillgate_ai.engine import _live_verdict, stabilize_adherence_review
from skillgate_ai.errors import HarnessError
from skillgate_ai.harness import (
    description_fits_request,
    select_skill_from_descriptions,
    usage_limit_message,
)
from skillgate_ai.ingest import Skill, ingest_skill
from skillgate_ai.judge_bank import PASS_LOCK, UNSURE_REVIEW
from skillgate_ai.judge_spec import JudgeQuestion, JudgeSpec, builtin_questions
from skillgate_ai.report import format_cli, report_to_dict
from skillgate_ai.scorers import Score, TriggerEvidence, score_skill_trigger
from skillgate_ai.span_facts import apply_log_facts, log_fact_kind, resolve_log_facts
from skillgate_ai.suite import TaskSpec

ROOT = Path(__file__).resolve().parents[1]

SQL_EDGE_PROMPT = (
    "Using schema.sql, write a SQL query that returns customer_email from orders. "
    "Do not invent a column the schema does not list. Save output/query.sql."
)
C6_LONG_PROMPT = (
    "A customer wrote in asking for a refund of $49.00 on charge ch_1 after the "
    "order arrived damaged. Look up the charge, call the payments connector, and "
    "if issue_refund returns succeeded, confirm the refund in the customer reply "
    "and write output/ticket.txt with what you told them. Do not invent a second "
    "refund. The catalog, policy notes, and connector scripts are in the workspace. "
    "This is a successful first-call refund, not a timeout or a 502."
)


@pytest.fixture(autouse=True)
def _never_touch_real_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    monkeypatch.chdir(tmp_path)


def _task(skill: str, prompt: str, *, expect: str | None) -> TaskSpec:
    return TaskSpec(id="case", prompt=prompt, expect_skill=expect, scorers=[])


def test_sql_writer_refusal_still_triggers() -> None:
    skill = ingest_skill(ROOT / "skills" / "sql-writer")
    task = _task(skill.name, SQL_EDGE_PROMPT, expect=skill.name)
    score = score_skill_trigger(
        task,
        TriggerEvidence(selected_skill=skill.name, read_paths=[], transcript=""),
        skills=[skill],
    )
    assert score.passed is True
    assert score.actual == "sql-writer"
    assert select_skill_from_descriptions(task.prompt, [skill]) is None
    assert description_fits_request(task.prompt, skill) is True


def test_sql_writer_open_orders_still_triggers() -> None:
    skill = ingest_skill(ROOT / "skills" / "sql-writer")
    prompt = (
        "Using schema.sql, write a SQL query that returns id and total for open "
        "orders. Save output/query.sql."
    )
    score = score_skill_trigger(
        _task(skill.name, prompt, expect=skill.name),
        TriggerEvidence(selected_skill=skill.name, read_paths=[], transcript=""),
        skills=[skill],
    )
    assert score.passed is True


def test_long_refund_prompt_still_triggers_c6_control() -> None:
    skill = Skill(
        path=Path("/tmp/ticket-deflector"),
        name="ticket-deflector",
        description=(
            "Handle customer refund tickets. Use when a customer asks about a "
            "refund, charge, or payment."
        ),
        body="# ticket-deflector\n",
    )
    score = score_skill_trigger(
        _task(skill.name, C6_LONG_PROMPT, expect=skill.name),
        TriggerEvidence(selected_skill=skill.name, read_paths=[], transcript=""),
        skills=[skill],
    )
    assert score.passed is True
    assert select_skill_from_descriptions(C6_LONG_PROMPT, [skill]) is None
    assert description_fits_request(C6_LONG_PROMPT, skill) is True


def test_golden_match_does_not_pass_a_wrong_description() -> None:
    skill = ingest_skill(ROOT / "skills" / "pdf-sabotaged")
    score = score_skill_trigger(
        _task(
            skill.name,
            "Extract the text from hello.pdf and save it to output/extracted.txt",
            expect=skill.name,
        ),
        TriggerEvidence(selected_skill=skill.name, read_paths=[], transcript=""),
        skills=[skill],
    )
    assert score.passed is False
    assert "description" in score.detail.lower()


def test_more_than_once_log_fact_uses_question_polarity() -> None:
    ask = "Did the agent call `shell` more than once to read status.txt (a duplicate call)?"
    spec = JudgeSpec(
        questions=tuple(
            builtin_questions()
            + [JudgeQuestion(id="dup_shell", type="predicate", ask=ask)]
        )
    )
    twice = [
        _shell_span("cat status.txt"),
        _shell_span("cat status.txt"),
    ]
    once = [_shell_span("cat status.txt")]
    assert log_fact_kind(ask) == "count"
    twice_facts = resolve_log_facts(spec, twice)
    once_facts = resolve_log_facts(spec, once)
    assert twice_facts["dup_shell"]["probability"] == 1.0
    assert once_facts["dup_shell"]["probability"] == 0.0
    assert twice_facts["dup_shell"]["source"] == "log"


def test_at_most_once_file_read_is_computed_from_the_log() -> None:
    ask = (
        "Did the agent read status.txt at most once "
        "(no duplicate tool calls reading the same file)?"
    )
    spec = JudgeSpec(
        questions=tuple(
            builtin_questions()
            + [JudgeQuestion(id="no_duplicate_read", type="predicate", ask=ask)]
        )
    )
    twice = [
        _shell_span("cat /tmp/ws/status.txt"),
        _shell_span("cat /tmp/ws/status.txt"),
    ]
    once = [_shell_span("cat /tmp/ws/status.txt")]
    assert log_fact_kind(ask) == "count"
    assert resolve_log_facts(spec, twice)["no_duplicate_read"]["probability"] == 0.0
    assert resolve_log_facts(spec, once)["no_duplicate_read"]["probability"] == 1.0


def test_computable_file_read_check_is_not_sent_to_the_judge() -> None:
    ask = (
        "Did the agent read status.txt at most once "
        "(no duplicate tool calls reading the same file)?"
    )
    spec = JudgeSpec(
        questions=tuple(
            builtin_questions()
            + [JudgeQuestion(id="no_duplicate_read", type="predicate", ask=ask)]
        )
    )
    spans = [_shell_span("cat status.txt")]
    payload = decisions_payload(confidence=0.91)
    payload["answers"].append(
        {"type": "noul", "name": "no_duplicate_read", "noul": 0.2, "probability": 0.2}
    )
    post = FakePost([FakeResponse(200, payload)])
    judged = _score(_judge(post), spec=spec, spans=spans)
    names = [item.get("name") for item in post.calls[0]["json"]["questions"]]
    assert "no_duplicate_read" not in names
    cell = judged["cells"]["no_duplicate_read"]
    assert cell["choice"] == "Yes"
    assert cell["source"] == "log"
    assert cell["label"] == ask


def test_answer_no_if_more_than_once_keeps_no_duplicate_polarity() -> None:
    ask = "Answer NO if the agent called issue_refund more than once."
    spec = JudgeSpec(
        questions=tuple(
            builtin_questions() + [JudgeQuestion(id="q0", type="predicate", ask=ask)]
        )
    )
    spans = [
        _shell_span("python3 payments_connector.py issue_refund --charge ch_1"),
    ]
    facts = resolve_log_facts(spec, spans)
    assert facts["q0"]["probability"] == 1.0
    merged = apply_log_facts(spec, {"q0": {"probability": 0.2}}, spans)
    assert merged["q0"]["probability"] == 1.0


def test_weekly_usage_limit_is_cannot_run() -> None:
    stdout = (
        '{"type":"error","error":"ActionRequiredError: Weekly usage limit reached"}\n'
    )
    message = usage_limit_message(stdout, "")
    assert message is not None
    assert "cannot run" in message.lower()
    err = HarnessError(message, hint="Wait until the agent quota resets, then retry.", exit_code=2)
    assert err.exit_code == 2
    assert "Got the job done" not in message


def test_usage_limit_in_result_event_is_cannot_run() -> None:
    stdout = (
        '{"type":"result","is_error":true,'
        '"result":"ActionRequiredError: Weekly usage limit reached for this user."}\n'
    )
    assert usage_limit_message(stdout, "") is not None
    assert usage_limit_message('{"type":"assistant","message":"refund ok"}', "") is None


def test_adherence_low_conf_is_not_review_when_scorers_passed() -> None:
    judged = {
        "status": "completed",
        "passed": True,
        "review": True,
        "warnings": [UNSURE_REVIEW],
        "cells": {
            "instruction_adherence": {
                "label": "Followed the rules?",
                "choice": "Fully followed",
                "confidence": 0.37,
                "status": "unsure",
            }
        },
        "answers": {
            "instruction_adherence": {"choice": "Fully followed", "confidence": 0.37}
        },
    }
    scores = [
        Score(scorer="skill_trigger", passed=True, detail="Triggered `pdf`"),
        Score(scorer="task_completion", passed=True, detail="All expected outputs present"),
    ]
    out = stabilize_adherence_review(judged, scores)
    assert out["review"] is False
    assert out["cells"]["instruction_adherence"].get("status") != "unsure"
    assert UNSURE_REVIEW not in (out.get("warnings") or [])
    passed, _failures, stamped = _live_verdict(
        out,
        "pdf",
        det_passed=True,
        det_failures=[],
        trigger_passed=True,
    )
    assert passed is True
    assert stamped is not None
    assert stamped.get("review") is False


def test_adherence_unsure_stays_when_a_scorer_failed() -> None:
    judged = {
        "status": "completed",
        "passed": True,
        "review": True,
        "warnings": [UNSURE_REVIEW],
        "cells": {
            "instruction_adherence": {
                "choice": "Fully followed",
                "confidence": 0.37,
                "status": "unsure",
            }
        },
    }
    scores = [Score(scorer="skill_trigger", passed=False, detail="Skill didn’t trigger")]
    out = stabilize_adherence_review(judged, scores)
    assert out["cells"]["instruction_adherence"].get("status") == "unsure"
    assert out["review"] is True


def test_other_unsure_cell_still_reviews() -> None:
    judged = {
        "status": "completed",
        "passed": True,
        "review": True,
        "warnings": [UNSURE_REVIEW],
        "cells": {
            "instruction_adherence": {
                "choice": "Fully followed",
                "confidence": 0.37,
                "status": "unsure",
            },
            "correctness": {
                "choice": "Correct",
                "confidence": 0.16,
                "status": "unsure",
            },
        },
    }
    scores = [Score(scorer="skill_trigger", passed=True, detail="Triggered")]
    out = stabilize_adherence_review(judged, scores)
    assert out["cells"]["instruction_adherence"].get("status") != "unsure"
    assert out["cells"]["correctness"].get("status") == "unsure"
    assert out["review"] is True


def test_followed_the_rules_pass_lock_unchanged() -> None:
    assert "fully followed" in PASS_LOCK["instruction_adherence"]
    assert "minor deviation" in PASS_LOCK["instruction_adherence"]


def test_ui_source_labels_are_in_the_rendered_markup() -> None:
    table = (ROOT / "web" / "src" / "components" / "dashboard" / "checks-results-table.tsx").read_text(
        encoding="utf-8"
    )
    legacy = (ROOT / "src" / "skillgate_ai" / "local_ui" / "static" / "app.js").read_text(
        encoding="utf-8"
    )
    assert "check-source" in table
    assert "from the log" in table or "item.source" in table
    assert "from the log" in legacy
    assert "from the judge" in legacy


def test_check_answers_carry_visible_source_label() -> None:
    from skillgate_ai.engine import SuiteReport, TaskReport

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
            "answers": {"no_duplicate_read": {"probability": 1.0, "source": "log"}},
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
    payload = report_to_dict(report)
    extra = payload["tasks"][0]["check_answers"][-1]
    assert extra["source"] == "log"
    assert extra.get("source_label") == "from the log"
    assert "from the log" in format_cli(report).lower()
