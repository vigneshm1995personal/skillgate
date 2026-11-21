from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from skillgate_ai.errors import SkillGateError
from skillgate_ai.extras import (
    EXTRA_MESSAGE,
    PDF_SCORING_FEATURE,
    UI_FEATURE,
    MissingExtraError,
    import_extra,
    require_extra,
)

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

UI_MODULES = ("fastapi", "starlette", "uvicorn", "multipart", "python_multipart")
DOCS_MODULES = ("pypdf", "docx", "openpyxl", "reportlab")

BLOCKER = """
import sys
class _Blocker:
    def find_spec(self, fullname, path=None, target=None):
        top = fullname.split(".", 1)[0]
        if top in set(sys.argv[1].split(",")):
            raise ModuleNotFoundError(f"blocked {{top}}")
        return None
sys.meta_path.insert(0, _Blocker())
"""


def _run_without(
    blocked: tuple[str, ...],
    code: str,
    tmp_path: Path,
    *,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    env = {
        **dict(__import__("os").environ),
        "HOME": str(tmp_path),
        "PYTHONPATH": str(SRC),
    }
    joined = ",".join(blocked)
    full = BLOCKER + code
    return subprocess.run(
        [sys.executable, "-c", full, joined],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(cwd or ROOT),
        timeout=60,
    )


def test_missing_extra_error_contract() -> None:
    err = MissingExtraError("x", "ui")
    assert isinstance(err, ImportError)
    assert isinstance(err, SkillGateError)
    assert err.exit_code == 2
    assert err.render() == str(err)
    assert err.hint is None


def test_missing_extra_message_is_exact() -> None:
    err = MissingExtraError(PDF_SCORING_FEATURE, "docs")
    expected = EXTRA_MESSAGE.format(feature=PDF_SCORING_FEATURE, extra="docs")
    assert str(err) == expected


def test_require_extra_passes_when_installed() -> None:
    require_extra("all", feature="all features")


def test_require_extra_unknown_extra_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Unknown extra"):
        require_extra("nope", feature="nope")


def test_import_extra_wraps_import_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib

    import skillgate_ai.extras as extras_mod

    real = importlib.import_module

    def fake(name: str, *args, **kwargs):
        if name == "fastapi":
            raise ModuleNotFoundError("no fastapi")
        return real(name, *args, **kwargs)

    monkeypatch.setattr(extras_mod.importlib, "import_module", fake)
    with pytest.raises(MissingExtraError) as caught:
        import_extra("fastapi", extra="ui", feature=UI_FEATURE)
    assert isinstance(caught.value.__cause__, ModuleNotFoundError)


def test_core_cli_imports_without_ui_or_docs_extras(tmp_path: Path) -> None:
    proc = _run_without(
        UI_MODULES + DOCS_MODULES,
        "import skillgate_ai.cli; from typer.testing import CliRunner; "
        "from skillgate_ai.cli import app; "
        "r=CliRunner().invoke(app, ['--help']); "
        "assert r.exit_code == 0, r.output",
        tmp_path,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_core_modules_import_without_extras(tmp_path: Path) -> None:
    mods = (
        "skillgate_ai.gate",
        "skillgate_ai.engine",
        "skillgate_ai.scorers",
        "skillgate_ai.demo_files",
        "skillgate_ai.pack",
        "skillgate_ai.api_payloads",
        "skillgate_ai.checks_show",
        "skillgate_ai.compare",
        "skillgate_ai.history",
        "skillgate_ai.judge_context",
        "skillgate_ai.document_text",
        "skillgate_ai.local_ui.api",
        "skillgate_ai.local_ui.server",
    )
    code = ";".join(f"import {m}" for m in mods)
    proc = _run_without(UI_MODULES + DOCS_MODULES, code, tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_checks_show_cli_runs_without_ui_extra(tmp_path: Path) -> None:
    proc = _run_without(
        UI_MODULES,
        "from typer.testing import CliRunner; from skillgate_ai.cli import app; "
        "r=CliRunner().invoke(app, ['checks','show','path_efficiency']); "
        "assert r.exit_code == 0",
        tmp_path,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_server_import_without_ui_extra_raises_friendly_error(tmp_path: Path) -> None:
    proc = _run_without(
        UI_MODULES,
        "try:\n import skillgate_ai.server\nexcept Exception as e:\n "
        "import sys; print(e); sys.exit(0 if 'skillgate-ai[ui]' in str(e) else 1)",
        tmp_path,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_create_app_without_ui_extra_raises_friendly_error(tmp_path: Path) -> None:
    proc = _run_without(
        UI_MODULES,
        "try:\n from skillgate_ai.api import create_app\nexcept Exception as e:\n "
        "import sys; print(e); sys.exit(0 if 'skillgate-ai[ui]' in str(e) else 1)",
        tmp_path,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_ui_command_without_ui_extra_exits_2_with_install_hint(tmp_path: Path) -> None:
    proc = _run_without(
        UI_MODULES,
        "from typer.testing import CliRunner; from skillgate_ai.cli import app; "
        "r=CliRunner().invoke(app, ['ui','--no-browser']); "
        "assert r.exit_code == 2; "
        "plain = ' '.join(r.output.split()); "
        "assert \"pip install 'skillgate-ai[ui]'\" in plain",
        tmp_path,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


@pytest.mark.parametrize(
    "module",
    [
        "skillgate_ai.api",
        "skillgate_ai.api_compare",
        "skillgate_ai.api_evals",
        "skillgate_ai.api_runs",
        "skillgate_ai.api_shims",
        "skillgate_ai.api_skills",
        "skillgate_ai.local_guard",
        "skillgate_ai.server",
    ],
)
def test_ui_modules_each_raise_friendly_error_without_fastapi(module: str, tmp_path: Path) -> None:
    proc = _run_without(
        UI_MODULES,
        f"from skillgate_ai.extras import MissingExtraError\n"
        f"try:\n import {module}\nexcept MissingExtraError as e:\n "
        "import sys; sys.exit(0 if e.extra == 'ui' else 2)\n"
        "raise SystemExit(9)",
        tmp_path,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_pyproject_core_dependencies_are_slim() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    deps = data["project"]["dependencies"]
    assert len(deps) == 7
    extras = data["project"]["optional-dependencies"]
    assert "ui" in extras and "docs" in extras and "all" in extras
    assert "fastapi>=" in " ".join(extras["ui"])
    assert "pypdf>=" in " ".join(extras["docs"])


def test_dockerfile_installs_docs_extra_not_ui() -> None:
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "['optional-dependencies']['docs']" in text
    assert "[ui]" not in text
    assert "fastapi" not in text.lower()


def test_readme_and_quickstart_document_extras() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    quick = (ROOT / "docs" / "quickstart.md").read_text(encoding="utf-8")
    for needle in (
        "skillgate-ai[ui]",
        "skillgate-ai[docs]",
        "skillgate-ai[all]",
    ):
        assert needle in readme
        assert needle in quick
