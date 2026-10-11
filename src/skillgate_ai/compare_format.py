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
    lines = [
        f"Compare · {skill} · {mode} · {len(cases)} checks · {len(arms)} arms",
    ]
    fp = str(data.get("pack_fingerprint") or "")
    if fp:
        lines.append(f"Dataset fingerprint  {fp[:12]}…")
    lines.append("")
    header = ["", *[str(a.get("label") or a.get("arm_id")) for a in arms]]
    lines.append("".join(f"{col:16}" for col in header[:1]) + "".join(f"{col:16}" for col in header[1:]))
    for arm in arms:
        pass
    summary_labels = ["Checks", "Tokens", "Cost", "Latency"]
    for label in summary_labels:
        row = [label]
        for arm in arms:
            if label == "Checks":
                row.append(f"{arm.get('passed_count')}/{arm.get('task_count')} Pass")
            elif label == "Tokens":
                usage = arm.get("usage") or {}
                total = usage.get("tokens_total")
                row.append(f"{total}k" if isinstance(total, int) and total >= 1000 else str(total or "—"))
            elif label == "Cost":
                usage = arm.get("usage") or {}
                cost = usage.get("cost_usd")
                row.append(f"${cost:.2f}" if isinstance(cost, (int, float)) else "—")
            else:
                dur = arm.get("duration_sec")
                row.append(_fmt_duration(dur) if dur is not None else "—")
        lines.append(_row_to_line(row))
    lines.append("")
    lines.append(f"{'Case':16}" + "".join(f"{str(a.get('label') or ''):16}" for a in arms))
    for case in cases:
        case_id = str(case.get("case_id") or "")
        row = [case_id[:16]]
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
        lines.append(_row_to_line(row))
    disagreements = sum(1 for c in cases if c.get("disagreement"))
    if disagreements:
        lines.append("")
        lines.append(f"{disagreements} cases disagreed.")
    spend = data.get("spend") or {}
    if spend.get("stopped_reason") == "spend_cap":
        lines.append("Stopped early: spend cap reached.")
    return "\n".join(lines)


def _row_to_line(cols: list[str]) -> str:
    return "".join(f"{(col or '—')[:16]:16}" for col in cols)


def _fmt_duration(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    minutes, secs = divmod(total, 60)
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"
