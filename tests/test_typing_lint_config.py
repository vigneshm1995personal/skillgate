"""Config and noqa hygiene for typing/lint hardening (PR B step 8)."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PYPROJECT = REPO / "pyproject.toml"
SRC = REPO / "src"
SCRIPTS = REPO / "scripts"

NOQA_BLE_S = re.compile(
    r"noqa: [A-Z0-9, ]+\s*(?:-|—)\s*\S",
)
NOQA_ABOVE = re.compile(r"#\s*(BLE001|S\d{3}):\s*\S")
TYPE_IGNORE = re.compile(r"type: ignore\[[a-z-, ]+\]\s+#\s*\S")


def test_mypy_checks_untyped_defs():
    cfg = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    mypy = cfg["tool"]["mypy"]
    assert mypy["check_untyped_defs"] is True
    assert mypy["warn_unused_ignores"] is True


def test_ruff_selects_ble_and_s():
    cfg = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    lint = cfg["tool"]["ruff"]["lint"]
    select = lint["select"]
    assert {"BLE", "S"} <= set(select)
    assert lint["per-file-ignores"]["tests/**/*.py"] == ["S"]
    ignore = lint.get("ignore", [])
    assert "BLE001" not in ignore
    assert "BLE" not in ignore
    assert "S" not in ignore


def test_bandit_and_ble_noqa_have_reasons():
    paths = list(SRC.rglob("*.py")) + list(SCRIPTS.rglob("*.py"))
    for path in paths:
        lines = path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            if "noqa:" not in line:
                continue
            if not re.search(r"BLE001|S\d{3}", line):
                continue
            if NOQA_BLE_S.search(line):
                continue
            prev = lines[index - 1] if index else ""
            assert NOQA_ABOVE.search(prev), f"{path}:{index + 1}: missing noqa reason"


def test_type_ignores_have_codes_and_reasons():
    for path in SRC.rglob("*.py"):
        for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if "type: ignore" not in line:
                continue
            assert TYPE_IGNORE.search(line), f"{path}:{index}: bare type ignore"
