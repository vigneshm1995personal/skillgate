#!/usr/bin/env python3
"""Extract merchant, date, and total from a text receipt. Reads SKILLGATE_TASK."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path


def _out(prompt: str, default: str) -> str:
    match = re.search(r"(output/[A-Za-z0-9_-]+(?:\.[A-Za-z0-9]+)?)", prompt)
    return match.group(1) if match else default


def extract(text: str) -> dict[str, str | None]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    merchant = lines[0] if lines else ""
    date = ""
    total: str | None = None
    for line in lines:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", line):
            date = line
        if line.lower().startswith("total"):
            parts = line.split()
            if parts:
                total = parts[-1]
    return {"merchant": merchant, "date": date, "total": total}


def main() -> int:
    prompt = os.environ.get("SKILLGATE_TASK", "")
    names = re.findall(r"([A-Za-z0-9_.-]+\.txt)", prompt)
    source = Path(names[0] if names else "harbor-receipt.txt")
    payload = extract(source.read_text(encoding="utf-8"))
    dest = Path(_out(prompt, "output/receipt.json"))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
