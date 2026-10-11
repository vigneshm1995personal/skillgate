"""AST deny-list: public package must not import hosted modules."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src" / "skillgate_ai"

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
