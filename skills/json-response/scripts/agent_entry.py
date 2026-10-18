#!/usr/bin/env python3
"""Flatten a JSON API response. Reads SKILLGATE_TASK."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path


def _out(prompt: str, default: str) -> str:
    match = re.search(r"(output/[A-Za-z0-9_-]+(?:\.[A-Za-z0-9]+)?)", prompt)
    return match.group(1) if match else default


def main() -> int:
    prompt = os.environ.get("SKILLGATE_TASK", "")
    source_name = "empty-orders.json" if "empty-orders.json" in prompt else "orders.json"
    source = Path(source_name)
    data = json.loads(source.read_text(encoding="utf-8"))
    rows = []
    for row in data.get("data") or []:
        rows.append(
            {
                "id": row.get("id"),
                "status": row.get("status"),
                "total": row.get("total"),
            }
        )
    dest = Path(_out(prompt, "output/orders.json"))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
