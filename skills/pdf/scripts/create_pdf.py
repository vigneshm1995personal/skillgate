#!/usr/bin/env python3
"""Create a simple one-page PDF."""

from __future__ import annotations

import argparse
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output")
    parser.add_argument("--title", default="Untitled")
    parser.add_argument("--body", default="")
    args = parser.parse_args()
    dest = Path(args.output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(dest), pagesize=letter)
    _, height = letter
    c.setFont("Times-Bold", 20)
    c.drawString(72, height - 96, args.title)
    c.setFont("Times-Roman", 14)
    c.drawString(72, height - 128, args.body)
    c.save()
    print(f"wrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
