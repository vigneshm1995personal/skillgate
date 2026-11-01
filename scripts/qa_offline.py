#!/usr/bin/env python
"""Helpers for scripts/qa.sh: offline saved-run checks, log redaction, results JSON.

Run with the venv python, e.g. `python -I scripts/qa_offline.py rescore wrong-amount`.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
R6 = ROOT / "tests" / "fixtures" / "r6"
R12 = ROOT / "tests" / "fixtures" / "r12"

# saved-run id -> expected `skillgate rescore` exit code (0 green, 1 red)
RESCORE = {
    "refund-twice-one-done": 1,
    "timeout-success-double": 1,
    "guard-refused": 0,
    "both-succeeded": 1,
    "rg4-negation": 0,
    "wrong-amount": 1,
}


def cmd_rescore(case: str) -> int:
    from skillgate_ai.history import append_eval

    want = RESCORE[case]
    task = json.loads((R6 / "runs" / f"{case}.json").read_text(encoding="utf-8"))
    passed = task.get("passed")
    with tempfile.TemporaryDirectory() as tmp:
        pack = Path(tmp) / "desk"
        shutil.copytree(R6 / "desk", pack)
        append_eval(
            pack,
            run_id=case,
            passed=passed,
            report={
                "gate": "green" if passed else "red",
                "passed": passed,
                "passed_count": 1 if passed else 0,
                "task_count": 1,
                "skill": "desk",
                "tasks": [task],
            },
        )
        done = subprocess.run(
            ["skillgate", "rescore", case, "--pack", str(pack)],
            capture_output=True,
            text=True,
        )
    print(f"rescore {case}: exit {done.returncode}, expected {want}")
    return 0 if done.returncode == want else 1


def cmd_adv_amt() -> int:
    """Copied 4.90 reply against a 49.00 billing log must be an amount mismatch (red)."""
    from skillgate_ai.span_facts import amount_mismatch

    task = json.loads((R12 / "adv-amt.json").read_text(encoding="utf-8"))
    note = amount_mismatch(task.get("outputs"))
    print(f"amount_mismatch: {note}")
    return 0 if note and "4.90" in note and "49.00" in note else 1


def cmd_redact() -> int:
    secrets = [v for k, v in os.environ.items() if k.startswith("SKILLGATE_") and len(v) >= 8]
    text = sys.stdin.read()
    for value in secrets:
        text = text.replace(value, "***")
    sys.stdout.write(text)
    return 0


def cmd_report(rows_dir: str, out: str) -> int:
    rows = [json.loads(p.read_text()) for p in sorted(Path(rows_dir).glob("*.json"))]
    count = lambda s: sum(1 for r in rows if r["status"] == s)  # noqa: E731
    summary = {"total": len(rows), "pass": count("PASS"), "fail": count("FAIL"), "skipped": count("SKIP")}
    Path(out).write_text(json.dumps({"summary": summary, "results": rows}, indent=2) + "\n")
    print(f"{summary['pass']} pass, {summary['fail']} fail, {summary['skipped']} skipped -> {out}")
    return 1 if summary["fail"] else 0


def main(argv: list[str]) -> int:
    cmd, args = argv[1], argv[2:]
    if cmd == "rescore":
        return cmd_rescore(args[0])
    if cmd == "adv-amt":
        return cmd_adv_amt()
    if cmd == "redact":
        return cmd_redact()
    if cmd == "report":
        return cmd_report(*args)
    print(f"unknown command {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
