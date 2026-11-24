from __future__ import annotations

import shutil
from pathlib import Path

from skillgate_ai.case_pack import load_case_pack, suite_from_checks
from skillgate_ai.case_pack.pins import pin_case_ids, pin_checks
from skillgate_ai.pack_edit import set_pack_tool_checks

ROOT = Path(__file__).resolve().parents[1]


def test_pin_checks_preserves_pack_tool_checks(tmp_path: Path) -> None:
    dest = tmp_path / "pdf"
    shutil.copytree(ROOT / "skills" / "pdf", dest)
    set_pack_tool_checks(dest, {"must_not_call": ["rm"]})
    pin_checks(dest, [{"id": "new-one", "prompt": "p"}])
    loaded = load_case_pack(dest)
    assert loaded is not None
    assert loaded.tool_checks is not None
    assert loaded.tool_checks.to_sparse_dict() == {"must_not_call": [{"tool": "rm"}]}


def test_pin_case_ids_preserves_pack_tool_checks(tmp_path: Path) -> None:
    dest = tmp_path / "pdf"
    shutil.copytree(ROOT / "skills" / "pdf", dest)
    set_pack_tool_checks(dest, {"must_not_call": ["rm"]})
    pin_case_ids(dest, ["extract-hello"])
    loaded = load_case_pack(dest)
    assert loaded is not None
    assert loaded.tool_checks is not None
    assert loaded.tool_checks.to_sparse_dict() == {"must_not_call": [{"tool": "rm"}]}


def test_suite_from_checks_applies_pack_must_not_call(tmp_path: Path) -> None:
    dest = tmp_path / "pdf"
    shutil.copytree(ROOT / "skills" / "pdf", dest)
    set_pack_tool_checks(dest, {"must_not_call": ["rm"]})
    loaded = load_case_pack(dest)
    assert loaded is not None
    row = next(c for c in loaded.cases if c.id == "extract-hello")
    spec = suite_from_checks(
        dest,
        [{"id": "extract-hello", "prompt": row.prompt}],
        tryout=True,
        only_listed=True,
    )
    assert spec.tasks[0].tool_checks is not None
    assert [r.tool for r in spec.tasks[0].tool_checks.must_not_call] == ["rm"]
