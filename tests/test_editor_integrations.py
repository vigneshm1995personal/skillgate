"""Validate Cursor and Claude Code Skill Gate MCP editor integrations."""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
MCP_URL = "https://mcp.skill-gate-ai.app"
SERVER_NAME = "skillgate"
TOKEN_ENV = "SKILLGATE_TOKEN"
TOOLS = ("check_skill", "run_eval", "gate")
PROVIDER_NAMES = (
    "openai",
    "anthropic",
    "openrouter",
    "cloudflare",
    "promptfoo",
    "jev",
)

CURSOR_MCP = ROOT / ".cursor" / "mcp.json"
CURSOR_COMMAND = ROOT / ".cursor" / "commands" / "gate-skill.md"
MARKETPLACE = ROOT / ".claude-plugin" / "marketplace.json"
PLUGIN_ROOT = ROOT / "plugins" / "skillgate"
PLUGIN_MANIFEST = PLUGIN_ROOT / ".claude-plugin" / "plugin.json"
PLUGIN_MCP = PLUGIN_ROOT / ".mcp.json"
PLUGIN_COMMAND = PLUGIN_ROOT / "commands" / "skillgate.md"
PLUGIN_HOOKS = PLUGIN_ROOT / "hooks" / "hooks.json"
PLUGIN_PRECOMMIT = PLUGIN_ROOT / "scripts" / "pre-commit"
EDITORS_DOC = ROOT / "docs" / "editors.md"
README = ROOT / "README.md"


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _cursor_server_config() -> dict:
    data = _load_json(CURSOR_MCP)
    assert isinstance(data, dict)
    servers = data["mcpServers"]
    assert isinstance(servers, dict)
    cfg = servers[SERVER_NAME]
    assert isinstance(cfg, dict)
    return cfg


def _compact_b64(obj: dict) -> str:
    raw = json.dumps(obj, separators=(",", ":"), ensure_ascii=True)
    return base64.b64encode(raw.encode("utf-8")).decode("ascii")


def test_cursor_mcp_json_uses_remote_http_and_token_env() -> None:
    cfg = _cursor_server_config()
    assert cfg["url"] == MCP_URL
    assert "command" not in cfg
    headers = cfg["headers"]
    assert headers["Authorization"] == f"Bearer ${{env:{TOKEN_ENV}}}"
    blob = CURSOR_MCP.read_text(encoding="utf-8")
    assert "Bearer sk-" not in blob
    assert re.search(r"Bearer [A-Za-z0-9._-]{12,}", blob) is None


def test_cursor_gate_skill_command_runs_check_skill_on_open_skill_md() -> None:
    text = CURSOR_COMMAND.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert "name: gate-skill" in text
    assert "check_skill" in text
    assert "SKILL.md" in text
    assert SERVER_NAME in text


def test_claude_marketplace_lists_skillgate_plugin() -> None:
    data = _load_json(MARKETPLACE)
    assert isinstance(data, dict)
    assert data["name"] == SERVER_NAME
    owner = data["owner"]
    assert isinstance(owner, dict)
    assert owner["name"]
    plugins = data["plugins"]
    assert isinstance(plugins, list) and len(plugins) == 1
    entry = plugins[0]
    assert entry["name"] == SERVER_NAME
    assert entry["source"] == "./plugins/skillgate"
    assert (ROOT / entry["source"].lstrip("./")).is_dir()


def test_claude_plugin_manifest_and_mcp_config() -> None:
    manifest = _load_json(PLUGIN_MANIFEST)
    assert isinstance(manifest, dict)
    assert manifest["name"] == SERVER_NAME
    assert manifest["license"] == "Apache-2.0"
    precommit = manifest["userConfig"]["precommit"]
    assert precommit["type"] == "boolean"
    assert precommit["default"] is False

    mcp = _load_json(PLUGIN_MCP)
    assert isinstance(mcp, dict)
    cfg = mcp["mcpServers"][SERVER_NAME]
    assert cfg["type"] == "http"
    assert cfg["url"] == MCP_URL
    assert cfg["headers"]["Authorization"] == f"Bearer ${{{TOKEN_ENV}}}"


def test_claude_skillgate_command_and_optional_precommit() -> None:
    command = PLUGIN_COMMAND.read_text(encoding="utf-8")
    assert "check_skill" in command
    assert "SKILL.md" in command
    for tool in TOOLS:
        assert tool in command

    hooks = _load_json(PLUGIN_HOOKS)
    assert isinstance(hooks, dict)
    pre = hooks["hooks"]["PreToolUse"]
    assert isinstance(pre, list) and pre
    command_line = pre[0]["hooks"][0]["command"]
    assert "pre-commit" in command_line
    assert "${CLAUDE_PLUGIN_ROOT}" in command_line

    script = PLUGIN_PRECOMMIT.read_text(encoding="utf-8")
    assert script.startswith("#!/")
    assert TOKEN_ENV in script or "CLAUDE_PLUGIN_OPTION_PRECOMMIT" in script
    assert PLUGIN_PRECOMMIT.stat().st_mode & 0o111


def test_docs_cover_both_installs_without_provider_names() -> None:
    doc = EDITORS_DOC.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    assert "## Editor MCP" in readme
    start = readme.find("## Editor MCP")
    rest = readme[start:]
    end_rel = rest.find("\n## ", 1)
    section = rest if end_rel < 0 else rest[:end_rel]
    assert "docs/editors.md" in section or "docs/editors.md" in readme

    for blob in (doc, section):
        lowered = blob.lower()
        assert "add to cursor" in lowered
        assert "claude mcp add" in lowered
        assert TOKEN_ENV in blob
        assert MCP_URL in blob
        assert "/gate-skill" in blob
        assert "/skillgate" in blob
        assert "skillgate check" in lowered
        assert "bring-your-own-key" in lowered or "bring your own key" in lowered
        for name in PROVIDER_NAMES:
            assert name not in lowered, name
        assert "sk-" not in blob


def test_docs_deeplink_matches_cursor_mcp_json() -> None:
    cfg = _cursor_server_config()
    encoded = _compact_b64(cfg)
    doc = EDITORS_DOC.read_text(encoding="utf-8") + "\n" + README.read_text(encoding="utf-8")
    https_link = f"https://cursor.com/install-mcp?name={SERVER_NAME}&config="
    deeplink = f"cursor://anysphere.cursor-deeplink/mcp/install?name={SERVER_NAME}&config="
    assert https_link in doc
    assert deeplink in doc

    found = False
    for match in re.finditer(r"https://cursor\.com/install-mcp\?[^\s)>\"]+", doc):
        parsed = urlparse(match.group(0))
        query = parse_qs(parsed.query)
        assert query["name"] == [SERVER_NAME]
        payload = query["config"][0]
        decoded = json.loads(base64.b64decode(payload).decode("utf-8"))
        assert decoded == cfg
        found = True
    assert found
    assert encoded in doc
