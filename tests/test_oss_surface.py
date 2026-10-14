"""AST deny-list: public package must not import hosted modules."""

from __future__ import annotations

import ast
import re
import shutil
import urllib.parse
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1] / "src" / "skillgate_ai"
REPO = ROOT.parents[1]

# Skill Gate product hosts — never a default/fallback for OSS check, harness, or judge.
# Provider URLs the user owns (OpenAI, Vercel AI Gateway, Anthropic, Cursor, AWS) are allowed.
_URL_RE = re.compile(r"https?://[^\s\"'`<>)\]},]+")
_HOSTED_SKILLGATE_HOSTS = (
    "skillgate.ai",
    "skillgate.dev",
    "skillgate.app",
    "skillgate.cloud",
    "skillgate.vercel.app",
    "skillgate-ai.vercel.app",
)
_HOSTED_SKILLGATE_PREFIXES = (
    "api.skillgate.",
    "hosted.skillgate.",
    "app.skillgate.",
    "www.skillgate.",
    "judge.skillgate.",
    "gateway.skillgate.",
)

DENIED = {
    "skillgate_ai.auth_siwv",
    "skillgate_ai.vault",
    "skillgate_ai.store",
    "skillgate_ai.store_postgres",
    "skillgate_ai.web",
    "skillgate_ai.eval_slice",
    "skillgate_ai.jev_qa",
    "skillgate_ai.author",
    "skillgate_ai.wizard",
    "skillgate_ai.stage_b",
    "skillgate_ai.deploy_git",
    "skillgate_ai.remote_harness",
}

DENIED_STEMS = {name.rsplit(".", 1)[-1] for name in DENIED}
DENIED_FILES = {f"{stem}.py" for stem in DENIED_STEMS} | {"web.py"}


def _imported_names(tree: ast.AST) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            found.add(module)
            for alias in node.names:
                found.add(f"{module}.{alias.name}" if module else alias.name)
    return found


def test_denied_modules_are_absent_on_disk() -> None:
    names = {path.name for path in ROOT.glob("*.py")}
    leaked = names & DENIED_FILES
    assert not leaked, f"hosted files in public tree: {sorted(leaked)}"
    assert not (ROOT / "remote_harness").exists()
    assert not (ROOT / "web").exists()


def test_no_denied_imports() -> None:
    leaks: list[str] = []
    for path in sorted(ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported = _imported_names(tree)
        for name in imported:
            for denied in DENIED:
                if name == denied or name.startswith(denied + "."):
                    leaks.append(f"{path.name}: {name}")
    assert not leaks, "hosted imports:\n" + "\n".join(leaks)


def test_helper_and_sync_stay_cli_only() -> None:
    """Helper/sync ship in the library CLI, not the local UI."""
    for rel in ("helper.py", "sync.py"):
        path = ROOT / rel
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        imported = _imported_names(tree)
        leaks = [name for name in imported if "local_ui" in name]
        assert not leaks, f"{rel} imported local UI: {leaks}"


def test_cli_imports_without_hosted() -> None:
    import skillgate_ai.api
    import skillgate_ai.catalog
    import skillgate_ai.cli
    import skillgate_ai.config
    import skillgate_ai.engine
    import skillgate_ai.judge_bank
    import skillgate_ai.judge_copy
    import skillgate_ai.judge_openai
    import skillgate_ai.judge_spec
    import skillgate_ai.judge_providers.jev
    import skillgate_ai.local_ui.server
    import skillgate_ai.mode
    import skillgate_ai.openai_http
    import skillgate_ai.output_match
    import skillgate_ai.server


def test_local_ui_may_exist_without_hosted_names() -> None:
    assert (ROOT / "local_ui").is_dir()
    assert not (ROOT / "web.py").exists()
    assert not (ROOT / "wizard.py").exists()
    assert not (ROOT / "local_ui" / "wizard.py").exists()
    assert (ROOT / "api.py").is_file()
    assert (ROOT / "server.py").is_file()
    assert (ROOT / "mode.py").is_file()
    repo_web = ROOT.parents[1] / "web"
    assert (repo_web / "package.json").is_file()
    tree = ast.parse((ROOT / "cli.py").read_text(encoding="utf-8"), filename="cli.py")
    imported = _imported_names(tree)
    assert "skillgate_ai.web" not in imported
    assert "skillgate_ai.auth_siwv" not in imported


def test_static_index_is_packaged() -> None:
    from importlib.resources import files

    index = files("skillgate_ai.local_ui").joinpath("static/index.html")
    text = index.read_text(encoding="utf-8")
    assert "no account" in text.lower()


def _is_skillgate_hosted_host(host: str) -> bool:
    name = (host or "").lower().rstrip(".")
    if not name:
        return False
    if name in _HOSTED_SKILLGATE_HOSTS:
        return True
    if name.endswith((".skillgate.ai", ".skillgate.dev", ".skillgate.app", ".skillgate.cloud")):
        return True
    return any(name.startswith(prefix) for prefix in _HOSTED_SKILLGATE_PREFIXES)


def _runtime_scan_roots() -> list[Path]:
    web_src = REPO / "web" / "src"
    roots = [ROOT]
    if web_src.is_dir():
        roots.append(web_src)
    example = REPO / ".env.example"
    if example.is_file():
        roots.append(example)
    return roots


def _scan_skillgate_hosted_urls() -> list[str]:
    hits: list[str] = []
    for root in _runtime_scan_roots():
        paths = [root] if root.is_file() else sorted(root.rglob("*"))
        for path in paths:
            if not path.is_file():
                continue
            if path.suffix not in {".py", ".ts", ".tsx", ".js", ".mjs", ".example", ""}:
                continue
            if path.name.endswith((".test.ts", ".test.tsx")):
                continue
            text = path.read_text(encoding="utf-8")
            for raw in _URL_RE.findall(text):
                host = urllib.parse.urlparse(raw).hostname or ""
                if _is_skillgate_hosted_host(host):
                    hits.append(f"{path.relative_to(REPO)}: {raw}")
    return hits


def _judge_cfg(**overrides: object):
    from skillgate_ai.config import LLMConfig

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
    }
    fields.update(overrides)
    return LLMConfig(**fields)  # type: ignore[arg-type]


def test_oss_never_calls_skillgate_hosted_endpoint_or_runs_without_user_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """OSS is BYO-key for harness and judge: no Skill Gate host, no keyless run."""
    from skillgate_ai.config import get_llm_config
    from skillgate_ai.errors import MissingLLMKeyError, SkillGateError
    from skillgate_ai.gate import run_check
    from skillgate_ai.helper import connect as connect_helper
    from skillgate_ai.judge import SkipJudge, resolve_judge
    from skillgate_ai.keys import (
        PROVIDER_KEY_NAMES,
        SKILLGATE_KEY_ENV,
        resolve_provider_keys,
        set_vault_key,
    )
    from skillgate_ai.mode import LOCAL_SLOTS

    hosted = _scan_skillgate_hosted_urls()
    assert hosted == [], "OSS must not hardcode Skill Gate-hosted endpoints:\n" + "\n".join(
        hosted
    )
    assert LOCAL_SLOTS["hostedJudge"] is False

    http_calls: list[str] = []

    def _record(url: object) -> None:
        http_calls.append(str(url))

    def _block_httpx(url, *args, **kwargs):
        del args, kwargs
        _record(url)
        raise AssertionError(f"OSS must not make HTTP without a user-set key: {url}")

    def _block_urlopen(req, *args, **kwargs):
        del args, kwargs
        url = getattr(req, "full_url", None) or getattr(req, "get_full_url", lambda: req)()
        _record(url)
        raise AssertionError(f"OSS must not make HTTP without a user-set key: {url}")

    monkeypatch.setattr(httpx, "post", _block_httpx)
    monkeypatch.setattr(httpx, "get", _block_httpx)
    monkeypatch.setattr(httpx, "request", _block_httpx)
    monkeypatch.setattr("urllib.request.urlopen", _block_urlopen)

    for name in PROVIDER_KEY_NAMES:
        monkeypatch.setenv(name, f"ambient-{name}")
        monkeypatch.setenv(SKILLGATE_KEY_ENV[name], "")
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.setenv("SKILLGATE_MODE", "local")

    cfg = get_llm_config(tmp_path)
    assert resolve_provider_keys(tmp_path) == {}
    assert cfg.has_any_key is False
    assert not any(
        [
            cfg.cursor_api_key,
            cfg.codex_api_key,
            cfg.openai_api_key,
            cfg.gateway_api_key,
            cfg.anthropic_api_key,
            cfg.jev_api_key,
            cfg.aws_access_key_id,
            cfg.aws_secret_access_key,
        ]
    )
    assert cfg.judge_endpoint in (None, "")
    assert isinstance(resolve_judge(cfg, harness_name="cursor-agent"), SkipJudge)

    with pytest.raises(SkillGateError) as missing_jev_host:
        resolve_judge(
            _judge_cfg(jev_api_key="jev-user-key", judge_provider="jev", judge_chosen=True),
            harness_name="cursor-agent",
        )
    assert missing_jev_host.value.exit_code == 2
    assert "base URL" in missing_jev_host.value.message

    pack = tmp_path / "pdf"
    shutil.copytree(REPO / "skills" / "pdf", pack)
    result = run_check(pack, source="test", root=tmp_path)
    assert result.exit_code == 2
    assert result.report is None
    assert http_calls == []

    set_vault_key(tmp_path, "JEV_API_KEY", "jev-only-not-a-harness-key")
    judge_only = run_check(pack, source="test", root=tmp_path)
    assert judge_only.exit_code == 2
    assert judge_only.report is None
    assert http_calls == []
    assert get_llm_config(tmp_path).has_any_key is False

    with pytest.raises(SkillGateError, match="hosted Skill Gate URL is required"):
        connect_helper("", "ABC12345")
    assert http_calls == []

    with pytest.raises(MissingLLMKeyError):
        resolve_judge(_judge_cfg(judge_pref="openai"), harness_name="cursor-agent")
    assert http_calls == []
