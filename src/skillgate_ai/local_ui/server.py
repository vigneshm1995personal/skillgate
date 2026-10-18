"""Loopback stdlib HTTP server for the local Skill Gate UI."""

from __future__ import annotations

import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from skillgate_ai.local_ui.api import UiState, handle

STATIC_NAMES = {"index.html", "app.js", "app.css", "favicon.svg"}
STATIC_DIR = Path(__file__).resolve().parent / "static"


def _static_bytes(name: str) -> tuple[bytes, str] | None:
    if name not in STATIC_NAMES:
        return None
    path = (STATIC_DIR / name).resolve()
    try:
        path.relative_to(STATIC_DIR.resolve())
    except ValueError:
        return None
    if not path.is_file():
        return None
    suffix = path.suffix.lower()
    types = {
        ".html": "text/html; charset=utf-8",
        ".js": "text/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".svg": "image/svg+xml",
    }
    return path.read_bytes(), types.get(suffix, "application/octet-stream")


def make_handler(state: UiState):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:
            return

        def _cors(self) -> None:
            host = self.headers.get("Host", f"127.0.0.1:{self.server.server_address[1]}")
            origin = self.headers.get("Origin") or f"http://{host}"
            if origin.startswith(("http://127.0.0.1", "http://localhost")):
                self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")

        def do_OPTIONS(self) -> None:
            self.send_response(204)
            self._cors()
            self.end_headers()

        def do_GET(self) -> None:
            self._handle()

        def do_POST(self) -> None:
            self._handle()

        def do_PUT(self) -> None:
            self._handle()

        def _read_json(self) -> dict | None:
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0:
                return None
            raw = self.rfile.read(length)
            if not raw:
                return None
            try:
                data = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                raise ValueError("Request body is not valid JSON.") from None
            if data is None:
                return None
            if not isinstance(data, dict):
                raise TypeError("JSON body must be an object.")
            return data

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self._cors()
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _handle(self) -> None:
            parsed = urlparse(self.path)
            route = unquote(parsed.path or "/")
            if self.command == "GET" and (route == "/" or route == "/index.html"):
                blob = _static_bytes("index.html")
                if blob is None:
                    self._send(500, b"missing index.html", "text/plain; charset=utf-8")
                    return
                data, ctype = blob
                self._send(200, data, ctype)
                return
            if self.command == "GET" and route.startswith("/static/"):
                name = Path(route[len("/static/") :]).name
                blob = _static_bytes(name)
                if blob is None:
                    self._send(404, b"not found", "text/plain; charset=utf-8")
                    return
                data, ctype = blob
                self._send(200, data, ctype)
                return
            try:
                body = self._read_json() if self.command in {"POST", "PUT"} else None
            except (ValueError, TypeError) as exc:
                payload = json.dumps({"error": str(exc)}).encode("utf-8")
                self._send(400, payload, "application/json")
                return
            status, data, ctype = handle(
                state, method=self.command, path=route, query=parsed.query, body=body
            )
            if data is None:
                raw = b""
            elif isinstance(data, bytes):
                raw = data
            else:
                raw = json.dumps(data).encode("utf-8")
            self._send(status, raw, ctype)

    return Handler


def start_background(
    *,
    root: Path,
    host: str = "127.0.0.1",
    port: int = 0,
    pack: Path | None = None,
) -> tuple[ThreadingHTTPServer, str, UiState]:
    state = UiState(root=root.resolve(), initial_pack=pack.resolve() if pack else None)
    server = ThreadingHTTPServer((host, port), make_handler(state))
    thread = threading.Thread(target=server.serve_forever, name="skillgate-ui", daemon=True)
    thread.start()
    bound_host, bound_port = server.server_address[:2]
    base = f"http://{bound_host}:{bound_port}"
    return server, base, state


def serve_ui(
    *,
    root: Path,
    host: str = "127.0.0.1",
    port: int = 8765,
    pack: Path | None = None,
    open_browser: bool = False,
) -> None:
    state = UiState(root=root.resolve(), initial_pack=pack.resolve() if pack else None)
    server = ThreadingHTTPServer((host, port), make_handler(state))
    bound_host, bound_port = server.server_address[:2]
    url = f"http://{bound_host}:{bound_port}/"
    print(f"Skill Gate UI (local, no account) at {url}", flush=True)
    print("Stop with Ctrl+C.", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping local UI.", flush=True)
    finally:
        server.shutdown()
        server.server_close()
