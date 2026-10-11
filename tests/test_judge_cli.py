from __future__ import annotations

from pathlib import Path

from conftest import plain_text
from typer.testing import CliRunner

from skillgate_ai.case_pack import (
    CasePack,
    ExtraQuestion,
    JudgeBlock,
    PackCase,
    load_case_pack,
    save_case_pack,
)
from skillgate_ai.cli import app
from skillgate_ai.judge_settings import load_judge_settings

runner = CliRunner()


def _skill(tmp_path: Path) -> Path:
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
                        pass_if={"gte": 0.8},
                    )
                ]
            ),
        ),
    )
    return dest


def test_judge_show_lists_builtins_then_extras(tmp_path: Path, monkeypatch) -> None:
    dest = _skill(tmp_path)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["judge", "show", str(dest)])
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code == 0, out
    assert "Got the job done?" in out
    assert "Do the totals match?" in out
    assert "numbers_match" not in out
    assert "Yes/No" in out
    assert "yes/no" not in out
    assert "Decisions" not in out
    json_result = runner.invoke(app, ["judge", "show", str(dest), "--json"])
    assert json_result.exit_code == 0
    assert "numbers_match" in json_result.stdout


def test_judge_reset_drops_extras(tmp_path: Path, monkeypatch) -> None:
    dest = _skill(tmp_path)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["judge", "reset", str(dest)])
    assert result.exit_code == 0, result.stdout
    text = (dest / "evals" / "cases.yaml").read_text(encoding="utf-8")
    assert "numbers_match" not in text
    assert "judge:" not in text


def test_judge_provider_set_and_show(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    saved = runner.invoke(app, ["judge", "provider", "set", "jev", "--base-url", "https://jev.example"])
    out = plain_text(saved.stdout + saved.stderr)
    assert saved.exit_code == 0, out
    assert "Jev" in out
    settings = load_judge_settings(tmp_path)
    assert settings.provider == "jev"
    assert settings.base_url == "https://jev.example"
    shown = runner.invoke(app, ["judge", "provider", "show"])
    assert "Jev" in plain_text(shown.stdout)


def test_judge_add_question_writes_extra(tmp_path: Path, monkeypatch) -> None:
    dest = _skill(tmp_path)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        [
            "judge",
            "add-question",
            str(dest),
            "--ask",
            "Are the page counts right?",
            "--type",
            "Yes/No",
        ],
    )
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code == 0, out
    assert "Are the page counts right?" in out
    shown = runner.invoke(app, ["judge", "show", str(dest)])
    shown_out = plain_text(shown.stdout)
    assert "Are the page counts right?" in shown_out
    assert "Yes/No" in shown_out


def test_case_add_and_expected_without_target_warns(tmp_path: Path, monkeypatch) -> None:
    dest = _skill(tmp_path)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        [
            "case",
            "add",
            str(dest),
            "--prompt",
            "Extract the invoice totals.",
            "--expected",
            "Total 40.00",
        ],
    )
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code == 0, out
    assert "Extract the invoice totals." in out or "added" in out.lower()
    assert "expected text" in out.lower()
    pack = load_case_pack(dest)
    assert pack is not None
    assert any(case.prompt == "Extract the invoice totals." for case in pack.cases)
