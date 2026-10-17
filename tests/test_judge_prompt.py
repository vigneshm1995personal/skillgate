"""The judge prompt shown in the UI and CLI is the decisions question the engine posts."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from skillgate_ai.case_pack import (
    CasePack,
    ExtraQuestion,
    JudgeBlock,
    PackCase,
    save_case_pack,
)
from skillgate_ai.cli import app
from skillgate_ai.errors import SkillGateError
from skillgate_ai.judge_bank import decisions_questions
from skillgate_ai.judge_prompt import prompt_for_id, render_judge_prompt
from skillgate_ai.judge_spec import parse_extra_question

runner = CliRunner()


def test_builtin_prompt_is_the_engine_question() -> None:
    task = next(row for row in decisions_questions() if row["name"] == "task_completion")
    text = render_judge_prompt(task)
    assert text.startswith(str(task["instructions"]))
    for choice in task["choices"]:
        assert choice["value"] in text
        assert choice["description"] in text
    shown = prompt_for_id("task_completion")
    assert shown["prompt"] == text
    assert shown["readonly"] is True
    assert shown["builtin"] is True


def test_custom_predicate_prompt_is_the_ask() -> None:
    question = parse_extra_question(
        {"id": "totals", "type": "Yes/No", "ask": "Do the totals match?"}
    )
    assert render_judge_prompt(question.to_decisions()) == "Do the totals match?"
    shown = prompt_for_id("totals", extras=(question,))
    assert shown["prompt"] == "Do the totals match?"
    assert shown["readonly"] is False


def test_unknown_check_id() -> None:
    try:
        prompt_for_id("not_a_check")
    except SkillGateError as exc:
        assert exc.exit_code == 2
        assert "not_a_check" in exc.message
    else:
        raise AssertionError("expected an error")


def test_checks_show_prints_builtin_prompt() -> None:
    task = next(row for row in decisions_questions() if row["name"] == "task_completion")
    result = runner.invoke(app, ["checks", "show", "task_completion"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert result.stdout.strip() == render_judge_prompt(task)


def test_checks_show_prints_custom_prompt(tmp_path: Path, monkeypatch) -> None:
    dest = tmp_path / "notes"
    dest.mkdir()
    (dest / "SKILL.md").write_text(
        "---\nname: notes\ndescription: Extract text from notes.\n---\n# notes\n",
        encoding="utf-8",
    )
    (dest / "evals").mkdir()
    save_case_pack(
        dest,
        CasePack(
            schema_version=1,
            skill="notes",
            cases=[PackCase(id="extract-hello", status="pinned", prompt="Extract hello")],
            judge=JudgeBlock(
                extra_questions=[
                    ExtraQuestion(
                        id="numbers_match",
                        type="predicate",
                        ask="Do the totals match?",
                        on_fail="block",
                    )
                ]
            ),
        ),
    )
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["checks", "show", "numbers_match", str(dest)])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "Do the totals match?"


def test_checks_show_unknown_exits_2() -> None:
    result = runner.invoke(app, ["checks", "show", "not_a_check"])
    assert result.exit_code == 2
