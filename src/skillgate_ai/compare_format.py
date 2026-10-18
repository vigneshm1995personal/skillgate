"""Human-readable compare output for CLI."""

from __future__ import annotations

from typing import Any

from skillgate_ai.compare import scrub_compare_payload


def format_compare_cli(payload: dict[str, Any]) -> str:
    data = scrub_compare_payload(payload)
    mode = str(data.get("mode") or "compare")
    skill = str(data.get("skill") or "")
    arms = data.get("arms") or []
    cases = data.get("cases") or []
    status = str(data.get("status") or "")
    lines = [
        f"Compare · {skill} · {mode} · {len(cases)} checks · {len(arms)} arms",
    ]
    picker = data.get("picker")
    if status == "dry_run" and isinstance(picker, dict):
        lines.append("")
        lines.append("Pick two history runs (--run twice) or two git refs (--git twice).")
        recent = picker.get("recent_runs") or []
        if recent:
            lines.append(f"Recent runs: {', '.join(str(r) for r in recent)}")
        git_refs = picker.get("git_refs") or []
        if git_refs:
            lines.append(f"Git refs: {', '.join(str(r) for r in git_refs)}")
    fp = str(data.get("pack_fingerprint") or "")
    if fp:
        lines.append(f"Dataset fingerprint  {fp[:12]}…")
    lines.append("")
    arm_width = 42 if status == "dry_run" else 12
    header = ["", *[_arm_column_title(a, status=status) for a in arms]]
    lines.append(_row_to_line(header, arm_col_width=arm_width))
    summary_labels = ["Checks", "Tokens", "Cost", "Latency"]
    for label in summary_labels:
        row = [label]
        for arm in arms:
            if label == "Checks":
                pc, tc = arm.get("passed_count"), arm.get("task_count")
                if pc is None or tc is None:
                    row.append("—")
                else:
                    row.append(f"{pc}/{tc} Pass")
            elif label == "Tokens":
                usage = arm.get("usage") or {}
                total = usage.get("tokens_total")
                if isinstance(total, int) and total >= 1000:
                    row.append(f"{total / 1000:.1f}k")
                else:
                    row.append(str(total if total is not None else "—"))
            elif label == "Cost":
                usage = arm.get("usage") or {}
                cost = usage.get("cost_usd")
                row.append(_fmt_cost(cost))
            else:
                dur = arm.get("duration_sec")
                row.append(_fmt_duration(dur) if dur is not None else "—")
        lines.append(_row_to_line(row, arm_col_width=arm_width))
    lines.append("")
    lines.append(_row_to_line(["Case", *[_arm_column_title(a, status=status) for a in arms]], arm_col_width=arm_width))
    for case in cases:
        case_id = str(case.get("case_id") or "")
        row = [case_id]
        results = case.get("results") or {}
        for arm in arms:
            cell = results.get(str(arm.get("arm_id"))) or {}
            passed = cell.get("passed")
            if passed is True:
                row.append("Pass")
            elif passed is False:
                row.append("Fail")
            else:
                row.append("—")
        lines.append(_row_to_line(row, arm_col_width=arm_width))
    disagreements = sum(1 for c in cases if c.get("disagreement"))
    if disagreements:
        lines.append("")
        lines.append(f"{disagreements} cases disagreed.")
    spend = data.get("spend") or {}
    if spend.get("stopped_reason") == "spend_cap":
        lines.append("Stopped early: spend cap reached.")
    return "\n".join(lines)


def _arm_column_title(arm: dict[str, Any], *, status: str) -> str:
    label = str(arm.get("label") or arm.get("arm_id") or "")
    if status == "dry_run":
        subtitle = str(arm.get("subtitle") or "").strip()
        if subtitle and subtitle not in label:
            return f"{label} · {subtitle}"
    return label


def _fmt_cost(cost: int | float | None) -> str:
    if not isinstance(cost, (int, float)):
        return "—"
    if 0 < abs(cost) < 0.01:
        return f"${cost:.4f}"
    return f"${cost:.2f}"


def _row_to_line(cols: list[str], *, arm_col_width: int = 12) -> str:
    if not cols:
        return ""
    first = (cols[0] or "—")[:32].ljust(32)
    rest = [(col or "—")[:arm_col_width].ljust(arm_col_width) for col in cols[1:]]
    return " | ".join([first, *rest])


def _fmt_duration(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    minutes, secs = divmod(total, 60)
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"
