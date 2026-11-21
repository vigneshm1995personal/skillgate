"""Compare runs: models (live arms) and versions (history / git)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from skillgate_ai.errors import SkillGateError

MAX_ARMS = 4

MIN_ARMS = 2

DEFAULT_MAX_SPEND_USD = 5.0

ALLOWED_COMPARE_HARNESS = frozenset({"auto", "cursor-agent", "codex", "claude"})


class CompareError(SkillGateError):
    exit_code = 1


@dataclass(frozen=True)
class CompareArmSpec:
    arm_id: str
    label: str
    harness_pref: str
    model: str | None = None
    timeout_sec: int | None = None
    temperature: float | None = None
    reasoning_effort: str | None = None

    def to_run_kwargs(self) -> dict[str, Any]:
        return {
            "harness": self.harness_pref,
            "model": self.model,
            "timeout": self.timeout_sec,
            "temperature": self.temperature,
            "reasoning_effort": self.reasoning_effort,
        }


@dataclass
class CompareResult:
    exit_code: int
    payload: dict[str, Any]


def arm_label_defaults(count: int) -> list[str]:
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    return [f"Arm {letters[i]}" for i in range(count)]


def parse_arm_spec(raw: str, *, arm_id: str, index: int) -> CompareArmSpec:
    text = (raw or "").strip()
    if not text:
        raise CompareError("Each arm needs a label and harness.", hint="Use --arm 'Label:codex'.")
    if ":" not in text:
        raise CompareError(
            "Each --arm needs Label:harness[:model].",
            hint="Example: --arm 'Arm A:codex:gpt-4o-mini'.",
        )
    parts = text.split(":")
    label = parts[0].strip() or arm_label_defaults(index + 1)[index]
    harness = (parts[1] if len(parts) > 1 else "auto").strip() or "auto"
    model = parts[2].strip() if len(parts) > 2 and parts[2].strip() else None
    return CompareArmSpec(arm_id=arm_id, label=label, harness_pref=harness, model=model or None)


def parse_arm_file(path: Path, *, arm_id: str, index: int) -> CompareArmSpec:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise CompareError(f"Arm file must be a JSON object: {path}")
    label = str(data.get("label") or arm_label_defaults(index + 1)[index]).strip()
    harness = str(data.get("harness_pref") or data.get("harness") or "auto").strip()
    return CompareArmSpec(
        arm_id=arm_id,
        label=label,
        harness_pref=harness,
        model=_blank(data.get("model")),
        timeout_sec=_as_int(data.get("timeout_sec")),
        temperature=_as_float(data.get("temperature")),
        reasoning_effort=_blank(data.get("reasoning_effort")),
    )


def _resolved_arm_model(report: dict[str, Any], requested: str | None) -> str | None:
    cfg = report.get("config")
    if isinstance(cfg, dict):
        resolved = _blank(cfg.get("model"))
        if resolved:
            return resolved
    tasks = report.get("tasks")
    if isinstance(tasks, list):
        for task in tasks:
            if isinstance(task, dict):
                resolved = _blank(task.get("model"))
                if resolved:
                    return resolved
    return _blank(requested)


def _blank(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _arm_ids(n: int) -> list[str]:
    return [chr(ord("a") + i) for i in range(n)]


def arm_id_for_index(index: int) -> str:
    if index < 0 or index >= MAX_ARMS:
        raise CompareError(f"Compare supports at most {MAX_ARMS} arms.")
    return chr(ord("a") + index)


def validate_compare_plan(
    arms: list[CompareArmSpec],
    *,
    max_spend_usd: float | None,
) -> None:
    if max_spend_usd is not None and max_spend_usd < 0:
        raise CompareError("Spend cap must be zero or positive.")
    if len(arms) < MIN_ARMS or len(arms) > MAX_ARMS:
        raise CompareError(f"Compare needs {MIN_ARMS}–{MAX_ARMS} arms.")
    labels: list[str] = []
    for spec in arms:
        harness = (spec.harness_pref or "auto").strip().lower()
        if harness not in ALLOWED_COMPARE_HARNESS:
            raise CompareError(
                f"Unknown harness {spec.harness_pref!r}.",
                hint="Use auto, cursor-agent, codex, or claude.",
            )
        labels.append(spec.label.strip().lower())
    if len(labels) != len(set(labels)):
        raise CompareError("Arm labels must be unique.")


def _resolve_compare_case_ids(pack: Path, case_ids: list[str] | None) -> list[str]:
    from skillgate_ai.case_pack import checks_from_pack, load_case_pack

    loaded = load_case_pack(pack)
    if loaded is None:
        raise CompareError("This skill has no checks yet.")
    all_checks = checks_from_pack(loaded)
    all_ids = [str(item["id"]) for item in all_checks if item.get("id")]
    if not all_ids:
        raise CompareError("This skill has no pinned checks to compare.")
    if not case_ids:
        return all_ids
    by_id = {str(item["id"]): item for item in all_checks}
    missing = [cid for cid in case_ids if cid not in by_id]
    if missing:
        raise CompareError(
            f"Unknown case ids: {', '.join(missing)}.",
            hint="Use `skillgate case list` to see check ids.",
        )
    return list(case_ids)


def checks_for_case_ids(pack: Path, case_ids: list[str]) -> list[dict[str, Any]]:
    from skillgate_ai.case_pack import checks_from_pack, load_case_pack

    loaded = load_case_pack(pack)
    if loaded is None:
        raise CompareError("This skill has no checks yet.")
    ordered = _resolve_compare_case_ids(pack, case_ids)
    all_checks = {str(c["id"]): c for c in checks_from_pack(loaded)}
    return [all_checks[cid] for cid in ordered]
