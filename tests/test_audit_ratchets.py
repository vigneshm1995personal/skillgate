from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "skillgate_ai"

_EXCEPT_LINE = re.compile(r"except Exception\b")
_NOQA_BLE = re.compile(r"# noqa: BLE001")


def test_no_source_module_over_600_lines() -> None:
    for path in SRC.rglob("*.py"):
        if "examples" in path.parts:
            continue
        lines = len(path.read_text(encoding="utf-8").splitlines())
        assert lines <= 600, f"{path.relative_to(ROOT / 'src')}: {lines} lines"


def test_broad_excepts_are_documented_boundaries() -> None:
    hits: list[tuple[Path, int, str]] = []
    for path in SRC.rglob("*.py"):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if _EXCEPT_LINE.search(line):
                hits.append((path, lineno, line))
    assert len(hits) <= 15
    for path, lineno, line in hits:
        prev = ""
        if lineno > 1:
            prev = path.read_text(encoding="utf-8").splitlines()[lineno - 2]
        documented = bool(_NOQA_BLE.search(line)) or prev.strip().startswith("#")
        assert documented, f"{path.relative_to(ROOT)}:{lineno}: {line.strip()}"


def test_dict_any_line_budget() -> None:
    count = 0
    for path in SRC.rglob("*.py"):
        count += sum(
            1 for line in path.read_text(encoding="utf-8").splitlines() if "dict[str, Any]" in line
        )
    assert count <= 550, f"{count} dict[str, Any] lines (baseline 583; plan ≤520)"
    outcome = SRC / "judge_openai" / "outcome.py"
    outcome_lines = sum(
        1 for line in outcome.read_text(encoding="utf-8").splitlines() if "dict[str, Any]" in line
    )
    assert outcome_lines <= 11
