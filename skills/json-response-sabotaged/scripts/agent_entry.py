#!/usr/bin/env python3
"""Intentional miss: write a snack list instead of the JSON the check expects."""

from __future__ import annotations

import os
import re
from pathlib import Path


def _out(prompt: str, default: str) -> str:
    match = re.search(r"(output/[A-Za-z0-9_-]+(?:\.[A-Za-z0-9]+)?)", prompt)
    return match.group(1) if match else default


def main() -> int:
    prompt = os.environ.get("SKILLGATE_TASK", "")
    dest = Path(_out(prompt, "output/orders.json"))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("coffee and pastry\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
