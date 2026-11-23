"""Pack/case/task models for deterministic tool-call checks."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DEFAULT_CALLS_LOG = "output/calls.log"
_GLOB_CHARS = frozenset("*?[]")


class ToolCallRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str
    args_match: dict[str, Any] | None = None
    min: int = 1
    max: int | None = None

    @model_validator(mode="before")
    @classmethod
    def _shorthand(cls, value: object) -> object:
        if isinstance(value, str):
            text = value.strip()
            return {"tool": text} if text else value
        return value

    @field_validator("tool")
    @classmethod
    def _tool_nonempty(cls, value: str) -> str:
        text = (value or "").strip()
        if not text:
            raise ValueError("tool must be non-empty")
        return text

    @field_validator("min")
    @classmethod
    def _min_ok(cls, value: int) -> int:
        if value < 0:
            raise ValueError("min must be >= 0")
        return value

    @model_validator(mode="after")
    def _max_ok(self) -> ToolCallRule:
        if self.max is not None and self.max < self.min:
            raise ValueError("max must be >= min")
        if self.args_match:
            for key, expected in self.args_match.items():
                if isinstance(expected, dict) and "regex" in expected:
                    pattern = str(expected["regex"])
                    try:
                        re.compile(pattern)
                    except re.error as exc:
                        raise ValueError(f"invalid regex for {key!r}: {exc}") from exc
        return self


def _rule_sparse(rule: ToolCallRule) -> dict[str, Any]:
    out: dict[str, Any] = {"tool": rule.tool}
    if rule.args_match:
        out["args_match"] = dict(rule.args_match)
    if rule.min != 1:
        out["min"] = rule.min
    if rule.max is not None:
        out["max"] = rule.max
    return out


class PackToolChecks(BaseModel):
    model_config = ConfigDict(extra="forbid")

    calls_log: str = DEFAULT_CALLS_LOG
    consequential_tools: list[str] = Field(default_factory=list)
    builtin_consequential: bool = True
    must_not_call: list[ToolCallRule] = Field(default_factory=list)
    skip_consequential_check: bool = False

    @field_validator("calls_log")
    @classmethod
    def _calls_log_relative(cls, value: str) -> str:
        text = (value or DEFAULT_CALLS_LOG).strip().replace("\\", "/").lstrip("/")
        if ".." in text.split("/"):
            raise ValueError("calls_log must not contain ..")
        return text or DEFAULT_CALLS_LOG

    def is_empty(self) -> bool:
        return (
            self.calls_log == DEFAULT_CALLS_LOG
            and not self.consequential_tools
            and self.builtin_consequential is True
            and not self.must_not_call
            and not self.skip_consequential_check
        )

    def to_sparse_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if self.calls_log != DEFAULT_CALLS_LOG:
            payload["calls_log"] = self.calls_log
        if self.consequential_tools:
            payload["consequential_tools"] = list(self.consequential_tools)
        if not self.builtin_consequential:
            payload["builtin_consequential"] = False
        if self.must_not_call:
            payload["must_not_call"] = [_rule_sparse(item) for item in self.must_not_call]
        if self.skip_consequential_check:
            payload["skip_consequential_check"] = True
        return payload


class CaseToolChecks(BaseModel):
    model_config = ConfigDict(extra="forbid")

    must_call: list[ToolCallRule] = Field(default_factory=list)
    must_not_call: list[ToolCallRule] = Field(default_factory=list)
    allow_consequential: list[str] = Field(default_factory=list)
    skip_consequential_check: bool = False

    def is_empty(self) -> bool:
        return (
            not self.must_call
            and not self.must_not_call
            and not self.allow_consequential
            and not self.skip_consequential_check
        )

    def to_sparse_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if self.must_call:
            payload["must_call"] = [_rule_sparse(item) for item in self.must_call]
        if self.must_not_call:
            payload["must_not_call"] = [_rule_sparse(item) for item in self.must_not_call]
        if self.allow_consequential:
            payload["allow_consequential"] = list(self.allow_consequential)
        if self.skip_consequential_check:
            payload["skip_consequential_check"] = True
        return payload


class TaskToolChecks(BaseModel):
    """Effective (pack + case merged) checks carried on TaskSpec."""

    model_config = ConfigDict(extra="forbid")

    calls_log: str = DEFAULT_CALLS_LOG

    @field_validator("calls_log")
    @classmethod
    def _calls_log_relative(cls, value: str) -> str:
        text = (value or DEFAULT_CALLS_LOG).strip().replace("\\", "/").lstrip("/")
        if ".." in text.split("/"):
            raise ValueError("calls_log must not contain ..")
        return text or DEFAULT_CALLS_LOG

    must_call: list[ToolCallRule] = Field(default_factory=list)
    must_not_call: list[ToolCallRule] = Field(default_factory=list)
    consequential_tools: list[str] = Field(default_factory=list)
    builtin_consequential: bool = True
    allow_consequential: list[str] = Field(default_factory=list)
    skip_consequential_check: bool = False

    def is_default(self) -> bool:
        return (
            self.calls_log == DEFAULT_CALLS_LOG
            and not self.must_call
            and not self.must_not_call
            and not self.consequential_tools
            and self.builtin_consequential is True
            and not self.allow_consequential
            and not self.skip_consequential_check
        )


def merge_tool_checks(
    pack: PackToolChecks | None,
    case: CaseToolChecks | None,
    *,
    should_trigger: bool,
) -> TaskToolChecks | None:
    if (pack is None or pack.is_empty()) and (case is None or case.is_empty()):
        return None
    pack_block = pack or PackToolChecks()
    case_block = case or CaseToolChecks()
    must_call = list(case_block.must_call) if should_trigger else []
    must_not_call = [*pack_block.must_not_call, *case_block.must_not_call]
    return TaskToolChecks(
        calls_log=pack_block.calls_log,
        must_call=must_call,
        must_not_call=must_not_call,
        consequential_tools=list(pack_block.consequential_tools),
        builtin_consequential=pack_block.builtin_consequential,
        allow_consequential=list(case_block.allow_consequential),
        skip_consequential_check=(
            pack_block.skip_consequential_check or case_block.skip_consequential_check
        ),
    )


def parse_tool_checks_block(
    raw: object,
    *,
    level: Literal["pack", "case"],
) -> PackToolChecks | CaseToolChecks | None:
    if raw is None:
        return None
    if isinstance(raw, dict) and not raw:
        return None
    if not isinstance(raw, dict):
        raise ValueError("tool_checks must be a mapping")
    if level == "pack":
        model = PackToolChecks.model_validate(raw)
        return None if model.is_empty() else model
    model = CaseToolChecks.model_validate(raw)
    return None if model.is_empty() else model


def declared_patterns(checks: TaskToolChecks) -> list[str]:
    """Literal tool patterns (no glob) for shell command matching."""
    names: list[str] = []
    for rule in [*checks.must_call, *checks.must_not_call]:
        if not any(ch in rule.tool for ch in _GLOB_CHARS):
            names.append(rule.tool)
    for pattern in [*checks.consequential_tools, *checks.allow_consequential]:
        if not any(ch in pattern for ch in _GLOB_CHARS):
            names.append(pattern)
    return names
