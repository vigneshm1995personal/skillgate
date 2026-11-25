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