# Audit scorecard — structure, typing, CI (PR C/3)

Behavior-preserving refactor: five module splits, deeper typing in four hot files, coverage floor, `pip-audit`, and CodeQL. Wire goldens and runtime behavior are unchanged.

## Metrics

| Metric | Before | After | Command |
|---|---|---|---|
| `span_facts` (monolith lines) | 678 | — (max submodule 276) | `wc -l` |
| `pack` | 661 | — (max 159) | |
| `report` | 648 | — (max 216) | |
| `judge_spec` | 627 | — (max 293) | |
| `engine/run.py` | 590 | 198 + helpers ≤160 each | |
| Largest `src/skillgate_ai` `.py` (excl. examples) | 678 | 614 (`advice.py`) | `find … \| sort -n \| tail` |
| `dict[str, Any]` lines (all `src`) | 516 | 480 | `rg -c 'dict\[str, Any\]' src/skillgate_ai` |
| `judge_openai/outcome.py` | 26 | 12 | per-file `rg` line count |
| `fixture_bind.py` | 20 | 7 | |
| `api_skills.py` | 18 | 17 | |
| `compare/payload.py` | 18 | 10 | |
| `Mapping[str, Any]` lines | — | 145 | `rg -c 'Mapping\[str, Any\]' src` |
| `TypedDict` classes | — | 26 | `rg 'class .+\(TypedDict'` |
| Broad `except Exception` | 20 | 20 | unchanged this PR |
| Unit test coverage | 77% | 77.39% | `pytest -m "not integration" --cov` |
| Unit tests passed | 1282 | 1463 | `pytest -m "not integration"` |

## Kept `dict[str, Any]` (selected)

| File | Reason |
|---|---|
| `api_skills.py` route handlers | FastAPI `response_model` / return contract |
| `judge_openai/outcome.py` `_extra_cell` cleaned blob | Mutable passthrough returned to callers |
| `compare/payload.py` `CompareResult.payload` | Stored compare JSON boundary |
| `fixture_bind.py` `_template_check`, `decide_gate*` | Returned into `metrics_blocking(dict)` |

## Scanners and gates

| Scanner | Where | Blocks merge |
|---|---|---|
| ruff (incl. S, BLE) | `gate.yml` lint | Yes |
| mypy | lint | Yes |
| pytest unit + integration | 3.11–3.13 matrix | Yes |
| coverage ≥ 77% | `test-matrix` on 3.12 | Yes |
| pip-audit (locked, hashed) | `audit` job | Yes |
| CodeQL (python, js/ts, actions) | `codeql.yml` | After ruleset (manual) |
| pinned SHAs + `uv.lock` | workflows | — |

## Open items

- S101 bare asserts in `judge_settings.py` (separate PR; may fail `ruff check` until merged)
- 20 broad `except Exception` handlers
- CodeQL alert triage and branch ruleset enablement (admin)
- Raise coverage floor after further tests land

_Footnote:_ PR C row `dict[str, Any]` "After 480" was re-measured on `cc8919a` as 583; see PR D.

## PR D/4 — excepts, typing, last splits, coverage

| Metric | Before (cc8919a) | After | Command |
|---|---|---|---|
| Broad `except Exception` | 23 (16 files) | 15 (documented boundaries) | `grep -rnE 'except Exception\b' src/skillgate_ai \| wc -l` |
| `dict[str, Any]` lines (all src) | 583 | 550 | `grep -rn 'dict\[str, Any\]' src/skillgate_ai \| wc -l` |
| `judge_openai/outcome.py` | 12 | 6 (cap ≤ 11) | `grep -c` |
| `fixture_bind.py` / `api_skills.py` / `compare/payload.py` | 7 / 17 / 10 | 3 / 14 / 4 (planned) | `grep -c` |
| Largest module | 715 (`tool_checks.py`) | 560 (`engine/task.py`) | `wc -l … \| sort -n` |
| Modules > 600 lines | 3 | 0 | |
| Unit coverage | 77.39% | 80.77% | `pytest -m "not integration" --cov` |
| `fail_under` | 77 | 80.5 | `pyproject.toml` |
| Unit tests passed | 1671 | 1855 | |

### Open items (post D)

- Coverage target ~85% / `dict[str, Any]` ≤ 520 needs more B2 + D3 tests (FastAPI routes and `mcp/` frozen)
- `judge_settings` S101, CodeQL triage

## PR F (Option B) — layering, strict FS mypy, gate payloads

| Metric | Before (`9b91ccb6`) | After | Command |
|---|---|---|---|
| `dict[str, Any]` lines (all `src`) | 516 | 490 | `grep -rn 'dict[str, Any\]' src/skillgate_ai --include='*.py' \| wc -l` |
| `mcp/` `dict[str, Any]` lines | 46 | 46 | same under `src/skillgate_ai/mcp` |
| `TypedDict` classes | 27 | 29+ | `grep -rnE 'class \w+\(TypedDict' src/skillgate_ai` |
| import-linter contracts | 0 | 4 kept | `lint-imports` |
| mypy strict modules | 4 | 13 (`agent_roots`, `scrub`, FS core) | `pyproject.toml` overrides |
| Unit coverage | ~84.06% | ~84.09% | `pytest -m "not integration" --cov` |
| Unit tests passed | 2138 | 2155+ | `pytest -m "not integration"` |

### Open items (post F)

- CodeQL alert triage (admin); FS `layers` contract (Option C)
- `engine/models.py` dataclass fields stay `dict[str, Any]` (judge protocol boundary)
- Branch coverage / `fail_under` ≥ 84.5 deferred