from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skillgate_ai.case_import import (
    CaseImportError,
    apply_case_import,
    parse_import_bytes,
    plan_case_import,
)
from skillgate_ai.case_pack import load_case_pack
from skillgate_ai.cli import app

runner = CliRunner()
ROOT = Path(__file__).resolve().parents[1]


def _copy_pdf(tmp_path: Path) -> Path:
    dest = tmp_path / "pdf"
    shutil.copytree(ROOT / "skills" / "pdf", dest)
    return dest


def test_parse_csv_jsonl_yaml() -> None:
    csv_rows = parse_import_bytes(
        b"id,prompt,expected\na,Do thing,ok\n",
        filename="rows.csv",
    )[1]
    assert csv_rows[0]["contains"] == "ok"
    jsonl_rows = parse_import_bytes(
        b'{"id":"b","prompt":"Ping"}\n',
        filename="rows.jsonl",
    )[1]
    assert jsonl_rows[0]["id"] == "b"
    yaml_rows = parse_import_bytes(
        b"cases:\n  - id: c\n    prompt: Hi\n",
        filename="rows.yaml",
    )[1]
    assert yaml_rows[0]["id"] == "c"


def test_plan_reports_row_errors_without_writing(tmp_path: Path) -> None:
    pack = _copy_pdf(tmp_path)
    content = b"id,prompt\nrow1,\n"
    plan = plan_case_import(pack, content, filename="bad.csv")
    assert any(row.error for row in plan.rows)


def test_conflict_fail_blocks_write(tmp_path: Path) -> None:
    pack = _copy_pdf(tmp_path)
    before = (pack / "evals" / "cases.yaml").read_text(encoding="utf-8")
    seed = (
        b"id,prompt,input\n"
        b"first-custom,One,evals/fixtures/hello.pdf\n"
    )
    apply_case_import(pack, seed, filename="seed.csv")
    after_seed = (pack / "evals" / "cases.yaml").read_text(encoding="utf-8")
    content = (
        b"id,prompt,input\n"
        b"first-custom,Duplicate row,evals/fixtures/hello.pdf\n"
    )
    with pytest.raises(CaseImportError, match="already exists"):
        apply_case_import(pack, content, filename="rows.csv", on_conflict="fail")
    assert (pack / "evals" / "cases.yaml").read_text(encoding="utf-8") == after_seed


def test_skip_on_conflict(tmp_path: Path) -> None:
    pack = _copy_pdf(tmp_path)
    content = (
        b"id,prompt,expected,output,input\n"
        b"extract-hello,Hacked,Hello,output/x.txt,evals/fixtures/hello.pdf\n"
        b"csv-new,List files in hello.pdf,,,evals/fixtures/hello.pdf\n"
    )
    plan = apply_case_import(pack, content, filename="rows.csv", on_conflict="skip")
    assert plan.rows[0].action == "skip"
    loaded = load_case_pack(pack)
    assert any(case.id == "csv-new" for case in loaded.cases)
    seed = next(case for case in loaded.cases if case.id == "extract-hello")
    assert "Hacked" not in seed.prompt


def test_cli_dry_run_and_import(tmp_path: Path, monkeypatch) -> None:
    pack = _copy_pdf(tmp_path)
    sample = ROOT / "docs" / "samples" / "dataset-import.csv"
    monkeypatch.chdir(tmp_path)
    dry = runner.invoke(
        app,
        ["case", "import", str(pack), str(sample), "--dry-run"],
    )
    assert dry.exit_code == 0, dry.stdout
    assert "Would import" in dry.stdout
    run = runner.invoke(app, ["case", "import", str(pack), str(sample)])
    assert run.exit_code == 0, run.stdout
    loaded = load_case_pack(pack)
    assert any(case.id == "csv-smoke" for case in loaded.cases)


def test_imported_case_visible_to_check(tmp_path: Path) -> None:
    pack = _copy_pdf(tmp_path)
    sample = ROOT / "docs" / "samples" / "dataset-import.csv"
    apply_case_import(pack, sample.read_bytes(), filename=sample.name)
    result = runner.invoke(app, ["case", "list", str(pack)])
    assert result.exit_code == 0, result.stdout
    assert "csv-smoke" in result.stdout
    loaded = load_case_pack(pack)
    pinned = [case for case in loaded.cases if case.status == "pinned" and case.id == "csv-smoke"]
    assert len(pinned) == 1
