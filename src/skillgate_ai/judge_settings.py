"""Gitignored scoring-provider file: `{project}/.skillgate/judge`."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from skillgate_ai.errors import SkillGateError
from skillgate_ai.keys import KEYS_DIRNAME
from skillgate_ai.paths import project_root

JUDGE_FILENAME = "judge"
PROVIDER_IDS = ("auto", "openai", "jev", "aws", "compatible")
CHOSEN_IDS = frozenset({"openai", "jev", "aws", "compatible"})
# Chat and reasoning models. The Checks tab must not offer these.
CHAT_PROVIDER_IDS = frozenset({"aws", "compatible"})
# Labels stay free of vendor names. Clef is listed so it appears when the
# engine allowlist gains that id (the 0.7.3 provider removal).
_DECISION_JUDGE_COPY: dict[str, dict[str, Any]] = {
    "openai": {
        "label": "Decision model",
        "detail": "Picks one answer for each check.",
        "needs_endpoint": False,
    },
    "jev": {
        "label": "Fast decision model",
        "detail": (
            "Picks one answer for each built-in check. "
            "Add a base URL and a key in Settings if this is not set up yet."
        ),
        "needs_endpoint": True,
    },
    "clef": {
        "label": "Alternate decision model",
        "detail": (
            "Picks one answer for each check. "
            "Add a base URL and a key in Settings if this is not set up yet."
        ),
        "needs_endpoint": True,
    },
}
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class JudgeProviderSettings:
    provider: str = "auto"
    region: str | None = None
    model: str | None = None
    base_url: str | None = None
    decisions_path: str | None = None
    key_env: tuple[str, ...] = ()

    @property
    def chosen(self) -> bool:
        return self.provider in CHOSEN_IDS

    def to_public_dict(self) -> dict[str, Any]:
        payload = {
            "provider": self.provider,
            "chosen": self.chosen,
            "region": self.region,
            "model": self.model,
            "base_url": self.base_url,
        }
        if self.key_env:
            payload["key_env"] = list(self.key_env)
        return payload


def decision_judges() -> list[dict[str, Any]]:
    """System 1 decision models the engine still accepts.

    Chat and reasoning ids are omitted. An id dropped from ``PROVIDER_IDS``
    disappears here, so the UI does not offer a judge the engine removed.
    """
    rows: list[dict[str, Any]] = []
    for provider_id in PROVIDER_IDS:
        if provider_id == "auto" or provider_id in CHAT_PROVIDER_IDS:
            continue
        copy = _DECISION_JUDGE_COPY.get(provider_id)
        if copy is None:
            continue
        rows.append({"id": provider_id, **copy})
    return rows


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
    decisions_path = _blank(raw.get("decisions_path"))
    settings = JudgeProviderSettings(
        provider=provider,
        region=_blank(raw.get("region")),
        model=_blank(raw.get("model")),
        base_url=_blank(raw.get("base_url")),
        decisions_path=decisions_path,
        key_env=_stored_key_env(raw.get("key_env")),
    )
    if "decisions_path" in raw:
        _rewrite_judge_file(path, settings)
    return settings


def _rewrite_judge_file(path: Path, settings: JudgeProviderSettings) -> None:
    payload = {
        "provider": settings.provider,
        "region": settings.region,
        "model": settings.model,
        "base_url": settings.base_url,
    }
    if settings.key_env:
        payload["key_env"] = list(settings.key_env)
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        fd = os.open(path, flags, 0o600)
        try:
            os.write(fd, json.dumps(payload, indent=2, sort_keys=True).encode("utf-8"))
            os.fchmod(fd, 0o600)
        finally:
            os.close(fd)
    except OSError:
        return


def save_judge_settings(
    root: str | Path,
    *,
    provider: str,
    region: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    decisions_path: str | None = None,
    key_env: list[str] | tuple[str, ...] | None = None,
    _persist_decisions_path: bool = False,
) -> JudgeProviderSettings:
    name = (provider or "auto").strip().lower() or "auto"
    if name == "other":
        name = "compatible"
    if name not in PROVIDER_IDS:
        raise SkillGateError(
            "Scoring provider must be auto or a supported judge id.",
            exit_code=2,
        )
    settings = JudgeProviderSettings(
        provider=name,
        region=_blank(region),
        model=_blank(model),
        base_url=_blank(base_url),
        decisions_path=_blank(decisions_path),
        key_env=_require_key_env(key_env),
    )
    dest = judge_settings_path(root)
    dest.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(dest.parent, 0o700)
    payload = {
        "provider": settings.provider,
        "region": settings.region,
        "model": settings.model,
        "base_url": settings.base_url,
    }
    if settings.key_env:
        payload["key_env"] = list(settings.key_env)
    if _persist_decisions_path and settings.decisions_path:
        payload["decisions_path"] = settings.decisions_path
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


def _require_key_env(value: Any) -> tuple[str, ...]:
    names = _key_env_items(value)
    for name in names:
        if not _ENV_NAME.fullmatch(name):
            raise SkillGateError(
                "Pass the env var name, not the key.",
                hint="Example: --key-env OPENROUTER_API_KEY",
                exit_code=2,
            )
    return tuple(names)


def _stored_key_env(value: Any) -> tuple[str, ...]:
    return tuple(name for name in _key_env_items(value) if _ENV_NAME.fullmatch(name))


def _key_env_items(value: Any) -> list[str]:
    if value is None:
        return []
    raw_items = value if isinstance(value, (list, tuple)) else [value]
    names: list[str] = []
    for item in raw_items:
        name = str(item or "").strip()
        if name and name not in names:
            names.append(name)
    return names


def _blank(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
