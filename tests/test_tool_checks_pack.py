"""Pack schema for tool_checks."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from skillgate_ai.case_pack.models import CasePack, PackCase
from skillgate_ai.case_pack.pins import _case_from_check
from skillgate_ai.case_pack.store import load_case_pack, save_case_pack
from skillgate_ai.case_pack.suites import pack_fingerprint, suite_from_pack
from skillgate_ai.errors import SuiteError
from skillgate_ai.tool_check_schema import merge_tool_checks

SEED_FINGERPRINTS = {
    "pdf": "47e0d5c6eef03369",
    "json-response": "9e56a42f283ad85b",
    "readme-writer": "e23b09952bf9441b",
    "log-summarizer": "a431b8673e3e8994",
    "sql-writer": "e39dd7d2dd6f5ad5",
    "receipt-extractor": "9e929e1dc48d5bff",
}


def test_pack_fingerprint_unchanged_without_tool_checks() -> None:
    for name, expected in SEED_FINGERPRINTS.items():
        root = Path("skills") / name
        if not root.is_dir():
            continue
        pack = load_case_pack(root)
        assert pack is not None
        assert pack_fingerprint(pack) == expected


def test_suite_from_pack_merges_tool_checks() -> None:
    pack = CasePack(
        schema=1,
        skill="demo",
        tool_checks={
            "must_not_call": ["pack_rule"],
            "consequential_tools": ["stripe_refunds_create"],
        },
        cases=[
            PackCase(
                id="c1",
                status="pinned",
                prompt="p",
                tool_checks={"must_not_call": ["case_rule"]},
            ),
        ],
    )
    spec = suite_from_pack(pack, "skills/demo")
    task = spec.tasks[0]
    assert task.tool_checks is not None
    assert [r.tool for r in task.tool_checks.must_not_call] == ["pack_rule", "case_rule"]
    merged_none = merge_tool_checks(pack.tool_checks, None, should_trigger=False)
    assert merged_none is not None
    assert merged_none.must_call == []


def test_must_call_on_no_trigger_case_rejected() -> None:
    with pytest.raises(ValueError, match="must_call on a no-trigger check never runs"):
        CasePack(
            schema=1,
            skill="demo",
            cases=[
                PackCase(
                    id="c1",
                    status="pinned",
                    prompt="p",
                    should_trigger=False,
                    tool_checks={"must_call": ["x"]},
                ),
            ],
        )


def test_case_from_check_keeps_tool_checks(tmp_path: Path) -> None:
    skill = tmp_path / "skills" / "demo"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: demo\ndescription: d\n---\n", encoding="utf-8")
    raw = {
        "id": "c1",
        "prompt": "p",
        "should_trigger": True,
        "tool_checks": {"must_not_call": ["stripe_refunds_create"]},
    }
    case = _case_from_check(skill, raw, "demo")
    assert case.tool_checks is not None
    assert case.tool_checks.must_not_call[0].tool == "stripe_refunds_create"


def test_pack_tool_checks_round_trip(tmp_path: Path) -> None:
    skill = tmp_path / "skills" / "billing"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: billing\ndescription: d\n---\n", encoding="utf-8")
    text = """schema: 1
skill: billing
tool_checks:
  consequential_tools:
    - stripe_refunds_create
cases:
  - id: c3
    status: pinned
    prompt: Why charged twice?
    tool_checks:
      must_not_call:
        - stripe_refunds_create
"""
    path = skill / "evals" / "cases.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(text, encoding="utf-8")
    pack = load_case_pack(skill)
    assert pack is not None
    save_case_pack(skill, pack)
    pack2 = load_case_pack(skill)
    assert pack2 is not None
    assert pack2.tool_checks is not None
    assert pack2.cases[0].tool_checks is not None


def test_unknown_tool_checks_key_rejected(tmp_path: Path) -> None:
    skill = tmp_path / "skills" / "demo"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: demo\ndescription: d\n---\n", encoding="utf-8")
    path = skill / "evals" / "cases.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(
        yaml.safe_dump(
            {
                "schema": 1,
                "skill": "demo",
                "cases": [
                    {
                        "id": "c1",
                        "status": "pinned",
                        "prompt": "p",
                        "tool_checks": {"must_cal": ["x"]},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(SuiteError):
        load_case_pack(skill)
