# Spec: Remove the one-off split helper scripts left over from PR #73

## Goal
Delete the four one-off helper scripts that were used to do the split in PR #73 (`341b36f`, "Split giant modules into packages"). Nothing in the package, the tests, CI, the GitHub Action or packaging uses them. This is a delete-only change. It must not change any runtime behavior, tests, CI or packaging.

## Files to delete
Delete exactly these four files:

| Path | Action |
|---|---|
| `scripts/split_package.py` | delete |
| `scripts/post_process_cli.py` | delete |
| `scripts/engine_task_helpers.py` | delete |
| `scripts/fix_harness_deps.py` | delete |

```bash
git rm scripts/split_package.py scripts/post_process_cli.py scripts/engine_task_helpers.py scripts/fix_harness_deps.py
```
If any of them is untracked, `git rm` will fail. Delete that one with plain `rm`.

**Keep:**
- `scripts/skillgate_action.py`: `action.yml:71` runs it with `python "${{ github.action_path }}/scripts/skillgate_action.py"`.
- `scripts/extract-from-skillgate-ai.sh`: a maintainer helper that PR #73 left untouched on purpose.
- Everything under `skills/**/scripts/`.

`scripts/__pycache__/` is local build output. You may delete it locally, but it is not part of this change.

## .gitignore
**Remove zero `.gitignore` lines.** No ignore rule exists for any of the four helper scripts. The only ignore line PR #73 added was `.spec-prompt-slim-deps.txt`. That line is for the slim-deps prompt, not the split helpers. **Do NOT remove `.spec-prompt-slim-deps.txt`.** `.gitignore` must stay byte-identical.

## Grep proof
Search the whole repo (excluding `.git`, `.venv`, `node_modules`) for references to the four scripts:

```bash
grep -rn -E "split_package|post_process_cli|engine_task_helpers|fix_harness_deps" \
  --exclude-dir=.git --exclude-dir=.venv --exclude-dir=node_modules .
```
```
scripts/split_package.py:112:def split_package(
scripts/split_package.py:191:    split_package(
```
The only two hits are inside `split_package.py` itself, so nothing else references these scripts.

| Location | Reference to the four scripts? | Notes |
|---|---|---|
| `src/**` | none | |
| `tests/**` | none | |
| `pyproject.toml` | none | `[project.scripts]` (line 77) only defines the console entry points `skillgate` / `skillgate-ai` |
| `.github/workflows/gate.yml` | none | Runs `ruff check`, `ruff format --check`, `mypy src`, `pytest -q -m "not integration"`, `pytest -q -m integration tests/integration` and `pytest -q tests/test_oss_surface.py tests/test_dockerfile.py` |
| `action.yml` | none | Only uses `scripts/skillgate_action.py` |
| `Dockerfile` | none | |
| `docs/**` | none | |

After the deletion, `ls scripts` (ignoring `__pycache__`) must list exactly:
```
extract-from-skillgate-ai.sh
skillgate_action.py
```

## Acceptance criteria
1. The four files above no longer exist, and `git status` shows exactly four deletions under `scripts/`.
2. Running the grep proof command again prints nothing.
3. `.gitignore`, `pyproject.toml`, `action.yml`, `Dockerfile` and `.github/**` are unchanged (`git diff --stat main -- .gitignore pyproject.toml action.yml Dockerfile .github` is empty).
4. Every command under "Verification commands" exits 0.
5. The file-size check from `docs/specs/split-giant-files.md` still prints `ok`. Every `.py` file in the `harness`, `engine`, `cli`, `case_pack`, `judge_openai` and `compare` packages, plus `cli_pack.py`, must be ≤ 600 lines, and every `def` in them must be ≤ 100 lines.

## Verification commands
Run from the repo root, inside an activated `.venv`:

```bash
pip install -e '.[dev]'
ruff check
ruff format --check
mypy src
pytest -q
pytest -q -m integration tests/integration
python - <<'EOF'
import ast, pathlib
base = pathlib.Path("src/skillgate_ai")
files = [base / "cli_pack.py"] + [p for d in ("harness","engine","cli","case_pack","judge_openai","compare") for p in (base / d).rglob("*.py")]
bad = []
for p in files:
    text = p.read_text(encoding="utf-8")
    if text.count("\n") > 600: bad.append(f"{p}: {text.count(chr(10))} lines")
    for n in ast.walk(ast.parse(text)):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.end_lineno - n.lineno + 1 > 100:
            bad.append(f"{p}:{n.lineno} {n.name} {n.end_lineno - n.lineno + 1}")
print("\n".join(bad) or "ok"); raise SystemExit(1 if bad else 0)
EOF
rg -n 'split_package|post_process_cli|engine_task_helpers|fix_harness_deps' \
  src tests .github pyproject.toml action.yml Dockerfile scripts ; test $? -eq 1
```

## DO-NOT-TOUCH
- `src/**`: no edits.
- `tests/**`: no edits, additions or deletions.
- `.github/**`, including `.github/workflows/gate.yml`, which must stay byte-identical.
- `action.yml`
- `Dockerfile`
- `pyproject.toml`: no edits. You would only remove a reference to one of the four scripts, and none exists.
- `.gitignore`: no edits. In particular, keep `.spec-prompt-slim-deps.txt`.
- `scripts/skillgate_action.py` and `scripts/extract-from-skillgate-ai.sh`
- `skills/**`, including every `skills/**/scripts/` directory.
- `docs/**`: no edits except adding this spec (`docs/specs/remove-split-scripts.md`).
- `CHANGELOG.md`, `.pre-commit-config.yaml` and `web/`
