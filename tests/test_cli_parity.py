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


_SETTINGS_TSX = (
    Path(__file__).resolve().parents[1] / "web" / "src" / "components" / "dashboard" / "settings-page.tsx"
)
_WEB_STATIC = Path(__file__).resolve().parents[1] / "src" / "skillgate_ai" / "web_static"
_OLD_KEY_COPY = (
    "Model keys",
    "Keys stay on this machine",
    "Runs live checks",
    "Paste key",
    "Claude / Anthropic",
    "settings-cursor-input",
    "settings-codex-input",
    "settings-openai-input",
    "settings-anthropic-input",
    "CURSOR_API_KEY",
    "CODEX_API_KEY",
    "ANTHROPIC_API_KEY",
    "AI Gateway",
)


def test_settings_screen_has_no_provider_key_fields() -> None:
    text = _SETTINGS_TSX.read_text(encoding="utf-8")
    for phrase in _OLD_KEY_COPY:
        assert phrase not in text, phrase
    assert text.count('type="password"') == 1
    assert "signed in" in text
    assert "not signed in" in text
    assert "Decision model" in text
    assert "Not selected" in text
    assert "Pick a decision model before running a live check." in text
    assert "File checks only" not in text
    assert "Decision model (optional)" not in text
    assert "OpenAI Decisions" not in text
    assert 'label: "Jev"' not in text
    assert 'label: "Clef"' not in text
    assert "settings-judge-account-id" in text
    assert "Skip it to run without the judge" not in text
    assert "Any OpenAI-compatible endpoint" not in text
    assert "AI_GATEWAY_API_KEY" not in text
    bundles = list((_WEB_STATIC / "assets").glob("index-*.js"))
    assert bundles, "packaged UI bundle is missing"
    bundled = "\n".join(path.read_text(encoding="utf-8") for path in bundles)
    for phrase in (
        "Model keys",
        "Keys stay on this machine",
        "Runs live checks",
        "Paste key",
        "Claude / Anthropic",
        "AI Gateway",
        "Skip it to run without the judge",
    ):
        assert phrase not in bundled, phrase
    assert "File checks only" not in bundled
    assert "Not selected" in bundled
    assert "Pick a decision model before running a live check." in bundled
    assert "Decision model" in bundled
    # One historical rewrite remains so old couldn't-score lines do not show a provider.
    assert bundled.count("OpenAI Decisions") == 1
