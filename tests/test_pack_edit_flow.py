from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from skillgate_ai.case_pack import load_case_pack
from skillgate_ai.errors import SuiteError
from skillgate_ai.pack_edit import (
    add_judge_question,
    add_pack_case,
    remove_judge_question,
    remove_pack_case,
    set_pack_tool_checks,
    set_question_on_fail,
    tryout_checks,
    validate_pin_judge,
)

ROOT = Path(__file__).resolve().parents[1]


def _pdf(tmp_path: Path) -> Path:
    dest = tmp_path / "pdf"
    shutil.copytree(ROOT / "skills" / "pdf", dest)
    return dest


def test_add_and_remove_pack_case(tmp_path: Path) -> None:
    pack = _pdf(tmp_path)
    add_pack_case(pack, prompt="Summarize the invoice", case_id="summarize-inv")
    loaded = load_case_pack(pack)
    assert loaded is not None
    assert any(c.id == "summarize-inv" for c in loaded.cases)
    remove_pack_case(pack, "summarize-inv")
    loaded2 = load_case_pack(pack)
    assert loaded2 is not None
    assert not any(c.id == "summarize-inv" for c in loaded2.cases)


def test_judge_question_lifecycle(tmp_path: Path) -> None:
    pack = _pdf(tmp_path)
    qid = "custom_extra"
    add_judge_question(pack, ask="Did the agent stay on task?", question_id=qid, on_fail="warn")
    set_question_on_fail(pack, qid, "block")
    remove_judge_question(pack, qid)
    loaded = load_case_pack(pack)
    assert loaded is not None
    assert not any(q.id == qid for q in (loaded.judge.extra_questions if loaded.judge else []))


def test_tryout_checks_exports_row(tmp_path: Path) -> None:
    pack = _pdf(tmp_path)
    rows = tryout_checks(pack, "extract-hello")
    assert rows and rows[0]["id"] == "extract-hello"


def test_validate_pin_judge_merges_pack_block(tmp_path: Path) -> None:
    pack = _pdf(tmp_path)
    validate_pin_judge(pack, [], None, has_pack_judge=True)


def test_set_pack_tool_checks_roundtrip(tmp_path: Path) -> None:
    pack = _pdf(tmp_path)
    set_pack_tool_checks(pack, {"must_not_call": ["rm"]})
    loaded = load_case_pack(pack)
    assert loaded and loaded.tool_checks
    with pytest.raises(SuiteError):
        set_pack_tool_checks(pack, {"must_call": "not-a-list"})
