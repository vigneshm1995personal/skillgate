"""Narrowed except handlers and parser-boundary behavior (PR B step 7)."""

from __future__ import annotations

import io
import logging
import sys
import types

import pytest
import yaml

from skillgate_ai.case_pack.models import CasePack, PackCase
from skillgate_ai.case_pack.pins import _skill_name
from skillgate_ai.case_pack.store import cases_path, load_case_pack, save_case_pack
from skillgate_ai.cli.base import _stdin_is_tty
from skillgate_ai.document_text import extract_document_text
from skillgate_ai.errors import IngestError, SuiteError
from skillgate_ai.metrics import CaseBudgets, _as_budgets, merge_budgets
from skillgate_ai.scorers import _pdf_pages, _pdf_text
from skillgate_ai.suite import load_suite


def test_as_budgets_invalid_values_fall_back_to_empty():
    assert _as_budgets({"tokens_total": -5}).is_empty()
    assert _as_budgets({"tokens_total": "abc", "max_steps": 3}).is_empty()


def test_merge_budgets_ignores_invalid_suite_layer():
    assert merge_budgets({"max_steps": 0}, {"tokens_total": 10}) == CaseBudgets(tokens_total=10)


def test_as_budgets_unexpected_error_propagates(monkeypatch):
    def boom(cls, data):
        raise RuntimeError("bug")

    monkeypatch.setattr(CaseBudgets, "model_validate", classmethod(boom))
    with pytest.raises(RuntimeError, match="bug"):
        _as_budgets({"tokens_total": 1})


def test_stdin_none_is_not_tty(monkeypatch):
    monkeypatch.setattr(sys, "stdin", None)
    assert _stdin_is_tty() is False


def test_closed_stdin_is_not_tty(monkeypatch):
    stream = io.StringIO()
    stream.close()
    monkeypatch.setattr(sys, "stdin", stream)
    assert _stdin_is_tty() is False


def test_stdin_oserror_is_not_tty(monkeypatch):
    class Broken:
        def isatty(self):
            raise OSError("broken")

    monkeypatch.setattr(sys, "stdin", Broken())
    assert _stdin_is_tty() is False


def test_stdin_tty_true(monkeypatch):
    class Tty:
        def isatty(self):
            return True

    monkeypatch.setattr(sys, "stdin", Tty())
    assert _stdin_is_tty() is True


def test_stdin_unexpected_error_propagates(monkeypatch):
    class Broken:
        def isatty(self):
            raise RuntimeError("boom")

    monkeypatch.setattr(sys, "stdin", Broken())
    with pytest.raises(RuntimeError, match="boom"):
        _stdin_is_tty()


@pytest.fixture
def skill_root(tmp_path):
    root = tmp_path / "demo"
    root.mkdir()
    (root / "SKILL.md").write_text("---\nname: demo\ndescription: d\n---\n", encoding="utf-8")
    return root


@pytest.mark.parametrize("exc", [IngestError("x"), OSError("x"), ValueError("x")])
def test_skill_name_tolerates_ingest_errors(skill_root, monkeypatch, exc):
    def fail(*args, **kwargs):
        raise exc

    monkeypatch.setattr("skillgate_ai.ingest.ingest_skill", fail)
    assert _skill_name(skill_root) == "demo"


def test_skill_name_propagates_unexpected(skill_root, monkeypatch):
    monkeypatch.setattr(
        "skillgate_ai.ingest.ingest_skill",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    with pytest.raises(RuntimeError, match="boom"):
        _skill_name(skill_root)


def test_skill_name_without_skill_md_uses_folder(tmp_path, monkeypatch):
    called = {"n": 0}

    def fail_ingest(*a, **k):
        called["n"] += 1
        raise RuntimeError("should not run")

    root = tmp_path / "demo"
    root.mkdir()
    monkeypatch.setattr("skillgate_ai.ingest.ingest_skill", fail_ingest)
    assert _skill_name(root) == "demo"
    assert called["n"] == 0


def test_load_case_pack_schema_error_is_friendly(tmp_path):
    root = tmp_path / "demo-skill"
    cases = root / "evals"
    cases.mkdir(parents=True)
    (cases / "cases.yaml").write_text(
        "schema: 1\nskill: demo-skill\ncases: 5\n",
        encoding="utf-8",
    )
    with pytest.raises(SuiteError) as caught:
        load_case_pack(root)
    exc = caught.value
    assert exc.exit_code == 2
    assert "pydantic" not in str(exc.message).lower()
    assert exc.__suppress_context__ is True


def test_load_case_pack_unexpected_error_propagates(tmp_path, monkeypatch):
    root = tmp_path / "demo-skill"
    cases = root / "evals"
    cases.mkdir(parents=True)
    (cases / "cases.yaml").write_text(
        "schema: 1\nskill: demo-skill\ncases: []\n",
        encoding="utf-8",
    )

    def boom(cls, data):
        raise RuntimeError("bug")

    monkeypatch.setattr(CasePack, "model_validate", classmethod(boom))
    with pytest.raises(RuntimeError, match="bug"):
        load_case_pack(root)


@pytest.mark.parametrize(
    "contents",
    [
        b"\xff\xfe\x00",
        b"cases: [\n",
        b"schema: 1\nskill: demo-skill\ncases: 5\n",
    ],
)
def test_save_case_pack_tolerates_unreadable_previous(tmp_path, contents):
    root = tmp_path / "demo-skill"
    dest = root / "evals" / "cases.yaml"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(contents)
    pack = CasePack(
        schema=1,
        skill="demo-skill",
        cases=[
            PackCase(
                id="should-trigger-1",
                status="pinned",
                prompt="Make a PDF",
                should_trigger=True,
            )
        ],
    )
    written = save_case_pack(root, pack)
    assert written == cases_path(root)
    loaded = yaml.safe_load(written.read_text(encoding="utf-8"))
    assert loaded["skill"] == "demo-skill"


def test_load_suite_schema_error_is_friendly(tmp_path):
    path = tmp_path / "suite.yaml"
    path.write_text('suite: demo\nskill: ../demo\ntasks: ["not-a-mapping"]\n', encoding="utf-8")
    with pytest.raises(SuiteError) as caught:
        load_suite(path)
    exc = caught.value
    assert "Eval suite" in str(exc.message) or "eval suite" in str(exc.message).lower()
    assert exc.__suppress_context__ is True


def test_load_suite_unexpected_error_propagates(tmp_path, monkeypatch):
    path = tmp_path / "suite.yaml"
    path.write_text("suite: demo\nskill: ../demo\ntasks: []\n", encoding="utf-8")
    from skillgate_ai.suite import SuiteSpec

    def boom(cls, data):
        raise RuntimeError("bug")

    monkeypatch.setattr(SuiteSpec, "model_validate", classmethod(boom))
    with pytest.raises(RuntimeError, match="bug"):
        load_suite(path)


@pytest.mark.parametrize(
    "exc",
    [KeyError("/Root"), ValueError("bad"), ModuleNotFoundError("pypdf"), RecursionError()],
)
def test_extract_document_text_parser_errors_return_none_and_log(
    tmp_path, monkeypatch, caplog, exc
):
    pdf = tmp_path / "out.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    def raiser(path):
        raise exc

    monkeypatch.setattr("skillgate_ai.document_text._pdf_text", raiser)
    with caplog.at_level(logging.DEBUG, logger="skillgate_ai.document_text"):
        assert extract_document_text(pdf) is None
    assert any(rec.exc_info for rec in caplog.records if rec.name == "skillgate_ai.document_text")


@pytest.mark.parametrize(
    "exc",
    [KeyError("/Root"), ValueError("bad"), ModuleNotFoundError("pypdf"), RecursionError()],
)
def test_scorers_pdf_helpers_parser_errors_return_none_and_log(tmp_path, monkeypatch, caplog, exc):
    pdf = tmp_path / "out.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    def raiser(*a, **k):
        raise exc

    monkeypatch.setattr(
        "skillgate_ai.scorers.import_extra",
        lambda *a, **k: types.SimpleNamespace(PdfReader=raiser),
    )
    with caplog.at_level(logging.DEBUG, logger="skillgate_ai.scorers"):
        assert _pdf_pages(pdf) is None
        assert _pdf_text(pdf) is None
    assert any(rec.exc_info for rec in caplog.records if rec.name == "skillgate_ai.scorers")


def test_parser_boundary_logs_are_debug_only(tmp_path, monkeypatch, caplog):
    pdf = tmp_path / "out.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    def raiser(path):
        raise ValueError("bad")

    monkeypatch.setattr("skillgate_ai.document_text._pdf_text", raiser)

    def bad_reader(*args, **kwargs):
        raise ValueError("bad")

    monkeypatch.setattr(
        "skillgate_ai.scorers.import_extra",
        lambda *a, **k: types.SimpleNamespace(PdfReader=bad_reader),
    )
    with caplog.at_level(logging.WARNING):
        extract_document_text(pdf)
        _pdf_pages(pdf)
        _pdf_text(pdf)
    noisy = {"skillgate_ai.document_text", "skillgate_ai.scorers"}
    assert not [r for r in caplog.records if r.name in noisy]
