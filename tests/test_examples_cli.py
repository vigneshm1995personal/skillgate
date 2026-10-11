from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from conftest import plain_text
from skillgate_ai.cli import app
from skillgate_ai.examples import bundled_example, copy_example

runner = CliRunner()


def test_example_pdf_writes_skill_md(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    dest = tmp_path / "copied"
    result = runner.invoke(app, ["example", "pdf", "--dest", str(dest)])
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code == 0, out
    assert (dest / "SKILL.md").is_file()
    assert "name: pdf" in (dest / "SKILL.md").read_text(encoding="utf-8")
    assert (dest / "evals" / "cases.yaml").is_file()


def test_bundled_examples_exist() -> None:
    pdf = bundled_example("pdf")
    sabotaged = bundled_example("pdf-sabotaged")
    assert (pdf / "SKILL.md").is_file()
    assert (sabotaged / "SKILL.md").is_file()


def test_copy_example_rejects_unknown_name(tmp_path: Path) -> None:
    from skillgate_ai.errors import SkillGateError

    try:
        copy_example("not-a-skill", tmp_path / "out")
    except SkillGateError as exc:
        assert "pdf" in exc.message or "pdf-sabotaged" in (exc.hint or "")
    else:
        raise AssertionError("expected SkillGateError")


def test_init_and_new_match_scaffold(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    init = runner.invoke(app, ["init", str(tmp_path)])
    assert init.exit_code == 0, init.stdout
    assert (tmp_path / "skills").is_dir()
    ignore = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert ".skillgate/" in ignore
    again = runner.invoke(app, ["init", str(tmp_path)])
    assert again.exit_code == 0, again.stdout
    created = runner.invoke(app, ["new", "notes-helper"])
    out = plain_text(created.stdout + created.stderr)
    assert created.exit_code == 0, out
    dest = tmp_path / "skills" / "notes-helper"
    assert (dest / "SKILL.md").is_file()
    assert (dest / "evals" / "cases.yaml").is_file()
    cases = (dest / "evals" / "cases.yaml").read_text(encoding="utf-8")
    assert "skill: notes-helper" in cases
    assert "should-trigger-1" in cases
    assert "no-trigger-unrelated" in cases
    skill_md = (dest / "SKILL.md").read_text(encoding="utf-8")
    assert "invoices" not in skill_md.lower()
    assert "documents" not in skill_md.lower()
