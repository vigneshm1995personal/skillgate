"""CodeQL workflow: enforce must query the same ref the analyze job uploaded."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODEQL = ROOT / ".github" / "workflows" / "codeql.yml"


def test_enforce_uses_analyze_scan_ref_output() -> None:
    text = CODEQL.read_text(encoding="utf-8")
    assert "scan_ref: ${{ steps.merge_meta.outputs.scan_ref }}" in text
    assert 'scan_ref="${{ needs.analyze.outputs.scan_ref }}"' in text
    assert "commits/$(git rev-parse HEAD)/pulls" not in text
    assert "pr_number=${pr_number}" not in text
