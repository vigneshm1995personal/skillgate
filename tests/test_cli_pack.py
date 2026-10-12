"""CLI commands that match OSS UI writes."""

from __future__ import annotations

import shutil
from pathlib import Path

from typer.testing import CliRunner

from conftest import plain_text
from skillgate_ai.case_pack import load_case_pack
from skillgate_ai.cli import app
from skillgate_ai.history import append_eval

runner = CliRunner()
ROOT = Path(__file__).resolve().parents[1]


def _skill(tmp_path: Path) -> Path:
    dest = tmp_path / "skills" / "pdf"
    shutil.copytree(ROOT / "skills" / "pdf", dest)
    return dest


def test_skill_write_and_history(tmp_path: Path, monkeypatch) -> None:
    dest = _skill(tmp_path)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    written = runner.invoke(
        app,
        [
            "skill",
            "write",
            str(dest),
            "--path",
            "evals/cli-note.txt",
            "--content",
            "hello from cli",
        ],
    )
    out = plain_text(written.stdout + written.stderr)
    assert written.exit_code == 0, out
    assert (dest / "evals" / "cli-note.txt").read_text(encoding="utf-8") == "hello from cli"
    skill_md = (dest / "SKILL.md").read_text(encoding="utf-8")
    overwritten = runner.invoke(
        app,
        ["skill", "write", str(dest), "--path", "SKILL.md", "--content", skill_md],
    )
    assert overwritten.exit_code == 0, overwritten.stdout
    assert (dest / "SKILL.md").read_text(encoding="utf-8") == skill_md
    empty = runner.invoke(app, ["history", "--pack", str(dest)])
    assert empty.exit_code == 0
    assert "No runs yet." in plain_text(empty.stdout)
    append_eval(dest, run_id="run-cli", passed=True, report={"skill": "pdf", "passed": True})
    listed = runner.invoke(app, ["history", "--pack", str(dest)])
    assert listed.exit_code == 0
    assert "run-cli" in plain_text(listed.stdout)


def test_skill_paste_and_import_md(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    md = tmp_path / "notes.md"
    md.write_text(
        "---\nname: notes-helper\ndescription: Take notes from a meeting.\n---\n\n# Notes\n",
        encoding="utf-8",
    )
    pasted = runner.invoke(app, ["skill", "paste", "--file", str(md)])
    out = plain_text(pasted.stdout + pasted.stderr)
    assert pasted.exit_code == 0, out
    assert (tmp_path / "skills" / "notes-helper" / "SKILL.md").is_file()
    other = tmp_path / "other.md"
    other.write_text(
        "---\nname: other-helper\ndescription: Another helper skill.\n---\n\n# Other\n",
        encoding="utf-8",
    )
    imported = runner.invoke(app, ["import", "--md", str(other)])
    imported_out = plain_text(imported.stdout + imported.stderr)
    assert imported.exit_code == 0, imported_out
    assert (tmp_path / "skills" / "other-helper" / "SKILL.md").is_file()


def test_case_list_edit_remove(tmp_path: Path, monkeypatch) -> None:
    dest = _skill(tmp_path)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    listed = runner.invoke(app, ["case", "list", str(dest)])
    listed_out = plain_text(listed.stdout)
    assert listed.exit_code == 0, listed_out
    assert "extract-hello" in listed_out
    added = runner.invoke(
        app,
        ["case", "add", str(dest), "--prompt", "Count the pages in the scan."],
    )
    assert added.exit_code == 0, added.stdout
    pack = load_case_pack(dest)
    assert pack is not None
    extra = next(case for case in pack.cases if case.prompt == "Count the pages in the scan.")
    edited = runner.invoke(
        app,
        ["case", "edit", str(dest), "--id", extra.id, "--prompt", "Count pages again."],
    )
    assert edited.exit_code == 0, edited.stdout
    removed = runner.invoke(app, ["case", "remove", str(dest), "--id", extra.id])
    assert removed.exit_code == 0, removed.stdout
    locked = runner.invoke(app, ["case", "remove", str(dest), "--id", "extract-hello"])
    assert locked.exit_code != 0
    assert "original checks stay" in plain_text(locked.stdout + locked.stderr).lower()


def test_judge_set_and_remove_question(tmp_path: Path, monkeypatch) -> None:
    dest = _skill(tmp_path)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    added = runner.invoke(
        app,
        ["judge", "add-question", str(dest), "--ask", "Are the stamps aligned?", "--id", "stamps"],
    )
    assert added.exit_code == 0, added.stdout
    updated = runner.invoke(
        app,
        ["judge", "set-question", str(dest), "--id", "stamps", "--on-fail", "Warn only"],
    )
    assert updated.exit_code == 0, updated.stdout
    pack = load_case_pack(dest)
    extra = next(q for q in (pack.judge.extra_questions if pack and pack.judge else []) if q.id == "stamps")
    assert extra.on_fail == "warn"
    removed = runner.invoke(app, ["judge", "remove-question", str(dest), "--id", "stamps"])
    assert removed.exit_code == 0, removed.stdout
    pack = load_case_pack(dest)
    ids = [q.id for q in (pack.judge.extra_questions if pack and pack.judge else [])]
    assert "stamps" not in ids
