"""No-op observability stubs. The private hosted app owns Sentry."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any


def init_sentry() -> None:
    return None


def capture_run_failure(_exc: BaseException) -> None:
    return None


@contextmanager
def eval_transaction(**_kwargs: Any) -> Iterator[None]:
    yield


@contextmanager
def span(_name: str, *_args: Any, **_kwargs: Any) -> Iterator[None]:
    yield


def set_eval_passed(_passed: bool | None) -> None:
    return None


def log_eval_finished(**_kwargs: Any) -> None:
    return None


def breadcrumb_harness_spawn(_command: list[str]) -> None:
    return None


def breadcrumb_timeout(_command: list[str], _timeout: int) -> None:
    return None


def breadcrumb_task(_phase: str, _task_id: str, **_kwargs: Any) -> None:
    return None


def report_eval_outcome(_report: Any, *, run_id: str = "") -> None:
    del run_id
    return None
