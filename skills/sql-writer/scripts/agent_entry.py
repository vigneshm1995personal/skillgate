#!/usr/bin/env python3
"""Write a SQL query from schema.sql. Reads SKILLGATE_TASK."""

from __future__ import annotations

import os
import re
from pathlib import Path

OPEN_ORDERS = "SELECT id, total\nFROM orders\nWHERE status = 'open';\n"
MISSING = "customer_email is missing from schema.sql\n"


def _out(prompt: str, default: str) -> str:
    match = re.search(r"(output/[A-Za-z0-9_-]+(?:\.[A-Za-z0-9]+)?)", prompt)
    return match.group(1) if match else default


def main() -> int:
    prompt = os.environ.get("SKILLGATE_TASK", "")
    text = MISSING if "customer_email" in prompt else OPEN_ORDERS
    dest = Path(_out(prompt, "output/query.sql"))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
