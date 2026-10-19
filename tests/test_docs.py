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


def _readme_outside_decision_setup(text: str) -> str:
    """Key-source names belong in the setup section. The rest of the README stays free of them."""
    start = text.find("## Set up a decision model")
    if start < 0:
        return text
    rest = text[start:]
    end_rel = rest.find("\n## ", 1)
    end = len(text) if end_rel < 0 else start + end_rel
    return text[:start] + text[end:]


def test_readme_points_at_docs() -> None:
    text = README.read_text(encoding="utf-8")
    assert "https://www.skill-gate-ai.app/docs" in text
    assert "docs/openai-judge.md" not in text
    assert "agentskills.io" not in text
    assert "decision model" in text.lower()
    assert "custom" in text.lower()
    assert "## Set up a decision model" in text
    lowered = _readme_outside_decision_setup(text).lower()
    for needle in (
        "promptfoo",
        "agentskills.io",
        "openai",
        "anthropic",
        "claude",
        "cursor",
        "codex",
        "dashboard",
        "hosted",
        "cloud",
    ):
        assert needle not in lowered, needle


def test_release_yml_example_tag_is_current() -> None:
    text = RELEASE.read_text(encoding="utf-8")
    assert "v0.3.0" not in text
    assert "v0.4.2" in text or "v0.5.0" in text or "v0.5.1" in text or "v0.6.0" in text


def test_package_and_docs_pin_078() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    init = (ROOT / "src" / "skillgate_ai" / "__init__.py").read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    quickstart = QUICKSTART.read_text(encoding="utf-8")
    judge = (ROOT / "docs" / "judge.md").read_text(encoding="utf-8")
    assert 'version = "0.7.9"' in pyproject
    assert '__version__ = "0.7.9"' in init
    assert "pip install skillgate-ai" in readme
    assert "0.7.9" in readme
    assert "skillgate-ai==0.7.9" in quickstart
    assert "skillgate-ai==0.7.9" in judge
    assert "# 10-minute" in quickstart


def test_deploy_docs_require_a_check_first() -> None:
    blob = README.read_text(encoding="utf-8") + "\n" + QUICKSTART.read_text(encoding="utf-8")
    assert "already has a passing check" in blob or "Run the checks first" in blob
    assert "does not run check" in blob.lower() or "does not run check for you" in blob
    readme = README.read_text(encoding="utf-8")
    # `skillgate example pdf` writes skills/<name>, so check and deploy take that path.
    assert "skillgate check skills/pdf" in readme
    assert "skillgate deploy skills/pdf" in readme
    lines = readme.splitlines()
    assert "skillgate check pdf" not in lines
    assert "skillgate deploy pdf" not in lines


def test_quickstart_installs_dataset_examples_and_shows_pass_and_fail() -> None:
    text = QUICKSTART.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    for blob in (text, readme):
        assert "skillgate examples install" in blob
        assert "skillgate check skills/json-response" in blob
        assert "skillgate check skills/json-response-sabotaged" in blob
    assert "skillgate examples list" in text
    assert "Run 3 cases" in text
    assert "Examples" in text
    guide = (ROOT / "docs" / "writing-a-dataset.md").read_text(encoding="utf-8")
    assert "docs/writing-a-dataset.md" in readme
    assert "https://www.skill-gate-ai.app/docs/writing-a-dataset" in readme
    for phrase in (
        "schema: 1",
        "should_trigger: false",
        "not specified",
        "3 to 6",
        "skillgate case list skills/json-response",
        "skillgate ingest skills/json-response",
        "Left N existing file(s) in place.",
        "json-response-sabotaged",
        "readme-writer",
        "log-summarizer",
        "sql-writer",
        "receipt-extractor",
    ):
        assert phrase in guide, phrase


def test_quickstart_uses_example_and_keys() -> None:
    text = QUICKSTART.read_text(encoding="utf-8")
    assert "skillgate example pdf" in text
    assert "skillgate keys set" in text
    assert "--key-env" in text
    assert "SKILLGATE_OPENAI_API_KEY" in text
    assert "CI/Docker" in text or "CI and Docker" in README.read_text(encoding="utf-8")
    blob = README.read_text(encoding="utf-8") + "\n" + text
    assert "even after a green check" in blob
    assert "SKILLGATE_*" in blob
    assert "always read" in blob
    assert "documented CI/Docker path" in blob or "documented job path" in blob
    ui = (ROOT / "docs" / "ui.md").read_text(encoding="utf-8")
    assert "even after a passing check" in ui
    assert "SKILLGATE_*" in ui
    assert "skillgate keys set" in ui


def test_docs_keys_set_never_puts_value_on_the_command_line() -> None:
    blob = README.read_text(encoding="utf-8") + "\n" + QUICKSTART.read_text(encoding="utf-8")
    assert "keys set OPENAI_API_KEY \"$OPENAI_API_KEY\"" not in blob
    assert "keys set OPENAI_API_KEY $OPENAI_API_KEY" not in blob
    assert "keys set OPENAI_API_KEY sk-" not in blob
    assert "skillgate keys set OPENAI_API_KEY" in blob


def test_quickstart_does_not_require_codex_api_key() -> None:
    text = QUICKSTART.read_text(encoding="utf-8")
    assert "isolated `CODEX_HOME`" not in text
    assert "authenticates the isolated run" not in text


def test_quickstart_does_not_promise_fixture_checks_without_a_key() -> None:
    text = QUICKSTART.read_text(encoding="utf-8").lower()
    assert "without that key, fixture checks" not in text
    assert "fixture checks (file exists, contains, page count) still decide pass/fail" not in text


def test_openai_judge_docs_do_not_say_fixture_checks_decide_pass_fail() -> None:
    text = (ROOT / "docs" / "judge.md").read_text(encoding="utf-8").lower()
    assert "fixture checks decide pass/fail" not in text
    assert "otherwise fixture checks" not in text
    assert "fixture checks decide the result" not in text


def test_pack_docs_drop_demo_harness() -> None:
    text = (ROOT / "docs" / "pack.md").read_text(encoding="utf-8").lower()
    assert "demo harness" not in text
    assert "openai-compatible" not in text
    assert "llm harness" not in text


def test_oct_extract_plans_are_marked_historical() -> None:
    for name in (
        "2026-10-03-skillgate-oss-extract.md",
        "2026-10-04-local-ui-setup-wizard.md",
    ):
        text = (ROOT / "docs" / "plans" / name).read_text(encoding="utf-8")
        head = "\n".join(text.splitlines()[:8]).lower()
        assert "historical" in head, name
