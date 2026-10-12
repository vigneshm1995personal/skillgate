"""Serve the React UI + local API on loopback. Not hosted serve."""

from __future__ import annotations

import errno
import socket
import webbrowser
from importlib.resources import files
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse, Response
from starlette.staticfiles import StaticFiles

from skillgate_ai.api import create_app
from skillgate_ai.errors import SkillGateError

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765

_MISSING_UI = """<!doctype html>
<html lang="en">
  <head><meta charset="utf-8"><title>Skill Gate</title></head>
  <body>
    <p>The local UI is not built yet. From the repo:</p>
    <pre>cd web &amp;&amp; pnpm install &amp;&amp; pnpm build
skillgate ui</pre>
    <p>API routes under <code>/api</code> still work. No account required.</p>
  </body>
</html>
"""


def web_static_dir() -> Path | None:
    """Packaged ``web_static`` (wheel) or repo ``web/dist`` (editable checkout)."""
    try:
        packaged = files("skillgate_ai").joinpath("web_static")
        path = Path(str(packaged))
        if (path / "index.html").is_file():
            return path
    except (FileNotFoundError, ModuleNotFoundError, TypeError, ValueError):
        pass
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        dist = parent / "web" / "dist"
        if (dist / "index.html").is_file():
            return dist
        if parent.name == "src" and (parent.parent / "web" / "dist" / "index.html").is_file():
            return parent.parent / "web" / "dist"
    return None


def attach_static(app: FastAPI, dist: Path | None = None) -> None:
    root = dist if dist is not None else web_static_dir()

    @app.get("/", response_model=None)
    def index() -> Response:
        if root is None or not (root / "index.html").is_file():
            return HTMLResponse(_MISSING_UI, status_code=503)
        return FileResponse(root / "index.html")

    if root is not None and root.is_dir():
        assets = root / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{full_path:path}", response_model=None)
        def spa(full_path: str) -> Response:
            if full_path.startswith("api/"):
                return HTMLResponse("not found", status_code=404)
            candidate = (root / full_path).resolve()
            try:
                candidate.relative_to(root.resolve())
            except ValueError:
                return HTMLResponse("not found", status_code=404)
            if candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(root / "index.html")
    else:

        @app.get("/{full_path:path}", response_model=None)
        def spa_missing(full_path: str) -> Response:
            if full_path.startswith("api/"):
                return HTMLResponse("not found", status_code=404)
            return HTMLResponse(_MISSING_UI, status_code=503)


def _ensure_port_free(host: str, port: int) -> None:
    family = socket.AF_INET6 if host in {"::1", "::"} or ":" in host and "." not in host else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE or getattr(exc, "winerror", None) == 10048:
            raise SkillGateError(
                f"Port {port} is already in use.",
                hint="Stop the other process, or pass --port with a free port.",
            ) from None
        raise SkillGateError(
            f"Could not bind {host}:{port}.",
            hint="Try another --host or --port.",
        ) from None
    finally:
        sock.close()


def serve_ui(
    *,
    root: Path,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    pack: Path | None = None,
    open_browser: bool = False,
) -> None:
    import uvicorn

    _ensure_port_free(host, port)
    app = create_app(root=root, pack=pack)
    attach_static(app)
    url = f"http://{host}:{port}/"
    print(f"Skill Gate UI (local, no account) at {url}", flush=True)
    print("Stop with Ctrl+C. Docker image still runs `skillgate check /pack`.", flush=True)
    if open_browser:
        webbrowser.open(url)
    uvicorn.run(app, host=host, port=port, log_level="warning")
