#!/usr/bin/env python3
"""Rotate every page of a PDF."""

from __future__ import annotations

import argparse
from pathlib import Path

from pypdf import PdfReader, PdfWriter


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_pdf")
    parser.add_argument("output_pdf")
    parser.add_argument("--degrees", type=int, default=90)
    args = parser.parse_args()
    reader = PdfReader(args.input_pdf)
    writer = PdfWriter()
    for page in reader.pages:
        page.rotate(args.degrees)
        writer.add_page(page)
    dest = Path(args.output_pdf)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as handle:
        writer.write(handle)
    print(f"wrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
