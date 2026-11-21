# PR 1: Audit security and retries

**Audit:** fe933a5 (6.5/10) · **Scope:** findings (a)–(f) only.

## Step order (test-first)

1. `http_retry.py` — deadline, Retry-After, transient set
2. `helper.py` — non-idempotent POST retries, token write, redirect opener
3. `sandbox.py` — env allowlist
4. `sync.py` — safe `git clone`

## (e) `src/skillgate_ai/http_retry.py`

| Function | Change |
|---|---|
| `is_retryable_exception` | Retry only `httpx.TimeoutException`, `ConnectError`, `ReadError`, `WriteError`, `RemoteProtocolError`, `PoolTimeout`. Do **not** retry all `TransportError`, `UnsupportedProtocol`, or `URLError` with `SSLCertVerificationError`. |
| `call_with_retry` | Use `stop_after_attempt(n) \| stop_before_delay(deadline)`. |
| `_WaitRetryOrExponential.__call__` | Honor full `Retry-After` when ≤ remaining deadline; if `Retry-After` > remaining budget, raise `RetryBudgetExceeded` (subclass of `RetryableStatus`). Exponential waits still cap per-step at `max_wait`. |

### New / updated tests (`tests/test_http_retry.py`)

| Test | Asserts |
|---|---|
| `test_retry_after_exceeds_deadline_raises_budget_exceeded` | `Retry-After: 120` with short deadline → `RetryBudgetExceeded`, one attempt. |
| `test_stop_before_delay_limits_total_time` | Fake clock / patched sleep: total elapsed ≤ deadline. |
| `test_does_not_retry_unsupported_protocol` | `httpx.UnsupportedProtocol` → single attempt. |
| `test_does_not_retry_ssl_cert_verification_urllib` | `URLError(SSLCertVerificationError)` → single attempt. |
| `test_retry_after_honored_within_deadline` | `Retry-After: 7` → sleep 7.0 (update if needed). |
| Update `test_retry_after_capped_at_max_wait` | Renamed/rewritten: long Retry-After within large deadline is honored, not truncated to 30. |

## (a)(c)(d) `src/skillgate_ai/helper.py`

| Function | Change |
|---|---|
| `_http_post` | Add `retries: bool = False`; thread to `_read_json` / `_urlopen_bytes`. |
| `_urlopen_bytes` | Add `retries: bool = True`; pass to `call_with_retry`. |
| `connect` | Call `_write_helper_config` (new) instead of `write_text` + `chmod`. |
| `_write_helper_config` | `mkdir` parent `0o700`; temp file via `os.open(..., 0o600)` + `os.replace` (mirror `keys._write_vault`). |
| `_urlopen` | Module hook wrapping secure `urllib.request.build_opener` (redirect handler strips `Authorization` on scheme/host/port change). |
| `run_helper` | Poll: `_http_post(..., retries=False)`; results: `_http_post(..., retries=True)`. |

### New / updated tests (`tests/test_helper.py`)

| Test | Asserts |
|---|---|
| `test_connect_writes_0600_helper_json` | Still 0600; parent dir 0700 when stat-able. |
| `test_exchange_post_not_retried_on_503` | Mock counts urlopen/call_with_retry: exchange makes one POST attempt on 503. |
| `test_poll_post_not_retried_on_503` | Same for poll. |
| `test_results_post_retries_on_503` | Results path retries transient 503. |
| `test_redirect_strips_authorization_cross_origin` | Redirect to different host → outbound request has no `Authorization`. |
| Patch sites | Tests that patched `urllib.request.urlopen` patch `helper_mod._urlopen` instead. |

## (b) `src/skillgate_ai/sandbox.py`

| Function | Change |
|---|---|
| `_sandbox_env` | Build from explicit allowlist (`PATH`, `HOME`, `LANG`, `LC_*`, `TMPDIR`, `TERM`, etc.) plus `extra`. |
| `_is_secret_env` | **Delete** |

### New tests (`tests/test_sandbox.py`)

| Test | Asserts |
|---|---|
| `test_sandbox_env_allowlist_drops_github_token` | With `GITHUB_TOKEN` set, it is absent from env. |
| `test_sandbox_env_includes_extra_and_python_flags` | `extra` keys present; `PYTHONUNBUFFERED` set. |

## (f) `src/skillgate_ai/sync.py`

| Function | Change |
|---|---|
| `_validate_repo_url` | Reject empty, leading `-`, unsafe schemes. |
| `_redact_repo_url` | Strip userinfo for error messages. |
| `_clone` | `git clone --depth 1 -- <url> <dir>`, `timeout=300`, safe error text. |

### New tests (`tests/test_sync.py`)

| Test | Asserts |
|---|---|
| `test_clone_uses_double_dash_and_timeout` | `subprocess.run` argv contains `--` before URL; `timeout=300`. |
| `test_clone_rejects_option_injection_url` | URL `--upload-pack=...` raises before subprocess. |
| `test_clone_error_redacts_credentials` | URL with `user:pass@` not in exception message. |

## Acceptance criteria

- All unit and integration tests pass.
- `mypy src`, `ruff check .`, `ruff format --check .` pass.
- No secrets printed in tests or logs.

## DO NOT TOUCH

- `pyproject.toml` dependencies, CI workflows, mypy overrides, unrelated refactors.
- Public CLI UX beyond these fixes.
- Idempotency-Key server protocol (hosted repo out of scope).