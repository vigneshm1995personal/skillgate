from __future__ import annotations

import os
from pathlib import Path

import pytest

from skillgate_ai.config import LLMConfig, get_llm_config
from skillgate_ai.errors import MissingLLMKeyError, SkillGateError
from skillgate_ai.judge import SkipJudge, resolve_judge
from skillgate_ai.judge_openai import OutcomeJudge, make_openai_judge
from skillgate_ai.judge_providers.aws import AwsBackend
from skillgate_ai.judge_providers.compatible import CompatibleBackend
from skillgate_ai.judge_providers.jev import JEV_EXTRAS_NOTE, JevBackend
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
    judge = resolve_judge(_cfg(cursor_api_key="cur-test"), harness_name="llm")
    assert isinstance(judge, SkipJudge)


def test_explicit_aws_without_key_exits_2() -> None:
    with pytest.raises(MissingLLMKeyError) as caught:
        resolve_judge(
            _cfg(judge_provider="aws", judge_chosen=True, judge_region="us-east-1"),
            harness_name="llm",
        )
    assert caught.value.exit_code == 2
    assert "AWS" in caught.value.message
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
            harness_name="llm",
        )
    assert caught.value.exit_code == 2
    assert "region" in caught.value.message.lower()


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
            harness_name="llm",
        )
    assert "Jev" in caught.value.message


def test_jev_skips_extras_with_plain_note() -> None:
    spec = resolve_judge_spec(
        pack={
            "extra_questions": [
                {
                    "id": "numbers_match",
                    "type": "predicate",
                    "ask": "Totals match?",
                    "pass_if": {"gte": 0.8},
                }
            ]
        }
    )
    posted: list[dict] = []

    def post(url, headers=None, json=None, timeout=None):
        del url, headers, timeout
        posted.append(json or {})
        names = [row["name"] for row in (json or {}).get("questions") or []]
        answers = [
            {"name": name, "choice": "Fully completed" if name != "path_efficiency" else "Efficient"}
            for name in names
        ]
        # Map to pass-lock enums for built-ins.
        mapping = {
            "task_completion": "Fully completed",
            "correctness": "Correct",
            "instruction_adherence": "Fully followed",
            "evidence_action_validity": "Fully supported",
            "result_quality": "Clear and complete",
            "path_efficiency": "Efficient",
        }
        answers = [{"name": key, "choice": value} for key, value in mapping.items()]
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
    assert judged["status"] == "completed"
    assert JEV_EXTRAS_NOTE in judged["warnings"]
    assert "numbers_match" not in (posted[0].get("questions") or [{}])[0].get("name", "")
    names = [row["name"] for row in posted[0]["questions"]]
    assert "numbers_match" not in names
    assert judged.get("why") is None


def test_compatible_404_falls_back_without_confidence_warning() -> None:
    spec = resolve_judge_spec()
    calls: list[str] = []

    def post(url, headers=None, json=None, timeout=None):
        del headers, json, timeout
        calls.append(url)
        if url.endswith("/decisions"):
            return FakeResponse(404, {"error": {"message": "missing"}})
        mapping = {
            "task_completion": "Fully completed",
            "correctness": "Correct",
            "instruction_adherence": "Fully followed",
            "evidence_action_validity": "Fully supported",
            "result_quality": "Clear and complete",
            "path_efficiency": "Efficient",
        }
        return FakeResponse(
            200,
            {
                "output_text": __import__("json").dumps(mapping),
                "model": "compat",
            },
        )

    backend = CompatibleBackend(
        api_key="gw-key",
        base_url="https://compat.example/v1",
        post=post,
    )
    judged = OutcomeJudge(
        backend,
        display_name="Other",
        provider="compatible",
        chosen=True,
        supports_why=True,
        supports_confidence=False,
    ).judge("goal", [], "tail", spec=spec, path={"had_path": True, "steps": 1})
    assert judged["status"] == "completed"
    assert judged["warnings"] == []
    assert any(url.endswith("/decisions") for url in calls)
    assert any("/responses" in url for url in calls)


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
    seen: dict[str, str] = {}

    def post(url, headers=None, json=None, content=None, timeout=None):
        del json, content, timeout
        seen["url"] = url
        seen["auth"] = str((headers or {}).get("Authorization") or "")
        return FakeResponse(
            200,
            {
                "output": {
                    "message": {
                        "content": [
                            {
                                "toolUse": {
                                    "input": {
                                        "task_completion": "Fully completed",
                                        "correctness": "Correct",
                                        "instruction_adherence": "Fully followed",
                                        "evidence_action_validity": "Fully supported",
                                        "result_quality": "Clear and complete",
                                        "path_efficiency": "Efficient",
                                    }
                                }
                            }
                        ]
                    }
                }
            },
        )

    backend = AwsBackend(
        access_key="AKIATEST",
        secret_key="vault-secret",
        region="us-west-2",
        model="amazon.nova-lite",
        post=post,
    )
    judged = backend.evaluate(
        state={"check_prompt": "p", "path": {"had_path": True, "steps": 1}},
        images=[],
        timeout_sec=5,
    )
    assert judged["status"] == "completed"
    assert "us-west-2" in seen["url"]
    assert "AKIATEST" in seen["auth"]
    assert "AKIAAAMBIENT" not in seen["auth"]
    assert os.environ.get("AWS_ACCESS_KEY_ID") == "AKIAAAMBIENT"


def test_aws_encodes_colon_in_model_id() -> None:
    seen: dict[str, str] = {}

    def post(url, headers=None, json=None, content=None, timeout=None):
        del headers, json, content, timeout
        seen["url"] = url
        return FakeResponse(
            200,
            {
                "output": {
                    "message": {
                        "content": [
                            {
                                "toolUse": {
                                    "input": {
                                        "task_completion": "Fully completed",
                                        "correctness": "Correct",
                                        "instruction_adherence": "Fully followed",
                                        "evidence_action_validity": "Fully supported",
                                        "result_quality": "Clear and complete",
                                        "path_efficiency": "Efficient",
                                    }
                                }
                            }
                        ]
                    }
                }
            },
        )

    backend = AwsBackend(
        access_key="AKIATEST",
        secret_key="vault-secret",
        region="us-east-1",
        model="anthropic.claude-3-haiku-20240307-v1:0",
        post=post,
    )
    judged = backend.evaluate(
        state={"check_prompt": "p", "path": {"had_path": True, "steps": 1}},
        images=[],
        timeout_sec=5,
    )
    assert judged["status"] == "completed"
    assert "%3A0" in seen["url"]
    assert "v1:0" not in seen["url"]


def test_compatible_evaluate_uses_decisions_path() -> None:
    calls: list[str] = []

    def post(url, headers=None, json=None, timeout=None):
        del headers, json, timeout
        calls.append(url)
        return FakeResponse(
            200,
            {
                "answers": [
                    {"name": "task_completion", "choice": "Fully completed"},
                    {"name": "correctness", "choice": "Correct"},
                    {"name": "instruction_adherence", "choice": "Fully followed"},
                    {"name": "evidence_action_validity", "choice": "Fully supported"},
                    {"name": "result_quality", "choice": "Clear and complete"},
                    {"name": "path_efficiency", "choice": "Efficient"},
                ],
                "model": "compat",
            },
        )

    backend = CompatibleBackend(
        api_key="gw-key",
        base_url="https://compat.example/v1",
        decisions_path="/score",
        post=post,
    )
    judged = OutcomeJudge(
        backend,
        display_name="Other",
        provider="compatible",
        chosen=True,
        supports_why=True,
        supports_confidence=True,
    ).judge("goal", [], "tail", spec=resolve_judge_spec(), path={"had_path": True, "steps": 1})
    assert judged["status"] == "completed"
    assert any(url.endswith("/score") for url in calls)
    assert not any(url.rstrip("/").endswith("/decisions") for url in calls)


def test_aws_extra_choice_is_visible() -> None:
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

    def post(url, headers=None, json=None, content=None, timeout=None):
        del url, headers, json, content, timeout
        return FakeResponse(
            200,
            {
                "output": {
                    "message": {
                        "content": [
                            {
                                "toolUse": {
                                    "input": {
                                        "task_completion": "Fully completed",
                                        "correctness": "Correct",
                                        "instruction_adherence": "Fully followed",
                                        "evidence_action_validity": "Fully supported",
                                        "result_quality": "Clear and complete",
                                        "path_efficiency": "Efficient",
                                        "totals_match": "yes",
                                    }
                                }
                            }
                        ]
                    }
                }
            },
        )

    backend = AwsBackend(
        access_key="AKIATEST",
        secret_key="vault-secret",
        region="us-east-1",
        model="amazon.nova-lite",
        post=post,
    )
    judged = OutcomeJudge(
        backend,
        display_name="AWS",
        provider="aws",
        chosen=True,
        supports_why=True,
        supports_confidence=False,
    ).judge("goal", [], "tail", spec=spec, path={"had_path": True, "steps": 1})
    assert judged["status"] == "completed"
    assert judged["cells"]["totals_match"]["choice"] == "yes"
    assert judged["answers"]["totals_match"]["choice"] == "yes"


def test_aws_extra_predicate_is_visible() -> None:
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

    def post(url, headers=None, json=None, content=None, timeout=None):
        del url, headers, json, content, timeout
        return FakeResponse(
            200,
            {
                "output": {
                    "message": {
                        "content": [
                            {
                                "toolUse": {
                                    "input": {
                                        "task_completion": "Fully completed",
                                        "correctness": "Correct",
                                        "instruction_adherence": "Fully followed",
                                        "evidence_action_validity": "Fully supported",
                                        "result_quality": "Clear and complete",
                                        "path_efficiency": "Efficient",
                                        "totals_ok": 0.91,
                                    }
                                }
                            }
                        ]
                    }
                }
            },
        )

    backend = AwsBackend(
        access_key="AKIATEST",
        secret_key="vault-secret",
        region="us-east-1",
        model="amazon.nova-lite",
        post=post,
    )
    judged = OutcomeJudge(
        backend,
        display_name="AWS",
        provider="aws",
        chosen=True,
        supports_why=True,
        supports_confidence=False,
    ).judge("goal", [], "tail", spec=spec, path={"had_path": True, "steps": 1})
    assert judged["status"] == "completed"
    assert judged["answers"]["totals_ok"]["probability"] == 0.91
    assert judged["cells"]["totals_ok"]["probability"] == 0.91


def test_save_provider_marks_chosen(tmp_path: Path) -> None:
    settings = save_judge_settings(tmp_path, provider="openai")
    assert settings.chosen is True
    assert settings.provider == "openai"
