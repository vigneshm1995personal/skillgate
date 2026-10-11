"""AWS Bedrock Converse + JSON schema. Vault keys only — no default credential chain."""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac as hmac_mod
import json
from typing import Any, Mapping
from urllib.parse import urlparse

import httpx

from skillgate_ai.errors import OFFLINE_MESSAGE
from skillgate_ai.judge_bank import CHECK_CELL_ORDER, SOFT_CELL_ORDER, UNUSABLE_ANSWER
from skillgate_ai.judge_openai import (
    DEFAULT_TIMEOUT_SEC,
    _normalize_answers,
    _path_is_recorded,
    _state_text,
)
from skillgate_ai.judge_spec import JudgeSpec, builtin_spec, spec_structured_schema
from skillgate_ai.openai_http import PostFn

DISPLAY_NAME = "AWS"
SERVICE = "bedrock"


class AwsBackend:
    name = "aws"
    supports_confidence = False
    supports_why = True

    def __init__(
        self,
        *,
        access_key: str,
        secret_key: str,
        region: str,
        model: str,
        session_token: str | None = None,
        post: PostFn | None = None,
    ) -> None:
        self.api_key = access_key
        self.secret_key = secret_key
        self.session_token = session_token or ""
        self.region = region
        self.model = model
        self._post = post

    def evaluate(
        self,
        *,
        state: Mapping[str, Any],
        images: list[dict[str, str]],
        timeout_sec: float,
        spec: JudgeSpec | None = None,
    ) -> dict[str, Any]:
        del images
        resolved = spec or builtin_spec()
        include_path = _path_is_recorded(state.get("path"))
        schema = spec_structured_schema(resolved, include_path=include_path)
        payload = {
            "inferenceConfig": {"maxTokens": 1024},
            "toolConfig": {
                "tools": [
                    {
                        "toolSpec": {
                            "name": "score_check",
                            "description": "Score this skill check.",
                            "inputSchema": {"json": schema},
                        }
                    }
                ],
                "toolChoice": {"tool": {"name": "score_check"}},
            },
            "messages": [{"role": "user", "content": [{"text": _state_text(state)}]}],
        }
        result = self._converse(payload, timeout_sec=timeout_sec)
        if result.get("status") != "ok":
            return result
        data = result["data"]
        parsed = _tool_input(data)
        if parsed is None:
            return {"status": "error", "reason": UNUSABLE_ANSWER, "model": self.model}
        answers = _normalize_answers(parsed, include_path=include_path, spec=resolved)
        _fill_extra_answers(answers, parsed, resolved)
        return {"status": "completed", "model": self.model, "answers": answers}

    def ping(self, *, timeout_sec: float = DEFAULT_TIMEOUT_SEC) -> dict[str, Any]:
        payload = {
            "inferenceConfig": {"maxTokens": 1},
            "messages": [{"role": "user", "content": [{"text": "ping"}]}],
        }
        result = self._converse(payload, timeout_sec=timeout_sec, retries=False)
        if result.get("status") == "ok":
            return {"ok": True, "message": f"Connected to {DISPLAY_NAME}."}
        return {
            "ok": False,
            "message": str(result.get("reason") or "Could not connect."),
        }

    def explain_fail_payload(self, user_blob: dict[str, Any], *, timeout_sec: float) -> str | None:
        schema = {
            "type": "object",
            "properties": {"why": {"type": "string"}},
            "required": ["why"],
            "additionalProperties": False,
        }
        payload = {
            "inferenceConfig": {"maxTokens": 128},
            "toolConfig": {
                "tools": [
                    {
                        "toolSpec": {
                            "name": "check_fail_why",
                            "inputSchema": {"json": schema},
                        }
                    }
                ],
                "toolChoice": {"tool": {"name": "check_fail_why"}},
            },
            "messages": [
                {
                    "role": "user",
                    "content": [{"text": json.dumps(user_blob, ensure_ascii=True, default=str)}],
                }
            ],
        }
        result = self._converse(payload, timeout_sec=timeout_sec, retries=False)
        if result.get("status") != "ok":
            return None
        parsed = _tool_input(result["data"])
        if not isinstance(parsed, Mapping):
            return None
        why = parsed.get("why")
        return why.strip() if isinstance(why, str) and why.strip() else None

    def _converse(
        self,
        payload: dict[str, Any],
        *,
        timeout_sec: float,
        retries: bool = True,
    ) -> dict[str, Any]:
        del retries
        host = f"bedrock-runtime.{self.region}.amazonaws.com"
        path = f"/model/{self.model}/converse"
        url = f"https://{host}{path}"
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        headers = _sigv4_headers(
            method="POST",
            url=url,
            body=body,
            access_key=self.api_key,
            secret_key=self.secret_key,
            session_token=self.session_token,
            region=self.region,
        )
        sender = self._post or httpx.post
        try:
            response = sender(url, headers=headers, content=body, timeout=timeout_sec)
        except httpx.TimeoutException:
            return {"status": "error", "reason": f"{DISPLAY_NAME} scoring timed out.", "model": self.model}
        except TypeError:
            # Tests often monkeypatch OpenAI-style json= payloads.
            try:
                response = sender(url, headers=headers, json=payload, timeout=timeout_sec)
            except httpx.TimeoutException:
                return {
                    "status": "error",
                    "reason": f"{DISPLAY_NAME} scoring timed out.",
                    "model": self.model,
                }
            except httpx.HTTPError:
                return {"status": "error", "reason": OFFLINE_MESSAGE, "model": self.model}
        except httpx.HTTPError:
            return {"status": "error", "reason": OFFLINE_MESSAGE, "model": self.model}
        if response.status_code >= 400:
            return {
                "status": "error",
                "reason": _aws_status(response.status_code),
                "model": self.model,
                "http_status": response.status_code,
            }
        try:
            data = response.json()
        except ValueError:
            return {"status": "error", "reason": UNUSABLE_ANSWER, "model": self.model}
        if not isinstance(data, Mapping):
            return {"status": "error", "reason": UNUSABLE_ANSWER, "model": self.model}
        return {"status": "ok", "data": data}


def _aws_status(status: int) -> str:
    if status == 401 or status == 403:
        return "AWS did not accept this API key."
    if status == 404:
        return "AWS has no scoring endpoint for this model."
    if status == 429:
        return "AWS rate-limited this request. Wait and retry."
    return f"AWS scoring failed (HTTP {status})."


def _sigv4_headers(
    *,
    method: str,
    url: str,
    body: bytes,
    access_key: str,
    secret_key: str,
    session_token: str,
    region: str,
) -> dict[str, str]:
    parsed = urlparse(url)
    host = parsed.netloc
    now = dt.datetime.now(dt.UTC)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    payload_hash = hashlib.sha256(body).hexdigest()
    canonical_headers = f"content-type:application/json\nhost:{host}\nx-amz-date:{amz_date}\n"
    signed_headers = "content-type;host;x-amz-date"
    if session_token:
        canonical_headers += f"x-amz-security-token:{session_token}\n"
        signed_headers += ";x-amz-security-token"
    canonical_request = "\n".join(
        [
            method,
            parsed.path or "/",
            parsed.query,
            canonical_headers,
            signed_headers,
            payload_hash,
        ]
    )
    credential_scope = f"{date_stamp}/{region}/{SERVICE}/aws4_request"
    string_to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            credential_scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ]
    )
    signing_key = _signing_key(secret_key, date_stamp, region, SERVICE)
    signature = hmac_mod.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    headers = {
        "Content-Type": "application/json",
        "Host": host,
        "X-Amz-Date": amz_date,
        "Authorization": (
            f"AWS4-HMAC-SHA256 Credential={access_key}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        ),
    }
    if session_token:
        headers["X-Amz-Security-Token"] = session_token
    return headers


def _signing_key(secret: str, date_stamp: str, region: str, service: str) -> bytes:
    def sign(key: bytes, msg: str) -> bytes:
        return hmac_mod.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

    k_date = sign(("AWS4" + secret).encode("utf-8"), date_stamp)
    k_region = sign(k_date, region)
    k_service = sign(k_region, service)
    return sign(k_service, "aws4_request")


def _tool_input(data: Mapping[str, Any]) -> dict[str, Any] | None:
    output = data.get("output")
    if isinstance(output, Mapping):
        message = output.get("message")
        if isinstance(message, Mapping):
            content = message.get("content")
            if isinstance(content, list):
                for part in content:
                    if not isinstance(part, Mapping):
                        continue
                    tool = part.get("toolUse") or part.get("tool_use")
                    if isinstance(tool, Mapping) and isinstance(tool.get("input"), Mapping):
                        return dict(tool["input"])
                    if isinstance(part.get("input"), Mapping):
                        return dict(part["input"])
    if isinstance(data.get("answers"), Mapping):
        return dict(data["answers"])
    return None


def _fill_extra_answers(
    answers: dict[str, Any],
    parsed: Mapping[str, Any],
    spec: JudgeSpec,
) -> None:
    for question in spec.extras:
        if question.id in parsed and question.id not in answers:
            answers[question.id] = parsed[question.id]


# Silence unused-import lints for cell constants used as documentation of the mapping.
_ = (CHECK_CELL_ORDER, SOFT_CELL_ORDER)
