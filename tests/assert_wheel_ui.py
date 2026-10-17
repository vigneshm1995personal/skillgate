#!/usr/bin/env python3
"""Fail CI if the built wheel is missing the React UI."""

from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"


def main() -> None:
    wheels = sorted(DIST.glob("skillgate_ai-*.whl"))
    assert wheels, f"no wheel in {DIST}"
    wheel = wheels[-1]
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
    index = [name for name in names if name.endswith("skillgate_ai/web_static/index.html")]
    assets = [name for name in names if "/web_static/assets/" in name]
    sample = [
        name for name in names if name.endswith("skillgate_ai/examples/sample-skill/SKILL.md")
    ]
    pdf = [name for name in names if name.endswith("skillgate_ai/examples/pdf/SKILL.md")]
    sabotaged = [
        name for name in names if name.endswith("skillgate_ai/examples/pdf-sabotaged/SKILL.md")
    ]
    assert index, f"{wheel.name} missing skillgate_ai/web_static/index.html\n{names[:40]}"
    assert assets, f"{wheel.name} missing web_static/assets"
    assert sample, f"{wheel.name} missing skillgate_ai/examples/sample-skill/SKILL.md"
    assert pdf, f"{wheel.name} missing skillgate_ai/examples/pdf/SKILL.md"
    assert sabotaged, f"{wheel.name} missing skillgate_ai/examples/pdf-sabotaged/SKILL.md"
    print(f"{wheel.name} ships {index[0]}, examples, and {len(assets)} asset files")


if __name__ == "__main__":
    main()
