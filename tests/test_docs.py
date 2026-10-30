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


def _strip_heading_section(text: str, heading: str) -> str:
    start = text.find(heading)
    if start < 0:
        return text
    rest = text[start:]
    end_rel = rest.find("\n## ", 1)
    end = len(text) if end_rel < 0 else start + end_rel
    return text[:start] + text[end:]


def _readme_outside_decision_setup(text: str) -> str:
    """Vendor names belong in the agent-key and decision-model setup sections."""
    out = text
    for heading in ("## Sign in an agent", "## Set up a decision model"):
        out = _strip_heading_section(out, heading)
    return out


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
    assert 'version = "0.7.10"' in pyproject
    assert '__version__ = "0.7.10"' in init
    assert "pip install skillgate-ai" in readme
    assert "0.7.10" in readme
    assert "Until 0.7.10 is published" in quickstart
    assert "Until 0.7.10 is published" in judge
    assert "skillgate-ai==0.7.10" not in quickstart
    assert "skillgate-ai==0.7.10" not in judge
    assert "version: 0.7.10" not in quickstart
    assert "version: 0.7.10" not in judge
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


def test_readme_installs_with_venv_or_pipx_and_links_quickstart() -> None:
    text = README.read_text(encoding="utf-8")
    assert "python3 -m venv .venv" in text
    assert "pipx install skillgate-ai" in text
    assert "docs/quickstart.md" in text


def test_readme_lists_agent_key_names_and_set_command() -> None:
    text = README.read_text(encoding="utf-8")
    for name in ("CURSOR_API_KEY", "ANTHROPIC_API_KEY", "CODEX_API_KEY"):
        assert name in text
    assert "printf '%s\\n' \"$CURSOR_API_KEY\" | skillgate keys set CURSOR_API_KEY" in text


def test_readme_maps_cli_labels_to_tools_and_deploy_folders() -> None:
    text = README.read_text(encoding="utf-8")
    start = text.find("## Sign in an agent")
    end = text.find("\n## ", start + 1)
    section = text[start:end]
    assert "Editor agent is Cursor" in section
    assert "`~/.cursor/skills`" in section
    assert "Code agent is Claude Code" in section
    assert "`~/.claude/skills`" in section
    assert "Terminal agent is Codex" in section
    assert "`~/.codex/skills`" in section


def test_readme_examples_toast_matches_install_count() -> None:
    from skillgate_ai.examples import DATASET_EXAMPLES, _example_files

    total = sum(len(_example_files(ROOT / "skills" / name)) for name in DATASET_EXAMPLES)
    text = README.read_text(encoding="utf-8")
    assert f"Installed 6 examples ({total} files)." in text


def test_openrouter_docs_pipe_openrouter_key_and_explain_jev() -> None:
    for path in (README, ROOT / "docs" / "judge.md"):
        text = path.read_text(encoding="utf-8")
        start = text.find("### OpenRouter")
        end = text.find("### OpenAI")
        section = text[start:end]
        assert start >= 0, path.name
        assert (
            "printf '%s\\n' \"$OPENROUTER_API_KEY\" | skillgate keys set JEV_API_KEY"
            in section
        )
        assert "$JEV_API_KEY" not in section
        assert "Jev" in section


def test_docs_cover_escalation_majority_named_reds_and_no_judge() -> None:
    readme = README.read_text(encoding="utf-8")
    guide = (ROOT / "docs" / "writing-a-dataset.md").read_text(encoding="utf-8")
    judge = (ROOT / "docs" / "judge.md").read_text(encoding="utf-8")
    blob = readme + "\n" + guide + "\n" + judge
    assert "escalation" in blob.lower() or "escalate" in blob.lower()
    assert "refusal" in blob.lower()
    assert "majority" in blob.lower()
    assert "tasks[].judge.votes" in blob
    assert "Got the job done?" in blob
    assert "--no-judge" in judge
    assert "still needs" in judge.lower() and "agent" in judge.lower()
    assert "history show" in blob.lower()


def test_judge_docs_require_a_decision_model() -> None:
    judge = (ROOT / "docs" / "judge.md").read_text(encoding="utf-8")
    head = "\n".join(judge.splitlines()[:8])
    assert "Optional." not in head
    assert "one is required" in judge
    readme = README.read_text(encoding="utf-8")
    assert "one is required" in readme


def test_deploy_docs_use_cli_agent_labels() -> None:
    quickstart = QUICKSTART.read_text(encoding="utf-8")
    assert "Editor agent" in quickstart
    assert "Code agent" in quickstart
    assert "Terminal agent" in quickstart
    deploy = quickstart.split("## Deploy", 1)[-1]
    assert "into Cursor, Claude, or Codex" not in deploy


def test_quickstart_maps_cli_labels_to_tools_and_deploy_folders() -> None:
    text = QUICKSTART.read_text(encoding="utf-8")
    keys = text.split("## Keys", 1)[-1].split("## ", 1)[0]
    deploy = text.split("## Deploy", 1)[-1]
    for section in (keys, deploy):
        assert "Editor agent is Cursor" in section
        assert "`~/.cursor/skills`" in section
        assert "Code agent is Claude Code" in section
        assert "`~/.claude/skills`" in section
        assert "Terminal agent is Codex" in section
        assert "`~/.codex/skills`" in section


def test_docker_docs_clone_before_compose() -> None:
    for path in (README, QUICKSTART):
        text = path.read_text(encoding="utf-8")
        clone_at = text.find("git clone")
        compose_at = text.find("docker compose run")
        assert clone_at >= 0, path.name
        assert compose_at >= 0, path.name
        assert clone_at < compose_at, path.name


def test_openai_judge_docs_name_default_model() -> None:
    blob = README.read_text(encoding="utf-8") + "\n" + (ROOT / "docs" / "judge.md").read_text(
        encoding="utf-8"
    )
    openai = blob[blob.find("### OpenAI") : blob.find("### Cloudflare")]
    assert "gpt-6-luna" in openai


def test_oct_extract_plans_are_marked_historical() -> None:
    for name in (
        "2026-10-03-skillgate-oss-extract.md",
        "2026-10-04-local-ui-setup-wizard.md",
    ):
        text = (ROOT / "docs" / "plans" / name).read_text(encoding="utf-8")
        head = "\n".join(text.splitlines()[:8]).lower()
        assert "historical" in head, name
