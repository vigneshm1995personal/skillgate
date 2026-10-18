#!/usr/bin/env python3
"""Summarize a log file. Reads SKILLGATE_TASK."""

from __future__ import annotations

import os
import re
from pathlib import Path


def _out(prompt: str, default: str) -> str:
    match = re.search(r"(output/[A-Za-z0-9_-]+(?:\.[A-Za-z0-9]+)?)", prompt)
    return match.group(1) if match else default


def summarize(text: str) -> str:
    errors = 0
    warnings = 0
    codes: dict[str, int] = {}
    for line in text.splitlines():
        kind = ""
        if " ERROR " in line:
            errors += 1
            kind = "error"
        elif " WARN " in line:
            warnings += 1
            kind = "warn"
        match = re.search(r"error=([A-Za-z0-9_-]+)", line)
        if match and kind:
            code = match.group(1)
            codes[code] = codes.get(code, 0) + 1
    lines = [f"Errors: {errors}", f"Warnings: {warnings}"]
    for code in sorted(codes):
        lines.append(f"{code}: {codes[code]}")
    return "\n".join(lines) + "\n"


def main() -> int:
    prompt = os.environ.get("SKILLGATE_TASK", "")
    names = re.findall(r"([A-Za-z0-9_.-]+\.log)", prompt)
    source = Path(names[0] if names else "app.log")
    dest = Path(_out(prompt, "output/summary.txt"))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(summarize(source.read_text(encoding="utf-8")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
