"""System 1 decision models.

A decision model answers the fixed questions directly. It does not complete
a chat or a Responses-style prompt.

Add another endpoint with ``register_decision_endpoint``. The id is the
value saved in settings. ``build(cfg)`` returns the engine judge. Copy a
built-in builder and register it at startup. Chat, completions, and
Responses ids are rejected.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol

from skillgate_ai.config import LLMConfig
from skillgate_ai.errors import SkillGateError

CHAT_NOT_A_JUDGE = (
    "A decision model scores checks directly. "
    "Chat and Responses completion models are not judges."
)
REMOVED_SETUP = (
    "That scoring setup was removed. Pick file checks only or a decision model."
)
NOT_A_DECISION_MODEL = (
    "That is not a decision model. Pick file checks only or a registered decision model."
)
NEEDS_KEY = (
    "This decision model needs an API key. Add it in Settings, or with `skillgate keys set`."
)
NEEDS_BASE_URL = "This decision model needs a base URL."
NEEDS_ACCOUNT = (
    "This decision model needs an account id. "
    "Set it with `skillgate judge provider set` and `--account-id`."
)

CHAT_BACKENDS = frozenset({"chat", "completions", "responses", "structured"})
REMOVED_BACKENDS = frozenset({"other", "compatible", "aws", "unknown"})
COMPLETION_BACKENDS = CHAT_BACKENDS | REMOVED_BACKENDS


class DecisionModel(Protocol):
    """One System 1 scorer. It answers questions. It does not complete a chat."""

    name: str
    model: str

    def evaluate(
        self,
        *,
        state: Mapping[str, Any],
        images: list[dict[str, str]],
        timeout_sec: float,
        spec: Any = None,
    ) -> dict[str, Any]:
        """Return status, model, and answers."""
        ...

    def ping(self, *, timeout_sec: float = 20.0) -> dict[str, Any]:
        """Check the endpoint. The message does not name a provider."""
        ...


@dataclass(frozen=True)
class DecisionEndpoint:
    """A registered System 1 endpoint. ``id`` is the settings value."""

    id: str
    build: Callable[[LLMConfig], Any]


_ENDPOINTS: dict[str, DecisionEndpoint] = {}


def register_decision_endpoint(endpoint: DecisionEndpoint) -> None:
    token = (endpoint.id or "").strip().lower()
    if not token or token in CHAT_BACKENDS or token in {"auto", "skip"}:
        raise SkillGateError(CHAT_NOT_A_JUDGE, exit_code=2)
    if token in REMOVED_BACKENDS:
        raise SkillGateError(REMOVED_SETUP, exit_code=2)
    _ENDPOINTS[token] = DecisionEndpoint(token, endpoint.build)


def unregister_decision_endpoint(endpoint_id: str) -> None:
    _ENDPOINTS.pop((endpoint_id or "").strip().lower(), None)


def decision_endpoint(endpoint_id: str) -> DecisionEndpoint | None:
    return _ENDPOINTS.get((endpoint_id or "").strip().lower())


def registered_decision_endpoint_ids() -> tuple[str, ...]:
    return tuple(sorted(_ENDPOINTS))


def require_decision_model(backend: Any) -> None:
    """Reject a chat or Responses client passed in as a judge."""
    name = str(getattr(backend, "name", "") or "").strip().lower()
    if name in COMPLETION_BACKENDS:
        message = REMOVED_SETUP if name in REMOVED_BACKENDS else CHAT_NOT_A_JUDGE
        raise SkillGateError(message, exit_code=2)
    if not callable(getattr(backend, "evaluate", None)):
        raise SkillGateError(CHAT_NOT_A_JUDGE, exit_code=2)
    if not callable(getattr(backend, "ping", None)):
        raise SkillGateError(CHAT_NOT_A_JUDGE, exit_code=2)
