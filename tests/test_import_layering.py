from __future__ import annotations

import subprocess
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"

CONTRACT_NAMES = frozenset(
    {
        "FS core does not import domain or surfaces",
        "Domain does not import HTTP, CLI or MCP surfaces",
        "HTTP surface does not import CLI or MCP",
        "FS primitives are leaves",
    }
)

FS_CORE_SOURCES = frozenset(
    {
        "skillgate_ai.path_traversal",
        "skillgate_ai.fs_anchor",
        "skillgate_ai.contained_fs",
        "skillgate_ai.pack_layout",
        "skillgate_ai.allow_root",
        "skillgate_ai.pack_io",
        "skillgate_ai.paths",
        "skillgate_ai.trusted_roots",
        "skillgate_ai.agent_roots",
    }
)


def _importlinter_config() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["tool"]["importlinter"]


def test_importlinter_contract_names() -> None:
    cfg = _importlinter_config()
    names = {c["name"] for c in cfg["contracts"]}
    assert names == CONTRACT_NAMES
    assert cfg["root_package"] == "skillgate_ai"


def test_fs_core_contract_lists_every_fs_module() -> None:
    cfg = _importlinter_config()
    contract = next(
        c for c in cfg["contracts"] if c["name"] == "FS core does not import domain or surfaces"
    )
    sources = set(contract["source_modules"])
    forbidden = set(contract["forbidden_modules"])
    assert sources >= FS_CORE_SOURCES
    assert {"skillgate_ai.deploy", "skillgate_ai.history", "skillgate_ai.mcp"} <= forbidden


def test_lint_imports_passes() -> None:
    pytest.importorskip("importlinter")
    import sys

    lint_imports = ROOT / ".venv" / "bin" / "lint-imports"
    if not lint_imports.is_file():
        lint_imports = Path(sys.executable).with_name("lint-imports")
    proc = subprocess.run(
        [str(lint_imports), "--no-cache"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    combined = proc.stdout + proc.stderr
    assert "0 broken" in combined or "KEPT" in combined


def test_gate_workflow_runs_lint_imports() -> None:
    gate_yml = (ROOT / ".github/workflows/gate.yml").read_text(encoding="utf-8")
    precommit = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    assert "run: lint-imports" in gate_yml
    assert "entry: lint-imports" in precommit
