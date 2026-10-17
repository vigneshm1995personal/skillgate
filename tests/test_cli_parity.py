"""Every OSS UI write route has a CLI command. New API writes must update the map."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from skillgate_ai.api import create_app
from skillgate_ai.cli import app
from skillgate_ai.cli_parity import HOSTED_SHIMS, READ_ROUTE_CLI, WRITE_ROUTE_CLI

WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
DOCS = Path(__file__).resolve().parents[1] / "docs" / "ui.md"
runner = CliRunner()


def _write_routes() -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for route in create_app().routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if not path or not methods:
            continue
        for method in methods:
            if method in WRITE_METHODS:
                found.add((method, path))
    return found


def test_every_oss_write_route_has_a_cli_command() -> None:
    routes = _write_routes()
    mapped = set(WRITE_ROUTE_CLI) | set(HOSTED_SHIMS)
    missing = sorted(routes - mapped)
    extra = sorted(set(WRITE_ROUTE_CLI) - routes)
    assert missing == [], f"UI write routes with no CLI map: {missing}"
    assert extra == [], f"CLI map entries that are not app write routes: {extra}"
    leaked = sorted(set(HOSTED_SHIMS) & set(WRITE_ROUTE_CLI))
    assert leaked == [], f"hosted shims listed as OSS writes: {leaked}"


def test_mapped_cli_commands_exist() -> None:
    seen: set[str] = set()
    for command in list(WRITE_ROUTE_CLI.values()) + list(READ_ROUTE_CLI.values()):
        if command in seen:
            continue
        seen.add(command)
        result = runner.invoke(app, [*command.split(), "--help"])
        assert result.exit_code == 0, f"{command}: {result.stdout}\n{result.stderr}"


def test_parity_table_is_in_docs() -> None:
    text = DOCS.read_text(encoding="utf-8")
    assert "UI / CLI parity" in text
    for command in sorted(set(WRITE_ROUTE_CLI.values())):
        assert command in text, command
    for command in sorted(set(READ_ROUTE_CLI.values())):
        assert command in text, command
    assert "login --status" in text
    assert "skillgate login" in text
    assert "skillgate history" in text
    assert "case list" in text
    assert "case remove" in text
    assert "judge remove-question" in text
    assert "check --case" in text
    assert "history show" in text
    assert "import --only" in text
    assert "--choices" in text
