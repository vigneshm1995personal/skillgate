"""Agent harnesses. v0 primary: Cursor Agent. Codex CLI is a sibling plugin. Demo shares scorers."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import httpx

from skillgate_ai.config import (
    DEFAULT_CODEX_REASONING_EFFORT,
    LLMConfig,
    missing_key_error,
    normalize_codex_reasoning_effort,
)
from skillgate_ai.errors import HarnessError, MissingLLMKeyError
from skillgate_ai.ingest import Skill
from skillgate_ai.sandbox import Sandbox, running_python
from skillgate_ai.scorers import TriggerEvidence
from skillgate_ai.spans import spans_from_jsonl
from skillgate_ai.usage import (
    Usage,
    merge_usage,
    parse_usage_line,
    render_stream_line,
    usage_from_event,
)


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


@dataclass
class Completion:
    """A single BYOLLM reply plus the usage its transport reported."""

    text: str
    usage: Usage | None = None


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


# --- Skill trigger (description-only) used by the demo harness and as a fallback ---

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


LIVE_HARNESS_NAMES = frozenset({"cursor-agent", "codex", "llm"})


def is_live_harness(name: str | None) -> bool:
    """True when a stored/resolved harness can clear Gate and unlock Deploy."""
    return (name or "").strip().lower() in LIVE_HARNESS_NAMES


class DemoHarness:
    """Deterministic skill-native executor for the bundled demo and CI without keys.

    Trigger uses name+description only (progressive disclosure). If a skill
    activates, `scripts/agent_entry.py` inside that skill is run in the sandbox.
    """

    name = "demo"
    supported_models: tuple[str, ...] = ()

    def run(
        self,
        sandbox: Sandbox,
        prompt: str,
        skills: list[Skill],
        timeout_sec: int,
    ) -> HarnessResult:
        pre = _read_selection(sandbox.workspace)
        if pre is _MISSING:
            selected = select_skill_from_descriptions(prompt, skills)
            transcript = [
                "phase 1: skill trigger from name + description only",
                f"selected: {selected or 'none'}",
            ]
        else:
            selected = pre  # type: ignore[assignment]
            transcript = [
                "phase 1: Gate pre-selected skill (skip catalog discovery)",
                f"selected: {selected or 'none'}",
            ]
        stdout = ""
        stderr = ""
        returncode = 0
        read_paths: list[str] = []
        if selected:
            entry = sandbox.workspace / ".skillgate" / "skills" / selected / "scripts" / "agent_entry.py"
            read_paths.append(str(Path(".skillgate") / "skills" / selected / "SKILL.md"))
            transcript.append(f"phase 2: loaded {selected}/SKILL.md")
            if entry.is_file():
                proc = sandbox.run(
                    [running_python(), str(entry)],
                    env={"SKILLGATE_TASK": prompt, "PYTHONPATH": ""},
                    timeout=timeout_sec,
                )
                stdout = proc.stdout
                stderr = proc.stderr
                returncode = proc.returncode
                transcript.append(f"ran scripts/agent_entry.py exit={proc.returncode}")
                if proc.returncode != 0:
                    transcript.append(stderr[-500:])
            else:
                transcript.append("no scripts/agent_entry.py — skill body has no executable entry")
        else:
            transcript.append("no skill triggered; task left untouched")
        _write_selection(sandbox.workspace, selected)
        text = "\n".join(transcript)
        return HarnessResult(
            trigger=TriggerEvidence(selected_skill=selected, read_paths=read_paths, transcript=text),
            stdout=stdout,
            stderr=stderr,
            transcript=text,
            returncode=returncode,
        )


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
        if not self.cfg.cursor_api_key:
            raise missing_key_error()
        binary = _resolve_agent_bin(self.cfg.cursor_agent_bin)
        if binary is None:
            raise HarnessError(
                "Cursor Agent CLI was not found (`agent` / `cursor-agent`).",
                hint=(
                    "Install Cursor Agent (https://cursor.com/docs/cli/using) "
                    "or set CURSOR_AGENT_BIN. Until then, run with `--demo` "
                    "or `--harness llm` if you have a BYO key (OPENAI_API_KEY / "
                    "AI_GATEWAY_API_KEY / ANTHROPIC_API_KEY)."
                ),
            )
        pinned = _read_selection(sandbox.workspace)
        pinned_skill = None if pinned is _MISSING else pinned  # type: ignore[assignment]
        agent_prompt = _cursor_prompt(prompt, skills, pinned_skill=pinned_skill)
        command = [
            binary,
            "-p",
            "--force",
            "--trust",
            "--sandbox",
            "disabled",
            "--workspace",
            str(sandbox.workspace),
            "--output-format",
            "stream-json",
            "--stream-partial-output",
        ]
        cursor_model = (self.cfg.cursor_model or "").strip()
        if cursor_model:
            command.extend(["--model", cursor_model])
        command.append(agent_prompt)
        env = {
            "CURSOR_API_KEY": self.cfg.cursor_api_key,
            "SKILLGATE_TASK": prompt,
        }
        proc = sandbox.run(command, env=env, timeout=timeout_sec)
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
        )


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
    (often `ultra`) does not make Skill Gate evals inherit that cost. Optional
    `-m` only when `CODEX_MODEL` is set — never invent a model id.

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
    return "is not supported when using Codex" in blob


def codex_chatgpt_model_hint(model: str | None) -> str:
    models = ", ".join(CodexCliHarness.supported_models)
    picked = (model or "").strip()
    extra = f" `{picked}` is not valid for Codex + ChatGPT login." if picked else ""
    return (
        f"Pick a Codex model from the list for this harness ({models}) "
        f"or leave Harness default (no -m).{extra} "
        "Gateway model ids like openai/gpt-4o-mini are LLM-only."
    )


class CodexCliHarness:
    """v0 harness: OpenAI Codex CLI (`codex exec`) in the sandbox workspace."""

    name = "codex"
    # Codex *client* models for ChatGPT-session auth (https://developers.openai.com/codex/models).
    # Do not list gateway model ids like openai/gpt-4o-mini — ChatGPT login rejects them.
    supported_models = (
        "gpt-5.6-luna",
        "gpt-5.6-terra",
        "gpt-5.6-sol",
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
                    "Install Codex CLI (https://developers.openai.com/codex/cli) "
                    "or set CODEX_BIN. Set CODEX_API_KEY or OPENAI_API_KEY, "
                    "or run `codex login`."
                ),
            )
        pinned = _read_selection(sandbox.workspace)
        pinned_skill = None if pinned is _MISSING else pinned  # type: ignore[assignment]
        agent_prompt = _cursor_prompt(prompt, skills, pinned_skill=pinned_skill)
        command = _codex_exec_command(
            binary,
            sandbox.workspace,
            agent_prompt,
            reasoning_effort=self.cfg.codex_reasoning_effort,
            model=self.cfg.codex_model,
        )
        env = {"SKILLGATE_TASK": prompt}
        if key:
            env["CODEX_API_KEY"] = key
        proc = sandbox.run(command, env=env, timeout=timeout_sec)
        transcript = _codex_transcript(proc.stdout or "", proc.stderr or "")
        if _codex_rejected_chatgpt_model(proc.stdout or "", proc.stderr or ""):
            raise HarnessError(
                f"Codex rejected model {self.cfg.codex_model!r}."
                if (self.cfg.codex_model or "").strip()
                else "Codex rejected the selected model.",
                hint=codex_chatgpt_model_hint(self.cfg.codex_model),
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
        )


class LLMHarness:
    """BYOLLM fallback with the same two-phase skill protocol as Cursor Agent.

    OpenAI-compatible chat uses the user's BYO key
    (`OPENAI_API_KEY` or `AI_GATEWAY_API_KEY`). Anthropic stays direct.
    """

    name = "llm"
    # Last-known BYOLLM examples (docs only). Picker uses the user's OpenAI-compatible or Anthropic key — not this tuple.
    supported_models = ("openai/gpt-4o-mini", "claude-sonnet-4-20250514")

    def __init__(self, cfg: LLMConfig):
        self.cfg = cfg

    def run(
        self,
        sandbox: Sandbox,
        prompt: str,
        skills: list[Skill],
        timeout_sec: int,
    ) -> HarnessResult:
        if not (self.cfg.gateway_api_key or self.cfg.openai_api_key or self.cfg.anthropic_api_key):
            raise missing_key_error()
        usage = Usage()
        pre = _read_selection(sandbox.workspace)
        if pre is _MISSING:
            catalog = "\n".join(f"- {s.name}: {s.description}" for s in skills)
            router_prompt = (
                "You are a skill router. Pick at most one skill for the user task.\n"
                "You may only use the skill name and description — not the skill body.\n"
                "Reply with JSON only: {\"skill\": \"<name>\"} or {\"skill\": null}.\n\n"
                f"Skills:\n{catalog}\n\nUser task:\n{prompt}"
            )
            router = self._complete(router_prompt, timeout_sec)
            router_text = router.text
            usage = router.usage or Usage()
            selected = _parse_skill_json(router_text, skills)
            transcript = [f"router: {router_text}", f"selected: {selected or 'none'}"]
        else:
            selected = pre  # type: ignore[assignment]
            transcript = [
                "Gate pre-selected skill (skip catalog discovery)",
                f"selected: {selected or 'none'}",
            ]
        stdout = ""
        stderr = ""
        returncode = 0
        read_paths: list[str] = []
        if selected:
            skill = next(s for s in skills if s.name == selected)
            read_paths.append(f".skillgate/skills/{selected}/SKILL.md")
            body = skill.body[:8000]
            scripts = list((sandbox.workspace / ".skillgate" / "skills" / selected / "scripts").glob("*.py"))
            script_list = "\n".join(f"- {p.name}" for p in scripts) or "(none)"
            act_prompt = (
                f"The skill `{selected}` is already selected (Gate pre-selected; "
                "skip catalog discovery). Follow its SKILL.md instructions immediately — "
                "do not restate the task or invent a plan first.\n"
                "You are in a workspace. Input files are already present.\n"
                "Write outputs where the user asked (usually under output/).\n"
                "Reply with one or more lines of the form:\n"
                "RUN: python3 .skillgate/skills/<skill>/scripts/<script>.py <args>\n"
                "Use only scripts bundled with the skill. No other commands.\n\n"
                f"Skill {skill.name} SKILL.md:\n{body}\n\n"
                f"Bundled scripts:\n{script_list}\n\n"
                f"User task:\n{prompt}"
            )
            act = self._complete(act_prompt, timeout_sec)
            if act.usage is not None:
                usage = merge_usage(usage, act.usage)
            act_text = act.text
            transcript.append(act_text)
            for command in _parse_run_lines(act_text):
                if not _command_allowed(command, selected):
                    transcript.append(f"blocked command: {command}")
                    continue
                proc = sandbox.run(command, env={"SKILLGATE_TASK": prompt}, timeout=timeout_sec)
                stdout += proc.stdout
                stderr += proc.stderr
                returncode = proc.returncode
                transcript.append(f"ran {command} exit={proc.returncode}")
        _write_selection(sandbox.workspace, selected)
        text = "\n".join(transcript)
        return HarnessResult(
            trigger=TriggerEvidence(selected_skill=selected, read_paths=read_paths, transcript=text),
            stdout=stdout,
            stderr=stderr,
            transcript=text,
            returncode=returncode,
            usage=usage if usage.known else None,
        )

    def _complete(self, prompt: str, timeout_sec: int) -> Completion:
        if self.cfg.anthropic_api_key and not (self.cfg.gateway_api_key or self.cfg.openai_api_key):
            return _anthropic_complete_response(self.cfg, prompt, timeout_sec)
        if self.cfg.gateway_api_key or self.cfg.openai_api_key:
            return _gateway_complete_response(self.cfg, prompt, timeout_sec)
        return _anthropic_complete_response(self.cfg, prompt, timeout_sec)


def harness_is_startable(harness: Harness, cfg: LLMConfig) -> bool:
    """True when this harness can spawn (CLI on PATH / HTTP key present).

    Auto must not pick Codex just because OPENAI_API_KEY filled ``codex_api_key``.
    A missing ``codex`` binary is not startable — Gate falls back to demo.
    """
    if isinstance(harness, DemoHarness):
        return True
    if isinstance(harness, CodexCliHarness):
        return _resolve_codex_bin(cfg.codex_bin) is not None
    if isinstance(harness, CursorAgentHarness):
        return _resolve_agent_bin(cfg.cursor_agent_bin) is not None
    if isinstance(harness, LLMHarness):
        return bool(cfg.gateway_api_key or cfg.openai_api_key or cfg.anthropic_api_key)
    return True


def resolve_harness(kind: str, cfg: LLMConfig, *, demo: bool = False) -> Harness:
    kind = (kind or "auto").lower()
    if demo or kind in {"demo", "fixture", "offline"}:
        return DemoHarness()
    if kind in {"cursor-agent", "cursor", "agent"}:
        return CursorAgentHarness(cfg)
    if kind == "codex":
        return CodexCliHarness(cfg)
    if kind in {"llm", "byollm"}:
        return LLMHarness(cfg)
    if kind in {"claude", "claude-code"}:
        raise HarnessError(
            "The Claude Code harness is not in this OSS package.",
            hint="Use `--harness llm` with ANTHROPIC_API_KEY, or `--demo`.",
        )
    if kind != "auto":
        raise HarnessError(
            f"Unknown harness {kind!r}",
            hint="Use auto, cursor-agent, codex, llm, or demo.",
        )
    # auto = built-in checker unless Gate sees a key (`run_check` / `--live`).
    return DemoHarness()


def live_harness_or_error(kind: str, cfg: LLMConfig) -> Harness:
    """Used when the user explicitly asked for a live run. Never returns DemoHarness."""
    kind = (kind or "auto").lower()
    if kind in {"claude", "claude-code"}:
        raise HarnessError(
            "The Claude Code harness is not in this OSS package.",
            hint="Use `--harness llm` with ANTHROPIC_API_KEY.",
        )
    if kind in {"demo", "fixture", "offline"}:
        raise HarnessError(
            "Live runs cannot use the demo harness.",
            hint=(
                "Pass `--demo` for offline checks (the default with no key). "
                "Set CURSOR_API_KEY, CODEX_API_KEY, OPENAI_API_KEY, or "
                "ANTHROPIC_API_KEY for a live harness."
            ),
        )
    if kind == "codex":
        if not _codex_ready(cfg):
            raise missing_key_error(for_codex=True)
        return CodexCliHarness(cfg)
    if not cfg.has_any_key:
        raise missing_key_error()
    harness = resolve_harness(kind, cfg, demo=False)
    if isinstance(harness, DemoHarness):
        if cfg.cursor_api_key and _resolve_agent_bin(cfg.cursor_agent_bin):
            return CursorAgentHarness(cfg)
        if cfg.codex_api_key and _resolve_codex_bin(cfg.codex_bin):
            return CodexCliHarness(cfg)
        if cfg.gateway_api_key or cfg.openai_api_key or cfg.anthropic_api_key:
            return LLMHarness(cfg)
        if cfg.cursor_api_key:
            return CursorAgentHarness(cfg)
        if cfg.codex_api_key:
            return CodexCliHarness(cfg)
        raise missing_key_error()
    return harness


def auto_live_harness_name(cfg: LLMConfig) -> str:
    """Harness Auto Start will run — picker catalog key. Never ``demo``.

    Same name as ``live_harness_or_error("auto")``. Empty keys still return
    ``cursor-agent`` for UI chrome (status has no live catalog either way).
    """
    try:
        return live_harness_or_error("auto", cfg).name
    except MissingLLMKeyError:
        return "cursor-agent"


def _codex_auth_key(cfg: LLMConfig) -> str | None:
    return cfg.codex_api_key


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


def _resolve_agent_bin(preferred: str) -> str | None:
    for name in (preferred, "agent", "cursor-agent"):
        path = shutil.which(name)
        if path:
            return path
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


def _pinned_has_agent_entry(skills: list[Skill], pinned_skill: str) -> bool:
    """True when the pinned skill pack ships ``scripts/agent_entry.py``."""
    for skill in skills:
        if skill.name == pinned_skill:
            return (skill.path / "scripts" / "agent_entry.py").is_file()
    return False


def _cursor_prompt(
    task: str,
    skills: list[Skill],
    *,
    pinned_skill: str | None = None,
) -> str:
    """Build the agent prompt. Gate always pre-selects; never catalog-discover.

    ``pinned_skill`` is the Gate skill (or ``None`` for negative/no-skill checks).
    ``.skillgate/selected.json`` is written by the engine before the harness runs.
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
        parts.append(
            "Put user-requested output files where the task says (usually `output/`)."
        )
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
            return _canonical_skill(data.get("skill"), skills)
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
    return _canonical_skill(data.get("skill"), skills)


def _canonical_skill(value: object, skills: list[Skill]) -> str | None:
    if value is None:
        return None
    name = str(value).strip()
    if name.lower() in {"", "none", "null"}:
        return None
    for skill in skills:
        if skill.name == name:
            return skill.name
    return name


def _parse_read_paths(transcript: str) -> list[str]:
    """SKILL.md paths from real tool/shell evidence only.

    Counts:

    - rendered Cursor/Codex lines (``$ read …``, ``$ cat …``)
    - raw stream-json / JSONL tool envelopes (``readToolCall``, ``"path":…``)
    - shell ``cat …/SKILL.md`` inside unrendered command strings

    Inject/prompt prose that merely mentions a SKILL.md path does **not**
    count — that avoids false ``no-trigger-unrelated`` fails when the null-pin
    preamble or assistant restates forbid-paths. Demo/LLM harnesses still set
    ``read_paths`` explicitly when they load a skill.
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


def _parse_run_lines(text: str) -> list[list[str]]:
    commands: list[list[str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("RUN:"):
            payload = stripped[4:].strip()
            commands.append(payload.split())
    return commands


def _command_allowed(command: list[str], skill_name: str) -> bool:
    if not command:
        return False
    joined = " ".join(command)
    if ".." in joined:
        return False
    needle = f".skillgate/skills/{skill_name}/"
    return command[0] in {"python", "python3"} and needle in joined


def _gateway_complete(
    cfg: LLMConfig,
    prompt: str,
    timeout_sec: int,
    *,
    json_object: bool = False,
    max_tokens: int | None = None,
) -> str:
    """Text-only wrapper kept for callers that ignore usage."""
    return _gateway_complete_response(
        cfg,
        prompt,
        timeout_sec,
        json_object=json_object,
        max_tokens=max_tokens,
    ).text


def _gateway_complete_response(
    cfg: LLMConfig,
    prompt: str,
    timeout_sec: int,
    *,
    json_object: bool = False,
    max_tokens: int | None = None,
) -> Completion:
    url = f"{cfg.gateway_base_url}/chat/completions"
    token = cfg.gateway_api_key or cfg.openai_api_key
    headers = {"Authorization": f"Bearer {token}"}
    payload: dict[str, Any] = {
        "model": cfg.gateway_model,
        "temperature": cfg.temperature,
        "messages": [{"role": "user", "content": prompt}],
    }
    if json_object:
        payload["response_format"] = {"type": "json_object"}
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    try:
        response = httpx.post(url, headers=headers, json=payload, timeout=timeout_sec)
    except httpx.HTTPError as exc:
        raise HarnessError(f"BYO LLM request failed: {exc}") from exc
    if response.status_code >= 400:
        raise HarnessError(
            f"BYO LLM returned {response.status_code}",
            hint="Check OPENAI_API_KEY or AI_GATEWAY_API_KEY and SKILLGATE_MODEL in `.env`.",
        )
    data = response.json()
    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise HarnessError("Unexpected BYO LLM response shape") from exc
    return Completion(text=text, usage=_completion_usage(data))


def _anthropic_complete(cfg: LLMConfig, prompt: str, timeout_sec: int) -> str:
    """Text-only wrapper kept for symmetry with `_gateway_complete`."""
    return _anthropic_complete_response(cfg, prompt, timeout_sec).text


def _anthropic_complete_response(
    cfg: LLMConfig, prompt: str, timeout_sec: int
) -> Completion:
    headers = {
        "x-api-key": cfg.anthropic_api_key or "",
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": cfg.anthropic_model,
        "max_tokens": 1024,
        "temperature": cfg.temperature,
        "messages": [{"role": "user", "content": prompt}],
    }
    try:
        response = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=payload,
            timeout=timeout_sec,
        )
    except httpx.HTTPError as exc:
        raise HarnessError(f"Anthropic request failed: {exc}") from exc
    if response.status_code >= 400:
        raise HarnessError(
            f"Anthropic API returned {response.status_code}",
            hint="Check ANTHROPIC_API_KEY in `.env`.",
        )
    data = response.json()
    try:
        text = "".join(part.get("text", "") for part in data.get("content", []))
    except (KeyError, TypeError) as exc:
        raise HarnessError("Unexpected Anthropic response shape") from exc
    return Completion(text=text, usage=_completion_usage(data))


def _completion_usage(data: Any) -> Usage | None:
    """Pull the `usage` object a completion response carries, if any."""
    if not isinstance(data, dict):
        return None
    usage = data.get("usage")
    if not isinstance(usage, dict):
        return None
    return usage_from_event({"usage": usage})
