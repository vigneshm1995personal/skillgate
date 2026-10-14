from __future__ import annotations

from pathlib import Path

import httpx

from skillgate_ai.errors import HarnessError
from skillgate_ai.harness import _gateway_complete_response
from skillgate_ai.harness_llm_run import command_allowed, parse_run_lines
from skillgate_ai.metrics import count_path_steps
from test_judge import _cfg


def test_parse_run_lines_keeps_quoted_title() -> None:
    text = (
        "RUN: python3 .skillgate/skills/pdf/scripts/create_pdf.py "
        '--title "Q3 Status" output/status.pdf --body "All systems are go."'
    )
    commands = parse_run_lines(text)
    assert commands == [
        [
            "python3",
            ".skillgate/skills/pdf/scripts/create_pdf.py",
            "--title",
            "Q3 Status",
            "output/status.pdf",
            "--body",
            "All systems are go.",
        ]
    ]
    assert command_allowed(commands[0], "pdf")
    assert '"Q3' not in commands[0]
    assert 'Status"' not in commands[0]


def test_command_allowed_rejects_python_c_with_skill_path_decoy() -> None:
    assert not command_allowed(
        [
            "python3",
            "-c",
            "open('/tmp/pwned','w').write('x')",
            ".skillgate/skills/pdf/scripts/create_pdf.py",
        ],
        "pdf",
    )
    assert not command_allowed(
        ["python3", "-m", "http.server", ".skillgate/skills/pdf/scripts/create_pdf.py"],
        "pdf",
    )


def test_byo_llm_429_is_plain_settings_copy(monkeypatch) -> None:
    def fake_post(url, headers=None, json=None, timeout=None):
        del url, headers, json, timeout
        return httpx.Response(429, json={"error": {"message": "rate"}})

    monkeypatch.setattr("skillgate_ai.harness.httpx.post", fake_post)
    try:
        _gateway_complete_response(_cfg(gateway_api_key="gw-test"), "hello", 5)
    except HarnessError as exc:
        blob = f"{exc.message} {exc.hint or ''}"
    else:
        raise AssertionError("expected HarnessError")
    assert "429" not in blob
    assert "BYO LLM" not in blob
    assert "OPENAI_API_KEY" not in blob
    assert "AI_GATEWAY_API_KEY" not in blob
    assert "SKILLGATE_MODEL" not in blob
    assert ".env" not in blob
    assert "Settings" in blob
    assert "rate-limited" in blob.lower() or "out of credit" in blob.lower()


def test_count_path_steps_counts_llm_run_commands() -> None:
    transcript = (
        "selected: pdf\n"
        'RUN: python3 .skillgate/skills/pdf/scripts/create_pdf.py --title "Q3 Status" output/status.pdf\n'
        "ran python3 .skillgate/skills/pdf/scripts/create_pdf.py --title Q3 Status output/status.pdf exit=0"
    )
    steps, _errors, had_path = count_path_steps(None, transcript)
    assert had_path is True
    assert steps >= 1


def test_llm_harness_auto_runs_agent_entry_when_model_omits_run(monkeypatch, tmp_path) -> None:
    import shutil

    from skillgate_ai.harness import Completion, LLMHarness
    from skillgate_ai.ingest import ingest_skill
    from skillgate_ai.sandbox import LocalSandbox
    from skillgate_ai.usage import Usage

    pack = tmp_path / "sample-skill"
    shutil.copytree(Path(__file__).resolve().parents[1] / "skills" / "sample-skill", pack)
    skill = ingest_skill(pack, strict=False)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    dest_skill = workspace / ".skillgate" / "skills" / "sample-skill"
    dest_skill.mkdir(parents=True)
    shutil.copytree(pack, dest_skill, dirs_exist_ok=True)
    (workspace / ".skillgate" / "selected.json").write_text(
        '{"skill": "sample-skill"}', encoding="utf-8"
    )
    harness = LLMHarness(_cfg(openai_api_key="sk-test"))
    prompt = "Write output/commit.txt for a cart fix diff in cart.py"

    def fake_complete(act_prompt, timeout_sec):
        del act_prompt, timeout_sec
        return Completion(
            text="fix: handle empty cart total",
            usage=Usage(tokens_in=1, tokens_out=1),
        )

    monkeypatch.setattr(harness, "_complete", fake_complete)
    sandbox = LocalSandbox(workspace)
    result = harness.run(sandbox, prompt, [skill], timeout_sec=5)
    assert (workspace / "output" / "commit.txt").is_file()
    assert "auto-ran agent_entry" in result.transcript
    assert any(span.get("name") == "tool.shell" for span in result.spans)


def test_llm_harness_records_run_commands_as_spans(monkeypatch, tmp_path) -> None:
    from skillgate_ai.harness import Completion, LLMHarness
    from skillgate_ai.ingest import ingest_skill
    from skillgate_ai.sandbox import LocalSandbox
    from skillgate_ai.usage import Usage

    pack = tmp_path / "pdf"
    import shutil

    shutil.copytree(Path(__file__).resolve().parents[1] / "skills" / "pdf", pack)
    scripts = pack / "scripts"
    scripts.mkdir(exist_ok=True)
    (scripts / "create_pdf.py").write_text("print('ok')\n", encoding="utf-8")
    skill = ingest_skill(pack, strict=False)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    dest_skill = workspace / ".skillgate" / "skills" / "pdf"
    dest_skill.mkdir(parents=True)
    shutil.copytree(pack, dest_skill, dirs_exist_ok=True)
    (workspace / ".skillgate" / "selected.json").write_text(
        '{"skill": "pdf"}', encoding="utf-8"
    )

    harness = LLMHarness(_cfg(openai_api_key="sk-test"))

    def fake_complete(prompt, timeout_sec):
        del prompt, timeout_sec
        return Completion(
            text='RUN: python3 .skillgate/skills/pdf/scripts/create_pdf.py output/out.pdf',
            usage=Usage(tokens_in=1, tokens_out=1),
        )

    monkeypatch.setattr(harness, "_complete", fake_complete)
    sandbox = LocalSandbox(workspace)
    result = harness.run(sandbox, "Make a PDF", [skill], timeout_sec=5)
    assert result.spans
    names = [span.get("name") for span in result.spans]
    assert "skill.select" in names
    assert any(str(name).startswith("tool.") for name in names)
    steps, _errors, had_path = count_path_steps(result.spans, result.transcript)
    assert had_path is True
    assert steps >= 1
