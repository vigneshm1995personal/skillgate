from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
QUICKSTART = ROOT / "docs" / "quickstart.md"
RELEASE = ROOT / ".github" / "workflows" / "release.yml"
INTERNAL = ("SIWV", "vault", "Neon", "BYOLLM", "BYO LLM")


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
    install = text.split("## Red")[0]
    assert "pip install skillgate-ai" in install
    assert "Python 3.11" in text
    if "pip install -e ." in install:
        assert install.index("pip install skillgate-ai") < install.index("pip install -e .")


def test_public_docs_drop_internal_words() -> None:
    blob = README.read_text(encoding="utf-8") + "\n" + QUICKSTART.read_text(encoding="utf-8")
    for word in INTERNAL:
        assert word not in blob, word


def test_readme_doc_links_are_absolute() -> None:
    text = README.read_text(encoding="utf-8")
    assert "https://github.com/vigneshm1995personal/skillgate/blob/main/docs/quickstart.md" in text
    assert (
        "https://github.com/vigneshm1995personal/skillgate/blob/main/docs/openai-judge.md" in text
    )
    assert "](docs/" not in text


def test_release_yml_example_tag_is_current() -> None:
    text = RELEASE.read_text(encoding="utf-8")
    assert "v0.3.0" not in text
    assert "v0.4.2" in text


def test_package_and_docs_pin_042() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    init = (ROOT / "src" / "skillgate_ai" / "__init__.py").read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    quickstart = QUICKSTART.read_text(encoding="utf-8")
    judge = (ROOT / "docs" / "openai-judge.md").read_text(encoding="utf-8")
    assert 'version = "0.4.2"' in pyproject
    assert '__version__ = "0.4.2"' in init
    assert "skillgate-ai==0.4.2" in readme
    assert "skillgate-ai==0.4.2" in quickstart
    assert "skillgate-ai==0.4.2" in judge
    assert "v0.4.2" in readme
    assert "# 0.4.2" in quickstart


def test_deploy_docs_explain_force() -> None:
    blob = README.read_text(encoding="utf-8") + "\n" + QUICKSTART.read_text(encoding="utf-8")
    assert "--force" in blob
    assert "did not pass" in blob or "latest local check" in blob
