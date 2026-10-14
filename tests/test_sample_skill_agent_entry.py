from __future__ import annotations

import shutil
from pathlib import Path

from skillgate_ai.harness import Completion, LLMHarness
from skillgate_ai.ingest import ingest_skill
from skillgate_ai.sandbox import LocalSandbox
from skillgate_ai.usage import Usage

ROOT = Path(__file__).resolve().parents[1]


def _feat_prompt() -> str:
    return """Write the Conventional Commits subject to output/commit.txt (one line). Run the skill script.

```diff
--- a/orders.py
+++ b/orders.py
@@ -1,4 +1,10 @@
+def export_orders_csv(path):
+    rows = load_all_orders()
+    write_csv(path, rows)
+
 def load_all_orders():
     ...
```
"""


def test_agent_entry_writes_feat_message(tmp_path: Path, monkeypatch) -> None:
    from test_judge import _cfg

    pack = tmp_path / "sample-skill"
    shutil.copytree(ROOT / "skills" / "sample-skill", pack)
    skill = ingest_skill(pack, strict=False)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    dest_skill = workspace / ".skillgate" / "skills" / "sample-skill"
    dest_skill.mkdir(parents=True)
    shutil.copytree(pack, dest_skill, dirs_exist_ok=True)
    (workspace / ".skillgate" / "selected.json").write_text(
        '{"skill": "sample-skill"}', encoding="utf-8"
    )
    harness = LLMHarness(_cfg(openai_api_key="sk-test"))
    prompt = _feat_prompt()

    def fake_complete(act_prompt, timeout_sec):
        del act_prompt, timeout_sec
        return Completion(
            text="feat: add csv export for orders",
            usage=Usage(tokens_in=1, tokens_out=1),
        )

    monkeypatch.setattr(harness, "_complete", fake_complete)
    sandbox = LocalSandbox(workspace)
    harness.run(sandbox, prompt, [skill], timeout_sec=5)
    out = workspace / "output" / "commit.txt"
    assert out.is_file(), out
    text = out.read_text(encoding="utf-8")
    assert text.startswith("feat:")
    assert "export" in text.lower()


def test_agent_entry_subject_from_diffs() -> None:
    from skillgate_ai.examples import bundled_example
    import importlib.util

    script = bundled_example("sample-skill") / "scripts" / "agent_entry.py"
    spec = importlib.util.spec_from_file_location("agent_entry", script)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    refactor = """```diff
--- a/pricing.py
+++ b/pricing.py
@@ -4,7 +4,7 @@
-def parseTotal(value):
+def parse_total(value):
     return int(value)
```"""
    assert "refactor:" in mod._subject(refactor)
    assert "parse" in mod._subject(refactor)
