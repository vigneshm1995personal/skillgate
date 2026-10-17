"""Sample files on Evaluate belong to the skill you picked.

csv-cleaner must not list the pdf example's alpha/beta/hello/invoice/notes
PDFs, and a check must not open those files out of the pdf skill's folder.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from skillgate_ai.api import create_app
from skillgate_ai.demo_files import ensure_demo_pdfs
from skillgate_ai.gate import prepare_pack_fixtures
from skillgate_ai.pack import relevant_eval_fixtures, resolve_input_file

ROOT = Path(__file__).resolve().parents[1]
PDF_DEMO = ("alpha.pdf", "beta.pdf", "hello.pdf", "invoice.pdf", "notes.pdf")


def _skill_md(name: str, description: str) -> str:
    return (
        f"---\nname: {name}\n"
        f"description: {description}\n"
        "---\n\n# Steps\n1. Read the file.\n"
    )


def _workspace(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    shutil.copytree(ROOT / "skills" / "pdf", root / "skills" / "pdf")
    csv = root / "skills" / "csv-cleaner"
    fixtures = csv / "evals" / "fixtures"
    fixtures.mkdir(parents=True)
    (csv / "SKILL.md").write_text(
        _skill_md("csv-cleaner", "Clean CSV exports when the user asks."),
        encoding="utf-8",
    )
    (fixtures / "orders.csv").write_text("id,amount\n1,2\n", encoding="utf-8")
    for name in PDF_DEMO:
        shutil.copy(root / "skills" / "pdf" / "evals" / "fixtures" / name, fixtures / name)
    (csv / "evals" / ".skillgate-example").write_text("pdf\n", encoding="utf-8")
    return root


def test_prepare_pack_fixtures_does_not_seed_pdf_demo_into_other_skills(tmp_path: Path) -> None:
    pack = tmp_path / "csv-cleaner"
    pack.mkdir()
    (pack / "SKILL.md").write_text(
        _skill_md("csv-cleaner", "Clean CSV exports when the user asks."),
        encoding="utf-8",
    )
    (pack / "evals").mkdir()
    (pack / "evals" / ".skillgate-example").write_text("pdf\n", encoding="utf-8")
    prepare_pack_fixtures(pack)
    assert not (pack / "evals" / "fixtures" / "hello.pdf").exists()
    assert not (pack / "evals" / "fixtures" / "invoice.pdf").exists()


def test_csv_cleaner_sample_files_omit_pdf_demo(tmp_path: Path, monkeypatch) -> None:
    root = _workspace(tmp_path)
    monkeypatch.setenv("SKILLGATE_MODE", "local")
    names = {Path(item["src"]).name for item in relevant_eval_fixtures(root / "skills" / "csv-cleaner")}
    assert names == {"orders.csv"}

    client = TestClient(create_app(root=root), base_url="http://127.0.0.1:8765")
    detail = client.get("/api/skills/csv-cleaner")
    assert detail.status_code == 200
    listed = {Path(item["src"]).name for item in detail.json()["skill"]["fixture_defaults"]}
    assert listed == {"orders.csv"}
    pdf = client.get("/api/skills/pdf")
    pdf_names = {Path(item["src"]).name for item in pdf.json()["skill"]["fixture_defaults"]}
    assert "hello.pdf" in pdf_names
    assert "orders.csv" not in pdf_names


def test_resolve_input_file_does_not_read_another_skill(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    csv = root / "skills" / "csv-cleaner"
    found = resolve_input_file(
        "skills/pdf/evals/fixtures/hello.pdf",
        skill_root=csv,
        root=root,
    )
    assert found is None
    own = resolve_input_file(
        "evals/fixtures/orders.csv",
        skill_root=csv,
        root=root,
    )
    assert own is not None
    assert own.name == "orders.csv"


def test_ensure_demo_pdfs_still_fills_the_pdf_example(tmp_path: Path) -> None:
    dest = tmp_path / "pdf"
    shutil.copytree(ROOT / "skills" / "pdf", dest)
    (dest / "evals" / "fixtures" / "hello.pdf").unlink()
    ensure_demo_pdfs(dest / "evals" / "fixtures")
    assert (dest / "evals" / "fixtures" / "hello.pdf").is_file()
