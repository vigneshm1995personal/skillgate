#!/usr/bin/env python3
"""Write a README from a brief. Reads SKILLGATE_TASK."""

from __future__ import annotations

import os
import re
from pathlib import Path


def _out(prompt: str, default: str) -> str:
    match = re.search(r"(output/[A-Za-z0-9_-]+(?:\.[A-Za-z0-9]+)?)", prompt)
    return match.group(1) if match else default


def _fields(path: Path) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        found[key.strip().lower()] = value.strip()
    return found


def _render(fields: dict[str, str]) -> str:
    license_value = fields.get("license") or "not specified"
    lines = [
        f"# {fields.get('project', 'Untitled')}",
        "",
        fields.get("what", ""),
        "",
        "## Install",
        "",
        fields.get("install", ""),
        "",
        "## Usage",
        "",
        fields.get("command", ""),
        "",
        "## License",
        "",
        license_value,
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    prompt = os.environ.get("SKILLGATE_TASK", "")
    source_name = "brief-no-license.txt" if "brief-no-license.txt" in prompt else "brief.txt"
    fields = _fields(Path(source_name))
    dest = Path(_out(prompt, "output/README.md"))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(_render(fields), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
