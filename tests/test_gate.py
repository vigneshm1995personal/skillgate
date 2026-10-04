from __future__ import annotations

from pathlib import Path

from skillgate_ai.demo_files import ensure_demo_pdfs
from skillgate_ai.gate import run_check


def test_gate_matches_cli_exits(project_root: Path) -> None:
    pdf = project_root / "skills" / "pdf"
    sabotaged = project_root / "skills" / "pdf-sabotaged"
    ensure_demo_pdfs(pdf / "evals" / "fixtures")
    ensure_demo_pdfs(sabotaged / "evals" / "fixtures")

    green = run_check(pdf, source="test", root=project_root)
    assert green.exit_code == 0
    assert green.report is not None and green.report.passed

    red = run_check(sabotaged, source="test", root=project_root)
    assert red.exit_code == 1
    assert red.report is not None and not red.report.passed

    expected = run_check(sabotaged, expect_fail=True, source="test", root=project_root)
    assert expected.exit_code == 0
    assert expected.expect_fail_notice

    live = run_check(pdf, live=True, source="test", root=project_root)
    assert live.exit_code == 2
    assert live.error is not None
    assert "No model key" in (live.error.get("message") or "")
