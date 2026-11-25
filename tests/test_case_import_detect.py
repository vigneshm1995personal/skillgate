from __future__ import annotations

import pytest

from skillgate_ai.case_import import CaseImportError, detect_format, parse_import_bytes


def test_detect_format_by_extension() -> None:
    assert detect_format("a.csv", b"x") == "csv"
    assert detect_format("a.jsonl", b"x") == "jsonl"
    assert detect_format("a.yaml", b"x") == "yaml"


def test_detect_format_sniffs_jsonl_multiline() -> None:
    assert detect_format(None, b'{"id":"x"}\n{"id":"y"}\n') == "jsonl"


def test_parse_import_bytes_rejects_unknown_format_hint() -> None:
    with pytest.raises(CaseImportError, match="Unsupported import format"):
        parse_import_bytes(b"id,prompt\na,p\n", filename="rows.csv", format_hint="xml")


def test_parse_import_handles_boolean_columns() -> None:
    rows = parse_import_bytes(
        b"id,prompt,should_trigger\nneg,no skill,false\n",
        filename="rows.csv",
    )[1]
    assert rows[0]["should_trigger"] is False
