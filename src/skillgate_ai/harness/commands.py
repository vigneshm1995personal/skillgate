"""Agent harnesses: Cursor Agent, Codex CLI, and Claude Code in the sandbox workspace."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from skillgate_ai.config import (
    DEFAULT_CODEX_REASONING_EFFORT,
    normalize_codex_reasoning_effort,
)
from skillgate_ai.errors import agent_timeout_error
from skillgate_ai.harness.base import CODEX_CHATGPT_DEFAULT
from skillgate_ai.sandbox import Sandbox


def _cursor_exec_command(
    binary: str,
    workspace: Path | str,
    prompt: str,
    *,
    model: str | None = None,
) -> list[str]:
    """argv for official Cursor headless CLI (`agent -p --force`)."""
    command = [
        binary,
        "-p",
        "--force",
        "--trust",
        "--sandbox",
        "disabled",
        "--workspace",
        str(workspace),
        "--output-format",
        "stream-json",
        "--stream-partial-output",
    ]
    model_id = (model or "").strip()
    if model_id:
        command.extend(["--model", model_id])
    command.append(prompt)
    return command


def _codex_model_flag(model: str | None, *, cli_login: bool) -> str | None:
    """ChatGPT login must pass -m so ~/.codex/config.toml cannot inherit."""
    raw = (model or "").strip()
    if raw == "codex-default":
        raw = ""
    if not cli_login:
        return raw or None
    from skillgate_ai.harness.agents import CodexCliHarness

    if raw in CodexCliHarness.supported_models or (raw.startswith("gpt-") and "/" not in raw):
        return raw
    return CODEX_CHATGPT_DEFAULT


def _codex_exec_command(
    binary: str,
    workspace: Path | str,
    prompt: str,
    *,
    reasoning_effort: str = DEFAULT_CODEX_REASONING_EFFORT,
    model: str | None = None,
    extra_config: list[str] | None = None,
) -> list[str]:
    """argv for `codex exec` on 0.154.

    `--approve-for-me` already implies workspace-write sandbox. Passing
    `--sandbox` together is a clap conflict:
    "the argument '--sandbox <SANDBOX_MODE>' cannot be used with '--approve-for-me'".
    Do not add `--dangerously-bypass-approvals-and-sandbox`; Skill Gate already
    points `-C` at a temp workspace, so implied workspace-write is enough.

    Always pass `-c model_reasoning_effort=...` so Mini's ~/.codex/config.toml
    (often `ultra`) does not make Skill Gate evals inherit that cost. ChatGPT
    login always passes `-m` (default `gpt-5.6-luna`) so config.toml cannot
    inherit a rejected client model.

    `--json` makes stdout JSONL so `turn.completed` carries real token counts.
    Skill selection still rides on `.skillgate/selected.json`; the JSONL rows
    are rendered back into a readable transcript for the trigger parser.

    ``skills.include_instructions=false`` and ``skills.bundled.enabled=false``
    are session overrides on Codex 0.163 (`codex exec -c`). They keep the
    login ``CODEX_HOME`` and drop user plus bundled skills from the prompt.
    """
    effort = normalize_codex_reasoning_effort(reasoning_effort)
    command = [
        binary,
        "exec",
        "--skip-git-repo-check",
        "--approve-for-me",
        "--color",
        "never",
        "--json",
        "-C",
        str(workspace),
        "-c",
        f'model_reasoning_effort="{effort}"',
        "-c",
        "skills.include_instructions=false",
        "-c",
        "skills.bundled.enabled=false",
    ]
    for item in extra_config or []:
        command.extend(["-c", item])
    model_id = (model or "").strip() or None
    if model_id:
        command.extend(["-m", model_id])
    command.append(prompt)
    return command


_CLAUDE_PREAMBLE = (
    "This run is non-interactive. Do not ask for confirmation and do not wait. "
    "Proceed and finish the task. Stay inside this workspace; "
    "do not read or write files outside it.\n\n"
)

_CLAUDE_SYSTEM_PREAMBLE = (
    "Non-interactive eval. Do not ask for confirmation. Do not use AskUserQuestion. "
    "Stay inside this workspace; do not read or write files outside it."
)

_CLAUDE_WORKSPACE_TOOLS = "Bash,Read,Edit,Write,Glob,Grep,Skill"


def _claude_code_exec_command(
    binary: str,
    prompt: str,
    *,
    model: str | None = None,
) -> list[str]:
    """argv for headless ``claude -p`` confined to the sandbox cwd."""
    command = [
        binary,
        "-p",
        "--permission-mode",
        "acceptEdits",
        "--permission-prompts",
        "none",
        "--allowedTools",
        _CLAUDE_WORKSPACE_TOOLS,
        "--append-system-prompt",
        _CLAUDE_SYSTEM_PREAMBLE,
        "--output-format",
        "stream-json",
        "--verbose",
    ]
    if model:
        command.extend(["--model", model])
    command.append(prompt)
    return command


_SKILL_WALK_SKIP = {"node_modules", ".git"}

_SKILL_WALK_MAX_DEPTH = 6


def _toml_basic_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _codex_user_skill_roots() -> list[Path]:
    """Directories Codex scans for user skills. Does not open auth.json."""
    codex_home = os.environ.get("CODEX_HOME", "").strip()
    if codex_home:  # noqa: SIM108
        roots = [Path(codex_home) / "skills"]
    else:
        roots = [Path.home() / ".codex" / "skills"]
    roots.append(Path.home() / ".agents" / "skills")
    return roots


def _skill_markdown_files(root: Path) -> list[Path]:
    """SKILL.md paths under ``root``. Stats only; file bodies are not read."""
    try:
        if not root.is_dir():
            return []
    except OSError:
        return []
    found: list[Path] = []
    seen_dirs: set[tuple[int, int]] = set()

    def _on_error(_err: OSError) -> None:
        return

    for dirpath, dirnames, filenames in os.walk(root, followlinks=True, onerror=_on_error):
        try:
            stat = os.stat(dirpath)
            depth = len(Path(dirpath).resolve().relative_to(root.resolve()).parts)
        except (OSError, ValueError):
            dirnames.clear()
            continue
        marker = (stat.st_dev, stat.st_ino)
        if marker in seen_dirs:
            dirnames.clear()
            continue
        seen_dirs.add(marker)
        dirnames[:] = [
            name for name in dirnames if not name.startswith(".") and name not in _SKILL_WALK_SKIP
        ]
        if depth >= _SKILL_WALK_MAX_DEPTH:
            dirnames.clear()
        if "SKILL.md" not in filenames:
            continue
        skill_md = Path(dirpath) / "SKILL.md"
        try:
            if skill_md.is_file():
                found.append(skill_md)
        except OSError:
            continue
    return found


def _codex_user_skill_config_override() -> str | None:
    """Session ``skills.config`` that disables discovered user skills.

    Codex 0.163 applies ``enabled=false`` only when ``path`` is the SKILL.md
    file. A directory path leaves the skill in the prompt. There is no config
    key that points the skills directory somewhere else.
    """
    paths: list[str] = []
    seen: set[str] = set()
    for root in _codex_user_skill_roots():
        for skill_md in _skill_markdown_files(root):
            text = str(skill_md)
            if text in seen or "\n" in text or text.endswith(f"{os.sep}auth.json"):
                continue
            seen.add(text)
            paths.append(text)
    if not paths:
        return None
    entries = ",".join(f"{{path={_toml_basic_string(path)},enabled=false}}" for path in paths)
    return f"skills.config=[{entries}]"


def _claude_sandbox_env(workspace: Path, base: dict[str, str]) -> dict[str, str]:
    """Claude subprocess env.

    Default: keep the host ``HOME`` / ``CLAUDE_CONFIG_DIR`` so subscription
    CLI login and API keys work. Eval skills load from the workdir
    ``.claude/skills/`` (project scope); Skill Gate never writes ``~/.claude/skills``.
    Set ``SKILLGATE_CLAUDE_ISOLATE_CONFIG=1`` to redirect config into the workdir.
    """
    env = dict(base)
    env["CLAUDE_CODE_DISABLE_BUNDLED_SKILLS"] = "1"
    from skillgate_ai.harness.prompts import claude_config_isolation_enabled

    if not claude_config_isolation_enabled():
        return env
    home = workspace / ".skillgate" / "claude-home"
    home.mkdir(parents=True, exist_ok=True)
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    config = home / ".claude"
    config.mkdir(parents=True, exist_ok=True)
    env["CLAUDE_CONFIG_DIR"] = str(config)
    return env


def _sandbox_run(
    sandbox: Sandbox,
    command: list[str],
    *,
    env: dict[str, str] | None,
    timeout: int,
) -> subprocess.CompletedProcess[str]:
    try:
        return sandbox.run(command, env=env, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise agent_timeout_error(timeout) from None
