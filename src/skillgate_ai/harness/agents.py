"""Agent harnesses: Cursor Agent, Codex CLI, and Claude Code in the sandbox workspace."""

from __future__ import annotations

import os

import skillgate_ai.harness.auth as auth
import skillgate_ai.harness.bins as bins
import skillgate_ai.harness.selection as selection
from skillgate_ai.config import (
    LLMConfig,
    missing_key_error,
)
from skillgate_ai.errors import HarnessError
from skillgate_ai.harness.auth import _codex_auth_key
from skillgate_ai.harness.base import (
    _AGENT_INSTALL,
    AUTH_API_KEY,
    AUTH_CLI_LOGIN,
    HarnessResult,
    harness_usage,
)
from skillgate_ai.harness.commands import (
    _CLAUDE_PREAMBLE,
    _claude_code_exec_command,
    _claude_sandbox_env,
    _codex_exec_command,
    _codex_model_flag,
    _codex_user_skill_config_override,
    _cursor_exec_command,
    _sandbox_run,
)
from skillgate_ai.harness.messages import (
    _CLAUDE_MODEL_ACCESS_HINT,
    _claude_model_access_error,
    _claude_model_access_message,
    _codex_rejected_chatgpt_model,
    _codex_rejected_model,
    _raise_if_cannot_run,
    codex_chatgpt_model_hint,
)
from skillgate_ai.harness.prompts import _agent_prompt
from skillgate_ai.harness.selection import (
    _collect_read_paths,
    _infer_from_reads,
)
from skillgate_ai.harness.transcripts import (
    _claude_used_model,
    _codex_transcript,
    _codex_used_model,
    _cursor_transcript,
    _jsonl_spans,
)
from skillgate_ai.ingest import Skill
from skillgate_ai.sandbox import Sandbox
from skillgate_ai.scorers import TriggerEvidence


class CursorAgentHarness:
    """v0 harness: Cursor Agent CLI in the sandbox workspace (not Claude Code)."""

    name = "cursor-agent"
    # Last-known CLI family ids (docs only). Evaluate picker uses live
    # GET https://api.cursor.com/v1/models for the current CURSOR_API_KEY.
    supported_models: tuple[str, ...] = ("composer-2.5", "composer-2.5-fast")

    def __init__(self, cfg: LLMConfig):
        self.cfg = cfg

    def run(
        self,
        sandbox: Sandbox,
        prompt: str,
        skills: list[Skill],
        timeout_sec: int,
    ) -> HarnessResult:
        if not auth._cursor_ready(self.cfg):
            raise missing_key_error(for_cursor=True)
        binary = bins._resolve_agent_bin(self.cfg.cursor_agent_bin)
        if binary is None:
            raise HarnessError(
                "Editor agent CLI was not found (`agent` / `cursor-agent`).",
                hint=(
                    f"Install this agent's CLI with `{_AGENT_INSTALL['cursor']}`, "
                    "or set CURSOR_AGENT_BIN, then run `skillgate login cursor`."
                ),
            )
        agent_prompt = _agent_prompt(sandbox.workspace, prompt, skills)
        command = _cursor_exec_command(
            binary,
            sandbox.workspace,
            agent_prompt,
            model=(self.cfg.cursor_model or "").strip() or None,
        )
        env: dict[str, str] = {"SKILLGATE_TASK": prompt}
        if self.cfg.cursor_api_key:
            env["CURSOR_API_KEY"] = self.cfg.cursor_api_key
        proc = _sandbox_run(sandbox, command, env=env, timeout=timeout_sec)
        _raise_if_cannot_run(proc.stdout or "", proc.stderr or "")
        transcript = _cursor_transcript(proc.stdout or "", proc.stderr or "")
        selected = selection._parse_selected(sandbox.workspace, transcript, skills)
        read_paths = _collect_read_paths(transcript, _jsonl_spans(proc.stdout or ""))
        if selected is None:
            selected = _infer_from_reads(read_paths, skills)
        selection._write_selection(sandbox.workspace, selected)
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


class CodexCliHarness:
    """v0 harness: OpenAI Codex CLI (`codex exec`) in the sandbox workspace."""

    name = "codex"
    # Codex *client* models for ChatGPT-session auth (https://developers.openai.com/codex/models).
    # Do not list gateway model ids like openai/gpt-4o-mini — ChatGPT login rejects them.
    supported_models: tuple[str, ...] = (
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
        if not auth._codex_ready(self.cfg):
            raise missing_key_error(for_codex=True)
        binary = bins._resolve_codex_bin(self.cfg.codex_bin)
        if binary is None:
            raise HarnessError(
                "Terminal agent CLI was not found (`codex`).",
                hint=(
                    f"Install this agent's CLI with `{_AGENT_INSTALL['codex']}`, "
                    "or set CODEX_BIN, then run `skillgate login codex`."
                ),
            )
        agent_prompt = _agent_prompt(sandbox.workspace, prompt, skills)
        model = _codex_model_flag(self.cfg.codex_model, cli_login=not bool(key))
        extra_config: list[str] = []
        skill_config = _codex_user_skill_config_override()
        if skill_config:
            extra_config.append(skill_config)
        command = _codex_exec_command(
            binary,
            sandbox.workspace,
            agent_prompt,
            reasoning_effort=self.cfg.codex_reasoning_effort,
            model=model,
            extra_config=extra_config,
        )
        # Leave CODEX_HOME alone so `codex login` (auth.json in that home) is used.
        # A tokenless home drops the subscription, and Codex 0.163 has no flag
        # that moves only the skills directory.
        env: dict[str, str] = {"SKILLGATE_TASK": prompt}
        if key:
            env["CODEX_API_KEY"] = key
        codex_home = os.environ.get("CODEX_HOME", "").strip()
        if codex_home:
            env["CODEX_HOME"] = codex_home
        proc = _sandbox_run(sandbox, command, env=env, timeout=timeout_sec)
        _raise_if_cannot_run(proc.stdout or "", proc.stderr or "")
        transcript = _codex_transcript(proc.stdout or "", proc.stderr or "")
        if _codex_rejected_chatgpt_model(proc.stdout or "", proc.stderr or ""):
            rejected, accepted = _codex_rejected_model(proc.stdout or "", proc.stderr or "")
            named = rejected or (self.cfg.codex_model or "").strip() or model
            raise HarnessError(
                f"The agent rejected model {named!r}.",
                hint=codex_chatgpt_model_hint(named, accepted=accepted),
            )
        selected = selection._parse_selected(sandbox.workspace, transcript, skills)
        read_paths = _collect_read_paths(transcript, _jsonl_spans(proc.stdout or ""))
        if selected is None:
            selected = _infer_from_reads(read_paths, skills)
        selection._write_selection(sandbox.workspace, selected)
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
    supported_models: tuple[str, ...] = (
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
        if not auth._claude_ready(self.cfg):
            raise missing_key_error(for_claude=True)
        binary = bins._resolve_claude_bin(self.cfg.claude_bin)
        if binary is None:
            raise HarnessError(
                "Code agent CLI was not found (`claude`).",
                hint=(
                    f"Install this agent's CLI with `{_AGENT_INSTALL['claude']}`, "
                    "or set CLAUDE_BIN, then run `skillgate login claude`."
                ),
            )
        agent_prompt = _agent_prompt(sandbox.workspace, prompt, skills, native_claude=True)
        command = _claude_code_exec_command(
            binary,
            _CLAUDE_PREAMBLE + agent_prompt,
            model=(self.cfg.anthropic_model or "").strip() or None,
        )
        env: dict[str, str] = {"SKILLGATE_TASK": prompt}
        if self.cfg.anthropic_api_key:
            env["ANTHROPIC_API_KEY"] = self.cfg.anthropic_api_key
        env = _claude_sandbox_env(sandbox.workspace, env)
        proc = _sandbox_run(sandbox, command, env=env, timeout=timeout_sec)
        _raise_if_cannot_run(proc.stdout or "", proc.stderr or "")
        requested = (self.cfg.anthropic_model or "").strip() or None
        if _claude_model_access_error(proc.stdout or "", proc.stderr or ""):
            raise HarnessError(
                _claude_model_access_message(requested),
                hint=_CLAUDE_MODEL_ACCESS_HINT,
                exit_code=2,
            )
        model = _claude_used_model(proc.stdout or "")
        transcript = _cursor_transcript(proc.stdout or "", proc.stderr or "")
        stdout = proc.stdout or ""
        spans = _jsonl_spans(stdout)
        selected, read_paths = selection._resolve_trigger_evidence(
            sandbox.workspace,
            transcript,
            skills,
            stdout=stdout,
            spans=spans,
        )
        selection._write_selection(sandbox.workspace, selected)
        return HarnessResult(
            trigger=TriggerEvidence(
                selected_skill=selected,
                read_paths=read_paths,
                transcript=transcript,
            ),
            stdout=proc.stdout,
            stderr=proc.stderr,
            transcript=transcript,
            spans=spans,
            returncode=proc.returncode,
            usage=harness_usage(stdout),
            auth_mode=AUTH_API_KEY
            if (self.cfg.anthropic_api_key or "").strip()
            else AUTH_CLI_LOGIN,
            model=model,
        )
