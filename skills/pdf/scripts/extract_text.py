#!/usr/bin/env python3
"""Extract text from a PDF."""

from __future__ import annotations

import sys
from pathlib import Path

from pypdf import PdfReader


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: extract_text.py INPUT.pdf OUTPUT.txt", file=sys.stderr)
        return 2
    source = Path(sys.argv[1])
    dest = Path(sys.argv[2])
    dest.parent.mkdir(parents=True, exist_ok=True)
    reader = PdfReader(str(source))
    text = "\n".join((page.extract_text() or "") for page in reader.pages)
    dest.write_text(text, encoding="utf-8")
    print(f"wrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
