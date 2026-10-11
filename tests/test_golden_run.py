"""Run must treat pack goldens as expected output (imported pdf)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from skillgate_ai.case_pack import (
    PIN_NEEDS_EXPECTED,
    _persist_golden,
    checks_from_pack,
    load_case_pack,
    suite_from_checks,
)
from skillgate_ai.pack import copy_skill_pack

ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / "skills" / "pdf"


def _imported_pdf(tmp_path: Path) -> Path:
    dest = tmp_path / "skills" / "pdf"
    copy_skill_pack(PDF, dest, include_goldens=True)
    assert (dest / "evals" / "goldens" / "merge-alpha-beta.pdf").is_file()
    return dest


def _ui_run_payload(checks: list[dict]) -> list[dict]:
    """What the Checks tab used to POST: ids and output_path, goldens stripped."""
    out = []
    for index, check in enumerate(checks):
        out.append(
            {
                "id": check.get("id") or f"check-{index + 1}",
                "prompt": check.get("prompt"),
                "should_trigger": check.get("should_trigger", True),
                "output_path": check.get("output_path"),
                "contains": check.get("contains") or None,
                "min_pages": check.get("min_pages"),
                "files": check.get("files") or [],
                "needs_upload": bool(check.get("needs_upload")),
            }
        )
    return out


def test_imported_pdf_binary_golden_is_enough_without_contains(tmp_path: Path) -> None:
    dest = _imported_pdf(tmp_path)
    pack = load_case_pack(dest)
    assert pack is not None
    checks = checks_from_pack(pack, include_drafts=True)
    merge = next(item for item in checks if item["id"] == "merge-alpha-beta")
    assert merge.get("golden_path")
    assert not merge.get("contains")

    spec = suite_from_checks(
        dest,
        [
            {
                "id": "merge-alpha-beta",
                "prompt": merge["prompt"],
                "should_trigger": True,
                "output_path": merge["output_path"],
                "golden_path": merge["golden_path"],
                "golden_kind": merge.get("golden_kind"),
                "files": merge["files"],
                "contains": None,
            }
        ],
    )
    assert spec.tasks
    assert spec.tasks[0].id == "merge-alpha-beta"


def test_imported_pdf_golden_survives_when_check_id_does_not_match_stem(
    tmp_path: Path,
) -> None:
    dest = _imported_pdf(tmp_path)
    pack = load_case_pack(dest)
    assert pack is not None
    merge = next(
        item
        for item in checks_from_pack(pack, include_drafts=True)
        if item["id"] == "merge-alpha-beta"
    )
    spec = suite_from_checks(
        dest,
        [
            {
                "id": "check-2",
                "prompt": merge["prompt"],
                "should_trigger": True,
                "output_path": merge["output_path"],
                "golden_path": merge["golden_path"],
                "files": merge["files"],
                "contains": None,
            }
        ],
    )
    assert spec.tasks[0].id == "check-2"


def test_imported_pdf_full_suite_from_ui_payload_with_golden_path(tmp_path: Path) -> None:
    dest = _imported_pdf(tmp_path)
    pack = load_case_pack(dest)
    assert pack is not None
    checks = checks_from_pack(pack, include_drafts=True)
    payload = []
    for index, check in enumerate(checks):
        payload.append(
            {
                "id": check.get("id") or f"check-{index + 1}",
                "prompt": check.get("prompt"),
                "should_trigger": check.get("should_trigger", True),
                "output_path": check.get("output_path"),
                "contains": check.get("contains") or None,
                "min_pages": check.get("min_pages"),
                "files": check.get("files") or [],
                "needs_upload": bool(check.get("needs_upload")),
                "golden_path": check.get("golden_path"),
                "golden_kind": check.get("golden_kind"),
            }
        )
    spec = suite_from_checks(dest, payload)
    assert len(spec.tasks) == 8


def test_ui_payload_without_golden_path_still_attaches_disk_file(tmp_path: Path) -> None:
    dest = _imported_pdf(tmp_path)
    pack = load_case_pack(dest)
    assert pack is not None
    checks = checks_from_pack(pack, include_drafts=True)
    spec = suite_from_checks(dest, _ui_run_payload(checks))
    assert len(spec.tasks) == 8


def test_pdf_golden_attached_by_path_is_bytes(tmp_path: Path) -> None:
    dest = _imported_pdf(tmp_path)
    golden = _persist_golden(
        dest,
        case_id="check-2",
        output_path="output/merged.pdf",
        golden_path="evals/goldens/merge-alpha-beta.pdf",
        contains_list=[],
    )
    assert golden.kind == "bytes"
    assert golden.path.endswith("merge-alpha-beta.pdf") or "check-2" in golden.path


def test_missing_golden_and_contains_still_asks_for_expected(tmp_path: Path) -> None:
    dest = tmp_path / "empty-skill"
    dest.mkdir()
    (dest / "SKILL.md").write_text("---\nname: empty-skill\n---\n\n# Empty\n", encoding="utf-8")
    with pytest.raises(Exception) as excinfo:
        suite_from_checks(
            dest,
            [
                {
                    "id": "needs-expected",
                    "prompt": "Write output/result.txt",
                    "should_trigger": True,
                    "output_path": "output/result.txt",
                    "contains": None,
                }
            ],
        )
    assert PIN_NEEDS_EXPECTED in str(excinfo.value)


def test_golden_path_cannot_copy_file_from_outside_skill(tmp_path: Path) -> None:
    dest = tmp_path / "skill"
    dest.mkdir()
    (dest / "SKILL.md").write_text("---\nname: skill\n---\n\n# Skill\n", encoding="utf-8")
    secret = tmp_path / "secret.txt"
    secret.write_text("hunter2\n", encoding="utf-8")
    with pytest.raises(Exception) as excinfo:
        suite_from_checks(
            dest,
            [
                {
                    "id": "leak",
                    "prompt": "Write output/result.txt",
                    "should_trigger": True,
                    "output_path": "output/result.txt",
                    "golden_path": str(secret),
                    "contains": None,
                }
            ],
        )
    assert PIN_NEEDS_EXPECTED in str(excinfo.value)
    goldens = dest / "evals" / "goldens"
    assert not goldens.exists() or not any(goldens.iterdir())


def test_golden_path_rejects_parent_directory_escape(tmp_path: Path) -> None:
    dest = tmp_path / "skill"
    dest.mkdir()
    (dest / "SKILL.md").write_text("---\nname: skill\n---\n\n# Skill\n", encoding="utf-8")
    secret = tmp_path / "secret.txt"
    secret.write_text("hunter2\n", encoding="utf-8")
    with pytest.raises(Exception) as excinfo:
        suite_from_checks(
            dest,
            [
                {
                    "id": "leak",
                    "prompt": "Write output/result.txt",
                    "should_trigger": True,
                    "output_path": "output/result.txt",
                    "golden_path": "../secret.txt",
                    "contains": None,
                }
            ],
        )
    assert PIN_NEEDS_EXPECTED in str(excinfo.value)
    goldens = dest / "evals" / "goldens"
    assert not goldens.exists() or not any(goldens.iterdir())
