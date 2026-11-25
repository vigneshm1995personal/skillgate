from __future__ import annotations

from pathlib import Path

from skillgate_ai.compare.core import CompareArmSpec
from skillgate_ai.compare.payload import _dry_run_payload
from skillgate_ai.compare_format import (
    _arm_column_title,
    _fmt_cost,
    _fmt_duration,
    _row_to_line,
    format_compare_cli,
)


def test_fmt_cost_formats_sub_cent_and_missing() -> None:
    assert _fmt_cost(None) == "—"
    assert _fmt_cost(0.005) == "$0.0050"
    assert _fmt_cost(1.234) == "$1.23"
    assert _fmt_cost(0) == "$0.00"


def test_fmt_duration_minutes_and_seconds() -> None:
    assert _fmt_duration(59.6) == "1m 00s"
    assert _fmt_duration(5) == "5s"
    assert _fmt_duration(-3) == "0s"


def test_row_to_line_pads_and_truncates() -> None:
    assert _row_to_line([]) == ""
    case_col = "case"
    assert _row_to_line([case_col, None], arm_col_width=4) == (case_col.ljust(32) + " | " + "—   ")


def test_arm_column_title_dry_run_appends_subtitle() -> None:
    arm = {"label": "A", "subtitle": "Codex"}
    assert _arm_column_title(arm, status="dry_run") == "A · Codex"
    assert _arm_column_title(arm, status="done") == "A"
    long_arm = {"label": "Codex arm", "subtitle": "Codex"}
    assert _arm_column_title(long_arm, status="dry_run") == "Codex arm"


def test_format_compare_cli_dry_run_lists_every_arm(tmp_path: Path) -> None:
    pack = tmp_path / "pdf"
    pack.mkdir()
    arms = [
        CompareArmSpec(arm_id="a1", label="Arm one", harness_pref="codex", model=None),
        CompareArmSpec(arm_id="a2", label="Arm two", harness_pref="codex", model=None),
    ]
    payload = _dry_run_payload(
        pack,
        arms=arms,
        compare_id="c1",
        case_ids=["a", "b"],
        max_spend_usd=None,
    )
    out = format_compare_cli(payload)
    assert "Arm one" in out
    assert "Arm two" in out
    assert "a" in out and "b" in out
