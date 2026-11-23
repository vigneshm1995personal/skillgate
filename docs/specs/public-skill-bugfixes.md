# Spec: Public skill ingest, harness limits, and pack-local UI history

Status: implementation target on `cursor/public-skill-bugfixes`

## 1. Bugs

### B1 — Nested `metadata` rejected in strict ingest

`ingest_skill(..., strict=True)` calls `_frontmatter_extras` which requires every `metadata` value to be a scalar string. Official skills (googleworkspace/cli, affaan-m ECC) ship nested maps under keys like `openclaw`.

### B2 — Display names fail strict `name` regex

`_require_name` rejects `Zendesk Automation`-style names. Lenient ingest already slugifies; strict mode should slugify, warn, and only fail when slug is empty or still invalid (e.g. consecutive hyphens after normalization).

### B3 — Provider session-limit / auth text in transcripts scored as quality runs

`usage_limit_message` / `auth_failure_message` miss Claude session-limit prose and some transcript-only errors. Runs should become cannot-run (`HarnessError` exit 2, `passed=None`), with the suite stopping on the first blocked task.

### B4 — `skillgate ui --pack` ignores pack for API root

`create_app` deletes the `pack` argument; `AppState.root` stays the workspace/repo. History calls `workspace_history` against the wrong tree → empty timeline despite pack-local `evals/history/*.jsonl`.

## 2. Files and functions

| Bug | File | Function(s) |
| --- | --- | --- |
| B1 | `src/skillgate_ai/ingest.py` | `Skill.metadata` type, `_frontmatter_extras`, `ingest_skill` |
| B2 | `src/skillgate_ai/ingest.py` | `slugify_skill_name`, `_require_name`, `folder_matches_skill`, `ingest_skill` |
| B3 | `src/skillgate_ai/harness/messages.py` | `_USAGE_LIMIT_RE`, `usage_limit_message`, `auth_failure_message`, `cannot_run_message` |
| B3 | `src/skillgate_ai/engine/run.py` | `_run_tasks_loop`, `_blocked_task_report`, `_fill_halted` |
| B4 | `src/skillgate_ai/api.py` | `create_app` |
| B4 | `src/skillgate_ai/cli/cmd_ui.py` | `ui_cmd` workspace selection |
| B4 | `src/skillgate_ai/api_payloads.py` | `workspace_history` pack-root fallback |

## 3. Tests (exact names and assertions)

| Test | Asserts |
| --- | --- |
| `test_ingest_strict_nested_metadata` | Strict ingest accepts `metadata: {openclaw: {nested: true}}`; value preserved on `Skill.metadata` |
| `test_ingest_strict_slugifies_display_name` | Strict ingest of `name: Zendesk Automation` → `zendesk-automation`, warning mentions normalized |
| `test_ingest_strict_slugify_empty_raises` | `name: '!!!'` raises `IngestError` |
| `test_usage_limit_claude_session_limit_transcript` | `usage_limit_message` matches `You've hit your session limit · resets` in transcript |
| `test_usage_limit_cursor_weekly_in_transcript` | Weekly limit string in transcript returns message |
| `test_auth_failure_in_transcript` | `auth_failure_message` sees `not logged in` in transcript text |
| `test_run_eval_halts_after_transcript_session_limit` | Two-task suite: first transcript has session limit → one harness call, `HarnessError` or halted second task |
| `test_create_app_pack_sets_root` | `create_app(pack=tmpdir)` → `app.state.ui.root == tmpdir` |
| `test_workspace_history_pack_root` | `workspace_history(AppState(pack))` timeline length matches `load_history` rows |

## 4. Implementation order

1. B4 `create_app` / `cmd_ui` / `workspace_history` fallback  
2. B1 metadata typing + `_frontmatter_extras`  
3. B2 slugify in strict `_require_name` + `folder_matches_skill`  
4. B3 harness patterns + optional `run.py` halt fill  
5. Tests, `./scripts/ci.sh` or project test command, live repro  

## 5. Acceptance criteria

- Unmodified googleworkspace/cli and ECC skills ingest with `strict=True`  
- claude-office-skills capitalized names ingest with warning  
- Simulated session-limit transcript → cannot-run, suite does not score remaining tasks as pass/fail  
- `skillgate ui --pack <pack>` History API shows pack tryouts (e.g. 18 rows for customer-billing-ops repro)  
- CI green  

## 6. DO-NOT-TOUCH

- `src/skillgate_ai/mcp/**` (except if unavoidable — not needed here)  
- `plugin/**`  
- `.github/workflows/**`  
- `.skillgate/keys`, `~/.skillgate`  
- `MARKETING_VERSION` / version bumps unrelated to fixes  

## 7. Live verification (Mini)

- Ingest public skills unmodified; claude-office-skills shows warnings  
- `skillgate ui --host 127.0.0.1 --pack ~/skillgate-runs/.../customer-billing-ops` → `GET /api/history` timeline count 18  
- Fixture transcript session-limit → excluded from scoring  