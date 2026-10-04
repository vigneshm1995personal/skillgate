"""Judge protocol. Default is skip — deterministic scorers own red/green."""

from __future__ import annotations

from typing import Any, Protocol


class Judge(Protocol):
    """Optional outcome judge. Private hosted injects Jev outside this repo."""

    def judge(
        self,
        goal: str,
        artifacts: list[dict[str, Any]],
        transcript_tail: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Return ``{passed, cells, ...}``. Skip implementations set ``status=skip``."""
        ...


class SkipJudge:
    """Det-only default. Does not change the scorer AND verdict."""

    name = "skip"

    def judge(
        self,
        goal: str,
        artifacts: list[dict[str, Any]],
        transcript_tail: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        del goal, artifacts, transcript_tail, kwargs
        return {
            "status": "skip",
            "passed": None,
            "cells": [],
            "reason": "SkipJudge: deterministic scorers own this check.",
        }


def default_judge() -> SkipJudge:
    return SkipJudge()
