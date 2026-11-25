from __future__ import annotations

import shutil
from pathlib import Path

from skillgate_ai.case_pack import load_case_pack, suite_from_pack
from skillgate_ai.case_pack.suites import (
    checks_from_pack,
    suite_fingerprint,
    trust_suite_for_skill,
)

ROOT = Path(__file__).resolve().parents[1]


def test_trust_suite_for_pdf_skill() -> None:
    trust = trust_suite_for_skill(ROOT / "skills" / "pdf")
    assert trust is not None
    assert trust.fingerprint
    assert trust.case_ids


def test_checks_from_pack_lists_pinned_rows(tmp_path: Path) -> None:
    dest = tmp_path / "pdf"
    shutil.copytree(ROOT / "skills" / "pdf", dest)
    pack = load_case_pack(dest)
    assert pack is not None
    rows = checks_from_pack(pack)
    assert rows
    assert all(row.get("bank_status") == "pinned" for row in rows)


def test_suite_fingerprint_is_stable_for_pack() -> None:
    pack = load_case_pack(ROOT / "skills" / "pdf")
    assert pack is not None
    spec = suite_from_pack(pack, str(ROOT / "skills" / "pdf"))
    first = suite_fingerprint(spec)
    second = suite_fingerprint(spec)
    assert first == second
    assert len(first) == 16
