from __future__ import annotations

import os
from pathlib import Path

import pytest

from skillgate_ai.config import LLMConfig, get_llm_config
from skillgate_ai.errors import MissingLLMKeyError, SkillGateError
from skillgate_ai.judge import SkipJudge, resolve_judge
from skillgate_ai.judge_openai import DecisionsBackend, OutcomeJudge, make_openai_judge
from skillgate_ai.judge_providers.jev import JevBackend
from skillgate_ai.judge_settings import save_judge_settings
from skillgate_ai.judge_spec import resolve_judge_spec
from skillgate_ai.keys import reset_key_env_bindings


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


class FakeResponse:
    def __init__(self, status_code: int, payload: object | None = None) -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self) -> object:
        return self._payload


def test_auto_with_only_cursor_key_skips() -> None:
    judge = resolve_judge(_cfg(cursor_api_key="cur-test"), harness_name="cursor-agent")
    assert isinstance(judge, SkipJudge)


def test_explicit_aws_without_key_exits_2() -> None:
    with pytest.raises(SkillGateError) as caught:
        resolve_judge(
            _cfg(judge_provider="aws", judge_chosen=True, judge_region="us-east-1"),
            harness_name="cursor-agent",
        )
    assert caught.value.exit_code == 2
    assert "removed" in caught.value.message.lower()
    assert "OPENAI" not in caught.value.message


def test_aws_without_region_exits_2() -> None:
    with pytest.raises(SkillGateError) as caught:
        resolve_judge(
            _cfg(
                judge_provider="aws",
                judge_chosen=True,
                aws_access_key_id="AKIATEST",
                aws_secret_access_key="secret",
            ),
            harness_name="cursor-agent",
        )
    assert caught.value.exit_code == 2
    assert "removed" in caught.value.message.lower()


def test_aws_ignores_ambient_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIAAAMBIENT")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "ambient-secret")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "ambient-token")
    monkeypatch.setenv("AWS_PROFILE", "default")
    reset_key_env_bindings()
    cfg = get_llm_config(tmp_path)
    assert cfg.aws_access_key_id is None
    assert cfg.aws_secret_access_key is None


def test_openai_key_not_reused_for_jev() -> None:
    with pytest.raises(MissingLLMKeyError) as caught:
        resolve_judge(
            _cfg(
                openai_api_key="sk-openai",
                judge_provider="jev",
                judge_chosen=True,
                judge_endpoint="https://example.test",
            ),
            harness_name="cursor-agent",
        )
    assert "Jev" in caught.value.message


def test_jev_scores_extra_questions_and_a_low_answer_fails() -> None:
    ask = "Totals match?"
    spec = resolve_judge_spec(
        pack={
            "extra_questions": [
                {
                    "id": "numbers_match",
                    "type": "predicate",
                    "ask": ask,
                    "pass_if": {"gte": 0.8},
                }
            ]
        }
    )
    posted: list[dict] = []

    def post(url, headers=None, json=None, timeout=None):
        del url, headers, timeout
        posted.append(json or {})
        mapping = {
            "task_completion": "Fully completed",
            "correctness": "Correct",
            "instruction_adherence": "Fully followed",
            "evidence_action_validity": "Fully supported",
            "result_quality": "Clear and complete",
            "path_efficiency": "Efficient",
        }
        answers = [{"name": key, "choice": value} for key, value in mapping.items()]
        answers.append({"name": "numbers_match", "noul": 0.1})
        return FakeResponse(200, {"answers": answers, "model": "jev"})

    backend = JevBackend(api_key="jev-key", base_url="https://jev.example/v1", post=post)
    judged = OutcomeJudge(
        backend,
        display_name="Jev",
        provider="jev",
        chosen=True,
        supports_why=False,
        supports_confidence=False,
    ).judge("goal", [], "tail", spec=spec, path={"had_path": True, "steps": 2})
    names = [row["name"] for row in posted[0]["questions"]]
    assert "numbers_match" in names
    assert judged["status"] == "completed"
    assert judged["passed"] is False
    assert judged.get("extra_failures") == [f"{ask} No"]
    assert judged["cells"]["numbers_match"]["choice"] == "No"
    assert judged["warnings"] == []
    assert judged.get("why") is None


def test_scoring_rejection_names_payload_size() -> None:
    from skillgate_ai.judge_openai import _state_text

    state = {
        "check_prompt": "write the report",
        "artifacts": [
            {"path": "reports/final.txt", "present": True, "body": "wanted"},
            {"path": "scratch/extra.txt", "present": True, "body": "n" * 4000},
        ],
    }
    nbytes = len(_state_text(state).encode("utf-8"))

    def post(url, headers=None, json=None, timeout=None):
        del headers, json, timeout
        assert str(url).endswith("/decisions")
        return FakeResponse(413, {"error": {"message": "payload too large"}})

    backend = DecisionsBackend(api_key="sk-test", post=post)
    result = backend.evaluate(state=state, images=[], timeout_sec=5)
    reason = str(result.get("reason") or "")
    assert result["status"] == "error"
    assert str(nbytes) in reason
    assert "2 files" in reason

    def post_bad(url, headers=None, json=None, timeout=None):
        del url, headers, json, timeout
        return FakeResponse(400, {"error": {"message": "rejected"}})

    bad = DecisionsBackend(api_key="sk-test", post=post_bad).evaluate(
        state=state, images=[], timeout_sec=5
    )
    assert str(nbytes) not in str(bad.get("reason") or "")


def test_removed_provider_does_not_post(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def post(url, headers=None, json=None, timeout=None):
        del headers, json, timeout
        calls.append(str(url))
        return FakeResponse(200, {})

    monkeypatch.setattr("skillgate_ai.openai_http.httpx.post", post)
    for provider in ("other", "compatible", "aws"):
        with pytest.raises(SkillGateError) as caught:
            resolve_judge(
                _cfg(
                    judge_provider=provider,
                    judge_chosen=True,
                    openai_api_key="sk-test",
                    gateway_api_key="gw-test",
                ),
                harness_name="cursor-agent",
            )
        assert "removed" in caught.value.message.lower()
    assert calls == []


def test_provider_test_401_omits_secret() -> None:
    def post(url, headers=None, json=None, timeout=None):
        del url, json, timeout, headers
        return FakeResponse(401, {"error": {"message": "nope sk-secret"}})

    backend = make_openai_judge(api_key="sk-secret", post=post).backend
    from skillgate_ai.judge_openai import ping_openai_backend

    result = ping_openai_backend(backend, display_name="the judge")
    assert result["ok"] is False
    assert "sk-secret" not in str(result)
    assert "did not accept this API key" in result["message"]


def test_jev_module_is_not_jev_qa() -> None:
    import skillgate_ai.judge_providers.jev as jev

    assert jev.__name__ == "skillgate_ai.judge_providers.jev"
    assert not hasattr(jev, "run_jev_outcome_judge")


def test_aws_backend_does_not_read_environ(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIAAAMBIENT")
    calls: list[str] = []

    def post(url, headers=None, json=None, content=None, timeout=None):
        del headers, json, content, timeout
        calls.append(str(url))
        return FakeResponse(200, {})

    monkeypatch.setattr("skillgate_ai.openai_http.httpx.post", post)
    with pytest.raises(SkillGateError) as caught:
        resolve_judge(
            _cfg(
                judge_provider="aws",
                judge_chosen=True,
                aws_access_key_id="AKIATEST",
                aws_secret_access_key="vault-secret",
                judge_region="us-west-2",
                judge_provider_model="amazon.nova-lite",
            ),
            harness_name="cursor-agent",
        )
    assert "removed" in caught.value.message.lower()
    assert calls == []
    assert os.environ.get("AWS_ACCESS_KEY_ID") == "AKIAAAMBIENT"


def test_decisions_extra_choice_is_visible() -> None:
    spec = resolve_judge_spec(
        pack={
            "extra_questions": [
                {
                    "id": "totals_match",
                    "type": "choice",
                    "ask": "Do the totals match?",
                    "choices": [{"value": "yes", "pass": True}, {"value": "no"}],
                }
            ]
        }
    )

    def post(url, headers=None, json=None, timeout=None):
        del url, headers, timeout
        answers = [
            {"name": "task_completion", "choice": "Fully completed"},
            {"name": "correctness", "choice": "Correct"},
            {"name": "instruction_adherence", "choice": "Fully followed"},
            {"name": "evidence_action_validity", "choice": "Fully supported"},
            {"name": "result_quality", "choice": "Clear and complete"},
            {"name": "path_efficiency", "choice": "Efficient"},
            {"name": "totals_match", "choice": "yes"},
        ]
        return FakeResponse(200, {"answers": answers, "model": "gpt-6-luna"})

    backend = DecisionsBackend(api_key="sk-test", post=post)
    judged = OutcomeJudge(
        backend,
        display_name="the judge",
        provider="openai",
        chosen=True,
        supports_why=False,
        supports_confidence=True,
    ).judge("goal", [], "tail", spec=spec, path={"had_path": True, "steps": 1})
    assert judged["status"] == "completed"
    assert judged["cells"]["totals_match"]["choice"] == "yes"
    assert judged["answers"]["totals_match"]["choice"] == "yes"


def test_decisions_extra_predicate_is_visible() -> None:
    spec = resolve_judge_spec(
        pack={
            "extra_questions": [
                {
                    "id": "totals_ok",
                    "type": "predicate",
                    "ask": "Are the totals OK?",
                }
            ]
        }
    )

    def post(url, headers=None, json=None, timeout=None):
        del url, headers, timeout
        answers = [
            {"name": "task_completion", "choice": "Fully completed"},
            {"name": "correctness", "choice": "Correct"},
            {"name": "instruction_adherence", "choice": "Fully followed"},
            {"name": "evidence_action_validity", "choice": "Fully supported"},
            {"name": "result_quality", "choice": "Clear and complete"},
            {"name": "path_efficiency", "choice": "Efficient"},
            {"name": "totals_ok", "noul": 0.91},
        ]
        return FakeResponse(200, {"answers": answers, "model": "gpt-6-luna"})

    backend = DecisionsBackend(api_key="sk-test", post=post)
    judged = OutcomeJudge(
        backend,
        display_name="the judge",
        provider="openai",
        chosen=True,
        supports_why=False,
        supports_confidence=False,
    ).judge("goal", [], "tail", spec=spec, path={"had_path": True, "steps": 1})
    assert judged["status"] == "completed"
    assert judged["answers"]["totals_ok"]["probability"] == 0.91
    assert judged["cells"]["totals_ok"]["probability"] == 0.91


def test_save_provider_marks_chosen(tmp_path: Path) -> None:
    settings = save_judge_settings(tmp_path, provider="openai")
    assert settings.chosen is True
    assert settings.provider == "openai"


_PASS_CHOICES = {
    "task_completion": "Fully completed",
    "correctness": "Correct",
    "instruction_adherence": "Fully followed",
    "evidence_action_validity": "Fully supported",
    "result_quality": "Clear and complete",
    "path_efficiency": "Efficient",
}
_OPENROUTER_DECISIONS = "https://openrouter.ai/api/alpha/decisions"
_PROVIDER_NAMES = ("jev", "openai", "openrouter", "aws")


def _assert_no_provider_name(text: str) -> None:
    lowered = text.lower()
    for name in _PROVIDER_NAMES:
        assert name not in lowered, text


def _capture_post(status: int, payload: object, calls: list[dict]):
    def post(url, headers=None, json=None, timeout=None):
        del headers, timeout
        calls.append({"url": url, "json": json or {}})
        return FakeResponse(status, payload)

    return post


def test_resolve_judge_passes_saved_jev_model_and_base_url() -> None:
    judge = resolve_judge(
        _cfg(
            jev_api_key="jev-key",
            judge_provider="jev",
            judge_chosen=True,
            judge_endpoint="https://openrouter.ai/api/v1",
            judge_provider_model="typesafe/jev-1.14",
        ),
        harness_name="cursor-agent",
    )
    assert isinstance(judge, OutcomeJudge)
    assert judge.backend.model == "typesafe/jev-1.14"
    assert judge.backend.base_url == "https://openrouter.ai/api/v1"


def test_jev_openrouter_posts_decisions_with_saved_model() -> None:
    calls: list[dict] = []
    backend = JevBackend(
        api_key="jev-key",
        base_url="https://openrouter.ai/api/v1/",
        model="typesafe/jev-1.14",
        post=_capture_post(200, {"model": "typesafe/jev-1.14", "answers": {}}, calls),
    )
    result = backend.ping()
    assert result["ok"] is True
    _assert_no_provider_name(result["message"])
    assert calls[0]["url"] == _OPENROUTER_DECISIONS
    body = calls[0]["json"]
    assert body["model"] == "typesafe/jev-1.14"
    assert body["state"] == "ping"
    assert "input" not in body
    question = body["questions"]["connection_test"]
    assert question["type"] == "noul"
    assert set(question["criteria"]) == {"true", "false"}
    assert len(calls) == 1


def test_jev_other_base_url_still_posts_evaluate() -> None:
    calls: list[dict] = []
    backend = JevBackend(
        api_key="jev-key",
        base_url="https://jev.example/v1",
        model="typesafe-ai/jev",
        post=_capture_post(200, {"model": "typesafe-ai/jev", "answers": []}, calls),
    )
    result = backend.ping()
    assert result["ok"] is True
    assert calls[0]["url"] == "https://jev.example/v1/evaluate"
    body = calls[0]["json"]
    assert body["model"] == "typesafe-ai/jev"
    assert body["input"] == "ping"
    assert isinstance(body["questions"], list)
    assert "state" not in body


def test_jev_openrouter_parses_choice_answers() -> None:
    calls: list[dict] = []

    def post(url, headers=None, json=None, timeout=None):
        del headers, timeout
        calls.append({"url": url, "json": json or {}})
        answers = {
            key: {
                "type": "choice",
                "choice": value,
                "confidence": 0.91,
                "probabilities": {value: 0.91},
            }
            for key, value in _PASS_CHOICES.items()
        }
        return FakeResponse(200, {"model": "typesafe/jev-1.14", "answers": answers})

    backend = JevBackend(
        api_key="jev-key",
        base_url="https://openrouter.ai/api/v1",
        model="typesafe/jev-1.14",
        post=post,
    )
    judged = OutcomeJudge(
        backend,
        display_name="the judge",
        provider="jev",
        chosen=True,
        supports_why=False,
        supports_confidence=False,
    ).judge("goal", [], "tail", spec=resolve_judge_spec(), path={"had_path": True, "steps": 1})
    assert calls[0]["url"] == _OPENROUTER_DECISIONS
    body = calls[0]["json"]
    assert body["model"] == "typesafe/jev-1.14"
    assert isinstance(body["state"], str) and body["state"]
    task = body["questions"]["task_completion"]
    assert task["type"] == "choice"
    assert "Fully completed" in task["criteria"]
    assert judged["status"] == "completed"
    assert judged["passed"] is True
    assert judged["answers"]["task_completion"]["choice"] == "Fully completed"
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("status", "code", "snippet"),
    [
        (404, None, "scoring endpoint"),
        (401, None, "api key"),
        (429, "insufficient_quota", "out of credits"),
    ],
)
def test_jev_errors_name_the_failure_not_a_provider(
    status: int, code: str | None, snippet: str
) -> None:
    calls: list[dict] = []
    error: dict[str, object] = {"message": "nope sk-secret"}
    if code:
        error["code"] = code
    backend = JevBackend(
        api_key="sk-secret",
        base_url="https://openrouter.ai/api/v1",
        model="typesafe/jev-1.14",
        post=_capture_post(status, {"error": error}, calls),
    )
    result = backend.ping()
    assert result["ok"] is False
    message = result["message"]
    assert snippet in message.lower()
    _assert_no_provider_name(message)
    assert "sk-secret" not in message
    assert [call["url"] for call in calls] == [_OPENROUTER_DECISIONS]
