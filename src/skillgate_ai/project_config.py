"""Committed project extras: `skillgate.yaml` (no secrets)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from skillgate_ai.errors import SuiteError


def load_project_judge(root: str | Path | None) -> dict[str, Any] | None:
    if root is None:
        return None
    path = Path(root).expanduser().resolve() / "skillgate.yaml"
    if not path.is_file():
        return None
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise SuiteError("skillgate.yaml is not valid YAML.", exit_code=2) from exc
    if not isinstance(raw, dict):
        raise SuiteError("skillgate.yaml must be a mapping.", exit_code=2)
    judge = raw.get("judge")
    return judge if isinstance(judge, dict) else None
