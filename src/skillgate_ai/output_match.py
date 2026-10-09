"""Expected vs actual output mismatch. Engine-owned; not applied inside the judge."""

from __future__ import annotations

from pathlib import Path
from typing import Any

REASON_BINARY_OUTPUT = "Expected output is text/JSON, but the file is binary (JPEG)."
REASON_MISSING_OUTPUT = "Expected output is missing."
_TEXT_OUTPUT_SUFFIXES = {".json", ".txt", ".md", ".csv"}
_BINARY_MAGICS = {"jpeg", "png", "pdf", "gif", "nul"}


def expected_output_mismatch_reason(
    *,
    golden: dict[str, Any] | None = None,
    actual: dict[str, Any] | None = None,
    artifacts: list[dict[str, Any]] | None = None,
) -> str | None:
    path: str | None = None
    if isinstance(golden, dict):
        path = str(golden.get("output_path") or golden.get("path") or "").strip() or None
    rows = [item for item in (artifacts or []) if isinstance(item, dict)]
    if not path and rows:
        path = str(rows[0].get("path") or "").strip() or None
    kind_hint = golden.get("kind") if isinstance(golden, dict) else None
    suffix = Path(path or "").suffix.lower()
    expected_text = kind_hint in {"json", "text"} or suffix in _TEXT_OUTPUT_SUFFIXES
    if not expected_text:
        return None
    present: bool | None = None
    kind: str | None = None
    magic: str | None = None
    if isinstance(actual, dict):
        present = actual.get("present") if "present" in actual else actual.get("body") is not None
        if actual.get("present") is False:
            present = False
        kind = actual.get("kind")
        magic = actual.get("magic")
        if present is None and actual.get("path"):
            present = True
    if present is None:
        for item in rows:
            if path and item.get("path") != path:
                continue
            present = bool(item.get("present"))
            kind = item.get("kind")
            magic = item.get("magic")
            break
    if present is False:
        return REASON_MISSING_OUTPUT
    if kind == "bytes" or (isinstance(magic, str) and magic in _BINARY_MAGICS):
        if magic in (None, "jpeg", "nul"):
            return REASON_BINARY_OUTPUT
        return f"Expected output is text/JSON, but the file is binary ({str(magic).upper()})."
    return None
