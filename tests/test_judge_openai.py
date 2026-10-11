from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from skillgate_ai.engine import _live_verdict, _maybe_explain_fail
from skillgate_ai.output_match import REASON_MISSING_OUTPUT, expected_output_mismatch_reason
from skillgate_ai.judge_bank import (
    CHECK_CELL_ORDER,
    LOW_CONFIDENCE_WARNING,
    PATH_NOT_AVAILABLE,
    UNUSABLE_ANSWER,
    decisions_questions,
)
from skillgate_ai.config import DEFAULT_GATEWAY_MODEL
from skillgate_ai.judge_openai import (
    DEFAULT_MODEL,
    DISPLAY_NAME,
    GATEWAY_DECISIONS_MODEL,
    IMAGE_MAX_BYTES,
    WHY_MAX_OUTPUT_TOKENS,
    WHY_OUTPUT_CHARS,
    collect_images,
    make_openai_judge,
    redact_secrets,
)

SECRET = "sk-test-secret-do-not-log"

PASS_CHOICES = {
    "task_completion": "Fully completed",
    "correctness": "Correct",
    "instruction_adherence": "Fully followed",
    "evidence_action_validity": "Fully supported",
    "result_quality": "Clear and complete",
    "path_efficiency": "Efficient",
}

PNG_1x1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)


class FakeResponse:
    def __init__(self, status_code: int, payload: object | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        if text:
            self.text = text
        elif payload is not None:
            self.text = json.dumps(payload)
        else:
            self.text = ""

    def json(self) -> object:
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class FakePost:
    def __init__(self, responses: list[object]) -> None:
        self.calls: list[dict] = []
        self._responses = list(responses)

    def __call__(self, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append(
            {"url": url, "headers": kwargs.get("headers"), "json": kwargs.get("json")}
        )
        if not self._responses:
            raise AssertionError(f"unexpected HTTP call: {url}")
        item = self._responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        assert isinstance(item, FakeResponse)
        return item


def decisions_payload(
    choices: dict[str, str] | None = None,
    *,
    confidence: float | None = 0.9,
    include_confidence: bool = True,
) -> dict:
    merged = {**PASS_CHOICES, **(choices or {})}
    answers = []
    for name, value in merged.items():
        row: dict = {
            "type": "choice",
            "name": name,
            "choice": value,
            "probabilities": [{"value": value, "probability": 0.91}],
        }
        if include_confidence and confidence is not None:
            row["confidence"] = confidence
        answers.append(row)
    return {"model": "gpt-6-luna", "answers": answers}


def why_payload(why: str = "The result did not match what was asked.") -> dict:
    return {"output_text": json.dumps({"why": why})}


def _judge(post: FakePost, *, backend: str = "decisions", why: bool = True):
    return make_openai_judge(
        api_key=SECRET,
        backend=backend,
        why_enabled=why,
        post=post,
    )


def _score(judge, **kwargs):
    artifacts = kwargs.pop("artifacts", [{"path": "out.txt", "present": True, "kind": "text"}])
    expect_skill = kwargs.pop("expect_skill", "pdf")
    selected_skill = kwargs.pop("selected_skill", "pdf")
    return judge.judge(
        "Extract the invoice total.",
        artifacts,
        "selected: pdf\n" + ("x" * 20),
        expect_skill=expect_skill,
        selected_skill=selected_skill,
        **kwargs,
    )


def _gated(judge, **kwargs):
    """Score cells, then apply the engine gate and Fail why-call.

    Returns ``(gate_passed, gate_failures, judged)``. Cell ``passed`` stays on
    ``judged``; the gate verdict is the first two values.
    """
    expect_skill = kwargs.get("expect_skill", "pdf")
    golden = kwargs.get("golden") if isinstance(kwargs.get("golden"), dict) else None
    actual = kwargs.get("actual_output") if isinstance(kwargs.get("actual_output"), dict) else None
    artifacts = kwargs.get("artifacts")
    if not isinstance(artifacts, list):
        artifacts = [{"path": "out.txt", "present": True, "kind": "text"}]
    judged = _score(judge, **kwargs)
    mismatch = expected_output_mismatch_reason(
        golden=golden,
        actual=actual,
        artifacts=artifacts,
    )
    passed, failures, stamped = _live_verdict(
        judged,
        expect_skill,
        det_passed=True,
        det_failures=[],
        mismatch=mismatch,
    )
    stamped = _maybe_explain_fail(
        judge,
        passed,
        failures,
        stamped,
        check="Extract the invoice total.",
        transcript_tail="selected: pdf\n" + ("x" * 20),
        expected_output=golden,
        actual_output=actual,
    )
    return passed, failures, stamped


def test_decisions_request_shape() -> None:
    post = FakePost([FakeResponse(200, decisions_payload())])
    judged = _score(_judge(post))
    assert judged["passed"] is True
    assert judged["backend"] == "decisions"
    assert judged["display_name"] == DISPLAY_NAME
    assert post.calls and post.calls[0]["url"].endswith("/v1/decisions")
    payload = post.calls[0]["json"]
    assert payload["model"] == "gpt-6-luna"
    assert set(payload.keys()) == {"model", "input", "questions"}
    questions = payload["questions"]
    assert len(questions) == 5
    assert all(item["type"] == "choice" for item in questions)
    names = [item["name"] for item in questions]
    assert "path_efficiency" not in names
    assert names == [item["name"] for item in decisions_questions(include_path=False)]
    task = next(item for item in questions if item["name"] == "task_completion")
    assert set(task.keys()) == {"type", "name", "instructions", "choices"}
    assert task["instructions"] == "Got the job done? Pick exactly one."
    assert [row["value"] for row in task["choices"]] == [
        "Fully completed",
        "Partially completed",
        "Not completed",
    ]
    assert set(task["choices"][0].keys()) == {"value", "description"}
    for item in questions:
        if item["name"] in CHECK_CELL_ORDER:
            assert item["instructions"].endswith("Pick exactly one.")
        assert "path.steps" not in item["instructions"]
    auth = post.calls[0]["headers"]["Authorization"]
    assert auth == f"Bearer {SECRET}"
    assert judged["answers"]["task_completion"]["choice"] == "Fully completed"
    assert judged["answers"]["task_completion"]["confidence"] == 0.9
    assert judged["answers"]["task_completion"]["probabilities"][0]["value"] == "Fully completed"
    assert judged["soft_answers"] == {}
    assert judged["cells"]["path_efficiency"]["choice"] is None
    assert judged["cells"]["path_efficiency"]["reason"] == PATH_NOT_AVAILABLE


def test_default_scoring_posts_decisions_not_the_task_model() -> None:
    """Direct and gateway scoring POST /decisions with luna; the task model never scores."""
    post = FakePost([FakeResponse(200, decisions_payload())])
    judged = _score(make_openai_judge(api_key="sk-test", post=post))
    assert judged["backend"] == "decisions"
    assert post.calls[0]["url"].endswith("/v1/decisions")
    assert post.calls[0]["json"]["model"] == DEFAULT_MODEL == "gpt-6-luna"
    assert post.calls[0]["json"]["model"] != DEFAULT_GATEWAY_MODEL

    post_gw = FakePost([FakeResponse(200, decisions_payload())])
    judged_gw = _score(
        make_openai_judge(
            api_key="gw-test",
            model=GATEWAY_DECISIONS_MODEL,
            base_url="https://ai-gateway.vercel.sh/v1",
            post=post_gw,
        )
    )
    assert judged_gw["backend"] == "decisions"
    assert post_gw.calls[0]["url"].endswith("/v1/decisions")
    assert post_gw.calls[0]["json"]["model"] == GATEWAY_DECISIONS_MODEL
    assert post_gw.calls[0]["json"]["model"] != DEFAULT_GATEWAY_MODEL

    post_task = FakePost([FakeResponse(200, decisions_payload())])
    _score(make_openai_judge(api_key="sk-test", model=DEFAULT_GATEWAY_MODEL, post=post_task))
    assert post_task.calls[0]["url"].endswith("/v1/decisions")
    assert post_task.calls[0]["json"]["model"] == "gpt-6-luna"
    assert post_task.calls[0]["json"]["model"] != DEFAULT_GATEWAY_MODEL


def test_fail_lock_does_not_fail_on_wasteful_path() -> None:
    post = FakePost(
        [
            FakeResponse(200, decisions_payload({"correctness": "Incorrect"})),
            FakeResponse(200, why_payload("The numbers were wrong.")),
        ]
    )
    passed, failures, judged = _gated(_judge(post))
    assert passed is False
    assert judged["passed"] is False
    assert any("Got it right?" in item for item in failures)
    assert judged["why"] == "The numbers were wrong."

    post2 = FakePost([FakeResponse(200, decisions_payload({"path_efficiency": "Wasteful"}))])
    judged2 = _score(_judge(post2), path={"steps": 4, "errors": 0, "had_path": True})
    assert judged2["passed"] is True
    assert judged2["soft_answers"]["path_efficiency"]["choice"] == "Wasteful"


def test_low_confidence_keeps_pass_and_warns() -> None:
    post = FakePost([FakeResponse(200, decisions_payload(confidence=0.2))])
    judged = _score(_judge(post))
    assert judged["status"] == "completed"
    assert judged["passed"] is True
    assert judged["warnings"] == [LOW_CONFIDENCE_WARNING]
    assert judged["answers"]["correctness"]["confidence"] == 0.2
    assert len(post.calls) == 1
    assert post.calls[0]["url"].endswith("/v1/decisions")


def test_missing_confidence_keeps_pass_and_warns() -> None:
    post = FakePost([FakeResponse(200, decisions_payload(include_confidence=False))])
    judged = _score(_judge(post))
    assert judged["passed"] is True
    assert judged["warnings"] == [LOW_CONFIDENCE_WARNING]


def test_unknown_choice_fails_closed() -> None:
    post = FakePost(
        [
            FakeResponse(200, decisions_payload({"correctness": "Pretty good"})),
            FakeResponse(200, why_payload("The scorer returned an answer we cannot use.")),
        ]
    )
    passed, _failures, judged = _gated(_judge(post))
    assert passed is False
    assert judged["status"] == "error"
    assert judged["passed"] is False
    assert judged["reasons"] == [UNUSABLE_ANSWER]
    assert judged["why"] == "The scorer returned an answer we cannot use."
    assert post.calls[1]["url"].endswith("/v1/responses")


def test_missing_answer_name_fails_closed() -> None:
    payload = decisions_payload()
    payload["answers"] = [row for row in payload["answers"] if row["name"] != "correctness"]
    post = FakePost(
        [
            FakeResponse(200, payload),
            FakeResponse(200, why_payload("A required score was missing.")),
        ]
    )
    passed, _failures, judged = _gated(_judge(post))
    assert passed is False
    assert judged["status"] == "error"
    assert judged["passed"] is False
    assert judged["reasons"] == [UNUSABLE_ANSWER]
    assert post.calls[0]["url"].endswith("/v1/decisions")
    assert post.calls[1]["url"].endswith("/v1/responses")


def test_http_errors_fail_and_never_log_key(caplog: pytest.LogCaptureFixture) -> None:
    cases = {
        401: "OpenAI did not accept this API key.",
        403: "OpenAI scoring is not enabled for this key.",
        404: "OpenAI has no scoring endpoint for this key.",
        400: "OpenAI rejected this scoring request.",
        429: "OpenAI rate limit or quota. Wait and retry, or check billing.",
    }
    for status, message in cases.items():
        copies = 3 if status == 429 else 1
        post = FakePost(
            [
                FakeResponse(
                    status,
                    {
                        "error": {
                            "message": f"Incorrect API key provided: sk-inval***test ({SECRET})",
                            "key": SECRET,
                        }
                    },
                )
            ]
            * copies
        )
        with caplog.at_level("WARNING"):
            passed, _failures, judged = _gated(_judge(post))
        assert passed is False
        assert judged["passed"] is False
        assert judged["status"] == "error"
        assert judged["reasons"] == [message]
        blob = json.dumps(judged) + caplog.text
        assert SECRET not in blob
        assert "sk-test" not in caplog.text
        assert "sk-inval" not in blob
        assert "Incorrect API key provided" not in caplog.text
        assert '"error"' not in caplog.text
        assert "insufficient_quota" not in caplog.text
        assert all(not str(item["url"]).endswith("/v1/responses") for item in post.calls)
        if status == 403:
            assert len(post.calls) == 1
            assert post.calls[0]["url"].endswith("/v1/decisions")


def test_redact_secrets_masks_full_and_partial_keys() -> None:
    leaked = "Incorrect API key provided: sk-inval***test. Also " + SECRET
    cleaned = redact_secrets(leaked, SECRET)
    assert SECRET not in cleaned
    assert "sk-inval" not in cleaned
    assert "sk-test" not in cleaned
    assert "sk-***" in cleaned


def test_quota_429_is_not_retried() -> None:
    post = FakePost(
        [
            FakeResponse(
                429,
                {
                    "error": {
                        "message": "You exceeded your current quota",
                        "type": "insufficient_quota",
                        "code": "insufficient_quota",
                    }
                },
            ),
            FakeResponse(200, decisions_payload()),
        ]
    )
    passed, failures, judged = _gated(_judge(post))
    assert passed is False
    assert judged["passed"] is False
    assert failures == [
        "Your OpenAI account is out of credits. Add credits at platform.openai.com "
        "billing, then try again."
    ]
    assert "rate limit" not in failures[0].lower()
    assert judged["why"] is None
    assert len(post.calls) == 1
    assert all(not str(item["url"]).endswith("/v1/responses") for item in post.calls)


def test_credit_balance_exhausted_429_is_not_retried() -> None:
    post = FakePost(
        [
            FakeResponse(
                429,
                {"error": {"code": "credit_balance_exhausted", "message": "no credits"}},
            ),
            FakeResponse(200, decisions_payload()),
        ]
    )
    passed, failures, judged = _gated(_judge(post))
    assert passed is False
    assert failures == [
        "Your OpenAI account is out of credits. Add credits at platform.openai.com "
        "billing, then try again."
    ]
    assert judged["why"] is None
    assert len(post.calls) == 1


def test_timeout_fails_closed() -> None:
    post = FakePost(
        [
            httpx.TimeoutException("slow"),
            FakeResponse(200, decisions_payload()),
        ]
    )
    passed, failures, judged = _gated(_judge(post))
    assert passed is False
    assert "timed out" in failures[0].lower()
    assert SECRET not in json.dumps(judged)
    assert judged["why"] is None
    assert len(post.calls) == 1
    assert all(not str(item["url"]).endswith("/v1/responses") for item in post.calls)


def test_why_call_on_fail_ignored_on_error() -> None:
    post = FakePost(
        [
            FakeResponse(200, decisions_payload({"correctness": "Incorrect"})),
            FakeResponse(429, {"error": "nope"}),
            FakeResponse(200, why_payload("should not be used")),
        ]
    )
    passed, _failures, judged = _gated(_judge(post))
    assert passed is False
    assert judged["passed"] is False
    assert judged["why"] is None
    assert len(post.calls) == 2
    assert post.calls[0]["url"].endswith("/v1/decisions")
    why_calls = [item for item in post.calls if str(item["url"]).endswith("/v1/responses")]
    assert len(why_calls) == 1
    why_json = why_calls[0]["json"]
    assert why_json["max_output_tokens"] == WHY_MAX_OUTPUT_TOKENS == 128
    schema = why_json["text"]["format"]
    assert schema["strict"] is True
    assert schema["name"] == "check_fail_why"


def test_why_call_skipped_on_pass() -> None:
    post = FakePost([FakeResponse(200, decisions_payload())])
    passed, _failures, judged = _gated(_judge(post))
    assert passed is True
    assert judged["passed"] is True
    assert judged["why"] is None
    assert len(post.calls) == 1


def test_why_call_skipped_on_low_confidence_pass() -> None:
    post = FakePost([FakeResponse(200, decisions_payload(confidence=0.1))])
    passed, _failures, judged = _gated(_judge(post))
    assert passed is True
    assert judged["passed"] is True
    assert judged["why"] is None
    assert len(post.calls) == 1


def test_responses_fallback_uses_structured_outputs() -> None:
    body = json.dumps(PASS_CHOICES)
    post = FakePost([FakeResponse(200, {"output_text": body, "model": "gpt-6-luna"})])
    judged = _score(_judge(post, backend="responses"))
    assert judged["passed"] is True
    assert judged["backend"] == "responses"
    assert judged["warnings"] == []
    assert len(post.calls) == 1
    assert post.calls[0]["url"].endswith("/v1/responses")
    fmt = post.calls[0]["json"]["text"]["format"]
    assert fmt["type"] == "json_schema"
    assert fmt["strict"] is True
    assert "path_efficiency" not in fmt["schema"]["properties"]
    assert "decisions" not in post.calls[0]["url"]
    assert judged["cells"]["path_efficiency"]["reason"] == PATH_NOT_AVAILABLE
    assert post.calls[0]["json"]["reasoning"] == {"effort": "low"}


def test_gateway_decisions_posts_luna_decisions_not_responses() -> None:
    post = FakePost([FakeResponse(200, decisions_payload())])
    judged = _score(
        make_openai_judge(
            api_key="gw-test",
            backend="decisions",
            model="openai/gpt-6-luna-decisions",
            base_url="https://ai-gateway.vercel.sh/v1",
            why_enabled=False,
            post=post,
        )
    )
    assert judged["passed"] is True
    assert post.calls[0]["url"].endswith("/v1/decisions")
    assert "responses" not in post.calls[0]["url"]
    assert post.calls[0]["json"]["model"] == "openai/gpt-6-luna-decisions"
    assert "reasoning" not in post.calls[0]["json"]


def test_gateway_why_call_uses_language_model_not_decisions() -> None:
    post = FakePost(
        [
            FakeResponse(200, decisions_payload({"correctness": "Incorrect"})),
            FakeResponse(200, why_payload("The numbers were wrong.")),
        ]
    )
    passed, _failures, judged = _gated(
        make_openai_judge(
            api_key="gw-test",
            backend="decisions",
            model="openai/gpt-6-luna-decisions",
            base_url="https://ai-gateway.vercel.sh/v1",
            why_enabled=True,
            post=post,
        )
    )
    assert passed is False
    assert judged["why"] == "The numbers were wrong."
    assert post.calls[0]["url"].endswith("/v1/decisions")
    assert post.calls[0]["json"]["model"] == "openai/gpt-6-luna-decisions"
    assert post.calls[1]["url"].endswith("/v1/responses")
    assert post.calls[1]["json"]["model"] == "openai/gpt-6-luna"
    assert post.calls[1]["json"]["model"].endswith("-decisions") is False


def test_gateway_mini_responses_omits_reasoning() -> None:
    body = json.dumps(PASS_CHOICES)
    post = FakePost([FakeResponse(200, {"output_text": body, "model": "openai/gpt-4o-mini"})])
    judge = make_openai_judge(
        api_key=SECRET,
        backend="responses",
        model="openai/gpt-4o-mini",
        why_enabled=False,
        post=post,
    )
    judged = _score(judge)
    assert judged["passed"] is True
    payload = post.calls[0]["json"]
    assert payload["model"] == "openai/gpt-4o-mini"
    assert "reasoning" not in payload


def test_o_series_responses_includes_reasoning() -> None:
    body = json.dumps(PASS_CHOICES)
    post = FakePost([FakeResponse(200, {"output_text": body, "model": "openai/o3-mini"})])
    judge = make_openai_judge(
        api_key=SECRET,
        backend="responses",
        model="openai/o3-mini",
        why_enabled=False,
        post=post,
    )
    judged = _score(judge)
    assert judged["passed"] is True
    assert post.calls[0]["json"]["reasoning"] == {"effort": "low"}


def test_gateway_mini_why_call_omits_reasoning() -> None:
    body = json.dumps({**PASS_CHOICES, "correctness": "Incorrect"})
    post = FakePost(
        [
            FakeResponse(200, {"output_text": body, "model": "openai/gpt-4o-mini"}),
            FakeResponse(200, why_payload("The numbers were wrong.")),
        ]
    )
    judge = make_openai_judge(
        api_key=SECRET,
        backend="responses",
        model="openai/gpt-4o-mini",
        why_enabled=True,
        post=post,
    )
    passed, _failures, judged = _gated(judge)
    assert passed is False
    assert judged["why"] == "The numbers were wrong."
    assert "reasoning" not in post.calls[0]["json"]
    assert post.calls[1]["url"].endswith("/v1/responses")
    assert "reasoning" not in post.calls[1]["json"]


def test_images_inline_jpeg_png_only(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    skill = tmp_path / "skill"
    workspace.mkdir()
    skill.mkdir()
    png = workspace / "shot.png"
    png.write_bytes(PNG_1x1)
    jpeg = workspace / "shot.jpg"
    jpeg.write_bytes(b"\xff\xd8\xff" + b"\x00" * 32)
    gif = workspace / "shot.gif"
    gif.write_bytes(b"GIF89a" + b"\x00" * 16)
    pdf = workspace / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4" + b"\x00" * 16)
    artifacts = [
        {"path": "shot.png", "present": True, "magic": "png"},
        {"path": "shot.jpg", "present": True, "magic": "jpeg"},
        {"path": "shot.gif", "present": True, "magic": "gif"},
        {"path": "doc.pdf", "present": True, "magic": "pdf"},
    ]
    images, _omitted = collect_images(
        artifacts=artifacts,
        golden=None,
        actual=None,
        workspace=workspace,
        skill_root=skill,
    )
    assert len(images) == 2
    assert all(item["type"] == "input_image" for item in images)
    joined = " ".join(item["image_url"] for item in images)
    assert joined.startswith("data:image/")
    assert "http://" not in joined
    assert "https://" not in joined
    assert "file_id" not in joined
    assert "base64," in joined

    post = FakePost([FakeResponse(200, decisions_payload())])
    judged = _score(
        _judge(post),
        artifacts=artifacts,
        workspace=workspace,
        skill_root=skill,
    )
    assert judged["passed"] is True
    content = post.calls[0]["json"]["input"][0]["content"]
    kinds = [item["type"] for item in content]
    assert "input_text" in kinds
    assert kinds.count("input_image") == 2
    blob = json.dumps(post.calls)
    assert "http://" not in blob
    assert "file_id" not in blob


def test_oversize_image_is_omitted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("skillgate_ai.judge_openai.IMAGE_MAX_BYTES", 16)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    big = workspace / "big.png"
    big.write_bytes(PNG_1x1 + b"\x00" * 64)
    images, omitted = collect_images(
        artifacts=[{"path": "big.png", "present": True, "magic": "png"}],
        golden=None,
        actual=None,
        workspace=workspace,
        skill_root=None,
    )
    assert images == []
    assert omitted and omitted[0]["reason"] == "too large"
    assert omitted[0]["size"] > 16
    assert IMAGE_MAX_BYTES == 4 * 1024 * 1024


def test_golden_actual_text_is_in_decisions_input() -> None:
    post = FakePost([FakeResponse(200, decisions_payload())])
    judged = _score(
        _judge(post),
        golden={"path": "want.txt", "kind": "text", "body": "TOTAL: 42"},
        actual_output={
            "path": "out.txt",
            "present": True,
            "kind": "text",
            "body": "TOTAL: 0",
        },
    )
    assert judged["passed"] is True
    blob = post.calls[0]["json"]["input"]
    assert isinstance(blob, str)
    assert "TOTAL: 42" in blob
    assert "TOTAL: 0" in blob


def test_output_mismatch_fails_and_makes_one_why_call() -> None:
    post = FakePost(
        [
            FakeResponse(200, decisions_payload()),
            FakeResponse(200, why_payload("The expected file was missing.")),
        ]
    )
    passed, failures, judged = _gated(
        _judge(post),
        golden={"path": "out.json", "kind": "json", "output_path": "out.json"},
        actual_output={"path": "out.json", "present": False, "body": None},
    )
    assert passed is False
    assert judged["passed"] is True
    assert REASON_MISSING_OUTPUT in failures
    assert judged["why"] == "The expected file was missing."
    assert judged["warnings"] == []
    assert len(post.calls) == 2
    assert post.calls[1]["url"].endswith("/v1/responses")
    assert post.calls[1]["json"]["max_output_tokens"] == 128


def test_image_paths_stay_inside_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    skill = tmp_path / "skill"
    workspace.mkdir()
    skill.mkdir()
    outside = tmp_path / "secret.png"
    outside.write_bytes(PNG_1x1)
    (workspace / "ok.png").write_bytes(PNG_1x1)
    images, omitted = collect_images(
        artifacts=[
            {"path": "../secret.png", "present": True, "magic": "png"},
            {"path": str(outside), "present": True, "magic": "png"},
            {"path": "ok.png", "present": True, "magic": "png"},
        ],
        golden={"path": "../secret.png"},
        actual=None,
        workspace=workspace,
        skill_root=skill,
    )
    assert len(images) == 1
    assert omitted == []
    joined = " ".join(item["image_url"] for item in images)
    assert joined.startswith("data:image/png;base64,")


def test_why_call_redacts_key_shaped_text() -> None:
    post = FakePost(
        [
            FakeResponse(200, decisions_payload({"correctness": "Incorrect"})),
            FakeResponse(
                200,
                why_payload(f"The scorer echoed {SECRET} and sk-otherleak123 in the explanation."),
            ),
        ]
    )
    passed, _failures, judged = _gated(_judge(post))
    assert passed is False
    assert judged["passed"] is False
    assert judged["why"] is not None
    assert SECRET not in judged["why"]
    assert "sk-otherleak123" not in judged["why"]
    assert "sk-***" in judged["why"]
    blob = json.dumps(judged)
    assert SECRET not in blob


def test_why_skipped_on_no_trigger_without_mismatch() -> None:
    post = FakePost(
        [
            FakeResponse(200, decisions_payload({"correctness": "Incorrect"})),
            FakeResponse(200, why_payload("should not fire")),
        ]
    )
    passed, failures, judged = _gated(_judge(post), expect_skill=None)
    assert passed is True
    assert failures == []
    assert judged["passed"] is False
    assert judged["why"] is None
    assert len(post.calls) == 1
    assert post.calls[0]["url"].endswith("/v1/decisions")


def test_why_skipped_on_no_trigger_when_output_missing() -> None:
    post = FakePost(
        [
            FakeResponse(200, decisions_payload()),
            FakeResponse(200, why_payload("The expected file was missing.")),
        ]
    )
    passed, failures, judged = _gated(
        _judge(post),
        expect_skill=None,
        selected_skill=None,
        golden={"path": "out.json", "kind": "json", "output_path": "out.json"},
        actual_output={"path": "out.json", "present": False, "body": None},
    )
    assert passed is True
    assert failures == []
    assert judged["why"] is None
    assert len(post.calls) == 1
    assert post.calls[0]["url"].endswith("/v1/decisions")


def test_http_error_with_missing_output_names_both() -> None:
    post = FakePost(
        [
            FakeResponse(
                401,
                {"error": {"message": f"Incorrect API key provided: {SECRET}"}},
            )
        ]
    )
    passed, failures, judged = _gated(
        _judge(post),
        golden={"path": "out.json", "kind": "json", "output_path": "out.json"},
        actual_output={"path": "out.json", "present": False, "body": None},
    )
    assert passed is False
    assert judged["passed"] is False
    assert REASON_MISSING_OUTPUT in failures
    assert "OpenAI did not accept this API key." in failures
    assert judged["why"] is None
    assert len(post.calls) == 1


def test_http_500_is_not_retried() -> None:
    post = FakePost(
        [
            FakeResponse(500, {"error": "nope"}),
            FakeResponse(200, decisions_payload()),
        ]
    )
    passed, failures, judged = _gated(_judge(post))
    assert passed is False
    assert "HTTP 500" in failures[0]
    assert judged["why"] is None
    assert len(post.calls) == 1


def test_why_call_includes_expected_and_actual_text() -> None:
    post = FakePost(
        [
            FakeResponse(200, decisions_payload({"correctness": "Incorrect"})),
            FakeResponse(
                200,
                why_payload(
                    "Expected 'Goodbye Skill Gate, totally different text' "
                    "but the output was 'Hello Skill Gate'."
                ),
            ),
        ]
    )
    passed, _failures, judged = _gated(
        _judge(post),
        golden={
            "path": "out.txt",
            "kind": "text",
            "body": "Goodbye Skill Gate, totally different text",
        },
        actual_output={
            "path": "out.txt",
            "present": True,
            "kind": "text",
            "body": "Hello Skill Gate",
        },
    )
    assert passed is False
    assert judged["why"] is not None
    assert "Hello Skill Gate" in judged["why"]
    assert "Goodbye Skill Gate" in judged["why"]
    assert len(post.calls) == 2
    why_json = post.calls[1]["json"]
    assert why_json["max_output_tokens"] == WHY_MAX_OUTPUT_TOKENS == 128
    user = json.loads(why_json["input"][1]["content"])
    assert user["expected_output"] == "Goodbye Skill Gate, totally different text"
    assert user["actual_output"] == "Hello Skill Gate"
    system = why_json["input"][0]["content"]
    assert "expected and actual" in system.lower()


def test_why_call_redacts_and_caps_output_text() -> None:
    long_actual = "ok " + ("x" * (WHY_OUTPUT_CHARS + 50)) + f" leaked {SECRET}"
    post = FakePost(
        [
            FakeResponse(200, decisions_payload({"correctness": "Incorrect"})),
            FakeResponse(200, why_payload("The output did not match.")),
        ]
    )
    passed, _failures, judged = _gated(
        _judge(post),
        golden={"path": "out.txt", "kind": "text", "body": f"safe {SECRET}"},
        actual_output={
            "path": "out.txt",
            "present": True,
            "kind": "text",
            "body": long_actual,
        },
    )
    assert passed is False
    why_json = post.calls[1]["json"]
    user = json.loads(why_json["input"][1]["content"])
    assert SECRET not in user["expected_output"]
    assert SECRET not in user["actual_output"]
    assert "sk-" not in user["expected_output"]
    assert "sk-" not in user["actual_output"]
    assert len(user["actual_output"]) <= WHY_OUTPUT_CHARS
    assert judged["why"] is not None
    assert SECRET not in judged["why"]


def test_path_not_asked_when_unrecorded() -> None:
    post = FakePost([FakeResponse(200, decisions_payload())])
    judged = _score(_judge(post), path={"steps": 0, "errors": 0, "had_path": False})
    assert judged["passed"] is True
    names = [item["name"] for item in post.calls[0]["json"]["questions"]]
    assert "path_efficiency" not in names
    assert judged["soft_answers"] == {}
    cell = judged["cells"]["path_efficiency"]
    assert cell["choice"] is None
    assert cell["reason"] == PATH_NOT_AVAILABLE
    assert "confidence" not in cell


def test_path_asked_when_recorded() -> None:
    post = FakePost([FakeResponse(200, decisions_payload())])
    judged = _score(_judge(post), path={"steps": 6, "errors": 0, "had_path": True})
    assert judged["passed"] is True
    names = [item["name"] for item in post.calls[0]["json"]["questions"]]
    assert names[-1] == "path_efficiency"
    assert judged["soft_answers"]["path_efficiency"]["choice"] == "Efficient"
    assert judged["cells"]["path_efficiency"]["choice"] == "Efficient"


def test_unrecorded_path_ignores_invented_rating() -> None:
    post = FakePost([FakeResponse(200, decisions_payload({"path_efficiency": "Efficient"}))])
    judged = _score(_judge(post), path={"steps": 0, "had_path": False})
    assert judged["passed"] is True
    assert judged["soft_answers"] == {}
    assert judged["cells"]["path_efficiency"]["reason"] == PATH_NOT_AVAILABLE
    assert judged["cells"]["path_efficiency"]["choice"] is None
