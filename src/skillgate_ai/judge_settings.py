"""Gitignored scoring-provider file: `{project}/.skillgate/judge`."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from skillgate_ai.errors import SkillGateError
from skillgate_ai.keys import KEYS_DIRNAME
from skillgate_ai.paths import project_root

JUDGE_FILENAME = "judge"
PROVIDER_IDS = ("auto", "openai", "jev", "aws", "compatible")
CHOSEN_IDS = frozenset({"openai", "jev", "aws", "compatible"})


@dataclass(frozen=True)
class JudgeProviderSettings:
    provider: str = "auto"
    region: str | None = None
    model: str | None = None
    base_url: str | None = None
    decisions_path: str | None = None

    @property
    def chosen(self) -> bool:
        return self.provider in CHOSEN_IDS

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "chosen": self.chosen,
            "region": self.region,
            "model": self.model,
            "base_url": self.base_url,
            "decisions_path": self.decisions_path,
        }


def judge_settings_path(root: str | Path | None = None) -> Path:
    base = Path(root).expanduser().resolve() if root is not None else project_root()
    return base / KEYS_DIRNAME / JUDGE_FILENAME


def load_judge_settings(root: str | Path | None = None) -> JudgeProviderSettings:
    path = judge_settings_path(root)
    if not path.is_file():
        return JudgeProviderSettings()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return JudgeProviderSettings()
    if not isinstance(raw, dict):
        return JudgeProviderSettings()
    provider = str(raw.get("provider") or "auto").strip().lower() or "auto"
    if provider not in PROVIDER_IDS:
        provider = "auto"
    return JudgeProviderSettings(
        provider=provider,
        region=_blank(raw.get("region")),
        model=_blank(raw.get("model")),
        base_url=_blank(raw.get("base_url")),
        decisions_path=_blank(raw.get("decisions_path")),
    )


def save_judge_settings(
    root: str | Path,
    *,
    provider: str,
    region: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    decisions_path: str | None = None,
) -> JudgeProviderSettings:
    name = (provider or "auto").strip().lower() or "auto"
    if name not in PROVIDER_IDS:
        raise SkillGateError(
            "Scoring provider must be auto, OpenAI, Jev, AWS, or Other.",
            exit_code=2,
        )
    settings = JudgeProviderSettings(
        provider=name,
        region=_blank(region),
        model=_blank(model),
        base_url=_blank(base_url),
        decisions_path=_blank(decisions_path),
    )
    dest = judge_settings_path(root)
    dest.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(dest.parent, 0o700)
    payload = {
        "provider": settings.provider,
        "region": settings.region,
        "model": settings.model,
        "base_url": settings.base_url,
        "decisions_path": settings.decisions_path,
    }
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(dest, flags, 0o600)
    try:
        os.write(fd, json.dumps(payload, indent=2, sort_keys=True).encode("utf-8"))
        os.fchmod(fd, 0o600)
    except OSError as exc:
        raise SkillGateError(
            "Couldn't save scoring settings.",
            hint="Check that this project folder is writable.",
        ) from exc
    finally:
        os.close(fd)
    return settings


def _blank(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
