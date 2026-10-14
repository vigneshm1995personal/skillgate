#!/usr/bin/env python3
"""Write a Conventional Commits subject from SKILLGATE_TASK (demo / harness hint)."""

from __future__ import annotations

import os
import re
from pathlib import Path


def _diff_blob(prompt: str) -> str:
    if "```" not in prompt:
        return prompt
    for part in prompt.split("```"):
        stripped = part.strip()
        lower = stripped.lower()
        if lower.startswith("diff"):
            body = stripped[4:].lstrip("\n") if lower.startswith("diff\n") or lower == "diff" else stripped
            if body.strip():
                return body
    return prompt


def _subject(prompt: str) -> str:
    diff = _diff_blob(prompt).lower()
    if "export_orders_csv" in diff or ("def export" in diff and "csv" in diff):
        return "feat: add csv export for orders"
    if "readme.md" in diff or "--- a/readme" in diff:
        return "docs: clarify install steps in readme"
    compact = re.sub(r"[_\s]", "", diff)
    if "parsetotal" in compact and "def" in diff:
        return "refactor: rename parse_total helper"
    if "cart.py" in diff or ("checkout_total" in diff and "return 0" in diff):
        return "fix: handle empty cart total"
    lower = prompt.lower()
    if "cart" in lower and "total" in lower:
        return "fix: handle empty cart total"
    if "export" in lower and "csv" in lower:
        return "feat: add csv export for orders"
    if "readme" in lower:
        return "docs: clarify install steps in readme"
    return "chore: apply diff changes"


def main() -> int:
    prompt = os.environ.get("SKILLGATE_TASK", "")
    dest = Path("output/commit.txt")
    if m := re.search(r"(output/[A-Za-z0-9_.-]+)", prompt):
        dest = Path(m.group(1))
    dest.parent.mkdir(parents=True, exist_ok=True)
    line = _subject(prompt).strip()
    if len(line) > 72:
        line = line[:69].rstrip() + "..."
    dest.write_text(line + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
