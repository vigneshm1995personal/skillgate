"""Loopback Host/Origin and JSON content-type for the local UI."""

from __future__ import annotations

from urllib.parse import urlparse

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
MUTATING = frozenset({"POST", "PUT", "PATCH", "DELETE"})
ALLOWED_CONTENT = frozenset({"application/json", "multipart/form-data"})


def hostname_of(host: str) -> str:
    raw = (host or "").strip()
    if not raw:
        return ""
    if raw.startswith("["):
        end = raw.find("]")
        if end > 0:
            return raw[1:end].lower()
    if raw.count(":") == 1:
        return raw.rsplit(":", 1)[0].lower()
    return raw.lower()


def host_is_loopback(host: str) -> bool:
    return hostname_of(host) in LOOPBACK_HOSTS


def origin_is_loopback(origin: str) -> bool:
    parsed = urlparse(origin)
    host = parsed.hostname or ""
    return host.lower() in LOOPBACK_HOSTS


class LocalUIGuard(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        host = request.headers.get("host") or ""
        if not host_is_loopback(host):
            return _forbid("This local UI only accepts requests on 127.0.0.1 or localhost.")
        if request.method in MUTATING:
            content_type = (request.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
            length = (request.headers.get("content-length") or "0").strip()
            empty_body = not content_type and length in {"", "0"}
            if not empty_body and content_type not in ALLOWED_CONTENT:
                return _forbid("This local UI only accepts JSON (or file uploads).")
            origin = (request.headers.get("origin") or "").strip()
            if origin and not origin_is_loopback(origin):
                return _forbid("This local UI only accepts requests from this machine.")
        return await call_next(request)


def _forbid(message: str) -> JSONResponse:
    return JSONResponse(status_code=403, content={"detail": {"message": message}})
