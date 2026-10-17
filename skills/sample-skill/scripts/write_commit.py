#!/usr/bin/env python3
"""Write the model-authored commit subject (argv) to the task output file."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: write_commit.py <subject line>", file=sys.stderr)
        return 2
    subject = " ".join(sys.argv[1:]).strip()
    if not subject:
        print("subject is empty", file=sys.stderr)
        return 2
    dest = Path("output/commit.txt")
    task = os.environ.get("SKILLGATE_TASK", "")
    if match := re.search(r"(output/[A-Za-z0-9_.-]+)", task):
        dest = Path(match.group(1))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(subject + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
