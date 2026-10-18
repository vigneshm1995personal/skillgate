"""Checks are scored only by decision models. No chat or Responses judge."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from skillgate_ai.config import LLMConfig
from skillgate_ai.errors import MissingLLMKeyError, SkillGateError
from skillgate_ai.judge import SkipJudge, resolve_judge
from skillgate_ai.judge_openai import OutcomeJudge, make_openai_judge
from skillgate_ai.judge_settings import load_judge_settings, save_judge_settings
from skillgate_ai.openai_http import post_openai_json
from skillgate_ai.suite import FileExpect, ScorerSpec, TaskSpec
from skillgate_ai.workspace_outputs import collect_workspace_outputs

ROOT = Path(__file__).resolve().parents[1]
_JUDGE_SOURCES = (
    ROOT / "src" / "skillgate_ai" / "judge.py",
    ROOT / "src" / "skillgate_ai" / "judge_openai.py",
    ROOT / "src" / "skillgate_ai" / "judge_providers" / "jev.py",
    ROOT / "src" / "skillgate_ai" / "judge_providers" / "clef.py",
    ROOT / "src" / "skillgate_ai" / "openai_http.py",
)
_BANNED_FRAGMENTS = ("/responses", "/chat/completions", "/v1/chat")
_PASS = {
    "task_completion": "Fully completed",
    "correctness": "Correct",
    "instruction_adherence": "Fully followed",
    "evidence_action_validity": "Fully supported",
    "result_quality": "Clear and complete",
    "path_efficiency": "Efficient",
}


def _cfg(**overrides: object) -> LLMConfig:
    fields: dict[str, object] = {
        "cursor_api_key": None,
        "gateway_api_key": None,
        "gateway_base_url": "https://api.openai.com/v1",
        "gateway_model": "openai/gpt-4o-mini",
        "anthropic_api_key": None,
        "anthropic_model": "claude-sonnet-4-20250514",
        "cursor_agent_bin": "agent",
        "claude_bin": "claude",
        "codex_api_key": None,
        "codex_bin": "codex",
        "harness_pref": "auto",
        "sandbox_pref": "local",
        "docker_image": "skillgate-sandbox:v0",
        "openai_api_key": None,
    }
    fields.update(overrides)
    return LLMConfig(**fields)  # type: ignore[arg-type]


class _Recorder:
    def __init__(self) -> None:
        self.urls: list[str] = []

    def __call__(self, url, headers=None, json=None, timeout=None, content=None):
        del headers, json, timeout, content
        self.urls.append(str(url))
        raise AssertionError(f"judge HTTP is not allowed in this test: {url}")


def test_auto_does_not_select_a_judge_when_keys_exist() -> None:
    recorder = _Recorder()
    with pytest.raises(SkillGateError) as caught:
        resolve_judge(
            _cfg(
                openai_api_key="sk-test",
                gateway_api_key="gw-test",
                jev_api_key="jev-test",
                clef_api_key="cf-token",
                gateway_base_url="https://ai-gateway.vercel.sh/v1",
            ),
            harness_name="cursor-agent",
        )
    message = caught.value.message.lower()
    assert "pick a decision model" in message
    assert "openai" not in message
    assert "jev" not in message
    assert "clef" not in message
    assert recorder.urls == []


def test_unconfigured_live_check_fails_and_names_no_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """A live check with no decision model fails. It does not skip or call a chat model."""
    recorder = _Recorder()
    monkeypatch.setattr("skillgate_ai.openai_http.httpx.post", recorder)
    for overrides in (
        {},
        {"judge_pref": "auto"},
        {"judge_pref": "skip"},
        {"judge_provider": "auto", "judge_chosen": False, "openai_api_key": "sk-test"},
        {"judge_backend": "responses", "openai_api_key": "sk-test", "judge_pref": "openai"},
    ):
        with pytest.raises(SkillGateError) as caught:
            resolve_judge(_cfg(**overrides), harness_name="cursor-agent")
        text = f"{caught.value.message} {caught.value.hint or ''}".lower()
        assert "decision model" in text
        assert "fallback" not in text
    assert recorder.urls == []


def test_openai_responses_backend_does_not_post(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = _Recorder()
    monkeypatch.setattr("skillgate_ai.openai_http.httpx.post", recorder)
    with pytest.raises(SkillGateError) as caught:
        make_openai_judge(api_key="sk-test", backend="responses", post=recorder)
    assert "decision model" in caught.value.message.lower()
    assert "not judges" in caught.value.message.lower()
    assert recorder.urls == []
    with pytest.raises(SkillGateError):
        resolve_judge(
            _cfg(openai_api_key="sk-test", judge_pref="openai", judge_backend="responses"),
            harness_name="cursor-agent",
        )
    assert recorder.urls == []


def test_removed_providers_do_not_post(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = _Recorder()
    monkeypatch.setattr("skillgate_ai.openai_http.httpx.post", recorder)
    for provider in ("other", "compatible", "aws"):
        with pytest.raises(SkillGateError) as caught:
            resolve_judge(
                _cfg(
                    judge_provider=provider,
                    judge_chosen=True,
                    openai_api_key="sk-test",
                    gateway_api_key="gw-test",
                    aws_access_key_id="AKIATEST",
                    aws_secret_access_key="secret",
                    judge_region="us-east-1",
                    judge_endpoint="https://openrouter.ai/api/v1",
                    judge_provider_model="openai/gpt-4o-mini",
                ),
                harness_name="cursor-agent",
            )
        assert "removed" in caught.value.message.lower()
        assert "openai" not in caught.value.message.lower()
        assert "jev" not in caught.value.message.lower()
    assert recorder.urls == []


def test_openai_missing_key_ignores_gateway() -> None:
    with pytest.raises(MissingLLMKeyError) as caught:
        resolve_judge(
            _cfg(
                gateway_api_key="gw-test",
                judge_pref="openai",
                gateway_base_url="https://ai-gateway.vercel.sh/v1",
            ),
            harness_name="cursor-agent",
        )
    assert "API key" in caught.value.message
    assert "OpenAI" not in caught.value.message
    assert "gateway" not in caught.value.message.lower()


def test_jev_missing_key_does_not_use_openai() -> None:
    with pytest.raises(MissingLLMKeyError) as caught:
        resolve_judge(
            _cfg(
                openai_api_key="sk-test",
                gateway_api_key="gw-test",
                judge_provider="jev",
                judge_chosen=True,
                judge_endpoint="https://openrouter.ai/api/v1",
            ),
            harness_name="cursor-agent",
        )
    assert "API key" in caught.value.message
    assert "Jev" not in caught.value.message
    assert "OpenAI" not in caught.value.message


def test_explain_fail_does_not_post() -> None:
    calls: list[str] = []

    def post(url, headers=None, json=None, timeout=None):
        del headers, json, timeout
        calls.append(str(url))

        class _Response:
            status_code = 200
            text = "{}"

            def json(self):
                return {"model": "gpt-6-luna", "answers": []}

        return _Response()

    judge = make_openai_judge(api_key="sk-test", why_enabled=True, post=post)
    assert judge.explain_fail(["the file was wrong"]) is None
    assert calls == []
    assert judge.supports_why is False


def test_post_openai_json_refuses_chat_and_responses() -> None:
    for url in (
        "https://api.openai.com/v1/responses",
        "https://api.openai.com/v1/chat/completions",
        "https://example.test/v1/chat",
    ):
        with pytest.raises(SkillGateError) as caught:
            post_openai_json(
                url,
                api_key="sk-test",
                payload={"model": "gpt-6-luna"},
                timeout_sec=1,
                model="gpt-6-luna",
            )
        assert "decision model" in caught.value.message.lower()


def test_judge_sources_do_not_call_chat_or_responses() -> None:
    assert not (ROOT / "src" / "skillgate_ai" / "judge_providers" / "compatible.py").exists()
    assert not (ROOT / "src" / "skillgate_ai" / "judge_providers" / "aws.py").exists()
    guard = (ROOT / "src" / "skillgate_ai" / "openai_http.py").read_text(encoding="utf-8")
    for fragment in _BANNED_FRAGMENTS:
        assert guard.count(fragment) == 1
    for path in _JUDGE_SOURCES:
        if path.name == "openai_http.py":
            continue
        text = path.read_text(encoding="utf-8")
        for fragment in _BANNED_FRAGMENTS:
            assert fragment not in text, f"{path.name} contains {fragment}"
        assert "StructuredOutputsBackend" not in text
        assert "CompatibleBackend" not in text


def test_clef_posts_workers_ai_decision_endpoint() -> None:
    from skillgate_ai.judge_providers.clef import ClefBackend
    from skillgate_ai.judge_spec import resolve_judge_spec

    calls: list[dict] = []

    def post(url, headers=None, json=None, timeout=None):
        del headers, timeout
        calls.append({"url": str(url), "json": json or {}})

        class _Response:
            status_code = 200
            text = ""

            def json(self):
                answers = {
                    key: {"choice": value, "confidence": 0.91} for key, value in _PASS.items()
                }
                return {
                    "success": True,
                    "result": {"model": "clef", "answers": answers, "usage": {}},
                }

        return _Response()

    judge = resolve_judge(
        _cfg(
            clef_api_key="cf-token",
            judge_provider="clef",
            judge_chosen=True,
            judge_account_id="abc123",
            judge_provider_model="clef",
        ),
        harness_name="cursor-agent",
    )
    assert isinstance(judge, OutcomeJudge)
    judge.backend._post = post  # type: ignore[attr-defined]
    judged = judge.judge(
        "goal",
        [],
        "tail",
        spec=resolve_judge_spec(),
        path={"had_path": True, "steps": 1},
    )
    assert judged["passed"] is True
    assert len(calls) == 1
    url = calls[0]["url"]
    assert url == (
        "https://api.cloudflare.com/client/v4/accounts/abc123/ai/run/@cf/cloudflare/clef"
    )
    body = calls[0]["json"]
    assert body["model"] == "clef"
    assert isinstance(body["questions"], dict)
    assert "task_completion" in body["questions"]
    assert "/responses" not in url
    assert "/chat" not in url
    assert isinstance(judge.backend, ClefBackend)


def test_clef_flash_uses_flash_slug() -> None:
    from skillgate_ai.judge_providers.clef import ClefBackend

    calls: list[str] = []

    def post(url, headers=None, json=None, timeout=None):
        del headers, json, timeout
        calls.append(str(url))

        class _Response:
            status_code = 200

            def json(self):
                return {"success": True, "result": {"answers": {}}}

        return _Response()

    backend = ClefBackend(
        api_key="cf-token",
        account_id="abc123",
        model="clef-flash",
        post=post,
    )
    result = backend.ping()
    assert result["ok"] is True
    assert result["message"] == "Connected to the judge."
    assert "cloudflare" not in result["message"].lower()
    assert "clef" not in result["message"].lower()
    assert calls == [
        "https://api.cloudflare.com/client/v4/accounts/abc123/ai/run/@cf/cloudflare/clef-flash"
    ]


def test_clef_missing_token_or_account_fails_clearly() -> None:
    with pytest.raises(MissingLLMKeyError) as missing_key:
        resolve_judge(
            _cfg(judge_provider="clef", judge_chosen=True, judge_account_id="abc123"),
            harness_name="cursor-agent",
        )
    assert "API key" in missing_key.value.message
    assert "Clef" not in missing_key.value.message
    assert "Cloudflare" not in missing_key.value.message
    with pytest.raises(SkillGateError) as missing_account:
        resolve_judge(
            _cfg(clef_api_key="cf-token", judge_provider="clef", judge_chosen=True),
            harness_name="cursor-agent",
        )
    assert "account id" in missing_account.value.message.lower()
    assert "Clef" not in missing_account.value.message
    assert "Cloudflare" not in missing_account.value.message
    assert "--account-id" in missing_account.value.message


def test_clef_rejects_chat_base_url() -> None:
    from skillgate_ai.judge_providers.clef import ClefBackend

    backend = ClefBackend(
        api_key="cf-token",
        account_id="abc123",
        base_url="https://api.openai.com/v1/chat/completions",
    )
    with pytest.raises(SkillGateError) as caught:
        backend.ping()
    assert "decision model" in caught.value.message.lower()


def test_a_new_decision_endpoint_plugs_in_and_chat_ids_do_not(tmp_path: Path) -> None:
    from skillgate_ai.judge_providers.decision import (
        DecisionEndpoint,
        register_decision_endpoint,
        unregister_decision_endpoint,
    )

    class _Direct:
        name = "northstar"
        model = "northstar-1"

        def evaluate(self, *, state, images, timeout_sec, spec=None):
            del state, images, timeout_sec, spec
            return {"status": "ok", "model": self.model, "answers": {}}

        def ping(self, *, timeout_sec: float = 20.0):
            del timeout_sec
            return {"ok": True, "message": "Connected to the judge."}

    def build(cfg: LLMConfig) -> OutcomeJudge:
        del cfg
        return OutcomeJudge(_Direct(), provider="northstar", display_name="the judge")

    register_decision_endpoint(DecisionEndpoint("northstar", build))
    try:
        judge = resolve_judge(
            _cfg(judge_provider="northstar", judge_chosen=True),
            harness_name="cursor-agent",
        )
        assert isinstance(judge, OutcomeJudge)
        assert judge.name == "northstar"
        assert judge.backend.name == "northstar"
        saved = save_judge_settings(tmp_path, provider="northstar")
        assert saved.provider == "northstar"
        for banned in ("chat", "responses", "completions", "structured", "aws"):
            with pytest.raises(SkillGateError):
                register_decision_endpoint(DecisionEndpoint(banned, build))

        class _Chat:
            name = "responses"
            model = "chat-model"

            def evaluate(self, *, state, images, timeout_sec, spec=None):
                del state, images, timeout_sec, spec
                return {}

            def ping(self, *, timeout_sec: float = 20.0):
                del timeout_sec
                return {"ok": True, "message": "no"}

        with pytest.raises(SkillGateError) as wrapped:
            OutcomeJudge(_Chat(), provider="responses")
        assert "not judges" in wrapped.value.message.lower()
    finally:
        unregister_decision_endpoint("northstar")
    with pytest.raises(SkillGateError) as gone:
        resolve_judge(
            _cfg(judge_provider="northstar", judge_chosen=True),
            harness_name="cursor-agent",
        )
    assert "decision model" in gone.value.message.lower()


def test_save_rejects_removed_providers_and_keeps_clef_account(tmp_path: Path) -> None:
    with pytest.raises(SkillGateError) as other:
        save_judge_settings(tmp_path, provider="other", base_url="https://example.test")
    assert "removed" in other.value.message.lower()
    with pytest.raises(SkillGateError) as aws:
        save_judge_settings(tmp_path, provider="aws", region="us-east-1")
    assert "removed" in aws.value.message.lower()
    saved = save_judge_settings(
        tmp_path,
        provider="clef",
        model="clef",
        account_id="abc123",
    )
    assert saved.provider == "clef"
    assert saved.account_id == "abc123"
    raw = (tmp_path / ".skillgate" / "judge").read_text(encoding="utf-8")
    assert "abc123" in raw
    loaded = load_judge_settings(tmp_path)
    assert loaded.provider == "clef"
    assert loaded.account_id == "abc123"
    stale = tmp_path / "stale"
    dest = stale / ".skillgate"
    dest.mkdir(parents=True)
    (dest / "judge").write_text(json.dumps({"provider": "compatible"}), encoding="utf-8")
    assert load_judge_settings(stale).provider == "compatible"


def test_workspace_capture_skips_pydeps(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    (ws / "reports").mkdir(parents=True)
    (ws / "reports" / "final.txt").write_text("wanted", encoding="utf-8")
    for name in (".pydeps", "pydeps", "__pypackages__"):
        folder = ws / name / "pkg"
        folder.mkdir(parents=True)
        (folder / "mod.py").write_text("dep", encoding="utf-8")
    task = TaskSpec(
        id="t",
        prompt="write the report",
        expect_skill="s",
        scorers=[
            ScorerSpec(
                type="task_completion",
                files=[FileExpect(path="reports/final.txt")],
            )
        ],
    )
    paths = [str(row["path"]) for row in collect_workspace_outputs(task, ws)]
    blob = " ".join(paths)
    assert ".pydeps" not in blob
    assert "pydeps" not in blob
    assert "__pypackages__" not in blob
    assert "reports/final.txt" in paths
