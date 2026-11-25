from __future__ import annotations

import json
from pathlib import Path

import pytest

from skillgate_ai.errors import HarnessError
from skillgate_ai.harness import selection as sel
from skillgate_ai.ingest import Skill


def _pdf_skill(tmp_path: Path) -> Skill:
    root = tmp_path / "skills" / "pdf"
    root.mkdir(parents=True)
    (root / "SKILL.md").write_text("---\nname: pdf\ndescription: PDF\n---\n", encoding="utf-8")
    return Skill(path=root, name="pdf", description="PDF", body="")


def test_write_and_read_selection_roundtrip(tmp_path: Path) -> None:
    sel._write_selection(tmp_path, "pdf")
    assert sel._read_selection(tmp_path) == "pdf"
    sel._write_selection(tmp_path, None)
    assert sel._read_selection(tmp_path) is None


def test_read_selection_missing_or_invalid(tmp_path: Path) -> None:
    assert sel._read_selection(tmp_path) is sel._MISSING
    bad = tmp_path / ".skillgate" / "selected.json"
    bad.parent.mkdir(parents=True)
    bad.write_text("not json", encoding="utf-8")
    assert sel._read_selection(tmp_path) is sel._MISSING


def test_parse_selected_prefers_selected_json(tmp_path: Path) -> None:
    skills = [_pdf_skill(tmp_path)]
    sel._write_selection(tmp_path, "pdf")
    assert sel._parse_selected(tmp_path, '{"skill":"ignored"}', skills) == "pdf"


def test_parse_skill_json_from_transcript(tmp_path: Path) -> None:
    skills = [_pdf_skill(tmp_path)]
    blob = 'noise {"skill": "pdf"} tail'
    assert sel._parse_skill_json(blob, skills) == "pdf"


def test_skill_tool_name_from_args_aliases() -> None:
    assert sel._skill_tool_name_from_args({"skillName": "pdf"}) == "pdf"
    assert sel._skill_tool_name_from_args({}) is None


def test_infer_from_skill_tool_completed_line(tmp_path: Path) -> None:
    skills = [_pdf_skill(tmp_path)]
    line = json.dumps(
        {
            "type": "tool_call",
            "subtype": "started",
            "tool_call": {"skillToolCall": {"args": {"skill": "pdf"}}},
        }
    )
    assert sel._infer_from_skill_tool(line, skills) == "pdf"


def test_parse_read_paths_requires_command_evidence() -> None:
    path = "/ws/.skillgate/skills/pdf/SKILL.md"
    assert sel._parse_read_paths(f"mention {path}") == []
    assert path in sel._parse_read_paths(f"$ read {path}")


def test_collect_read_paths_dedupes() -> None:
    path = "/proj/.skillgate/skills/pdf/SKILL.md"
    transcript = f"$ cat {path}\n$ read {path}\n"
    assert sel._collect_read_paths(transcript) == [path]


def test_infer_from_reads_single_skill() -> None:
    skills = [
        Skill(path=Path("/x/pdf"), name="pdf", description="", body=""),
        Skill(path=Path("/x/csv"), name="csv", description="", body=""),
    ]
    paths = ["/ws/skills/pdf/SKILL.md"]
    assert sel._infer_from_reads(paths, skills) == "pdf"
    assert sel._infer_from_reads(paths + ["/ws/skills/csv/SKILL.md"], skills) is None


def test_skill_for_selection_unknown_raises(tmp_path: Path) -> None:
    with pytest.raises(HarnessError, match="Couldn't find skill"):
        sel._skill_for_selection("missing", [_pdf_skill(tmp_path)])


def test_skill_name_from_path_claude_layout() -> None:
    assert sel._skill_name_from_path("/home/.claude/skills/pdf/scripts/run.py") == "pdf"


def test_resolve_trigger_evidence_uses_reads(tmp_path: Path) -> None:
    skills = [_pdf_skill(tmp_path)]
    path = f"{tmp_path}/.skillgate/skills/pdf/SKILL.md"
    transcript = f"$ read {path}\n"
    selected, reads = sel._resolve_trigger_evidence(tmp_path, transcript, skills)
    assert reads
    assert selected == "pdf"
