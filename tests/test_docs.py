from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
QUICKSTART = ROOT / "docs" / "quickstart.md"
RELEASE = ROOT / ".github" / "workflows" / "release.yml"
INTERNAL = ("SIWV", "Neon", "BYOLLM", "BYO LLM")


def test_readme_leads_with_pypi_install() -> None:
    text = README.read_text(encoding="utf-8")
    lead = text.split("## 10 minutes")[0]
    assert "pip install skillgate-ai" in lead
    idx_pypi = lead.index("pip install skillgate-ai")
    if "pip install -e ." in lead:
        assert lead.index("pip install -e .") > idx_pypi
    assert "Until the first PyPI release" not in text
    assert "Python 3.11" in text


def test_quickstart_leads_with_pypi_install() -> None:
    text = QUICKSTART.read_text(encoding="utf-8")
    install = text.split("## Keys")[0]
    assert "pip install skillgate-ai" in install
    assert "Python 3.11" in text
    if "pip install -e ." in install:
        assert install.index("pip install skillgate-ai") < install.index("pip install -e .")


def test_public_docs_drop_internal_words() -> None:
    blob = README.read_text(encoding="utf-8") + "\n" + QUICKSTART.read_text(encoding="utf-8")
    for word in INTERNAL:
        assert word not in blob, word


def test_readme_points_at_docs() -> None:
    text = README.read_text(encoding="utf-8")
    assert "docs/quickstart.md" in text
    assert "docs/openai-judge.md" in text


def test_release_yml_example_tag_is_current() -> None:
    text = RELEASE.read_text(encoding="utf-8")
    assert "v0.3.0" not in text
    assert "v0.4.2" in text or "v0.5.0" in text


def test_package_and_docs_pin_050() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    init = (ROOT / "src" / "skillgate_ai" / "__init__.py").read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    quickstart = QUICKSTART.read_text(encoding="utf-8")
    judge = (ROOT / "docs" / "openai-judge.md").read_text(encoding="utf-8")
    assert 'version = "0.5.0"' in pyproject
    assert '__version__ = "0.5.0"' in init
    assert "skillgate-ai==0.5.0" in readme
    assert "skillgate-ai==0.5.0" in quickstart
    assert "skillgate-ai==0.5.0" in judge
    assert "0.5.0" in readme
    assert "# 10-minute" in quickstart


def test_deploy_docs_require_a_check_first() -> None:
    blob = README.read_text(encoding="utf-8") + "\n" + QUICKSTART.read_text(encoding="utf-8")
    assert "already has a passing check" in blob or "Run the checks first" in blob
    assert "does not run check" in blob.lower() or "does not run check for you" in blob
    assert "deploy skills/pdf" not in README.read_text(encoding="utf-8")
    assert "skillgate deploy pdf" in README.read_text(encoding="utf-8")


def test_quickstart_uses_example_and_keys() -> None:
    text = QUICKSTART.read_text(encoding="utf-8")
    assert "skillgate example pdf" in text
    assert "skillgate keys set" in text
    assert "--key-env" in text
