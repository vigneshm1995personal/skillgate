"""Optional dependency extras. Core installs stay slim; features name their extra."""

from __future__ import annotations

import importlib
from types import ModuleType
from typing import Final

from skillgate_ai.errors import SkillGateError

EXTRA_MESSAGE: Final = (
    "Missing optional dependency for {feature}. Install with: pip install 'skillgate-ai[{extra}]'"
)

UI_FEATURE: Final = "the local UI (skillgate ui)"
PDF_SCORING_FEATURE: Final = "PDF scoring"
DEMO_PDF_FEATURE: Final = "demo PDF generation"
MCP_FEATURE: Final = "the MCP server (skillgate mcp)"

EXTRA_MODULES: Final[dict[str, tuple[str, ...]]] = {
    "ui": ("fastapi", "uvicorn"),
    "docs": ("pypdf", "docx", "openpyxl", "reportlab"),
    "mcp": ("mcp",),
    "all": ("fastapi", "uvicorn", "pypdf", "docx", "openpyxl", "reportlab", "mcp"),
}


class MissingExtraError(SkillGateError, ImportError):
    """A feature needs an optional extra that is not installed. Cannot run, not a fail."""

    exit_code = 2

    def __init__(self, feature: str, extra: str) -> None:
        self.feature = feature
        self.extra = extra
        super().__init__(EXTRA_MESSAGE.format(feature=feature, extra=extra))

    def render(self) -> str:
        return str(self)


def import_extra(module: str, *, extra: str, feature: str) -> ModuleType:
    """Import one optional module or raise MissingExtraError naming the extra."""
    try:
        return importlib.import_module(module)
    except ImportError as exc:
        raise MissingExtraError(feature, extra) from exc


def require_extra(extra: str, *, feature: str) -> None:
    """Raise MissingExtraError unless every probe module of `extra` imports."""
    if extra not in EXTRA_MODULES:
        raise ValueError(f"Unknown extra {extra!r}")
    for module in EXTRA_MODULES[extra]:
        import_extra(module, extra=extra, feature=feature)
