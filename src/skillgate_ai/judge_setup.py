"""Fields each decision model actually scores with.

The Settings form, the Checks picker, and `skillgate judge provider set`
read this list. A field that is not here is rejected, not stored.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from skillgate_ai.errors import SkillGateError

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
JEV_MODEL = "typesafe/jev-1.14"
CLEF_MODELS = ("clef", "clef-flash")

WORKS = "This decision model works."
KEY_REJECTED = "This API key was rejected."
WRONG_ENDPOINT = "This key is for a different endpoint."
OUT_OF_CREDITS = "This account is out of credits."
DECISION_ONE_LINE = "A decision model scores each live check, and one is required."
NEEDS_MODEL = "This decision model needs a model."

_FIELD_WORDS = {
    "base_url": "a base URL",
    "model": "a model",
    "account_id": "an account id",
    "region": "a region",
}


@dataclass(frozen=True)
class DecisionOption:
    id: str
    label: str
    detail: str
    fields: tuple[str, ...]
    advanced: tuple[str, ...] = ()
    models: tuple[str, ...] = ()
    model_free: bool = False
    defaults: tuple[tuple[str, str], ...] = ()
    key_name: str | None = None
    key_label: str = "API key"

    def default(self, name: str) -> str | None:
        for key, value in self.defaults:
            if key == name:
                return value
        return None

    def to_public(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "label": self.label,
            "detail": self.detail,
            "fields": list(self.fields),
            "advanced": list(self.advanced),
            "models": list(self.models),
            "model_free": self.model_free,
            "defaults": {key: value for key, value in self.defaults},
            "key_name": self.key_name,
            "key_label": self.key_label,
            "needs_endpoint": "base_url" in self.fields,
        }
        return payload


OPTIONS: dict[str, DecisionOption] = {
    "openai": DecisionOption(
        id="openai",
        label="OpenAI",
        detail="Uses an OpenAI key.",
        fields=("key",),
        key_name="OPENAI_API_KEY",
    ),
    "jev": DecisionOption(
        id="jev",
        label="OpenRouter",
        detail="Uses an OpenRouter key.",
        fields=("base_url", "model", "key"),
        advanced=("base_url", "model"),
        models=(JEV_MODEL,),
        defaults=(("base_url", OPENROUTER_BASE_URL), ("model", JEV_MODEL)),
        key_name="JEV_API_KEY",
    ),
    "clef": DecisionOption(
        id="clef",
        label="Cloudflare",
        detail="Uses a Cloudflare token.",
        fields=("account_id", "model", "key"),
        models=CLEF_MODELS,
        defaults=(("model", "clef"),),
        key_name="CLOUDFLARE_API_TOKEN",
        key_label="Token",
    ),
    "custom": DecisionOption(
        id="custom",
        label="Custom endpoint",
        detail="Uses a key for this URL.",
        fields=("base_url", "model", "key"),
        model_free=True,
        key_name="CUSTOM_DECISION_API_KEY",
    ),
}

_KEY_ATTR = {
    "OPENAI_API_KEY": "openai_api_key",
    "JEV_API_KEY": "jev_api_key",
    "CLOUDFLARE_API_TOKEN": "clef_api_key",
    "CUSTOM_DECISION_API_KEY": "custom_api_key",
}

# Key prefixes that belong to one option. Anything else is not guessed.
_KEY_FAMILY = (
    ("sk-or-", "jev"),
    ("sk-", "openai"),
)


def option_for(provider: str) -> DecisionOption | None:
    return OPTIONS.get((provider or "").strip().lower())


def blank(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def needs_phrase(option: DecisionOption) -> str:
    if option.id == "openai":
        return "It only needs an API key."
    if option.id == "clef":
        return "It needs an account id, a model, and a token."
    if option.id == "custom":
        return "It needs a base URL, a model, and an API key."
    return "It needs a base URL, a model, and an API key."


def unused_field_message(option: DecisionOption, field: str) -> str:
    word = _FIELD_WORDS.get(field, field)
    return f"{option.label} does not use {word}. {needs_phrase(option)}"


def model_error(option: DecisionOption, model: str) -> str:
    names = " or ".join(option.models)
    base = f"{option.label} scores only with {names}."
    pointer = _model_pointer(model, option.id)
    if pointer:
        return f"{base} {pointer}"
    return base


def _model_pointer(model: str, current: str) -> str:
    slug = (model or "").strip()
    lowered = slug.lower()
    if current != "jev" and (slug == JEV_MODEL or lowered.startswith("typesafe/jev")):
        return f"Choose OpenRouter for {JEV_MODEL}."
    if current != "clef" and lowered in CLEF_MODELS:
        return "Choose Cloudflare for clef or clef-flash."
    return ""


def prepare_option_fields(
    provider: str,
    *,
    region: Any = None,
    model: Any = None,
    base_url: Any = None,
    account_id: Any = None,
) -> tuple[str | None, str | None, str | None, str | None]:
    """Return region, model, base_url, account_id after defaults and rejection.

    ``None`` region means the option does not store one. Extra flags raise.
    """
    name = (provider or "auto").strip().lower() or "auto"
    option = option_for(name)
    given = {
        "region": blank(region),
        "model": blank(model),
        "base_url": blank(base_url),
        "account_id": blank(account_id),
    }
    if option is None:
        if name in {"", "auto"} and any(given.values()):
            raise SkillGateError(
                "Clearing the decision model does not take extra flags.",
                exit_code=2,
            )
        return given["region"], given["model"], given["base_url"], given["account_id"]
    for field, value in given.items():
        if value and field not in option.fields:
            raise SkillGateError(unused_field_message(option, field), exit_code=2)
    resolved = {
        field: given[field] if field in option.fields else None
        for field in ("region", "model", "base_url", "account_id")
    }
    if "base_url" in option.fields and not resolved["base_url"]:
        resolved["base_url"] = option.default("base_url")
    if "model" in option.fields and not resolved["model"]:
        resolved["model"] = option.default("model")
    if "model" in option.fields:
        resolved["model"] = resolve_model(name, resolved["model"]) or None
    if "base_url" in option.fields and not resolved["base_url"]:
        from skillgate_ai.judge_providers.decision import NEEDS_BASE_URL

        raise SkillGateError(NEEDS_BASE_URL, exit_code=2)
    if "account_id" in option.fields and not resolved["account_id"]:
        from skillgate_ai.judge_providers.decision import NEEDS_ACCOUNT

        raise SkillGateError(NEEDS_ACCOUNT, exit_code=2)
    return resolved["region"], resolved["model"], resolved["base_url"], resolved["account_id"]


def _is_chat_model(model: str) -> bool:
    leaf = (model or "").strip().split("/")[-1].lower()
    if not leaf or leaf.endswith("-decisions"):
        return False
    if leaf in {"gpt-6-luna", "clef", "clef-flash"} or leaf.startswith("jev"):
        return False
    if leaf.startswith(("gpt-3.5", "gpt-4", "gpt-5")) or "claude" in leaf:
        return True
    return any(
        leaf == token or leaf.startswith((f"{token}-", f"{token}."))
        for token in ("o1", "o3", "o4")
    )


def _require_model(option: DecisionOption, model: str | None) -> None:
    if option.model_free:
        if not model:
            raise SkillGateError(NEEDS_MODEL, exit_code=2)
        if _is_chat_model(model):
            raise SkillGateError(f"{model.strip()} isn't a decision model.", exit_code=2)
        return
    if not option.models:
        return
    slug = (model or "").strip()
    allowed = {item.lower() for item in option.models}
    if slug.lower() not in allowed:
        raise SkillGateError(model_error(option, slug), exit_code=2)


def resolve_model(provider: str, model: str | None) -> str:
    """Model used at score time. Known options reject anything outside the list."""
    option = option_for(provider)
    slug = (model or "").strip()
    if option is None:
        return slug
    if not slug:
        slug = option.default("model") or ""
    _require_model(option, slug or None)
    for item in option.models:
        if item.lower() == slug.lower():
            return item
    return slug


def resolve_base_url(provider: str, base_url: str | None) -> str:
    option = option_for(provider)
    slug = (base_url or "").strip()
    if slug:
        return slug
    if option is not None:
        return option.default("base_url") or ""
    return ""


def configured_key(cfg: Any, provider: str) -> str:
    option = option_for(provider)
    if option is None or not option.key_name:
        return ""
    attr = _KEY_ATTR.get(option.key_name)
    if not attr:
        return ""
    return str(getattr(cfg, attr, None) or "").strip()


def key_family(secret: str) -> str | None:
    token = (secret or "").strip()
    for prefix, owner in _KEY_FAMILY:
        if token.startswith(prefix):
            return owner
    return None


def key_mismatch(provider: str, secret: str) -> dict[str, Any] | None:
    """When the key prefix belongs to a different option, say so. Do not call out."""
    owner = key_family(secret)
    selected = (provider or "").strip().lower()
    if not owner or owner == selected or selected not in OPTIONS or owner not in OPTIONS:
        return None
    if selected == "custom":
        return None
    label = OPTIONS[owner].label
    return {
        "ok": False,
        "message": (
            f"This looks like an {label} key. "
            f"Switch to {label} with `skillgate judge provider set {owner}`."
        ),
        "switch_to": owner,
    }


def format_provider_selection(settings: Any) -> str:
    """Option id, model, and base URL for `judge provider show` and `set`."""
    from skillgate_ai.judge_providers.decision import NEEDS_DECISION_MODEL

    provider = str(getattr(settings, "provider", "") or "auto").strip().lower() or "auto"
    if provider in {"", "auto", "skip"}:
        return NEEDS_DECISION_MODEL
    model = resolve_model(provider, getattr(settings, "model", None))
    if provider == "openai" and not model:
        from skillgate_ai.judge_openai import DEFAULT_MODEL

        model = DEFAULT_MODEL
    base = _selection_base_url(provider, settings, model)
    parts = ["the judge", provider]
    if model:
        parts.append(model)
    if base:
        parts.append(base)
    return "\n".join(parts)


def _selection_base_url(provider: str, settings: Any, model: str) -> str:
    if provider == "openai":
        from skillgate_ai.judge_openai import DEFAULT_BASE_URL

        return DEFAULT_BASE_URL
    stored = str(getattr(settings, "base_url", "") or "").strip()
    if provider == "clef" and not stored:
        account = str(getattr(settings, "account_id", "") or "").strip()
        slug = model or "clef"
        return (
            "https://api.cloudflare.com/client/v4/accounts/"
            f"{account}/ai/run/@cf/cloudflare/{slug}"
        )
    return resolve_base_url(provider, stored or None)


def classify_test_result(ok: bool, message: str) -> str:
    if ok:
        return WORKS
    lower = (message or "").lower()
    if "out of credits" in lower:
        return OUT_OF_CREDITS
    if (
        "no scoring endpoint" in lower
        or "different endpoint" in lower
        or "for a different endpoint" in lower
    ):
        return WRONG_ENDPOINT
    if (
        "did not accept" in lower
        or "was not accepted" in lower
        or "not allowed to score" in lower
    ):
        return KEY_REJECTED
    return message or "The judge did not answer."
