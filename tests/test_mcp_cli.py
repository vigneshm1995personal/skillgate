from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from skillgate_ai.cli import app
from skillgate_ai.extras import MCP_FEATURE, MissingExtraError

runner = CliRunner()


def test_mcp_command_registered() -> None:
    result = runner.invoke(app, ["mcp", "--help"])
    assert result.exit_code == 0
    assert "stdio" in result.stdout.lower() or "mcp" in result.stdout.lower()


def test_mcp_missing_extra_exits_2_on_stderr(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a, **_k):
        raise MissingExtraError(MCP_FEATURE, "mcp")

    monkeypatch.setattr("skillgate_ai.extras.require_extra", boom)
    result = runner.invoke(app, ["mcp"])
    assert result.exit_code == 2
    assert "skillgate-ai[mcp]" in result.output
    assert result.stdout == ""


def test_mcp_root_option_and_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict = {}

    def fake_serve(root: Path) -> None:
        seen["root"] = root
        raise SystemExit(0)

    monkeypatch.setattr("skillgate_ai.mcp.server.serve", fake_serve)
    explicit = runner.invoke(app, ["mcp", "--root", str(tmp_path)])
    assert explicit.exit_code == 0
    assert seen["root"] == tmp_path.resolve()
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path / "env-root"))
    (tmp_path / "env-root").mkdir()
    seen.clear()
    from_env = runner.invoke(app, ["mcp"])
    assert from_env.exit_code == 0
    assert seen["root"] == (tmp_path / "env-root").resolve()


def test_mcp_bad_root_exits_2(tmp_path: Path) -> None:
    missing = tmp_path / "nope"
    result = runner.invoke(app, ["mcp", "--root", str(missing)])
    assert result.exit_code == 2
    assert "not a folder" in result.output.lower()
