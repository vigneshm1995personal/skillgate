#!/usr/bin/env python3
"""Fix harness package dependency order and seam-style cross-calls."""

from __future__ import annotations

import re
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / "src/skillgate_ai/harness"
ORDER = [
    "base",
    "messages",
    "transcripts",
    "bins",
    "selection",
    "commands",
    "prompts",
    "auth",
    "login",
    "agents",
    "resolve",
]
RANK = {name: i for i, name in enumerate(ORDER)}

# Symbols that must be called as submodule.attr from higher modules (seams + internal).
SEAM_MODULES = {
    "bins": {
        "_resolve_agent_bin",
        "_executable_path",
        "_looks_like_bin_path",
        "_resolve_codex_bin",
        "_resolve_claude_bin",
        "_pinned_has_agent_entry",
    },
    "auth": {
        "_codex_ready",
        "_cursor_ready",
        "_claude_ready",
        "_codex_session_ok",
        "_cursor_session_ok",
        "_claude_session_ok",
        "_probe_codex_login_status",
        "_probe_cursor_login_status",
        "_probe_claude_login_status",
        "claude_auth_kind",
    },
    "selection": {
        "_write_selection",
        "_read_selection",
        "_parse_selected",
        "_resolve_trigger_evidence",
        "_parse_read_paths",
    },
    "login": {"_run_inherited"},
}


def _strip_upward_imports(text: str, submod: str) -> str:
    rank = RANK[submod]
    lines = []
    for line in text.splitlines():
        m = re.match(r"from skillgate_ai\.harness\.(\w+) import ", line)
        if m and RANK.get(m.group(1), 99) > rank:
            continue
        lines.append(line)
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def _qualify_seams(text: str, submod: str) -> str:
    rank = RANK[submod]
    for mod, names in SEAM_MODULES.items():
        if RANK[mod] >= rank:
            continue
        if f"from skillgate_ai.harness import {mod}" not in text:
            if f"import skillgate_ai.harness.{mod}" not in text:
                text = f"from skillgate_ai.harness import {mod}\n" + text
        for name in names:
            text = re.sub(rf"(?<![\w.]){re.escape(name)}\(", rf"{mod}.{name}(", text)
    return text


def main() -> None:
    for submod in ORDER:
        path = PKG / f"{submod}.py"
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        text = _strip_upward_imports(text, submod)
        # CodexCliHarness upward refs
        text = text.replace("from skillgate_ai.harness.agents import CodexCliHarness\n", "")
        if "CodexCliHarness.supported_models" in text and "def " in text:
            text = text.replace(
                "CodexCliHarness.supported_models",
                '(__import__("skillgate_ai.harness.agents", fromlist=["CodexCliHarness"]).CodexCliHarness.supported_models)',
            )
        text = _qualify_seams(text, submod)
        while text.count("from __future__ import annotations") > 1:
            text = text.replace(
                "from __future__ import annotations\n\nfrom __future__ import annotations\n",
                "from __future__ import annotations\n\n",
            )
        path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()