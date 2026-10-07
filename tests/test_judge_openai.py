from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from skillgate_ai.judge_bank import LOW_CONFIDENCE_WARNING, UNUSABLE_ANSWER, decisions_questions
from skillgate_ai.judge_openai import (
    DISPLAY_NAME,
    IMAGE_MAX_BYTES,
    collect_images,
    make_openai_judge,
    user_message_for_status,
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
        self.calls.append({"url": url, "headers": kwargs.get("headers"), "json": kwargs.get("json")})
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
    return judge.judge(
        "Extract the invoice total.",
        kwargs.pop("artifacts", [{"path": "out.txt", "present": True, "kind": "text"}]),
        "selected: pdf\n" + ("x" * 20),
        expect_skill="pdf",
        selected_skill="pdf",
        **kwargs,
    )


def test_decisions_request_shape() -> None:
    post = FakePost([FakeResponse(200, decisions_payload())])
    judged = _score(_judge(post))
    assert judged["passed"] is True
    assert judged["backend"] == "decisions"
    assert judged["display_name"] == DISPLAY_NAME
    assert post.calls and post.calls[0]["url"].endswith("/v1/decisions")
    payload = post.calls[0]["json"]
    assert payload["model"] == "gpt-6-luna"
    questions = payload["questions"]
    assert len(questions) == 6
    assert all(item["type"] == "choice" for item in questions)
    names = [item["name"] for item in questions]
    assert names == [item["name"] for item in decisions_questions()]
    task = next(item for item in questions if item["name"] == "task_completion")
    assert [row["value"] for row in task["choices"]] == [
        "Fully completed",
        "Partially completed",
        "Not completed",
    ]
    auth = post.calls[0]["headers"]["Authorization"]
    assert auth == f"Bearer {SECRET}"
    assert judged["answers"]["task_completion"]["choice"] == "Fully completed"
    assert judged["answers"]["task_completion"]["confidence"] == 0.9
    assert judged["answers"]["task_completion"]["probabilities"][0]["value"] == "Fully completed"


def test_fail_lock_does_not_fail_on_wasteful_path() -> None:
    post = FakePost(
        [
            FakeResponse(200, decisions_payload({"correctness": "Incorrect"})),
            FakeResponse(200, why_payload("The numbers were wrong.")),
        ]
    )
    judged = _score(_judge(post))
    assert judged["passed"] is False
    assert any("Got it right?" in item for item in judged["reasons"])
    assert judged["why"] == "The numbers were wrong."

    post2 = FakePost([FakeResponse(200, decisions_payload({"path_efficiency": "Wasteful"}))])
    judged2 = _score(_judge(post2))
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
    post = FakePost([FakeResponse(200, decisions_payload({"correctness": "Pretty good"}))])
    judged = _score(_judge(post))
    assert judged["status"] == "error"
    assert judged["passed"] is False
    assert judged["reasons"] == [UNUSABLE_ANSWER]


def test_http_errors_fail_and_never_log_key(caplog: pytest.LogCaptureFixture) -> None:
    cases = {
        401: user_message_for_status(401),
        403: user_message_for_status(403),
        404: user_message_for_status(404),
        400: user_message_for_status(400),
        429: user_message_for_status(429),
    }
    for status, message in cases.items():
        copies = 3 if status == 429 else 1
        post = FakePost(
            [FakeResponse(status, {"error": {"message": "nope", "key": SECRET}})] * copies
        )
        with caplog.at_level("WARNING"):
            judged = _score(_judge(post))
        assert judged["passed"] is False
        assert judged["status"] == "error"
        assert judged["reasons"] == [message]
        blob = json.dumps(judged) + caplog.text
        assert SECRET not in blob
        assert "sk-test" not in caplog.text


def test_timeout_fails_closed() -> None:
    post = FakePost([httpx.TimeoutException("slow") for _ in range(3)])
    judged = _score(_judge(post))
    assert judged["passed"] is False
    assert "timed out" in judged["reasons"][0].lower()
    assert SECRET not in json.dumps(judged)


def test_why_call_on_fail_ignored_on_error() -> None:
    post = FakePost(
        [
            FakeResponse(200, decisions_payload({"correctness": "Incorrect"})),
            FakeResponse(500, {"error": "nope"}),
            FakeResponse(500, {"error": "nope"}),
            FakeResponse(500, {"error": "nope"}),
        ]
    )
    judged = _score(_judge(post))
    assert judged["passed"] is False
    assert judged["why"] is None
    assert post.calls[0]["url"].endswith("/v1/decisions")
    why_calls = [item for item in post.calls if str(item["url"]).endswith("/v1/responses")]
    assert why_calls
    schema = why_calls[0]["json"]["text"]["format"]
    assert schema["strict"] is True
    assert schema["name"] == "check_fail_why"


def test_why_call_skipped_on_pass() -> None:
    post = FakePost([FakeResponse(200, decisions_payload())])
    judged = _score(_judge(post))
    assert judged["passed"] is True
    assert judged["why"] is None
    assert len(post.calls) == 1


def test_why_call_skipped_on_low_confidence_pass() -> None:
    post = FakePost([FakeResponse(200, decisions_payload(confidence=0.1))])
    judged = _score(_judge(post))
    assert judged["passed"] is True
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
    assert "decisions" not in post.calls[0]["url"]


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
    images, omitted = collect_images(
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


def test_no_http_when_skip_backend_not_constructed() -> None:
    post = FakePost([])
    from skillgate_ai.judge import SkipJudge

    judged = SkipJudge().judge("goal", [], "tail")
    assert judged["status"] == "skip"
    assert judged["passed"] is None
    assert post.calls == []
