from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skillgate_ai.case_pack import load_case_pack
from skillgate_ai.cli import app
from skillgate_ai.errors import SuiteError
from skillgate_ai.gate import run_check

runner = CliRunner()
ROOT = Path(__file__).resolve().parents[1]


def _copy_pdf(tmp_path: Path) -> Path:
    dest = tmp_path / "pdf"
    shutil.copytree(ROOT / "skills" / "pdf", dest)
    return dest


def test_missing_fixture_fails_check_naming_file(tmp_path: Path) -> None:
    pack = _copy_pdf(tmp_path)
    cases = pack / "evals" / "cases.yaml"
    text = cases.read_text(encoding="utf-8").replace(
        "evals/fixtures/hello.pdf", "evals/fixtures/missing-scan.pdf", 1
    )
    cases.write_text(text, encoding="utf-8")
    result = runner.invoke(app, ["check", str(pack)])
    assert result.exit_code == 1, result.stdout
    combined = result.stdout + result.stderr
    assert "missing-scan.pdf" in combined
    assert "GREEN" not in combined
    assert "Gate is green" not in combined
    assert "pydantic" not in combined.lower()


def test_missing_fixture_raises_before_run(tmp_path: Path) -> None:
    pack = _copy_pdf(tmp_path)
    (pack / "evals" / "fixtures" / "alpha.pdf").unlink()
    with pytest.raises(SuiteError, match="alpha.pdf") as caught:
        load_case_pack(pack)
    assert caught.value.exit_code == 1


def test_schema_2_exits_2_plain_message(tmp_path: Path) -> None:
    pack = _copy_pdf(tmp_path)
    path = pack / "evals" / "cases.yaml"
    text = path.read_text(encoding="utf-8").replace("schema: 1", "schema: 2", 1)
    path.write_text(text, encoding="utf-8")
    result = runner.invoke(app, ["check", str(pack)])
    assert result.exit_code == 2, result.stdout
    combined = result.stdout + result.stderr
    assert "schema 2" in combined
    assert "schema 1" in combined
    assert "pydantic" not in combined.lower()
    assert "errors.pydantic.dev" not in combined


def test_bad_case_id_names_the_case(tmp_path: Path) -> None:
    pack = _copy_pdf(tmp_path)
    path = pack / "evals" / "cases.yaml"
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text
        + "  - id: Bad_ID\n"
        + "    status: pinned\n"
        + "    prompt: Extra check.\n"
        + "    should_trigger: true\n",
        encoding="utf-8",
    )
    result = runner.invoke(app, ["check", str(pack)])
    assert result.exit_code == 1, result.stdout
    combined = result.stdout + result.stderr
    assert "Bad_ID" in combined
    assert "cases.0.id" not in combined
    assert "errors.pydantic.dev" not in combined
    assert "pydantic" not in combined.lower()
    assert "Case pack is invalid" not in combined


def test_run_cases_yaml_is_friendly(tmp_path: Path) -> None:
    pack = _copy_pdf(tmp_path)
    result = runner.invoke(app, ["run", str(pack / "evals" / "cases.yaml")])
    assert result.exit_code != 0
    combined = result.stdout + result.stderr
    assert "checks file" in combined.lower()
    assert "Case pack is invalid" not in combined
    assert "pydantic" not in combined.lower()
    assert "errors.pydantic.dev" not in combined


def test_run_check_missing_fixture_exit_1(tmp_path: Path) -> None:
    pack = _copy_pdf(tmp_path)
    cases = pack / "evals" / "cases.yaml"
    text = cases.read_text(encoding="utf-8").replace(
        "evals/fixtures/hello.pdf", "evals/fixtures/missing-scan.pdf", 1
    )
    cases.write_text(text, encoding="utf-8")
    result = run_check(pack, source="cli", root=pack.parent)
    assert result.exit_code == 1
    assert result.error is not None
    assert "missing-scan.pdf" in (result.error.get("message") or "")


def test_empty_seed_cases_yaml_is_clear_error(tmp_path: Path) -> None:
    pack = _copy_pdf(tmp_path)
    (pack / "evals" / "cases.yaml").write_text(
        "schema: 1\nskill: pdf\ncases: []\n", encoding="utf-8"
    )
    with pytest.raises(SuiteError) as caught:
        load_case_pack(pack)
    assert caught.value.exit_code == 2
    assert "original checks stay" in caught.value.message.lower()
    result = runner.invoke(app, ["check", str(pack)])
    combined = (result.stdout + result.stderr).lower()
    assert result.exit_code == 2
    assert "original checks stay" in combined
    assert "seed checks cannot be removed" not in combined
