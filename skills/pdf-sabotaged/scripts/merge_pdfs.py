#!/usr/bin/env python3
"""Merge PDFs into one file. First argument is the output path."""

from __future__ import annotations

import sys
from pathlib import Path

from pypdf import PdfReader, PdfWriter


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: merge_pdfs.py OUTPUT.pdf INPUT1.pdf INPUT2.pdf ...", file=sys.stderr)
        return 2
    dest = Path(sys.argv[1])
    inputs = [Path(p) for p in sys.argv[2:]]
    writer = PdfWriter()
    for path in inputs:
        reader = PdfReader(str(path))
        for page in reader.pages:
            writer.add_page(page)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as handle:
        writer.write(handle)
    print(f"wrote {dest} ({len(writer.pages)} pages)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
