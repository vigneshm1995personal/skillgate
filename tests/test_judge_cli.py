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
    assert "the judge" in out.lower()
    settings = load_judge_settings(tmp_path)
    assert settings.provider == "jev"
    assert settings.base_url == "https://jev.example"
    shown = runner.invoke(app, ["judge", "provider", "show"])
    assert "the judge" in plain_text(shown.stdout).lower()


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


def test_judge_provider_set_help_is_neutral(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    result = runner.invoke(app, ["judge", "provider", "set", "--help"])
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code == 0, out
    assert "--decisions-path" not in out
    assert "--account-id" in out
    assert "clef" in out.lower()
    assert "jev" in out.lower()
    assert "openai" in out.lower()
    assert "aws" not in out.lower()
    assert "other" not in out.lower()
    saved = runner.invoke(app, ["judge", "provider", "set", "other"])
    saved_out = plain_text(saved.stdout + saved.stderr)
    assert saved.exit_code != 0
    assert "removed" in saved_out.lower()


def test_case_add_expected_without_output_pins_text_check(tmp_path: Path, monkeypatch) -> None:
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
            "What is 2+2?",
            "--expected",
            "4",
        ],
    )
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code == 0, out
    pack = load_case_pack(dest)
    assert any(case.contains == ["4"] for case in pack.cases)


def test_case_add_short_slug_and_input_file(tmp_path: Path, monkeypatch) -> None:
    dest = _skill(tmp_path)
    fixture = dest / "sample-note.txt"
    fixture.write_text("hello note\n", encoding="utf-8")
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    prompt = "Extract the invoice totals from this very long prompt that must not become the id"
    result = runner.invoke(
        app,
        [
            "case",
            "add",
            str(dest),
            "--prompt",
            prompt,
            "--expected",
            "Total 40.00",
            "--output",
            "output/invoice.txt",
            "--input",
            str(fixture),
        ],
    )
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code == 0, out
    pack = load_case_pack(dest)
    assert pack is not None
    added = next(case for case in pack.cases if case.prompt == prompt)
    assert added.id.startswith("extract-the-invoice")
    assert added.id != prompt.lower().replace(" ", "-")
    assert len(added.id) < len(prompt)
    assert added.golden is not None
    assert added.golden.output_path == "output/invoice.txt"
    assert added.input.files
    assert (dest / added.input.files[0].src).is_file()
    again = runner.invoke(
        app,
        ["case", "add", str(dest), "--prompt", prompt],
    )
    assert again.exit_code == 0, again.stdout
    pack = load_case_pack(dest)
    ids = [case.id for case in pack.cases if case.prompt == prompt]
    assert len(set(ids)) == 2
    assert any(item.endswith("-2") for item in ids)


def test_pin_does_not_truncate_existing_case_ids(tmp_path: Path) -> None:
    dest = _skill(tmp_path)
    from skillgate_ai.case_pack import load_case_pack, pin_checks, save_case_pack

    pack = load_case_pack(dest)
    assert pack is not None
    long_id = "this-is-a-very-long-custom-check-id-that-exceeds-forty-chars"
    extra = pack.cases[0].model_copy(update={"id": long_id, "prompt": "Keep this id."})
    save_case_pack(dest, pack.model_copy(update={"cases": [*pack.cases, extra]}))
    pin_checks(
        dest,
        [
            {
                "id": long_id,
                "prompt": "Keep this id.",
                "should_trigger": True,
            }
        ],
    )
    reloaded = load_case_pack(dest)
    assert reloaded is not None
    assert any(case.id == long_id for case in reloaded.cases)
    assert not any(case.id == long_id[:40].rstrip("-") and case.id != long_id for case in reloaded.cases)


def test_keys_list_labels_ai_gateway_key(tmp_path: Path, monkeypatch) -> None:
    from skillgate_ai.keys import set_vault_key

    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    set_vault_key(tmp_path, "AI_GATEWAY_API_KEY", "gw-from-vault")
    result = runner.invoke(app, ["keys", "list"])
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code == 0, out
    assert "AI Gateway key" in out
    saved = runner.invoke(app, ["keys", "set", "Other", "gw-from-cli"])
    assert saved.exit_code == 0, saved.stdout
    assert "AI Gateway key" in plain_text(saved.stdout)
