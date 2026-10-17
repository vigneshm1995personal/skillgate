"""Product mode: local (this package) or cloud (private wrapper later).

Paid / hosted surfaces are **hidden** in local mode, not locked. The same React
app reads ``status.mode`` and ``status.slots``. Core never imports cloud.
"""

from __future__ import annotations

import os
from typing import Literal

LOCAL = "local"
CLOUD = "cloud"
Mode = Literal["local", "cloud"]

# Hidden in local (not locked). Names match the React slot checks.
# Home is a core screen in both modes, so analyticsHome stays on.
LOCAL_SLOTS: dict[str, bool] = {
    "signIn": False,
    "billing": False,
    "sharedHistory": False,
    "hostedJudge": False,
    "sandboxes": False,
    "tryoutCaps": False,
    "generateChecks": False,
    "gitPublish": False,
    "suggestUpdates": False,
    "analyticsHome": True,
}

CLOUD_SLOTS: dict[str, bool] = {key: True for key in LOCAL_SLOTS}


def current_mode() -> Mode:
    raw = os.environ.get("SKILLGATE_MODE", LOCAL).strip().lower()
    if raw == CLOUD:
        return CLOUD
    return LOCAL


def slots_for(mode: Mode | None = None) -> dict[str, bool]:
    kind = mode or current_mode()
    return dict(CLOUD_SLOTS if kind == CLOUD else LOCAL_SLOTS)


def is_local(mode: Mode | None = None) -> bool:
    return (mode or current_mode()) == LOCAL
