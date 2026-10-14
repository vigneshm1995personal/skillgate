#!/usr/bin/env python3
"""Write a Conventional Commits subject from SKILLGATE_TASK (demo / harness hint)."""

from __future__ import annotations

import os
import re
from pathlib import Path


def _subject(prompt: str) -> str:
    lower = prompt.lower()
    if "readme" in lower or "documentation" in lower or "docstring" in lower:
        if "install" in lower or "readme" in lower:
            return "docs: clarify install steps in readme"
        return "docs: update project documentation"
    if "rename" in lower or "refactor" in lower:
        return "refactor: rename parse helper for clarity"
    if "export" in lower and "csv" in lower:
        return "feat: add csv export for orders"
    if "cart" in lower and ("total" in lower or "empty" in lower):
        return "fix: handle empty cart total"
    if "feat" in lower or "add " in lower:
        return "feat: add requested capability"
    if "fix" in lower or "bug" in lower:
        return "fix: correct reported issue"
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
