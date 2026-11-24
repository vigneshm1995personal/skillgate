from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugin"

ALL_MCP_TOOLS = frozenset(
    {
        "doctor",
        "validate_skill",
        "dataset_scaffold",
        "dataset_get",
        "case_get",
        "case_add",
        "case_edit",
        "case_remove",
        "case_import",
        "pack_tool_checks_set",
        "check_start",
        "check_poll",
        "check_cancel",
        "report_latest",
        "report_get",
    }
)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _skill_frontmatter(skill_dir: Path) -> dict:
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    assert match, f"missing frontmatter in {skill_dir}"
    return yaml.safe_load(match.group(1))


def test_plugin_cursor_manifest_name_and_skills() -> None:
    manifest = _read_json(PLUGIN / ".cursor-plugin" / "plugin.json")
    assert manifest["name"] == "skillgate"
    assert manifest["skills"] == "./skills/"
    assert manifest["mcpServers"] == "./mcp.json"


def test_plugin_claude_manifest_name_and_skills() -> None:
    manifest = _read_json(PLUGIN / ".claude-plugin" / "plugin.json")
    assert manifest["name"] == "skillgate"
    assert manifest["skills"] == "./skills/"
    assert manifest["mcpServers"] == "./.mcp.json"


def test_plugin_version_matches_pyproject() -> None:
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    cursor_ver = _read_json(PLUGIN / ".cursor-plugin" / "plugin.json")["version"]
    claude_ver = _read_json(PLUGIN / ".claude-plugin" / "plugin.json")["version"]
    assert cursor_ver == version
    assert claude_ver == version


def test_cursor_marketplace_lists_plugin_source() -> None:
    market = _read_json(ROOT / ".cursor-plugin" / "marketplace.json")
    assert len(market["plugins"]) == 1
    entry = market["plugins"][0]
    assert entry["name"] == "skillgate"
    assert entry["source"] == "./plugin"


def test_claude_marketplace_lists_plugin_source() -> None:
    market = _read_json(ROOT / ".claude-plugin" / "marketplace.json")
    assert len(market["plugins"]) == 1
    entry = market["plugins"][0]
    assert entry["name"] == "skillgate"
    assert entry["source"] == "./plugin"


def test_mcp_json_skillgate_stdio_no_secrets() -> None:
    cases = (
        ("mcp.json", "${CURSOR_PLUGIN_ROOT}/bin/skillgate-mcp"),
        (".mcp.json", "${CLAUDE_PLUGIN_ROOT}/bin/skillgate-mcp"),
    )
    wrapper = PLUGIN / "bin" / "skillgate-mcp"
    assert wrapper.is_file()
    assert wrapper.stat().st_mode & 0o111
    for name, command in cases:
        path = PLUGIN / name
        text = path.read_text(encoding="utf-8")
        assert "sk-" not in text
        assert "API_KEY" not in text
        assert "/Users/" not in text
        cfg = json.loads(text)
        server = cfg["mcpServers"]["skillgate"]
        assert server["command"] == command
        assert server["args"] == ["--root", "."]


def test_skillgate_mcp_wrapper_prefers_path_not_secrets() -> None:
    text = (PLUGIN / "bin" / "skillgate-mcp").read_text(encoding="utf-8")
    assert "SKILLGATE_BIN" in text
    assert ".skillgate" not in text
    assert "sk-" not in text


def test_skillgate_setup_skill_frontmatter() -> None:
    meta = _skill_frontmatter(PLUGIN / "skills" / "skillgate-setup")
    assert meta["name"] == "skillgate-setup"
    assert meta.get("description", "").strip()


def test_skillgate_dataset_skill_frontmatter() -> None:
    meta = _skill_frontmatter(PLUGIN / "skills" / "skillgate-dataset")
    assert meta["name"] == "skillgate-dataset"
    assert meta.get("description", "").strip()


def test_skillgate_check_skill_frontmatter() -> None:
    meta = _skill_frontmatter(PLUGIN / "skills" / "skillgate-check")
    assert meta["name"] == "skillgate-check"
    assert meta.get("description", "").strip()


def test_plugin_skills_document_all_mcp_tools() -> None:
    found: set[str] = set()
    for sub in ("skillgate-setup", "skillgate-dataset", "skillgate-check"):
        body = (PLUGIN / "skills" / sub / "SKILL.md").read_text(encoding="utf-8")
        for tool in ALL_MCP_TOOLS:
            if f"`{tool}`" in body:
                found.add(tool)
    assert found == ALL_MCP_TOOLS
