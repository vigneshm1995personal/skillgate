"""Explicit Skill Gate keys. Ambient provider env names are never used unless opted in."""

from __future__ import annotations

import os
from pathlib import Path

from skillgate_ai.errors import SkillGateError

PROVIDER_KEY_NAMES = (
    "CURSOR_API_KEY",
    "CODEX_API_KEY",
    "OPENAI_API_KEY",
    "AI_GATEWAY_API_KEY",
    "ANTHROPIC_API_KEY",
    "JEV_API_KEY",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
)

_PUBLIC_TO_INTERNAL = {
    "Other": "AI_GATEWAY_API_KEY",
    "other": "AI_GATEWAY_API_KEY",
}

SKILLGATE_KEY_ENV = {
    "CURSOR_API_KEY": "SKILLGATE_CURSOR_API_KEY",
    "CODEX_API_KEY": "SKILLGATE_CODEX_API_KEY",
    "OPENAI_API_KEY": "SKILLGATE_OPENAI_API_KEY",
    "AI_GATEWAY_API_KEY": "SKILLGATE_AI_GATEWAY_API_KEY",
    "ANTHROPIC_API_KEY": "SKILLGATE_ANTHROPIC_API_KEY",
    "JEV_API_KEY": "SKILLGATE_JEV_API_KEY",
    "AWS_ACCESS_KEY_ID": "SKILLGATE_AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY": "SKILLGATE_AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN": "SKILLGATE_AWS_SESSION_TOKEN",
}

KEYS_DIRNAME = ".skillgate"
KEYS_FILENAME = "keys"

_bound_key_env: set[str] = set()


def reset_key_env_bindings() -> None:
    _bound_key_env.clear()


def bind_key_env(names: list[str] | tuple[str, ...] | None) -> None:
    """Allow this process to read the named ambient provider env vars."""
    for raw in names or []:
        name = (raw or "").strip()
        if name in PROVIDER_KEY_NAMES:
            _bound_key_env.add(name)
            continue
        for provider, alias in SKILLGATE_KEY_ENV.items():
            if name == alias:
                _bound_key_env.add(provider)
                break


def bound_key_env_names() -> frozenset[str]:
    return frozenset(_bound_key_env)


def keys_path(root: str | Path) -> Path:
    return Path(root).expanduser().resolve() / KEYS_DIRNAME / KEYS_FILENAME


def _read_env_file(path: Path) -> dict[str, str]:
    found: dict[str, str] = {}
    if not path.is_file():
        return found
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return found
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        name = key.strip()
        if name in PROVIDER_KEY_NAMES and value.strip():
            found[name] = value.strip()
    return found


def read_vault(root: str | Path) -> dict[str, str]:
    return _read_env_file(keys_path(root))


def _write_vault(root: str | Path, values: dict[str, str]) -> Path:
    dest = keys_path(root)
    dest.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(dest.parent, 0o700)
    lines = [f"{name}={values[name]}" for name in PROVIDER_KEY_NAMES if values.get(name)]
    text = "\n".join(lines)
    if text:
        text += "\n"
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(dest, flags, 0o600)
    try:
        os.write(fd, text.encode("utf-8"))
        os.fchmod(fd, 0o600)
    except OSError as exc:
        raise SkillGateError(
            "Couldn't save the key with private file permissions.",
            hint="Check that this project folder is writable.",
        ) from exc
    finally:
        os.close(fd)
    return dest


def set_vault_key(root: str | Path, name: str, value: str) -> Path:
    key = _require_name(name)
    token = (value or "").strip()
    if not token:
        raise SkillGateError("Paste a key before saving.")
    if any(ch in token for ch in "\r\n"):
        raise SkillGateError("API keys cannot contain line breaks.")
    current = read_vault(root)
    current[key] = token
    return _write_vault(root, current)


def clear_vault_key(root: str | Path, name: str) -> Path:
    key = _require_name(name)
    current = read_vault(root)
    current.pop(key, None)
    return _write_vault(root, current)


def resolve_provider_keys(root: str | Path) -> dict[str, str]:
    """Vault, then SKILLGATE_* overlay, then --key-env ambient names. Never bare provider env."""
    found = dict(read_vault(root))
    for provider, alias in SKILLGATE_KEY_ENV.items():
        overlay = os.environ.get(alias, "").strip()
        if overlay:
            found[provider] = overlay
    for provider in _bound_key_env:
        ambient = os.environ.get(provider, "").strip()
        if ambient:
            found[provider] = ambient
    return found


def internal_key_name(name: str) -> str:
    key = (name or "").strip()
    return _PUBLIC_TO_INTERNAL.get(key) or _PUBLIC_TO_INTERNAL.get(key.lower()) or key


def public_key_name(name: str) -> str:
    canonical = internal_key_name(name)
    return canonical if canonical in PROVIDER_KEY_NAMES else name


def public_key_presence(root: str | Path) -> dict[str, dict[str, bool]]:
    return {public_key_name(name): meta for name, meta in key_presence(root).items()}


def key_presence(root: str | Path) -> dict[str, dict[str, bool]]:
    vault = read_vault(root)
    resolved = resolve_provider_keys(root)
    keys: dict[str, dict[str, bool]] = {}
    for name in PROVIDER_KEY_NAMES:
        in_vault = name in vault
        from_env = bool(resolved.get(name)) and not in_vault
        keys[name] = {
            "set": bool(resolved.get(name)),
            "from_vault": in_vault,
            "from_env": from_env,
        }
    return keys


def list_key_names(root: str | Path) -> list[str]:
    return [name for name, meta in key_presence(root).items() if meta["set"]]


def _require_name(name: str) -> str:
    key = internal_key_name(name)
    if key not in PROVIDER_KEY_NAMES:
        raise SkillGateError(
            "Unknown key name.",
            hint="Use CURSOR_API_KEY, CODEX_API_KEY, OPENAI_API_KEY, "
            "Other, ANTHROPIC_API_KEY, JEV_API_KEY, "
            "AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, or AWS_SESSION_TOKEN.",
        )
    return key
