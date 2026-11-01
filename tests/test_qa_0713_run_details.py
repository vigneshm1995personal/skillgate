"""0.7.14: history/gate run details — case name, scores, reply, tools."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import ROOT, plain_text
from typer.testing import CliRunner

from skillgate_ai.cli import app
from skillgate_ai.errors import SkillGateError
from skillgate_ai.history import append_eval, load_history
from skillgate_ai.openai_http import redact_secrets
from skillgate_ai.report import report_to_dict
from skillgate_ai.run_details import (
    agent_reply,
    case_name,
    case_scenario,
    check_rows,
    format_run_show,
    redact_run_text,
    task_detail,
    tool_calls,
)

SHARED_PROMPT = (
    "A customer wrote in asking for a refund of $49.00 on charge ch_3QX81. "
    "Look up the account, follow the skill, and reply to the customer."
)
REPLY = (
    "I've submitted a full refund of USD 49.00 to your original card. "
    "Once our payment provider completes their review, the credit should appear."
)
CALLS_LOG = (
    json.dumps(
        {
            "argv": ["lookup", "dana.okafor@lumenfit.co"],
            "exit": 0,
            "response": {
                "http_status": 200,
                "charges": [{"id": "ch_3QX81", "amount": "49.00"}],
            },
        }
    )
    + "\n"
    + json.dumps(
        {
            "argv": ["issue_refund", "--charge", "ch_3QX81", "--amount", "49.00"],
            "exit": 0,
            "response": {
                "http_status": 200,
                "id": "re_48bdbc33ec",
                "amount": "49.00",
                "status": "pending",
                "note": "Refund held for manual review. Funds have not been returned.",
            },
        }
    )
    + "\n"
)


def _isolate_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    return home


def _refund_task(**extra: object) -> dict:
    task = {
        "id": "c3-pending",
        "name": "Pending refund — do not claim submitted",
        "scenario": (
            "Dana asked to refund $49. The payments connector returned pending, "
            "held for manual review."
        ),
        "prompt": SHARED_PROMPT,
        "passed": False,
        "happened": (
            "The reply uses banned wording: \"I've submitted a full refund\"."
        ),
        "outputs": [
            {"path": "output/reply.txt", "body": REPLY},
            {"path": "output/calls.log", "body": CALLS_LOG},
        ],
        "judge": {
            "status": "completed",
            "passed": False,
            "cells": {
                "task_completion": {
                    "label": "Got the job done?",
                    "choice": "Fully completed",
                    "reason": "The bot looked up the charge and called the connector.",
                    "confidence": 0.91,
                },
                "wording": {
                    "label": "The reply follows the skill's wording.",
                    "choice": "No",
                    "probability": 0.0,
                    "source": "text",
                    "reason": (
                        'The reply uses banned wording: "I\'ve submitted a full refund".'
                    ),
                },
            },
            "answers": {
                "task_completion": {
                    "choice": "Fully completed",
                    "confidence": 0.91,
                    "reason": "The bot looked up the charge and called the connector.",
                },
                "wording": {
                    "probability": 0.0,
                    "source": "text",
                    "reason": (
                        'The reply uses banned wording: "I\'ve submitted a full refund".'
                    ),
                },
            },
            "questions": {
                "wording": {
                    "type": "predicate",
                    "instructions": "The reply follows the skill's wording.",
                }
            },
        },
    }
    task.update(extra)
    return task


def _refund_report(tasks: list[dict] | None = None) -> dict:
    rows = tasks or [_refund_task()]
    return {
        "skill": "refund-desk",
        "title": "Refund desk",
        "passed": False,
        "gate": "red",
        "passed_count": 0,
        "task_count": len(rows),
        "tasks": rows,
        "scored_by": "Scored by the judge",
    }


def test_case_name_prefers_name_then_id() -> None:
    assert case_name(_refund_task()) == "Pending refund — do not claim submitted"
    assert case_name({"id": "c3-pending", "prompt": SHARED_PROMPT}) == "c3-pending"
    assert case_name({"prompt": SHARED_PROMPT}) == ""


def test_case_scenario_uses_setup_then_prompt() -> None:
    assert "Dana asked" in case_scenario(_refund_task())
    assert case_scenario({"id": "c3-pending", "prompt": SHARED_PROMPT}) == SHARED_PROMPT
    assert case_scenario({"id": "c3-pending", "setup": "Ticket is pending."}) == (
        "Ticket is pending."
    )


def test_check_rows_include_score_reason_and_source() -> None:
    rows = check_rows(_refund_task())
    by_label = {row["label"]: row for row in rows}
    job = by_label["Got the job done?"]
    assert job["score"] == pytest.approx(1.0)
    assert "looked up the charge" in job["reason"]
    assert job["source_label"] == "from the judge"
    wording = by_label["The reply follows the skill's wording."]
    assert wording["score"] == pytest.approx(0.0)
    assert "banned wording" in wording["reason"]
    assert wording["source_label"] == "from the log/text"
    assert wording["passed"] is False


def test_reply_and_connector_calls_from_outputs() -> None:
    task = _refund_task()
    assert "I've submitted a full refund" in agent_reply(task)
    calls = tool_calls(task)
    names = [row["name"] for row in calls]
    assert "lookup" in names
    assert "issue_refund" in names
    refund = next(row for row in calls if row["name"] == "issue_refund")
    assert "ch_3QX81" in json.dumps(refund["arguments"])
    assert "pending" in json.dumps(refund["response"]).lower()


def test_redact_run_text_strips_keys() -> None:
    blob = (
        "Authorization: Bearer sk-live-abcdefghijklmnopqrstuvwxyz012345 "
        "OPENAI_API_KEY=sk-proj-ABCDEFGHIJKLMNOPQRSTUV "
        "password=hunter2 extra"
    )
    cleaned = redact_run_text(blob)
    assert "sk-live-abcdefghijklmnopqrstuvwxyz012345" not in cleaned
    assert "sk-proj-ABCDEFGHIJKLMNOPQRSTUV" not in cleaned
    assert "hunter2" not in cleaned
    assert "***" in cleaned


def test_task_detail_redacts_secrets_in_reply_and_tools() -> None:
    task = _refund_task(
        outputs=[
            {
                "path": "output/reply.txt",
                "body": "Call us with key sk-live-abcdefghijklmnopqrstuvwxyz012345.",
            },
            {
                "path": "output/calls.log",
                "body": json.dumps(
                    {
                        "argv": ["lookup", "--api-key", "sk-live-abcdefghijklmnopqrstuvwxyz012345"],
                        "response": {"token": "sk-live-abcdefghijklmnopqrstuvwxyz012345"},
                    }
                ),
            },
        ]
    )
    detail = task_detail(task)
    blob = json.dumps(detail)
    assert "sk-live-abcdefghijklmnopqrstuvwxyz012345" not in blob
    assert "***" in blob


def test_old_history_task_still_renders() -> None:
    old = {
        "id": "extract-hello",
        "prompt": "Extract the text from hello.pdf.",
        "passed": True,
        "happened": "Output matched what was expected.",
    }
    detail = task_detail(old)
    assert detail["name"] == "extract-hello"
    assert "hello.pdf" in detail["scenario"]
    assert detail["passed"] is True
    assert detail["checks"] == []
    assert detail["reply"] == ""
    assert detail["tool_calls"] == []
    text = format_run_show(
        {
            "run_id": "old-1",
            "passed": True,
            "report": {
                "passed_count": 1,
                "task_count": 1,
                "tasks": [old],
            },
        },
        detail=True,
    )
    assert "extract-hello" in text
    assert "hello.pdf" in text
    assert "pass" in text.lower()


def test_format_run_show_uses_case_name_not_shared_prompt() -> None:
    text = format_run_show(
        {
            "run_id": "run-blog",
            "passed": False,
            "report": _refund_report(),
        }
    )
    assert "Pending refund — do not claim submitted" in text
    assert SHARED_PROMPT not in text
    assert "run-blog" in text
    assert "fail" in text.lower()


def test_format_run_show_detail_prints_score_reason_reply_tools() -> None:
    text = format_run_show(
        {
            "run_id": "run-blog",
            "passed": False,
            "report": _refund_report(),
        },
        detail=True,
    )
    assert "Dana asked" in text
    assert "1.00" in text
    assert "from the judge" in text
    assert "from the log/text" in text
    assert "banned wording" in text
    assert "I've submitted a full refund" in text
    assert "issue_refund" in text
    assert "pending" in text.lower()


def test_format_run_show_case_filters_one_task() -> None:
    other = _refund_task(
        id="c6-success",
        name="Successful refund",
        passed=True,
        outputs=[{"path": "output/reply.txt", "body": "Your refund is on its way."}],
    )
    row = {
        "run_id": "run-blog",
        "passed": False,
        "report": _refund_report([_refund_task(), other]),
    }
    one = format_run_show(row, case_id="c3-pending")
    assert "Pending refund" in one
    assert "Successful refund" not in one
    with pytest.raises(SkillGateError, match="no-such"):
        format_run_show(row, case_id="no-such")


def test_history_show_cli_detail_and_case(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_home(tmp_path, monkeypatch)
    pack = tmp_path / "skills" / "refund-desk"
    (pack / "evals").mkdir(parents=True)
    (pack / "SKILL.md").write_text(
        "---\nname: refund-desk\ndescription: Handle refund tickets.\n---\n# refund-desk\n",
        encoding="utf-8",
    )
    append_eval(
        pack,
        run_id="run-blog",
        passed=False,
        report=_refund_report(),
    )
    runner = CliRunner()
    listed = runner.invoke(app, ["history", "show", "run-blog", "--pack", str(pack)])
    listed_out = plain_text(listed.stdout + listed.stderr)
    assert listed.exit_code == 0, listed_out
    assert "Pending refund" in listed_out
    assert SHARED_PROMPT not in listed_out

    detailed = runner.invoke(
        app, ["history", "show", "run-blog", "--pack", str(pack), "--detail"]
    )
    detail_out = plain_text(detailed.stdout + detailed.stderr)
    assert detailed.exit_code == 0, detail_out
    assert "1.00" in detail_out
    assert "from the log/text" in detail_out
    assert "issue_refund" in detail_out
    assert "I've submitted a full refund" in detail_out

    one = runner.invoke(
        app,
        ["history", "show", "run-blog", "--pack", str(pack), "--case", "c3-pending"],
    )
    one_out = plain_text(one.stdout + one.stderr)
    assert one.exit_code == 0, one_out
    assert "Dana asked" in one_out

    missing = runner.invoke(
        app,
        ["history", "show", "run-blog", "--pack", str(pack), "--case", "no-such"],
    )
    missing_out = plain_text(missing.stdout + missing.stderr)
    assert missing.exit_code != 0, missing_out
    assert "no-such" in missing_out.lower() or "No case" in missing_out

    secret = runner.invoke(
        app, ["history", "show", "run-blog", "--pack", str(pack), "--json"]
    )
    secret_out = plain_text(secret.stdout + secret.stderr)
    assert "sk-" not in secret_out.lower() or "sk-***" in secret_out


def test_history_show_does_not_touch_real_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_home = Path.home()
    home = _isolate_home(tmp_path, monkeypatch)
    pack = tmp_path / "skills" / "refund-desk"
    (pack / "evals").mkdir(parents=True)
    (pack / "SKILL.md").write_text(
        "---\nname: refund-desk\ndescription: Handle refund tickets.\n---\n# refund-desk\n",
        encoding="utf-8",
    )
    before = set()
    marker = original_home / ".skillgate-0713-marker"
    if original_home.exists():
        before = {path.name for path in original_home.glob(".skillgate*")}
    append_eval(pack, run_id="run-home", passed=True, report={"passed_count": 1, "task_count": 1})
    result = CliRunner().invoke(
        app, ["history", "show", "run-home", "--pack", str(pack), "--detail"]
    )
    assert result.exit_code == 0, result.stdout
    assert Path.home() == home
    assert str(home) != str(original_home)
    assert not marker.exists()
    if original_home.exists():
        after = {path.name for path in original_home.glob(".skillgate*")}
        assert after == before


def test_report_to_dict_stamps_run_details() -> None:
    from skillgate_ai.engine import SuiteReport, TaskReport

    task = TaskReport(
        task_id="c3-pending",
        prompt=SHARED_PROMPT,
        expect_skill="refund-desk",
        passed=False,
        scores=[],
        selected_skill="refund-desk",
        name="Pending refund — do not claim submitted",
        scenario="Dana asked to refund $49. The connector returned pending.",
        outputs=[
            {"path": "output/reply.txt", "body": REPLY},
            {"path": "output/calls.log", "body": CALLS_LOG},
        ],
        judge={
            "status": "completed",
            "cells": {
                "wording": {
                    "label": "The reply follows the skill's wording.",
                    "choice": "No",
                    "probability": 0.0,
                    "source": "text",
                    "reason": 'The reply uses banned wording: "I\'ve submitted a full refund".',
                }
            },
            "answers": {
                "wording": {"probability": 0.0, "source": "text"}
            },
        },
    )
    payload = report_to_dict(
        SuiteReport(
            suite="suite",
            title="Refunds",
            skill="refund-desk",
            harness="cursor-agent",
            sandbox="local",
            passed=False,
            tasks=[task],
        )
    )
    row = payload["tasks"][0]
    assert row["name"] == "Pending refund — do not claim submitted"
    assert "Dana asked" in row["scenario"]
    assert "I've submitted" in row["reply"]
    assert any(item["name"] == "issue_refund" for item in row["tool_calls"])
    wording = next(
        item
        for item in row["check_answers"]
        if "wording" in item["label"].lower() or item.get("source") == "text"
    )
    assert wording.get("score") == pytest.approx(0.0)
    assert wording.get("reason")
    assert wording.get("source_label") == "from the log/text"


def test_wording_facts_include_written_reason() -> None:
    from skillgate_ai.judge_spec import JudgeQuestion, JudgeSpec
    from skillgate_ai.wording_facts import resolve_wording_facts

    spec = JudgeSpec(
        questions=(
            JudgeQuestion(
                id="wording",
                type="predicate",
                ask="The reply follows the skill's wording: do not use I've submitted a full refund.",
                on_fail="block",
            ),
        ),
    )
    skill = (
        'Never say "I\'ve submitted a full refund" unless the connector returned succeeded.\n'
        'Banned phrases: "I\'ve submitted a full refund".\n'
    )
    facts = resolve_wording_facts(
        spec,
        [{"path": "output/reply.txt", "body": REPLY}],
        skill,
    )
    row = facts["wording"]
    assert row["probability"] == pytest.approx(0.0)
    assert row["source"] == "text"
    assert "banned" in str(row.get("reason") or "").lower()


def test_case_labels_read_pack_name_and_setup(tmp_path: Path) -> None:
    from skillgate_ai.engine import TaskSpec, _case_labels

    pack = tmp_path / "refund-desk"
    (pack / "evals").mkdir(parents=True)
    (pack / "SKILL.md").write_text(
        "---\nname: refund-desk\ndescription: Handle refund tickets.\n---\n# refund-desk\n",
        encoding="utf-8",
    )
    (pack / "evals" / "cases.yaml").write_text(
        "schema: 1\n"
        "skill: refund-desk\n"
        "cases:\n"
        "  - id: c3-pending\n"
        "    status: pinned\n"
        "    name: Pending refund — do not claim submitted\n"
        "    setup: Dana asked to refund $49. The connector returned pending.\n"
        "    prompt: |\n"
        f"      {SHARED_PROMPT}\n"
        "    should_trigger: false\n",
        encoding="utf-8",
    )
    name, scenario = _case_labels(
        pack,
        TaskSpec(
            id="c3-pending",
            prompt=SHARED_PROMPT,
            expect_skill="refund-desk",
            scorers=[],
        ),
    )
    assert name == "Pending refund — do not claim submitted"
    assert "Dana asked" in scenario


def test_ui_markup_renders_run_details() -> None:
    table = (
        ROOT / "web" / "src" / "components" / "dashboard" / "checks-results-table.tsx"
    ).read_text(encoding="utf-8")
    legacy = (
        ROOT / "src" / "skillgate_ai" / "local_ui" / "static" / "app.js"
    ).read_text(encoding="utf-8")
    for blob in (table, legacy):
        assert "caseRowTitle" in blob or "case-name" in blob
        assert "scenario" in blob.lower() or "case-setup" in blob
        assert "item.score" in blob or "check-score" in blob
        assert "item.reason" in blob or "check-reason" in blob
        assert "from the log/text" in blob or "item.source" in blob
        assert "agent-reply" in blob or "Agent reply" in blob
        assert "tool-call" in blob or "Connector" in blob
    assert "OpenAI" not in table
    assert "Jev" not in table


def test_load_history_scrubs_keys_from_new_fields(tmp_path: Path) -> None:
    pack = tmp_path / "skill"
    append_eval(
        pack,
        run_id="secret-run",
        passed=False,
        report={
            "tasks": [
                {
                    "id": "c3-pending",
                    "reply": "key sk-live-abcdefghijklmnopqrstuvwxyz012345",
                    "tool_calls": [
                        {
                            "name": "lookup",
                            "arguments": {"api_key": "sk-live-abcdefghijklmnopqrstuvwxyz012345"},
                            "response": {"ok": True},
                        }
                    ],
                }
            ]
        },
    )
    rows = load_history(pack)
    blob = json.dumps(rows)
    assert "sk-live-abcdefghijklmnopqrstuvwxyz012345" not in blob
    assert redact_secrets("sk-live-abcdefghijklmnopqrstuvwxyz012345") == "sk-***"


RUBRIC_CORRECT = "The result matches the expected outcome."
RUBRIC_QUALITY = "The delivered result is clear and complete."
RUBRIC_ACCEPTABLE = (
    "The skill finished with only minor extra steps and no looping."
)
CUSTOM_ASK = (
    "Did the agent call issue_refund more than once for the same charge?"
)


def _contradicting_scores_task() -> dict:
    """QA D1/D2 fixture: passing choices with low confidence, Acceptable path."""
    return {
        "id": "c4-partial",
        "name": "Partial refund",
        "scenario": "Dana asked to refund $49. The connector refunded $4.90.",
        "passed": True,
        "review": True,
        "status": "unsure",
        "happened": "unsure, needs review",
        "outputs": [
            {"path": "output/reply.txt", "body": REPLY},
            {"path": "output/calls.log", "body": CALLS_LOG},
        ],
        "judge": {
            "status": "completed",
            "passed": True,
            "review": True,
            "cells": {
                "correctness": {
                    "label": "Got it right?",
                    "choice": "Correct",
                    "confidence": 0.24,
                    "reason": RUBRIC_CORRECT,
                },
                "result_quality": {
                    "label": "Delivered a good result?",
                    "choice": "Clear and complete",
                    "confidence": 0.17,
                    "reason": RUBRIC_QUALITY,
                },
                "path_efficiency": {
                    "label": "How it ran",
                    "choice": "Acceptable",
                    "confidence": 0.71,
                    "reason": RUBRIC_ACCEPTABLE,
                    "status": "unsure",
                },
                "no_dup": {
                    "label": CUSTOM_ASK,
                    "choice": "Yes",
                    "probability": 1.0,
                    "source": "log",
                    "reason": f"{CUSTOM_ASK} Yes",
                },
            },
            "answers": {
                "correctness": {
                    "choice": "Correct",
                    "confidence": 0.24,
                    "reason": RUBRIC_CORRECT,
                },
                "result_quality": {
                    "choice": "Clear and complete",
                    "confidence": 0.17,
                    "reason": RUBRIC_QUALITY,
                },
                "path_efficiency": {
                    "choice": "Acceptable",
                    "confidence": 0.71,
                    "reason": RUBRIC_ACCEPTABLE,
                },
                "no_dup": {
                    "choice": "Yes",
                    "probability": 1.0,
                    "source": "log",
                    "reason": f"{CUSTOM_ASK} Yes",
                },
            },
        },
    }


def test_check_rows_use_outcome_score_not_confidence() -> None:
    rows = {row["id"]: row for row in check_rows(_contradicting_scores_task())}
    correct = rows["correctness"]
    assert correct["passed"] is True
    assert correct["score"] == pytest.approx(1.0)
    assert correct["score"] != pytest.approx(0.24)
    quality = rows["result_quality"]
    assert quality["passed"] is True
    assert quality["score"] == pytest.approx(1.0)
    path = rows["path_efficiency"]
    assert path["passed"] is not False
    assert path["score"] == pytest.approx(0.75)
    assert path["score"] != pytest.approx(0.71)


def test_check_rows_show_this_run_reason_not_rubric() -> None:
    rows = {row["id"]: row for row in check_rows(_contradicting_scores_task())}
    correct = rows["correctness"]
    assert correct["reason"] == "No reason recorded"
    assert correct["reason"] != RUBRIC_CORRECT
    assert "matches the expected outcome" not in correct["reason"].lower()
    assert "on this run" not in correct["reason"].lower()
    quality = rows["result_quality"]
    assert quality["reason"] == "No reason recorded"
    path = rows["path_efficiency"]
    assert path["reason"] == "No reason recorded"


def test_missing_judge_reason_is_not_labeled_as_from_the_judge() -> None:
    text = format_run_show(
        {
            "run_id": "b88788af8f81",
            "passed": False,
            "report": {
                "gate": "red",
                "passed_count": 0,
                "task_count": 1,
                "tasks": [_contradicting_scores_task()],
            },
        },
        detail=True,
        case_id="c4-partial",
    )
    assert "No reason recorded" in text
    assert "Correct on this run" not in text
    blob = text.split("Got it right?", 1)[1].split("\n", 1)[0]
    assert "from the judge" in blob
    assert "No reason recorded" in text.split("Got it right?", 1)[1]


def test_check_rows_keep_written_judge_reason() -> None:
    task = _refund_task()
    rows = {row["label"]: row for row in check_rows(task)}
    job = rows["Got the job done?"]
    assert "looked up the charge" in job["reason"]
    assert job["score"] == pytest.approx(1.0)


def test_custom_check_does_not_repeat_the_prompt() -> None:
    rows = {row["id"]: row for row in check_rows(_contradicting_scores_task())}
    extra = rows["no_dup"]
    assert extra["label"] == CUSTOM_ASK
    assert extra["answer"] == "Yes"
    blob = f"{extra['label']} {extra['reason']}"
    assert blob.lower().count("issue_refund more than once") == 1


def test_format_run_show_agrees_pass_fail_and_score() -> None:
    text = format_run_show(
        {
            "run_id": "edde008b6e96",
            "passed": True,
            "report": {
                "gate": "needs review",
                "passed_count": 1,
                "task_count": 1,
                "tasks": [_contradicting_scores_task()],
            },
        },
        detail=True,
        case_id="c4-partial",
    )
    assert "FAIL  0.71" not in text
    assert "How it ran" in text
    assert "FAIL" not in text.split("How it ran", 1)[1].split("\n", 1)[0]
    assert "1.00" in text
    assert RUBRIC_CORRECT not in text
    assert "Correct on this run" not in text
    assert text.lower().count("issue_refund more than once") == 1


def test_unknown_case_is_cannot_run() -> None:
    with pytest.raises(SkillGateError) as caught:
        format_run_show(
            {"run_id": "run-blog", "passed": False, "report": _refund_report()},
            case_id="nope",
        )
    assert caught.value.exit_code == 2
    assert "nope" in str(caught.value)


def test_history_show_unknown_case_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_home(tmp_path, monkeypatch)
    pack = tmp_path / "skills" / "refund-desk"
    (pack / "evals").mkdir(parents=True)
    (pack / "SKILL.md").write_text(
        "---\nname: refund-desk\ndescription: Handle refund tickets.\n---\n# refund-desk\n",
        encoding="utf-8",
    )
    append_eval(pack, run_id="run-blog", passed=False, report=_refund_report())
    missing = CliRunner().invoke(
        app,
        ["history", "show", "run-blog", "--pack", str(pack), "--case", "nope"],
    )
    missing_out = plain_text(missing.stdout + missing.stderr)
    assert missing.exit_code == 2, missing_out
    assert "nope" in missing_out.lower() or "No case" in missing_out


def test_cell_entry_does_not_store_rubric_as_reason() -> None:
    from skillgate_ai.judge_openai import _cell_entry

    cell = _cell_entry(
        "correctness",
        {"choice": "Correct", "confidence": 0.24},
        {"correctness": "Got it right?"},
    )
    assert cell["choice"] == "Correct"
    assert (cell.get("reason") or "") != RUBRIC_CORRECT


def test_cell_entry_keeps_the_judge_reason() -> None:
    from skillgate_ai.judge_openai import _cell_entry

    cell = _cell_entry(
        "correctness",
        {
            "choice": "Correct",
            "confidence": 0.9,
            "reason": "The lookup returned ch_3QX81 for $49.00.",
        },
        {"correctness": "Got it right?"},
    )
    assert "ch_3QX81" in (cell.get("reason") or "")


def test_shared_call_dump_is_not_shown_as_a_judge_reason() -> None:
    dump = "Connector calls: lookup, issue_refund"
    task = _refund_task()
    task["judge"]["cells"]["task_completion"]["reason"] = dump
    task["judge"]["answers"]["task_completion"]["reason"] = dump
    rows = {row["id"]: row for row in check_rows(task)}
    assert rows["task_completion"]["reason"] == "No reason recorded"
    text = format_run_show(
        {"run_id": "b88788af8f81", "passed": False, "report": _refund_report()},
        detail=True,
        case_id="c3-pending",
    )
    job = text.split("Got the job done?", 1)[1]
    assert dump not in job.split("The reply follows", 1)[0]


def test_canned_why_is_not_shown_as_a_judge_reason() -> None:
    canned = "The facts on this run are right."
    task = _refund_task()
    task["judge"]["cells"]["correctness"] = {
        "label": "Got it right?",
        "choice": "Incorrect",
        "reason": canned,
        "source": "judge",
    }
    task["judge"]["answers"]["correctness"] = {
        "choice": "Incorrect",
        "reason": canned,
    }
    rows = {row["id"]: row for row in check_rows(task)}
    assert rows["correctness"]["passed"] is False
    assert rows["correctness"]["score"] == pytest.approx(0.0)
    assert rows["correctness"]["reason"] == "No reason recorded"
    text = format_run_show(
        {
            "run_id": "canned-why",
            "passed": False,
            "report": _refund_report([task]),
        },
        detail=True,
        case_id="c3-pending",
    )
    assert canned not in text
    assert "No reason recorded" in text.split("Got it right?", 1)[1]


def test_canned_why_picks_are_not_stamped_on_cells() -> None:
    from skillgate_ai.judge_bank import CHECK_CELL_ORDER
    from skillgate_ai.judge_context import apply_why_reasons, with_run_reason_questions
    from skillgate_ai.judge_openai import _cell_entry

    questions = with_run_reason_questions(
        [
            {
                "type": "choice",
                "name": name,
                "instructions": f"{name}?",
                "choices": [{"value": "ok", "description": "ok"}],
            }
            for name in CHECK_CELL_ORDER
        ],
        {"actual_output": {"body": REPLY}},
    )
    why = [item for item in questions if str(item.get("name") or "").endswith("_why")]
    assert why
    cells = {
        name: _cell_entry(name, {"choice": "Correct"}, {name: name})
        for name in CHECK_CELL_ORDER
    }
    answers = {
        "task_completion_why": {"choice": "finished"},
        "correctness_why": {"choice": "facts_right"},
        "instruction_adherence_why": {"choice": "rules_followed"},
        "evidence_action_validity_why": {"choice": "tools_ok"},
        "result_quality_why": {"choice": "reply_clear"},
    }
    apply_why_reasons(cells, answers, questions)
    canned = "The facts on this run are right."
    for name in CHECK_CELL_ORDER:
        reason = str(cells[name].get("reason") or "")
        assert reason != canned
        assert "the facts on this run are right" not in reason.lower()


def test_check_rows_skip_why_companion_answers() -> None:
    task = _refund_task()
    task["judge"]["answers"]["correctness_why"] = {
        "choice": "calls",
        "reason": "Connector calls: lookup, issue_refund",
    }
    ids = [row["id"] for row in check_rows(task)]
    assert "correctness_why" not in ids


def test_jev_evaluate_does_not_stamp_canned_why() -> None:
    from skillgate_ai.judge_openai import OutcomeJudge
    from skillgate_ai.judge_providers.jev import JevBackend
    from skillgate_ai.judge_spec import resolve_judge_spec

    class FakeResponse:
        def __init__(self, status_code: int, payload: object) -> None:
            self.status_code = status_code
            self._payload = payload

        def json(self) -> object:
            return self._payload

    posted: list[dict] = []

    def post(url, headers=None, json=None, timeout=None):
        del url, headers, timeout
        posted.append(json or {})
        body = json or {}
        questions = body.get("questions") or []
        answers = {
            "task_completion": {"choice": "Fully completed"},
            "correctness": {"choice": "Incorrect"},
            "instruction_adherence": {"choice": "Fully followed"},
            "evidence_action_validity": {"choice": "Fully supported"},
            "result_quality": {"choice": "Clear and complete"},
            "path_efficiency": {"choice": "Acceptable"},
        }
        for item in questions:
            name = str(item.get("name") or "")
            if not name.endswith("_why"):
                continue
            pick = next(
                (
                    str(choice.get("value") or "")
                    for choice in item.get("choices") or []
                    if str(choice.get("value") or "") not in {"", "none"}
                ),
                "none",
            )
            answers[name] = {"choice": pick}
        return FakeResponse(200, {"model": "jev", "answers": answers})

    judged = OutcomeJudge(
        JevBackend(api_key="jev-key", base_url="https://jev.example/v1", post=post),
        display_name="the judge",
        provider="jev",
        chosen=True,
        supports_why=False,
        supports_confidence=False,
    ).judge(
        "goal",
        [{"path": "output/reply.txt", "body": REPLY, "present": True, "kind": "text"}],
        "",
        spec=resolve_judge_spec(),
        path={"had_path": True, "steps": 2, "tools": ["lookup", "issue_refund"]},
        agent_trajectory={
            "commands": [
                {"argv": ["lookup"]},
                {"argv": ["issue_refund", "--charge", "ch_3QX81"]},
            ]
        },
        actual_output={"body": REPLY},
    )
    questions = posted[0].get("questions") or []
    if isinstance(questions, dict):
        names = list(questions)
    else:
        names = [str(item.get("name") or "") for item in questions]
    assert any(name.endswith("_why") for name in names)
    canned = "The facts on this run are right."
    assert judged["cells"]["correctness"].get("reason") not in {canned, canned.rstrip(".")}
    rows = {row["id"]: row for row in check_rows({"judge": judged, "passed": False})}
    assert canned not in rows["correctness"]["reason"]
    assert rows["correctness"]["reason"] != "No reason recorded"
    assert "Facts in the reply:" in rows["correctness"]["reason"]


def test_passed_green_run_check_rows_do_not_say_unsure() -> None:
    task = {
        "id": "extract-hello",
        "name": "extract-hello",
        "passed": True,
        "review": False,
        "status": "done",
        "happened": "unsure, needs review",
        "judge": {
            "passed": True,
            "review": False,
            "provider": "jev",
            "backend": "jev",
            "supports_confidence": True,
            "warnings": ["unsure, needs review"],
            "cells": {
                "task_completion": {
                    "label": "Got the job done?",
                    "choice": "Fully completed",
                    "status": "unsure",
                },
                "correctness": {
                    "label": "Got it right?",
                    "choice": "Correct",
                    "status": "unsure",
                },
            },
            "answers": {
                "task_completion": {"choice": "Fully completed"},
                "correctness": {"choice": "Correct"},
            },
        },
    }
    rows = check_rows(task)
    blob = json.dumps(rows)
    assert "unsure, needs review" not in blob
    assert all(row["answer"] != "unsure, needs review" for row in rows)
    text = format_run_show(
        {
            "run_id": "green-8",
            "passed": True,
            "report": {
                "gate": "green",
                "passed": True,
                "passed_count": 8,
                "task_count": 8,
                "tasks": [task] * 8,
            },
        },
        detail=True,
    )
    assert "unsure, needs review" not in text
    assert "PASS" in text
