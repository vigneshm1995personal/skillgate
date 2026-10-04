from __future__ import annotations

from pathlib import Path

import pytest

from skillgate_ai.case_pack import load_case_pack
from skillgate_ai.errors import IngestError, SuiteError
from skillgate_ai.gate import run_check
from skillgate_ai.ingest import ingest_skill
from skillgate_ai.scaffold import create_pack, scaffold_trigger_cases
from skillgate_ai.skill_md import write_skill_md


def test_create_pack_name_matches_folder(tmp_path: Path) -> None:
    dest = create_pack(tmp_path, "my-notes")
    skill = ingest_skill(dest)
    assert skill.name == "my-notes"
    assert dest.name == "my-notes"


def test_create_pack_rejects_bad_name(tmp_path: Path) -> None:
    with pytest.raises(IngestError, match="invalid"):
        create_pack(tmp_path, "MyNotes")


def test_name_mismatch_on_write(tmp_path: Path) -> None:
    folder = tmp_path / "other"
    folder.mkdir()
    with pytest.raises(IngestError, match="must match"):
        write_skill_md(
            folder,
            name="my-skill",
            description="Produce notes and extracts for this skill. Use when the user asks for notes.",
        )


def test_trigger_only_pack_greens_without_keys(tmp_path: Path, project_root: Path) -> None:
    dest = create_pack(tmp_path, "doc-notes")
    scaffold_trigger_cases(dest)
    result = run_check(dest, source="test", root=project_root)
    assert result.exit_code == 0, result.error
    assert result.report is not None and result.report.passed


def test_invalid_cases_yaml_is_suite_error(tmp_path: Path) -> None:
    dest = create_pack(tmp_path, "bad-yaml")
    cases = dest / "evals" / "cases.yaml"
    cases.parent.mkdir(parents=True, exist_ok=True)
    cases.write_text("{[ definitely not yaml", encoding="utf-8")
    with pytest.raises(SuiteError, match="not valid YAML"):
        load_case_pack(dest)
