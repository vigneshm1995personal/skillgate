"""Agent harnesses: Cursor Agent, Codex CLI, and Claude Code in the sandbox workspace."""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from skillgate_ai.config import (
    DEFAULT_CODEX_REASONING_EFFORT,
    LLMConfig,
    missing_key_error,
    no_agent_available_error,
    normalize_codex_reasoning_effort,
)
from skillgate_ai.errors import HarnessError, MissingLLMKeyError
from skillgate_ai.ingest import Skill, canonical_skill_name
from skillgate_ai.sandbox import Sandbox
from skillgate_ai.scorers import TriggerEvidence
from skillgate_ai.spans import spans_from_jsonl
from skillgate_ai.usage import (
    Usage,
    merge_usage,
    parse_usage_line,
    render_stream_line,
)


AUTH_API_KEY = "api_key"
AUTH_CLI_LOGIN = "cli_login"
AUTH_NONE = "none"

LOGIN_AGENTS = ("cursor", "codex", "claude")

LOGIN_TIMEOUT_SEC = 600
LOGIN_TIMEOUT_ENV = "SKILLGATE_LOGIN_TIMEOUT"


def _login_timeout_sec() -> float:
    """Official-login timeout (seconds), overridable via SKILLGATE_LOGIN_TIMEOUT."""
    raw = os.environ.get(LOGIN_TIMEOUT_ENV, "").strip()
    if raw:
        try:
            value = float(raw)
        except ValueError:
            value = LOGIN_TIMEOUT_SEC
        if value > 0:
            return value
    return float(LOGIN_TIMEOUT_SEC)

_AGENT_INSTALL = {
    "cursor": "curl https://cursor.com/install -fsS | bash",
    "codex": "npm install -g @openai/codex",
    "claude": "npm install -g @anthropic-ai/claude-code",
}


@dataclass
class HarnessResult:
    trigger: TriggerEvidence
    stdout: str = ""
    stderr: str = ""
    transcript: str = ""
    duration_note: str = ""
    returncode: int | None = None
    usage: Usage | None = None
    spans: list[dict] | None = None
    auth_mode: str = AUTH_API_KEY
    model: str | None = None


def harness_usage(stdout: str) -> Usage | None:
    """Monotonic usage from every JSONL line a harness printed, or None.

    The same parser the live `RunControl` uses, so an off-stream harness
    (MagicMock sandbox, tests, CLI without a sink) reports identical numbers.
    """
    usage = Usage()
    for line in stdout.splitlines():
        update = parse_usage_line(line)
        if update is not None:
            usage = merge_usage(usage, update)
    return usage if usage.known else None


class Harness(Protocol):
    name: str
    supported_models: tuple[str, ...]

    def run(
        self,
        sandbox: Sandbox,
        prompt: str,
        skills: list[Skill],
        timeout_sec: int,
    ) -> HarnessResult: ...


# --- Skill trigger (description-only) fallback for advice / scorers ---

_STOP = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "to",
    "of",
    "for",
    "in",
    "on",
    "at",
    "from",
    "with",
    "this",
    "that",
    "user",
    "wants",
    "use",
    "when",
    "into",
    "file",
    "files",
    "output",
    "write",
    "it",
    "its",
    "is",
    "be",
    "as",
    "by",
}


def tokenize(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in _STOP and len(t) > 1}


def rank_skills(prompt: str, skills: list[Skill]) -> list[tuple[Skill, float]]:
    task_tokens = tokenize(prompt)
    ranked: list[tuple[Skill, float]] = []
    for skill in skills:
        # Description is the trigger surface. Do not split the folder name into
        # keywords (otherwise `pdf-sabotaged` would still fire on PDF tasks).
        desc_tokens = tokenize(skill.description)
        if not task_tokens or not desc_tokens:
            ranked.append((skill, 0.0))
            continue
        overlap = task_tokens & desc_tokens
        score = len(overlap) / max(len(task_tokens), 1)
        if "pdf" in task_tokens and "pdf" in desc_tokens:
            score += 0.35
        if skill.name in prompt.lower() or skill.name.replace("-", " ") in prompt.lower():
            score += 0.1
        ranked.append((skill, score))
    ranked.sort(key=lambda item: item[1], reverse=True)
    return ranked


def select_skill_from_descriptions(prompt: str, skills: list[Skill]) -> str | None:
    ranked = rank_skills(prompt, skills)
    if not ranked:
        return None
    best, score = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0.0
    if score < 0.22:
        return None
    if len(ranked) > 1 and score - second < 0.05 and score < 0.45:
        return None
    return best.name


LIVE_HARNESS_NAMES = frozenset({"cursor-agent", "codex", "claude", "claude-code"})


def is_live_harness(name: str | None) -> bool:
    """True when a stored/resolved harness can clear Gate and unlock Deploy."""
    return (name or "").strip().lower() in LIVE_HARNESS_NAMES


class CursorAgentHarness:
    """v0 harness: Cursor Agent CLI in the sandbox workspace (not Claude Code)."""

    name = "cursor-agent"
    # Last-known CLI family ids (docs only). Evaluate picker uses live
    # GET https://api.cursor.com/v1/models for the current CURSOR_API_KEY.
    supported_models = ("composer-2.5", "composer-2.5-fast")

    def __init__(self, cfg: LLMConfig):
        self.cfg = cfg

    def run(
        self,
        sandbox: Sandbox,
        prompt: str,
        skills: list[Skill],
        timeout_sec: int,
    ) -> HarnessResult:
        if not _cursor_ready(self.cfg):
            raise missing_key_error(for_cursor=True)
        binary = _resolve_agent_bin(self.cfg.cursor_agent_bin)
        if binary is None:
            raise HarnessError(
                "Cursor Agent CLI was not found (`agent` / `cursor-agent`).",
                hint=(
                    f"Install Cursor with `{_AGENT_INSTALL['cursor']}`, "
                    "or set CURSOR_AGENT_BIN, then run `skillgate login cursor`."
                ),
            )
        pinned = _read_selection(sandbox.workspace)
        if pinned is _MISSING:
            agent_prompt = _cursor_discover_prompt(prompt, skills)
        else:
            agent_prompt = _cursor_prompt(
                prompt, skills, pinned_skill=pinned  # type: ignore[arg-type]
            )
        command = _cursor_exec_command(
            binary,
            sandbox.workspace,
            agent_prompt,
            model=(self.cfg.cursor_model or "").strip() or None,
        )
        env: dict[str, str] = {"SKILLGATE_TASK": prompt}
        if self.cfg.cursor_api_key:
            env["CURSOR_API_KEY"] = self.cfg.cursor_api_key
        proc = sandbox.run(command, env=env, timeout=timeout_sec)
        _raise_if_auth_failed(proc.stdout or "", proc.stderr or "")
        transcript = _cursor_transcript(proc.stdout or "", proc.stderr or "")
        selected = _parse_selected(sandbox.workspace, transcript, skills)
        read_paths = _parse_read_paths(transcript)
        if selected is None:
            selected = _infer_from_reads(read_paths, skills)
        _write_selection(sandbox.workspace, selected)
        return HarnessResult(
            trigger=TriggerEvidence(
                selected_skill=selected,
                read_paths=read_paths,
                transcript=transcript,
            ),
            stdout=proc.stdout,
            stderr=proc.stderr,
            transcript=transcript,
            spans=_jsonl_spans(proc.stdout or ""),
            returncode=proc.returncode,
            usage=harness_usage(proc.stdout or ""),
            auth_mode=AUTH_API_KEY if (self.cfg.cursor_api_key or "").strip() else AUTH_CLI_LOGIN,
        )


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


CODEX_CHATGPT_DEFAULT = "gpt-5.6-luna"
_CODEX_REJECTED_MODEL = re.compile(
    r"The ['\"]([^'\"]+)['\"] model is not supported",
    re.IGNORECASE,
)
_CODEX_SUPPORTED_MODELS = re.compile(
    r"(?:supported models|accepted)\s*[:=]\s*(.+)",
    re.IGNORECASE,
)


def _codex_model_flag(model: str | None, *, cli_login: bool) -> str | None:
    """ChatGPT login must pass -m so ~/.codex/config.toml cannot inherit."""
    raw = (model or "").strip()
    if raw == "codex-default":
        raw = ""
    if not cli_login:
        return raw or None
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
    ]
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
# Docs: code.claude.com/docs/en/headless — acceptEdits auto-approves edits only
# inside the working directory. --permission-prompts none removes AskUserQuestion
# and denies anything that would wait for a person. bypassPermissions is not used:
# it auto-approves writes outside the throwaway workspace.
_CLAUDE_SYSTEM_PREAMBLE = (
    "Non-interactive eval. Do not ask for confirmation. Do not use AskUserQuestion. "
    "Stay inside this workspace; do not read or write files outside it."
)


def _claude_code_exec_command(
    binary: str,
    prompt: str,
    *,
    model: str | None = None,
) -> list[str]:
    """argv for headless ``claude -p`` confined to the sandbox cwd.

    ``--permission-mode acceptEdits`` auto-approves file edits in the working
    directory only (https://code.claude.com/docs/en/headless).
    ``--permission-prompts none`` does not wait for a person.
    """
    command = [
        binary,
        "-p",
        "--permission-mode",
        "acceptEdits",
        "--permission-prompts",
        "none",
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


def _claude_used_model(stdout: str) -> str | None:
    """Model Claude Code actually used, from stream-json output.

    The final ``result`` message carries ``modelUsage`` (keys are model ids);
    the ``system`` init message carries a top-level ``model`` field as a
    fallback for runs that never emit a result envelope.
    """
    fallback: str | None = None
    for raw in (stdout or "").splitlines():
        line = raw.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        kind = obj.get("type")
        if kind == "system" and isinstance(obj.get("model"), str):
            fallback = str(obj["model"]).strip() or fallback
        if kind == "result" and isinstance(obj.get("modelUsage"), dict):
            chosen = _busiest_model_usage(obj["modelUsage"])
            if chosen:
                return chosen
    return fallback


def _busiest_model_usage(model_usage: dict[str, Any]) -> str | None:
    """Model id that did the work. A side model listed first must not win."""
    best_id: str | None = None
    best_tokens = -1
    for model_id, stats in model_usage.items():
        if not isinstance(model_id, str) or not model_id.strip():
            continue
        tokens = 0
        if isinstance(stats, dict):
            for key in ("outputTokens", "output_tokens", "inputTokens", "input_tokens"):
                value = stats.get(key)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    tokens += int(value)
        if tokens > best_tokens:
            best_tokens = tokens
            best_id = model_id.strip()
    return best_id


def _codex_used_model(stdout: str, default: str | None) -> str | None:
    """Model Codex actually used: any model id in `--json` output, else the -m flag."""
    for raw in (stdout or "").splitlines():
        line = raw.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        model_id = obj.get("model") or obj.get("model_id") or obj.get("modelId")
        if isinstance(model_id, str) and model_id.strip():
            return model_id.strip()
    return (default or "").strip() or None


_MODEL_ACCESS_ERROR = re.compile(
    r"(?:"
    r"there's an issue with the selected model"
    r"|model not found"
    r"|does not have access to (?:the )?model"
    r"|not available on your plan"
    r"|is not supported when using Codex"
    r"|model is not supported"
    r")",
    re.IGNORECASE,
)


def _claude_model_access_error(stdout: str, stderr: str) -> bool:
    """True when Claude Code refused the chosen/default model on the first request."""
    blob = f"{stdout}\n{stderr}"
    return bool(_MODEL_ACCESS_ERROR.search(blob))


def _claude_model_access_message(model: str | None) -> str:
    named = (model or "").strip()
    if named:
        return f"Claude couldn't use the selected model {named!r}."
    return "Claude couldn't use its default model."


_CLAUDE_MODEL_ACCESS_HINT = "Pass --model with an available alias (for example, --model sonnet)."


def _jsonl_spans(stdout: str) -> list[dict]:
    """OTLP-shaped spans from the same JSONL that feeds the transcript."""
    return spans_from_jsonl(stdout or "")


def _jsonl_transcript(stdout: str, stderr: str) -> str:
    """Render harness JSONL stdout back to readable lines, then append stderr.

    Used for every JSONL harness (Codex `--json`, Cursor `stream-json`) so
    skill selection, read-path inference, and the transcript the UI shows all
    see the same readable text regardless of adapter.
    """
    lines = [
        rendered
        for rendered in (render_stream_line(line) for line in stdout.splitlines())
        if rendered
    ]
    text = "\n".join(lines)
    if stderr:
        return f"{text}\n{stderr}" if text else stderr
    return text


def _codex_transcript(stdout: str, stderr: str) -> str:
    return _jsonl_transcript(stdout, stderr)


def _cursor_transcript(stdout: str, stderr: str) -> str:
    return _jsonl_transcript(stdout, stderr)


def _codex_rejected_chatgpt_model(stdout: str, stderr: str) -> bool:
    blob = f"{stdout}\n{stderr}"
    return "is not supported when using Codex" in blob or bool(_CODEX_REJECTED_MODEL.search(blob))


def _codex_rejected_model(stdout: str, stderr: str) -> tuple[str | None, list[str]]:
    blob = f"{stdout}\n{stderr}"
    match = _CODEX_REJECTED_MODEL.search(blob)
    rejected = match.group(1).strip() if match else None
    accepted: list[str] = []
    listed = _CODEX_SUPPORTED_MODELS.search(blob)
    if listed:
        raw = listed.group(1).strip()
        for part in re.split(r"[,/]| and ", raw):
            name = part.strip().strip(".")
            if name.startswith("gpt-") and name not in accepted:
                accepted.append(name)
    return rejected, accepted


def codex_chatgpt_model_hint(
    model: str | None,
    *,
    accepted: list[str] | None = None,
) -> str:
    rejected = (model or "").strip()
    catalog = [item for item in (accepted or []) if item and item != rejected]
    if not catalog:
        catalog = [item for item in CodexCliHarness.supported_models if item != rejected]
    models = ", ".join(catalog) if catalog else CODEX_CHATGPT_DEFAULT
    return (
        "ChatGPT login rejected that model. "
        f"Pass --model with a supported id ({models}), "
        f"or change model in ~/.codex/config.toml."
    )


class CodexCliHarness:
    """v0 harness: OpenAI Codex CLI (`codex exec`) in the sandbox workspace."""

    name = "codex"
    # Codex *client* models for ChatGPT-session auth (https://developers.openai.com/codex/models).
    # Do not list gateway model ids like openai/gpt-4o-mini — ChatGPT login rejects them.
    supported_models = (
        "gpt-5.6-luna",
        "gpt-5.6-terra",
        "gpt-6-astra",
    )

    def __init__(self, cfg: LLMConfig):
        self.cfg = cfg

    def run(
        self,
        sandbox: Sandbox,
        prompt: str,
        skills: list[Skill],
        timeout_sec: int,
    ) -> HarnessResult:
        key = _codex_auth_key(self.cfg)
        if not _codex_ready(self.cfg):
            raise missing_key_error(for_codex=True)
        binary = _resolve_codex_bin(self.cfg.codex_bin)
        if binary is None:
            raise HarnessError(
                "Codex CLI was not found (`codex`).",
                hint=(
                    f"Install Codex with `{_AGENT_INSTALL['codex']}`, "
                    "or set CODEX_BIN, then run `skillgate login codex`."
                ),
            )
        pinned = _read_selection(sandbox.workspace)
        if pinned is _MISSING:
            agent_prompt = _cursor_discover_prompt(prompt, skills)
        else:
            agent_prompt = _cursor_prompt(
                prompt, skills, pinned_skill=pinned  # type: ignore[arg-type]
            )
        model = _codex_model_flag(self.cfg.codex_model, cli_login=not bool(key))
        command = _codex_exec_command(
            binary,
            sandbox.workspace,
            agent_prompt,
            reasoning_effort=self.cfg.codex_reasoning_effort,
            model=model,
        )
        env: dict[str, str] = {"SKILLGATE_TASK": prompt}
        home_env = _prepare_codex_env(sandbox.workspace, api_key=key)
        env.update(home_env)
        try:
            proc = sandbox.run(command, env=env, timeout=timeout_sec)
        finally:
            if not key:
                _restore_codex_auth(Path(home_env["CODEX_HOME"]))
        _raise_if_auth_failed(proc.stdout or "", proc.stderr or "")
        transcript = _codex_transcript(proc.stdout or "", proc.stderr or "")
        if _codex_rejected_chatgpt_model(proc.stdout or "", proc.stderr or ""):
            rejected, accepted = _codex_rejected_model(proc.stdout or "", proc.stderr or "")
            named = rejected or (self.cfg.codex_model or "").strip() or model
            raise HarnessError(
                f"Codex rejected model {named!r}.",
                hint=codex_chatgpt_model_hint(named, accepted=accepted),
            )
        selected = _parse_selected(sandbox.workspace, transcript, skills)
        read_paths = _parse_read_paths(transcript)
        if selected is None:
            selected = _infer_from_reads(read_paths, skills)
        _write_selection(sandbox.workspace, selected)
        return HarnessResult(
            trigger=TriggerEvidence(
                selected_skill=selected,
                read_paths=read_paths,
                transcript=transcript,
            ),
            stdout=proc.stdout,
            stderr=proc.stderr,
            transcript=transcript,
            spans=_jsonl_spans(proc.stdout or ""),
            returncode=proc.returncode,
            usage=harness_usage(proc.stdout or ""),
            auth_mode=AUTH_API_KEY if key else AUTH_CLI_LOGIN,
            model=_codex_used_model(proc.stdout or "", model),
        )


class ClaudeCodeHarness:
    """Claude Code CLI (`claude -p`) in the sandbox workspace."""

    name = "claude"
    # Claude Code model aliases and full ids (code.claude.com/docs/en/model-config).
    # `default` clears any override; Claude resolves it per plan.
    supported_models = (
        "default",
        "best",
        "fable",
        "opus",
        "sonnet",
        "haiku",
        "sonnet[1m]",
        "opus[1m]",
        "opusplan",
        "claude-fable-5-1",
        "claude-fable-5",
        "claude-opus-5-5",
        "claude-opus-5",
        "claude-opus-4-8",
        "claude-opus-4-7",
        "claude-opus-4-6",
        "claude-sonnet-5-5",
        "claude-sonnet-5",
        "claude-sonnet-4-6",
        "claude-sonnet-4-5",
        "claude-sonnet-4-20250514",
        "claude-haiku-5-5",
        "claude-haiku-4-5",
    )

    def __init__(self, cfg: LLMConfig):
        self.cfg = cfg

    def run(
        self,
        sandbox: Sandbox,
        prompt: str,
        skills: list[Skill],
        timeout_sec: int,
    ) -> HarnessResult:
        if not _claude_ready(self.cfg):
            raise missing_key_error(for_claude=True)
        binary = _resolve_claude_bin(self.cfg.claude_bin)
        if binary is None:
            raise HarnessError(
                "Claude Code CLI was not found (`claude`).",
                hint=(
                    f"Install Claude Code with `{_AGENT_INSTALL['claude']}`, "
                    "or set CLAUDE_BIN, then run `skillgate login claude`."
                ),
            )
        pinned = _read_selection(sandbox.workspace)
        if pinned is _MISSING:
            agent_prompt = _cursor_discover_prompt(prompt, skills)
        else:
            agent_prompt = _cursor_prompt(
                prompt, skills, pinned_skill=pinned  # type: ignore[arg-type]
            )
        command = _claude_code_exec_command(
            binary,
            _CLAUDE_PREAMBLE + agent_prompt,
            model=(self.cfg.anthropic_model or "").strip() or None,
        )
        env: dict[str, str] = {"SKILLGATE_TASK": prompt}
        if self.cfg.anthropic_api_key:
            env["ANTHROPIC_API_KEY"] = self.cfg.anthropic_api_key
        proc = sandbox.run(command, env=env, timeout=timeout_sec)
        _raise_if_auth_failed(proc.stdout or "", proc.stderr or "")
        requested = (self.cfg.anthropic_model or "").strip() or None
        if _claude_model_access_error(proc.stdout or "", proc.stderr or ""):
            raise HarnessError(
                _claude_model_access_message(requested),
                hint=_CLAUDE_MODEL_ACCESS_HINT,
                exit_code=2,
            )
        model = _claude_used_model(proc.stdout or "")
        transcript = _cursor_transcript(proc.stdout or "", proc.stderr or "")
        selected = _parse_selected(sandbox.workspace, transcript, skills)
        read_paths = _parse_read_paths(transcript)
        if selected is None:
            selected = _infer_from_reads(read_paths, skills)
        _write_selection(sandbox.workspace, selected)
        return HarnessResult(
            trigger=TriggerEvidence(
                selected_skill=selected,
                read_paths=read_paths,
                transcript=transcript,
            ),
            stdout=proc.stdout,
            stderr=proc.stderr,
            transcript=transcript,
            spans=_jsonl_spans(proc.stdout or ""),
            returncode=proc.returncode,
            usage=harness_usage(proc.stdout or ""),
            auth_mode=AUTH_API_KEY if (self.cfg.anthropic_api_key or "").strip() else AUTH_CLI_LOGIN,
            model=model,
        )


def harness_is_startable(harness: Harness, cfg: LLMConfig) -> bool:
    """True when this harness can spawn (CLI on PATH / key or CLI login)."""
    if isinstance(harness, CodexCliHarness):
        return _codex_ready(cfg) and _resolve_codex_bin(cfg.codex_bin) is not None
    if isinstance(harness, CursorAgentHarness):
        return _cursor_ready(cfg) and _resolve_agent_bin(cfg.cursor_agent_bin) is not None
    if isinstance(harness, ClaudeCodeHarness):
        return _claude_ready(cfg) and _resolve_claude_bin(cfg.claude_bin) is not None
    return True


def _named_harness(kind: str, cfg: LLMConfig) -> Harness:
    if kind in {"cursor-agent", "cursor", "agent"}:
        return CursorAgentHarness(cfg)
    if kind == "codex":
        return CodexCliHarness(cfg)
    if kind in {"claude", "claude-code"}:
        return ClaudeCodeHarness(cfg)
    if kind in {"llm", "byollm", "demo"}:
        raise HarnessError(
            f"The {kind!r} harness was removed.",
            hint="Use auto, cursor-agent, codex, or claude.",
        )
    raise HarnessError(
        f"Unknown harness {kind!r}",
        hint="Use auto, cursor-agent, codex, or claude.",
    )


def resolve_harness(kind: str, cfg: LLMConfig) -> Harness:
    return live_harness_or_error(kind, cfg)


_LIVE_HARNESS_KINDS = frozenset(
    {
        "auto",
        "cursor-agent",
        "cursor",
        "agent",
        "codex",
        "claude",
        "claude-code",
    }
)

_AGENT_PRIORITY = ("cursor-agent", "codex", "claude")


def _agent_candidates(cfg: LLMConfig) -> list[tuple[str, Harness]]:
    found: list[tuple[str, Harness]] = []
    if _cursor_ready(cfg) and _resolve_agent_bin(cfg.cursor_agent_bin):
        found.append(("cursor-agent", CursorAgentHarness(cfg)))
    if _codex_ready(cfg) and _resolve_codex_bin(cfg.codex_bin):
        found.append(("codex", CodexCliHarness(cfg)))
    if _claude_ready(cfg) and _resolve_claude_bin(cfg.claude_bin):
        found.append(("claude", ClaudeCodeHarness(cfg)))
    order = {name: index for index, name in enumerate(_AGENT_PRIORITY)}
    found.sort(key=lambda item: order.get(item[0], 99))
    return found


def startable_agent_kinds(cfg: LLMConfig) -> list[str]:
    return [name for name, harness in _agent_candidates(cfg) if harness_is_startable(harness, cfg)]


def has_startable_agent(cfg: LLMConfig) -> bool:
    return bool(startable_agent_kinds(cfg))


def live_harness_or_error(kind: str, cfg: LLMConfig) -> Harness:
    """Pick a live harness. Missing agent → MissingLLMKeyError (exit 2)."""
    kind = (kind or "auto").lower()
    if kind in {"llm", "byollm", "demo"}:
        raise HarnessError(
            f"The {kind!r} harness was removed.",
            hint="Use auto, cursor-agent, codex, or claude.",
        )
    if kind not in _LIVE_HARNESS_KINDS:
        return _named_harness(kind, cfg)
    if kind == "auto":
        agents = _agent_candidates(cfg)
        if not agents:
            raise no_agent_available_error(cfg)
        harness = agents[0][1]
        if not harness_is_startable(harness, cfg):
            raise no_agent_available_error(cfg)
        return harness
    harness = _named_harness(kind, cfg)
    if not harness_is_startable(harness, cfg):
        if kind in {"cursor-agent", "cursor", "agent"}:
            raise missing_key_error(for_cursor=True)
        if kind == "codex":
            raise missing_key_error(for_codex=True)
        if kind in {"claude", "claude-code"}:
            raise missing_key_error(for_claude=True)
        raise no_agent_available_error(cfg)
    return harness


def auto_live_harness_name(cfg: LLMConfig) -> str:
    """Harness Auto will run — picker catalog key."""
    try:
        return live_harness_or_error("auto", cfg).name
    except MissingLLMKeyError:
        return "auto"


def _codex_auth_key(cfg: LLMConfig) -> str | None:
    return cfg.codex_api_key


def _prepare_codex_env(workspace: Path, *, api_key: str | None) -> dict[str, str]:
    """Throwaway CODEX_HOME so exec cannot write ~/.codex/config.toml."""
    home = workspace / ".skillgate" / "codex-home"
    home.mkdir(parents=True, exist_ok=True)
    env = {"CODEX_HOME": str(home)}
    if api_key:
        env["CODEX_API_KEY"] = api_key
        return env
    _symlink_codex_auth(home)
    return env


def _symlink_codex_auth(temp_home: Path) -> None:
    dest = temp_home / "auth.json"
    if dest.exists() or dest.is_symlink():
        dest.unlink()
    src = Path.home() / ".codex" / "auth.json"
    try:
        if src.exists() or src.is_symlink():
            dest.symlink_to(src)
    except OSError:
        return


def _restore_codex_auth(temp_home: Path) -> None:
    """If Codex rotated auth.json over the symlink, put the file back without reading it."""
    dest = temp_home / "auth.json"
    if dest.is_symlink() or not dest.is_file():
        return
    src = Path.home() / ".codex" / "auth.json"
    src.parent.mkdir(parents=True, exist_ok=True)
    os.replace(dest, src)


_CODEX_LOGIN_STATUS_TIMEOUT_SEC = 5


def _codex_ready(cfg: LLMConfig) -> bool:
    """Explicit Codex may use an env key or a ChatGPT CLI session. Auto must not call this for has_any_key."""
    return bool(_codex_auth_key(cfg) or _codex_session_ok(cfg))


def _codex_login_status_authenticated(returncode: int, stdout: str, stderr: str) -> bool:
    if returncode != 0:
        return False
    text = f"{stdout}\n{stderr}".lower()
    if "not logged in" in text:
        return False
    return "logged in" in text


def _probe_codex_login_status(binary: str) -> bool:
    """Host `codex login status` only. Never read auth files."""
    try:
        proc = subprocess.run(
            [binary, "login", "status"],
            capture_output=True,
            text=True,
            timeout=_CODEX_LOGIN_STATUS_TIMEOUT_SEC,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return _codex_login_status_authenticated(proc.returncode, proc.stdout or "", proc.stderr or "")


def _codex_session_ok(cfg: LLMConfig) -> bool:
    binary = _resolve_codex_bin(cfg.codex_bin)
    if binary is None:
        return False
    return _probe_codex_login_status(binary)


_CURSOR_LOGIN_STATUS_TIMEOUT_SEC = 5


_AUTH_FAILURE_RE = re.compile(
    r"unable to fetch user details"
    r"|not logged in"
    r"|not authenticated"
    r"|authentication required"
    r"|please (?:re-?)?log ?in"
    r"|invalid api key",
    re.IGNORECASE,
)


def auth_failure_message(stdout: str, stderr: str) -> str | None:
    """Auth failure in harness stderr or an error event. Not assistant prose."""
    if _AUTH_FAILURE_RE.search(stderr or ""):
        return "The agent is not signed in."
    for line in (stdout or "").splitlines():
        text = line.strip()
        if not text.startswith("{"):
            continue
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        kind = str(obj.get("type") or "")
        errored = kind == "error" or (kind == "result" and obj.get("is_error") is True)
        if not errored:
            continue
        blob = " ".join(str(obj.get(key) or "") for key in ("message", "error", "result"))
        if _AUTH_FAILURE_RE.search(blob):
            return "The agent is not signed in."
    return None


def _raise_if_auth_failed(stdout: str, stderr: str) -> None:
    message = auth_failure_message(stdout, stderr)
    if message is None:
        return
    raise HarnessError(
        message,
        hint="Run `skillgate login` for Cursor, Codex, or Claude Code.",
        exit_code=2,
    )


def _cursor_login_status_authenticated(returncode: int, stdout: str, stderr: str) -> bool:
    if returncode != 0:
        return False
    text = f"{stdout}\n{stderr}".lower()
    if "unable to fetch user details" in text:
        return False
    if "not logged in" in text or "not authenticated" in text:
        return False
    return True


def _probe_cursor_login_status(binary: str) -> bool:
    """Host `cursor-agent status` / `agent status` only. Never read auth files."""
    try:
        proc = subprocess.run(
            [binary, "status"],
            capture_output=True,
            text=True,
            timeout=_CURSOR_LOGIN_STATUS_TIMEOUT_SEC,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return _cursor_login_status_authenticated(proc.returncode, proc.stdout or "", proc.stderr or "")


def _cursor_session_ok(cfg: LLMConfig) -> bool:
    binary = _resolve_agent_bin(cfg.cursor_agent_bin)
    if binary is None:
        return False
    return _probe_cursor_login_status(binary)


def _cursor_ready(cfg: LLMConfig) -> bool:
    return cursor_auth_kind(cfg) != AUTH_NONE


_CLAUDE_LOGIN_STATUS_TIMEOUT_SEC = 5


def _claude_login_status_authenticated(returncode: int, stdout: str, stderr: str) -> bool:
    if returncode != 0:
        return False
    for blob in (stdout, stderr):
        raw = (blob or "").strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and "loggedIn" in payload:
            return payload.get("loggedIn") is True
    text = f"{stdout}\n{stderr}".lower()
    if "not logged in" in text or "not authenticated" in text:
        return False
    return "logged in" in text or "authenticated" in text


def _probe_claude_login_status(binary: str) -> bool:
    """Host `claude auth status` only. Never read auth files."""
    try:
        proc = subprocess.run(
            [binary, "auth", "status"],
            capture_output=True,
            text=True,
            timeout=_CLAUDE_LOGIN_STATUS_TIMEOUT_SEC,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return _claude_login_status_authenticated(proc.returncode, proc.stdout or "", proc.stderr or "")


def _claude_session_ok(cfg: LLMConfig) -> bool:
    binary = _resolve_claude_bin(cfg.claude_bin)
    if binary is None:
        return False
    return _probe_claude_login_status(binary)


def _claude_ready(cfg: LLMConfig) -> bool:
    return claude_auth_kind(cfg) != AUTH_NONE


def cursor_auth_kind(cfg: LLMConfig) -> str:
    if (cfg.cursor_api_key or "").strip():
        return AUTH_API_KEY
    if _cursor_session_ok(cfg):
        return AUTH_CLI_LOGIN
    return AUTH_NONE


def codex_auth_kind(cfg: LLMConfig) -> str:
    if _codex_auth_key(cfg):
        return AUTH_API_KEY
    if _codex_session_ok(cfg):
        return AUTH_CLI_LOGIN
    return AUTH_NONE


def claude_auth_kind(cfg: LLMConfig) -> str:
    if (cfg.anthropic_api_key or "").strip():
        return AUTH_API_KEY
    if _claude_session_ok(cfg):
        return AUTH_CLI_LOGIN
    return AUTH_NONE


def _display_status(*, installed: bool, auth: str) -> str:
    if auth == AUTH_API_KEY:
        return "API key"
    if auth == AUTH_CLI_LOGIN:
        return "logged in"
    if installed:
        return "installed"
    return "none"


def normalize_login_agent(raw: str | None) -> str | None:
    name = (raw or "").strip().lower()
    if name in {"cursor", "cursor-agent", "agent"}:
        return "cursor"
    if name == "codex":
        return "codex"
    if name in {"claude", "claude-code"}:
        return "claude"
    return None


def harness_auth_status(cfg: LLMConfig) -> list[dict[str, str | bool]]:
    """Per-agent install + auth. Never includes secrets."""
    rows: list[tuple[str, str, str, str | None, str]] = [
        (
            "Cursor",
            "cursor-agent",
            "cursor",
            _resolve_agent_bin(cfg.cursor_agent_bin),
            cursor_auth_kind(cfg),
        ),
        (
            "Codex",
            "codex",
            "codex",
            _resolve_codex_bin(cfg.codex_bin),
            codex_auth_kind(cfg),
        ),
        (
            "Claude Code",
            "claude",
            "claude",
            _resolve_claude_bin(cfg.claude_bin),
            claude_auth_kind(cfg),
        ),
    ]
    out: list[dict[str, str | bool]] = []
    for name, kind, agent, binary, auth in rows:
        installed = binary is not None
        out.append(
            {
                "name": name,
                "kind": kind,
                "agent": agent,
                "installed": installed,
                "auth": auth,
                "status": _display_status(installed=installed, auth=auth),
                "install": _AGENT_INSTALL[agent],
                "command": f"skillgate login {agent}",
            }
        )
    return out


def format_harness_status(rows: list[dict[str, str | bool]]) -> str:
    lines: list[str] = []
    for row in rows:
        lines.append(str(row["name"]))
        lines.append(f"  status     {row['status']}")
        if not row["installed"]:
            lines.append(f"  install    {row['install']}")
        elif row["auth"] == AUTH_NONE:
            lines.append(f"  login      {row['command']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _terminate_process_group(proc: subprocess.Popen[str]) -> None:
    """SIGTERM the child's process group, then SIGKILL if it ignores the term."""
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            os.kill(proc.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            pass
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass


def _run_inherited(argv: list[str], *, timeout: float | None = None) -> int:
    """Run an official login CLI with the user's terminal (OAuth / browser).

    The child runs in its own session/process group so Ctrl-C, SIGTERM, or a
    timeout can tear down the whole tree (no orphaned `claude auth login`).

    `signal.signal` raises ValueError outside the main thread, so the SIGTERM
    forwarder is only installed (and restored) from the main thread; the local
    UI can start a login from a worker thread.
    """
    proc = subprocess.Popen(argv, start_new_session=True)
    interrupted: dict[str, int | None] = {"sig": None}
    in_main_thread = threading.current_thread() is threading.main_thread()

    def _on_sigterm(signum: int, frame: object) -> None:
        del frame
        interrupted["sig"] = signum
        _terminate_process_group(proc)

    previous = signal.signal(signal.SIGTERM, _on_sigterm) if in_main_thread else None
    try:
        code: int | None
        try:
            code = int(proc.wait(timeout=timeout) or 0)
        except subprocess.TimeoutExpired:
            _terminate_process_group(proc)
            code = 124
        except KeyboardInterrupt:
            _terminate_process_group(proc)
            raise
        if interrupted["sig"] is not None:
            return 128 + int(interrupted["sig"])
        return code
    finally:
        if in_main_thread:
            signal.signal(signal.SIGTERM, previous)  # type: ignore[arg-type]


def run_official_login(agent: str, cfg: LLMConfig) -> dict[str, str | bool]:
    """Start the agent's official login, then verify with a status probe."""
    kind = normalize_login_agent(agent)
    if kind is None:
        return {
            "ok": False,
            "agent": (agent or "").strip() or "unknown",
            "installed": False,
            "status": "none",
            "install": "",
            "command": "skillgate login",
            "message": "Use cursor, claude, or codex.",
        }
    if kind == "cursor":
        binary = _resolve_agent_bin(cfg.cursor_agent_bin)
        argv = [binary, "login"] if binary else []
        probe = _probe_cursor_login_status
    elif kind == "codex":
        binary = _resolve_codex_bin(cfg.codex_bin)
        argv = [binary, "login"] if binary else []
        probe = _probe_codex_login_status
    else:
        binary = _resolve_claude_bin(cfg.claude_bin)
        argv = [binary, "auth", "login"] if binary else []
        probe = _probe_claude_login_status
    install = _AGENT_INSTALL[kind]
    command = f"skillgate login {kind}"
    if binary is None:
        return {
            "ok": False,
            "agent": kind,
            "installed": False,
            "status": "none",
            "install": install,
            "command": command,
            "message": f"Not installed. {install}",
        }
    code = _run_inherited(argv, timeout=_login_timeout_sec())
    if code == 124:
        return {
            "ok": False,
            "agent": kind,
            "installed": True,
            "status": "installed",
            "install": install,
            "command": command,
            "message": f"{kind} login timed out. Run `{command}` in your terminal.",
        }
    logged_in = probe(binary)
    return {
        "ok": logged_in,
        "agent": kind,
        "installed": True,
        "status": "logged in" if logged_in else "installed",
        "install": install,
        "command": command,
        "message": (
            f"{kind} is logged in."
            if logged_in
            else f"{kind} login did not complete. Run `{command}` in your terminal."
        ),
    }


def _resolve_agent_bin(preferred: str) -> str | None:
    """Find `agent` (official) or `cursor-agent` alias, including ~/.local/bin."""
    names: list[str] = []
    if preferred:
        names.append(preferred)
    for name in ("agent", "cursor-agent"):
        if name not in names:
            names.append(name)
    for name in names:
        found = shutil.which(name)
        if found:
            return found
        if _looks_like_bin_path(name):
            found = _executable_path(Path(name).expanduser())
            if found:
                return found
    home_local = Path.home() / ".local" / "bin"
    for name in ("agent", "cursor-agent"):
        found = _executable_path(home_local / name)
        if found:
            return found
    return None


def _executable_path(path: Path) -> str | None:
    if path.is_file() and os.access(path, os.X_OK):
        return str(path)
    return None


def _looks_like_bin_path(name: str) -> bool:
    return name.startswith(("~", ".", "/")) or "/" in name


def _resolve_codex_bin(preferred: str) -> str | None:
    if preferred:
        found = shutil.which(preferred)
        if found:
            return found
        if _looks_like_bin_path(preferred):
            found = _executable_path(Path(preferred).expanduser())
            if found:
                return found
    found = shutil.which("codex")
    if found:
        return found
    return _executable_path(Path.home() / ".local" / "bin" / "codex")


def _resolve_claude_bin(preferred: str) -> str | None:
    if preferred:
        found = shutil.which(preferred)
        if found:
            return found
        if _looks_like_bin_path(preferred):
            found = _executable_path(Path(preferred).expanduser())
            if found:
                return found
    return shutil.which("claude")


def _pinned_has_agent_entry(skills: list[Skill], pinned_skill: str) -> bool:
    """True when the pinned skill pack ships ``scripts/agent_entry.py``."""
    for skill in skills:
        if skill.name == pinned_skill:
            return (skill.path / "scripts" / "agent_entry.py").is_file()
    return False


def _cursor_discover_prompt(task: str, skills: list[Skill]) -> str:
    """No-trigger / unpinned: the agent must choose from the catalog."""
    catalog = "\n".join(f"- {s.name}: {s.description}" for s in skills)
    return (
        "You are running inside Skill Gate.\n"
        "No skill is pre-selected. Read `.skillgate/catalog.md` if it exists, "
        "or use the skill names and descriptions below, and pick at most one "
        "skill for the user task. If none fits, complete the task without using "
        "a skill and write {\"skill\": null} to `.skillgate/selected.json`.\n"
        "If you pick a skill, write {\"skill\": \"<name>\"} to "
        "`.skillgate/selected.json`, then read that skill's SKILL.md and follow it.\n\n"
        f"Skills:\n{catalog}\n\nTask:\n{task}"
    )


def _cursor_prompt(
    task: str,
    skills: list[Skill],
    *,
    pinned_skill: str | None = None,
) -> str:
    """Build the agent prompt when Gate has already pinned a skill (or none).

    ``pinned_skill`` is the Gate skill (or ``None`` for an explicit null pin).
    Unpinned no-trigger checks use ``_cursor_discover_prompt`` instead.
    When pinned, the agent's first action must be a Read of that skill's SKILL.md.
    When that skill also ships ``scripts/agent_entry.py``, the second action must
    be a Shell that runs it — SKILL.md text alone is not enough to stop live
    agents from inventing output files (receipt-photo extract-image-stub RCA).
    """
    if pinned_skill:
        skill_md = f".skillgate/skills/{pinned_skill}/SKILL.md"
        entry = f".skillgate/skills/{pinned_skill}/scripts/agent_entry.py"
        parts = [
            "You are running inside Skill Gate.",
            f"The skill `{pinned_skill}` is already selected "
            "and written to `.skillgate/selected.json` for scorers. "
            "Do **not** read `.skillgate/catalog.md` or `.skillgate/selected.json`, "
            "open other skills, or rewrite the selection.",
            f"Your FIRST action must be a tool call that reads `{skill_md}` "
            "(Read / open that file). Do **not** emit assistant planning text, "
            "restate the task, or call any other tool before that Read.",
        ]
        if _pinned_has_agent_entry(skills, pinned_skill):
            parts.append(
                f"Your SECOND action — immediately after that Read, before any "
                f"Write / create / edit of output files — MUST be a Shell tool "
                f"call that runs exactly:\n"
                f"  python3 {entry}\n"
                "Do **not** hand-write, guess, OCR-invent, or otherwise author "
                "output files yourself. Only that script may create them. "
                "If it exits non-zero, fix the invocation and re-run it; never "
                "substitute your own JSON or text."
            )
        else:
            parts.append(
                "After reading SKILL.md, follow it to complete the task. "
                "Use bundled scripts under that skill when they exist."
            )
        parts.append("Put user-requested output files where the task says (usually `output/`).")
        parts.append(f"Task:\n{task}")
        return "\n".join(parts)
    return (
        "You are running inside Skill Gate.\n"
        "No skill is selected for this check "
        '(.skillgate/selected.json has {"skill": null}). '
        "Do **not** browse `.skillgate/catalog.md`, open anything under "
        "`.skillgate/skills/`, or read any `SKILL.md`. "
        "Complete the task without using skills.\n"
        f"Task:\n{task}"
    )


def _write_selection(workspace: Path, selected: str | None) -> None:
    target = workspace / ".skillgate" / "selected.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"skill": selected}), encoding="utf-8")


_MISSING = object()


def _read_selection(workspace: Path):
    """Pre-seeded skill name, ``None`` for null pin, or ``_MISSING`` if absent."""
    target = workspace / ".skillgate" / "selected.json"
    if not target.is_file():
        return _MISSING
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return _MISSING
    if not isinstance(data, dict) or "skill" not in data:
        return _MISSING
    raw = data.get("skill")
    if raw is None:
        return None
    name = str(raw).strip()
    if name.lower() in {"", "none", "null"}:
        return None
    return name


def _parse_selected(workspace: Path, transcript: str, skills: list[Skill]) -> str | None:
    selected_path = workspace / ".skillgate" / "selected.json"
    if selected_path.is_file():
        try:
            data = json.loads(selected_path.read_text(encoding="utf-8"))
            return canonical_skill_name(data.get("skill"), skills)
        except json.JSONDecodeError:
            pass
    return _parse_skill_json(transcript, skills)


def _parse_skill_json(text: str, skills: list[Skill]) -> str | None:
    match = re.search(r"\{[^{}]*\"skill\"[^{}]*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return canonical_skill_name(data.get("skill"), skills)


def _skill_for_selection(selected: str, skills: list[Skill]) -> Skill:
    name = canonical_skill_name(selected, skills) or selected
    for skill in skills:
        if skill.name == name:
            return skill
    raise HarnessError(
        f"Couldn't find skill {selected}.",
        hint="The folder name can be `pack` when the skill name differs.",
    )


def _parse_read_paths(transcript: str) -> list[str]:
    """SKILL.md paths from real tool/shell evidence only.

    Counts:

    - rendered Cursor/Codex lines (``$ read …``, ``$ cat …``)
    - raw stream-json / JSONL tool envelopes (``readToolCall``, ``"path":…``)
    - shell ``cat …/SKILL.md`` inside unrendered command strings

    Inject/prompt prose that merely mentions a SKILL.md path does **not**
    count — that avoids false ``no-trigger-unrelated`` fails when the null-pin
    preamble or assistant restates forbid-paths.
    """
    path_re = re.compile(r"[^\s'\"]+/SKILL\.md")
    out: list[str] = []
    for line in transcript.splitlines():
        found = path_re.findall(line)
        if not found:
            continue
        stripped = line.lstrip()
        if stripped.startswith("$ "):
            out.extend(found)
        elif "readToolCall" in line or '"path"' in line:
            out.extend(found)
        elif "cat" in line and "SKILL.md" in line:
            out.extend(found)
    return out


def _infer_from_reads(paths: list[str], skills: list[Skill]) -> str | None:
    names = set()
    for path in paths:
        for skill in skills:
            if f"/{skill.name}/SKILL.md" in path.replace("\\", "/"):
                names.add(skill.name)
    if len(names) == 1:
        return next(iter(names))
    return None


