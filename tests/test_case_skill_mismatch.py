from __future__ import annotations

import shutil
from pathlib import Path

from typer.testing import CliRunner

from conftest import plain_text
from skillgate_ai.case_pack import load_case_pack
from skillgate_ai.errors import SuiteError

runner = CliRunner()
ROOT = Path(__file__).resolve().parents[1]


def test_cases_yaml_skill_mismatch_is_plain(tmp_path: Path) -> None:
    pack = tmp_path / "pdf"
    shutil.copytree(ROOT / "skills" / "pdf", pack)
    path = pack / "evals" / "cases.yaml"
    text = path.read_text(encoding="utf-8").replace("skill: pdf", "skill: other", 1)
    path.write_text(text, encoding="utf-8")
    try:
        load_case_pack(pack)
    except SuiteError as exc:
        message = exc.render()
        assert "This check file is for `other`" in message
        assert "folder is `pdf`" in message
        assert "Traceback" not in message
        assert "pydantic" not in message.lower()
    else:
        raise AssertionError("expected SuiteError")


def test_cases_yaml_allows_docker_pack_mount(tmp_path: Path) -> None:
    pack = tmp_path / "pack"
    shutil.copytree(ROOT / "skills" / "pdf", pack)
    loaded = load_case_pack(pack)
    assert loaded is not None
    assert loaded.skill == "pdf"


def test_cases_yaml_skill_mismatch_cli_prints_once(tmp_path: Path, monkeypatch) -> None:
    from skillgate_ai.cli import app

    pack = tmp_path / "pdf"
    shutil.copytree(ROOT / "skills" / "pdf", pack)
    path = pack / "evals" / "cases.yaml"
    path.write_text(
        path.read_text(encoding="utf-8").replace("skill: pdf", "skill: other", 1),
        encoding="utf-8",
    )
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    result = runner.invoke(app, ["check", str(pack)])
    combined = plain_text(result.stdout + result.stderr)
    assert result.exit_code != 0
    assert combined.count("This check file is for `other`") == 1
    assert "Traceback" not in combined
