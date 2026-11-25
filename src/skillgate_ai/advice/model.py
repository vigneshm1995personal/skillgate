from __future__ import annotations

from dataclasses import dataclass

BEHAVIOR_FAIL_LEAD = (
    "The agent's behavior failed this check: {question} → No. Review the run log below."
)
TRIGGER_SECONDARY_NOTE = (
    "Note: this skill wasn't opened during this run. If it should have been, "
    "you can review the description."
)

_MEAL_NOISE = {
    "dinner",
    "dinners",
    "recipe",
    "recipes",
    "grocery",
    "groceries",
    "pantry",
    "meal",
    "meals",
    "shopping",
}


@dataclass
class FixAdvice:
    headline: str
    why: str
    change: str
    paste: str
    target: str  # description | body
    description: str | None = None
    demo_note: str | None = None
    apply_label: str = "Run"
    restore_scripts_from: str | None = None
