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
REMOVED_IDS = frozenset({"other", "compatible", "aws", "unknown"})
_ACCOUNT_ID = re.compile(r"^[A-Za-z0-9]+$")
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PREFERRED_DECISION_IDS = ("openai", "jev", "clef")
# Labels stay free of vendor names. An id the engine drops disappears here.
_DECISION_JUDGE_COPY: dict[str, dict[str, Any]] = {
    "openai": {
        "label": "Decision model",
        "detail": "Picks one answer for each check.",
        "needs_endpoint": False,
        "key_name": "OPENAI_API_KEY",
    },
    "jev": {
        "label": "Fast decision model",
        "detail": (
            "Picks one answer for each built-in check. "
            "Add a base URL and a key in Settings if this is not set up yet."
        ),
        "needs_endpoint": True,
        "key_name": "JEV_API_KEY",
    },
    "clef": {
        "label": "Alternate decision model",
        "detail": (
            "Picks one answer for each check. "
            "Add an account id and a key in Settings if this is not set up yet."
        ),
        "needs_endpoint": False,
        "key_name": "CLOUDFLARE_API_TOKEN",
    },
}
_GENERIC_DECISION_COPY: dict[str, Any] = {
    "label": "Decision model",
    "detail": "Picks one answer for each check.",
    "needs_endpoint": True,
    "key_name": None,
}


@dataclass(frozen=True)
class JudgeProviderSettings:
    provider: str = "auto"
    region: str | None = None
    model: str | None = None
    base_url: str | None = None
    decisions_path: str | None = None
    key_env: tuple[str, ...] = ()
    account_id: str | None = None

    @property
    def chosen(self) -> bool:
        if self.provider in {"", "auto", "skip"} or self.provider in REMOVED_IDS:
            return False
        return _is_decision_endpoint(self.provider)

    def to_public_dict(self) -> dict[str, Any]:
        payload = {
            "provider": self.provider,
            "chosen": self.chosen,
            "region": self.region,
            "model": self.model,
            "base_url": self.base_url,
            "account_id": self.account_id,
        }
        if self.key_env:
            payload["key_env"] = list(self.key_env)
        return payload


def decision_judges() -> list[dict[str, Any]]:
    """System 1 decision models the engine still accepts.

    Chat and reasoning ids are not registered, so they are not listed.
    An id the engine drops disappears here.
    """
    from skillgate_ai.judge import ensure_builtin_decision_endpoints
    from skillgate_ai.judge_providers.decision import registered_decision_endpoint_ids

    ensure_builtin_decision_endpoints()
    registered = set(registered_decision_endpoint_ids())
    ordered = [item for item in _PREFERRED_DECISION_IDS if item in registered]
    ordered.extend(item for item in sorted(registered) if item not in ordered)
    rows: list[dict[str, Any]] = []
    for endpoint_id in ordered:
        copy = _DECISION_JUDGE_COPY.get(endpoint_id, _GENERIC_DECISION_COPY)
        rows.append({"id": endpoint_id, **copy})
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
    decisions_path = _blank(raw.get("decisions_path"))
    settings = JudgeProviderSettings(
        provider=provider,
        region=_blank(raw.get("region")),
        model=_blank(raw.get("model")),
        base_url=_blank(raw.get("base_url")),
        decisions_path=decisions_path,
        key_env=_stored_key_env(raw.get("key_env")),
        account_id=_account_id(raw.get("account_id"), required=False),
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
        "account_id": settings.account_id,
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
    account_id: str | None = None,
    _persist_decisions_path: bool = False,
) -> JudgeProviderSettings:
    name = (provider or "auto").strip().lower() or "auto"
    if name in REMOVED_IDS:
        from skillgate_ai.judge_providers.decision import REMOVED_SETUP

        raise SkillGateError(REMOVED_SETUP, exit_code=2)
    if name != "auto" and not _is_decision_endpoint(name):
        from skillgate_ai.judge_providers.decision import NOT_A_DECISION_MODEL

        raise SkillGateError(NOT_A_DECISION_MODEL, exit_code=2)
    settings = JudgeProviderSettings(
        provider=name,
        region=_blank(region),
        model=_blank(model),
        base_url=_blank(base_url),
        decisions_path=_blank(decisions_path),
        key_env=_require_key_env(key_env),
        account_id=_account_id(account_id, required=name == "clef" and account_id is not None),
    )
    dest = judge_settings_path(root)
    dest.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(dest.parent, 0o700)
    payload = {
        "provider": settings.provider,
        "region": settings.region,
        "model": settings.model,
        "base_url": settings.base_url,
        "account_id": settings.account_id,
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
                hint="Example: --key-env DECISION_MODEL_API_KEY",
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


def _is_decision_endpoint(name: str) -> bool:
    from skillgate_ai.judge import ensure_builtin_decision_endpoints
    from skillgate_ai.judge_providers.decision import decision_endpoint

    ensure_builtin_decision_endpoints()
    return decision_endpoint(name) is not None


def _account_id(value: Any, *, required: bool) -> str | None:
    text = _blank(value)
    if text is None:
        return None
    if not _ACCOUNT_ID.fullmatch(text):
        from skillgate_ai.judge_providers.decision import NEEDS_ACCOUNT

        raise SkillGateError(NEEDS_ACCOUNT, exit_code=2)
    del required
    return text


def _blank(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
