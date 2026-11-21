# Prompt for Claude Opus — split-giant-files spec

Write the complete spec to stdout as markdown only (no preamble). Path on disk after capture: `docs/specs/split-giant-files.md`.

## Mission

Behavior-preserving split of these modules in `src/skillgate_ai/`:

| File | Lines (2026-11-20 on main 82e77aa) |
|------|-------------------------------------|
| harness.py | 2032 |
| engine.py | 1293 |
| cli.py | 1282 |
| cli_pack.py | 506 (register_pack_commands ~489 lines) |
| case_pack.py | 1091 |
| judge_openai.py | 1001 |
| compare.py | 971 |

Targets: no file > ~600 lines, no function > ~100 lines (split oversized functions into helpers in same subpackage).

## Precedent in repo

- `cli_compare.py` already holds `register_compare_commands`; `cli.py` imports it at bottom (E402).
- `cli_pack.py` already holds `register_pack_commands` but the function itself is still one giant nested definition block — break that next.

## Hard constraints for the spec

1. Every **public import path** used anywhere in repo must keep working via re-exports from the original module path (`skillgate_ai.harness`, `skillgate_ai.engine`, `skillgate_ai.cli`, `skillgate_ai.case_pack`, `skillgate_ai.judge_openai`, `skillgate_ai.compare`). List every symbol to re-export per stub module (grep-driven; include test imports of private names like `_run_task`, `_live_verdict`, `_jsonl_transcript`, etc.).
2. **CLI**: command names, options, help strings, exit codes, stdout/stderr text unchanged. Entry points remain `skillgate_ai.cli:app` in pyproject.
3. **No logic/behavior/dependency changes** — moves and thin forwarding only. Lazy imports that exist today stay lazy at the same call sites (or move with the code they guard).
4. **mypy**: ruff + mypy clean after build. **Do not add** entries to `[[tool.mypy.overrides]]`; removals from ignore list for split modules are allowed when typing allows.
5. **Tests**: full `pytest` (unit + `tests/integration`), `tests/test_engine.py`, web tests (`npm test` or project equivalent). Add **one new test file** `tests/test_public_imports.py` that imports every re-exported public symbol from the six modules and asserts `__all__` or an explicit REGISTRY matches.
6. **Commit order**: one file family per commit (spec defines order). After each commit: `ruff check`, `ruff format --check`, `mypy src`, `pytest -q`, web tests if applicable.
7. **Import cycles**: call out risks (especially `cli` ↔ `cli_pack`, `engine` ↔ `harness` ↔ `case_pack`, `compare` ↔ `compare_git` ↔ `gate`).

## Spec document sections (required)

Use the same tone/structure as `docs/specs/integration-tests.md` and `docs/specs/slim-deps-qa-cleanup.md`:

- Title + one-paragraph summary
- **DO-NOT-TOUCH** (tests assertions except import paths; pyproject version; gate.yml bytes; behavior)
- **Acceptance criteria** (line limits, CI commands, import test)
- **Step order** (numbered commits with exact new paths)
- For **each** of the six targets:
  - Proposed package layout (e.g. `harness/` subpackage vs `harness_*.py` siblings — pick one cohesive approach per module and justify)
  - Table: symbol → new defining module (every class, def, constant that moves)
  - What the **shim** file contains (re-exports only; `from X import Y as Y` or `__all__`)
  - Functions >100 lines: how to split (helper names and responsibility)
  - Import-cycle mitigations (TYPE_CHECKING, lazy imports, dependency direction)
- **Public import inventory**: exhaustive list from codebase (at minimum all symbols imported in `tests/` and `src/` from these six modules)
- **New test** `tests/test_public_imports.py`: exact code skeleton
- Delete `docs/specs/_split-giant-files-prompt.md` in final PR (not in step 1)

## Largest functions (must address in spec)

harness: CodexCliHarness.run 69, _infer_from_skill_tool 68, ClaudeCodeHarness.run 66, run_official_login 62, _cursor_prompt 56, _codex_exec_command 55
engine: _run_task 267, run_eval 164, stabilize_adherence_review 95, _run_outcome_judge 87, _eval_progress 78, _live_verdict 60
cli: _run_gate 131, login 89, judge_show 85, case_add_cmd 51
cli_pack: register_pack_commands 489 — split into per-command register functions in separate modules
case_pack: suite_from_pack 80, golden_state 56, dataset_view 49
judge_openai: OutcomeJudge._stamp 143, OutcomeJudge.judge 97, DecisionsBackend.evaluate 47
compare: _run_models_compare 143, _run_versions_compare 113, _versions_dry_run_payload 79

## AST inventory

See attached file `/tmp/skillgate-split-inventory.txt` (full top-level defs).

## CI commands

- `ruff check src tests`
- `ruff format --check src tests`
- `mypy src`
- `pytest -q`
- `pytest -q tests/integration` (or `-m integration` per pyproject markers)
- Web: check `web/package.json` scripts and `.github/workflows/gate.yml` for exact command

Produce the spec now.