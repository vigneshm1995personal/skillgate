from __future__ import annotations

import pytest

from skillgate_ai.case_import import CaseImportError, detect_format, parse_import_bytes


def test_detect_format_from_suffix() -> None:
    assert detect_format("rows.csv", b"id,prompt\na,x\n") == "csv"
    assert detect_format("rows.jsonl", b"{}\n") == "jsonl"


def test_detect_format_empty_raises() -> None:
    with pytest.raises(CaseImportError, match="empty"):
        detect_format(None, b"")


def test_detect_format_json_array_is_yaml() -> None:
    assert detect_format(None, b"[{id: a, prompt: p}]\n") == "yaml"


def test_parse_import_bytes_tsv_uses_csv_parser() -> None:
    fmt, rows = parse_import_bytes(b"id\tprompt\na\tDo\n", filename="x.tsv")
    assert fmt == "csv"
    assert rows[0]["id"] == "a"
