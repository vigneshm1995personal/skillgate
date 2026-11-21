## DO-NOT-TOUCH
- All existing files under `tests/`. That includes `tests/conftest.py`, `tests/helpers.py`, `tests/test_gate.py`, `tests/test_check_cli.py`, `tests/test_http_retry.py`, `tests/test_release_072.py`, `tests/test_engine.py`, and every `test_qa_*`, `test_dogfood_*` and `test_release_*` file. If one of them goes red, fix your change, not the test.
- **Do not create `tests/integration/conftest.py`.** pytest runs in `prepend` import mode with no `__init__.py` files, so a second `conftest.py` replaces `sys.modules["conftest"]`. The `tests/integration` directory is collected before `tests/test_*.py`. Once that happens, `from conftest import plain_text` (for example at the top of `test_release_072.py`) and every runtime `from conftest import enable_cursor_agent` would bind to the wrong module. Put shared code in `tests/integration/_support.py` instead.
- Do not add an `__init__.py` anywhere under `tests/`.
- `src/**`, except under the bug rule in "Production fixes" below.
- In `pyproject.toml`: `[project*]`, `[tool.ruff*]`, `[tool.mypy*]`, and every `[tool.pytest.ini_options]` key except `markers`. Keep `timeout = 120` and `pythonpath = ["src", "tests"]`.
- In `.github/workflows/gate.yml`: the jobs `lint`, `gate`, `web-build`, `oss-surface` and `docker`. In the `test` job, change only the single `pytest` line. These strings must stay byte-identical because `test_dockerfile.py` asserts them: `skillgate example pdf --dest /tmp/pdf`, `skillgate ingest /tmp/pdf`, `SKILLGATE_OPENAI_API_KEY`, `--key-env`.
- `.pre-commit-config.yaml`, `Dockerfile`, `skills/`, `src/skillgate_ai/examples/`, `src/skillgate_ai/local_ui/static/`, `web/`.
- `docs/` apart from this spec. Delete `docs/specs/_integration-tests-prompt.md` before the PR; it is scratch. No CHANGELOG entry and no version bump. `test_version_is_078` pins the version.

## Strategy (one strategy for every E2E test; do not mix)
- **Entry point.** Use the real CLI: `typer.testing.CliRunner().invoke(skillgate_ai.cli.app, argv)` in-process, or a real `skillgate` subprocess in `test_cli_subprocess.py` only.
- **Agent seam.** Patch exactly one name: `skillgate_ai.gate.live_harness_or_error`. Replace it with `lambda *_a, **_k: harness`, where `harness` is a `FakeHarness`. The rest of the path is real code and is never patched: `run_check`, `_execute_check`, `ingest_skill(strict=True)`, `resolve_eval_config`, `run_eval`, `_run_task`, `LocalSandbox`, scorers, `collect_workspace_outputs`, `_live_verdict`, `report_to_dict`, `persist_eval` and `append_eval`.
- **Judge seam.** Use the real judge: env `SKILLGATE_JUDGE=openai` plus `SKILLGATE_OPENAI_API_KEY=FAKE_KEY`. Then `resolve_judge` builds the real `OutcomeJudge(DecisionsBackend)`, whose `post=None` means it calls `httpx.post` at request time. Patch the network at exactly one name: `skillgate_ai.openai_http.httpx.post` (the same seam as `test_qa_0710_fixes.py:628`).
- **Forbidden in `tests/integration/`.** Do not patch `skillgate_ai.cli.run_check`, `skillgate_ai.gate.run_eval`, `skillgate_ai.gate.resolve_judge`, `skillgate_ai.engine.*` or `call_with_retry`. The shallow `cli.run_check` mock stays in `test_qa_cli_fixes.py` and is out of scope.
- **Harness name.** `FakeHarness.name = "cursor-agent"`, so `is_live_harness` is True. That gives the real live verdict and the real exit-2 rules for unscored quality.

## What "retry" means here (be exact)
- The product does **not** retry suites, checks, or harness or agent errors. `run_check` runs each task once. A raising harness gives exactly one `harness.calls` entry, and tests assert this.
- The only retry in the check path is `http_retry.call_with_retry`. It is reached through `openai_http.post_openai`, which is called by `DecisionsBackend.evaluate` → `OutcomeJudge.judge` → `engine._outcome_judge` during `skillgate check`.
  - It retries `RetryableStatus` (HTTP 429 or 5xx, unless the 429 is quota-exhausted) and `httpx.TransportError` / `TimeoutException`.
  - It never retries 4xx auth errors.
  - When retries run out it returns the last response, which becomes judge `status=error`. That makes the task `passed=None` and the process exits 2.
- `test_judge_retry.py` drives that path end to end through the CLI. Unit-level retry math stays in `tests/test_http_retry.py`; do not copy it.
- `tests/conftest.py` autouse `_no_http_retry_sleep` already makes backoff instant. One test overrides it with a recorder.

## Step order
Use one PR on branch `cursor/integration-tests` with one commit per step. After each step run `pytest -q && ruff check && ruff format --check && mypy src`, and every step must be green before the next one starts.
1. **Marker.** Edit `pyproject.toml` `markers` (exact text in "pyproject.toml" below). Delete `docs/specs/_integration-tests-prompt.md`.
2. **`tests/integration/_support.py`** plus `test_pack_flow.py`. These need no fakes beyond `make_workspace`.
3. **`test_check_gate.py`.** Write `test_check_green_exit_0_writes_history` first and get it green before writing the rest. It proves the fake harness and the decision-API payload against the real judge.
4. **`test_judge_retry.py`.**
5. **`test_cli_subprocess.py`.**
6. **`test_live_smoke.py`.** Run it once without the env var to confirm the whole module skips.
7. **`gate.yml`** `integration` job, plus the `-m "not integration"` change in the `test` job.
8. **Production fixes**, only if earlier steps exposed a bug, with one commit per bug (see the rule below).

**Production fixes / deviations rule.** When a spec'd assertion fails, decide which case it is:
- **(i) It is a product bug.** The behavior contradicts the CLI docstring "Exit 0 if green, 1 if red, 2 if it cannot run", leaks `FAKE_KEY`, or crashes with a traceback. Make the smallest possible `src/` fix plus a regression assertion. List it in the PR body under **Bugs fixed**.
- **(ii) The spec assumed wrong current behavior** (wrong wording or a wrong count). Change only that literal to the observed value and list it in the PR body under **Spec deviations**, with the observed output.
- In both cases: never delete a test, never turn an exact exit code into a range or `!= 0` (unless this spec already says so), and never turn an exact call count into `>=`.

## tests/integration/_support.py
Imports allowed: stdlib, `httpx`, `pytest`, `typer.testing`, `conftest` (`plain_text`, `enable_cursor_agent`), `skillgate_ai.cli.app`, `skillgate_ai.harness.HarnessResult`, `skillgate_ai.scorers.TriggerEvidence`. Every module-level name below is required, spelled exactly as shown.

- `FAKE_KEY = "sk-test-integration-not-real"`
- `NO_TRIGGER_MARKER = "FastAPI"`. It matches `scaffold.UNRELATED_PROMPT` and the `no-trigger-unrelated` prompt in `skills/pdf`.
- `PASS_ANSWERS: list[dict]`. Six rows of `{"name": k, "choice": v, "confidence": 0.95}`, in this order: `task_completion`/`"Fully completed"`, `correctness`/`"Correct"`, `instruction_adherence`/`"Fully followed"`, `evidence_action_validity`/`"Fully supported"`, `result_quality`/`"Clear and complete"`, `path_efficiency`/`"Efficient"`.
- `runner = CliRunner()`
- `def cli(argv: list[str]) -> tuple[int, str]`: invokes `runner.invoke(app, argv)` and returns `(result.exit_code, plain_text(result.stdout + result.stderr))`. If `result.exception` is set and is not a `SystemExit`, it re-raises it so tracebacks surface.
- `def cli_json(argv: list[str]) -> tuple[int, dict]`: invokes the same way and returns `(exit_code, json.loads(result.stdout))`. Do not run stdout through `plain_text` here.
- `def make_workspace(monkeypatch, tmp_path) -> Path`:
  - `root = tmp_path / "ws"`, then `root.mkdir()`.
  - setenv `SKILLGATE_ROOT=root`.
  - setenv `SKILLGATE_CURSOR_SKILLS`, `SKILLGATE_CODEX_SKILLS` and `SKILLGATE_CLAUDE_SKILLS` to `tmp_path/"cursor-skills"`, `tmp_path/"codex-skills"` and `tmp_path/"claude-skills"`.
  - delenv `SKILLGATE_TASK_TIMEOUT_SEC` and `SKILLGATE_HTTP_RETRY_ATTEMPTS` (`raising=False`).
  - `monkeypatch.chdir(root)`, then return `root`.
- `def enable_live(monkeypatch, root: Path, *, judge_key: bool = True) -> None`: calls `enable_cursor_agent(monkeypatch, root)` and setenv `SKILLGATE_JUDGE=openai`. If `judge_key` is set, it also setenv `SKILLGATE_OPENAI_API_KEY=FAKE_KEY`.
- `def new_pack(root: Path, name: str = "memo") -> Path`: `code, out = cli(["new", name])`, then `assert code == 0, out`, then return `root / "skills" / name`.
- `def example_pack(root: Path, name: str = "pdf") -> Path`: `dest = root / "skills" / name`, then `cli(["example", name, "--dest", str(dest)])`, assert exit 0, and return `dest`.
- `class FakeHarness`:
  - `name = "cursor-agent"`; `supported_models: tuple[str, ...] = ()`.
  - `__init__(self, *, skill: str | None, writes: dict[str, str] | None = None, raises: BaseException | None = None)` sets `self.skill`, `self.writes = writes or {}`, `self.raises`, and `self.calls: list[str] = []`.
  - `run(self, sandbox, prompt, skills, timeout_sec) -> HarnessResult` does the following:
    - appends `prompt` to `self.calls`;
    - raises `self.raises` if it is set;
    - sets `selected = None if NO_TRIGGER_MARKER in prompt else self.skill`;
    - if `selected` is set, writes each `rel → body` pair from `writes` to `Path(sandbox.workspace) / rel` (with `parents=True`);
    - returns `HarnessResult(trigger=TriggerEvidence(selected_skill=selected), transcript=f"fake agent ran: {prompt}", returncode=0)`.
- `def install_harness(monkeypatch, harness: FakeHarness) -> None`: `monkeypatch.setattr("skillgate_ai.gate.live_harness_or_error", lambda *_a, **_k: harness)`.
- `class FakeResponse`:
  - `__init__(self, status_code: int, payload: object, headers: dict[str, str] | None = None)` sets `status_code`, `_payload`, `headers = headers or {}`, and `text = ""`.
  - `json(self)` returns `_payload`.
- `class DecisionAPI`:
  - `__init__(self, script: list[int | BaseException] | None = None, *, default: int = 200, error_code: str | None = None, retry_after: str | None = None)` sets `self.script = list(script or [])` and `self.urls: list[str] = []`, and stores the other arguments.
  - `__call__(self, url, headers=None, json=None, timeout=None)` does the following:
    - appends `str(url)` to `self.urls`;
    - sets `step = self.script.pop(0) if self.script else self.default`, and raises `step` if it is an exception;
    - if `step == 200`, returns `FakeResponse(200, {"answers": PASS_ANSWERS, "model": "decision-test"})`;
    - otherwise sets `err = {"message": f"upstream {step} {FAKE_KEY}"}` (plus `"code": error_code` when one is set), sets `hdr = {"Retry-After": retry_after} if retry_after is not None else {}`, and returns `FakeResponse(step, {"error": err}, hdr)`.
- `def install_decision_api(monkeypatch, api: DecisionAPI) -> DecisionAPI`: `monkeypatch.setattr("skillgate_ai.openai_http.httpx.post", api)`, then return `api`.
- `def history_rows(pack: Path) -> list[dict]`: reads every row from `sorted((pack/"evals"/"history").glob("*.jsonl"))` in file order and returns `[]` if the directory is missing.
- `def run_rows(pack: Path) -> list[dict]`: the history rows with `row.get("kind") == "run"`.
- `def live_check(monkeypatch, tmp_path, harness: FakeHarness, api: DecisionAPI | None = None) -> tuple[Path, Path, DecisionAPI]`: runs `make_workspace` → `enable_live` → `new_pack` → `install_harness` → `install_decision_api(api or DecisionAPI())`, and returns `(root, pack, api)`.

Every test module starts with `pytestmark = pytest.mark.integration`; the live-smoke module uses the list form shown below. Test modules import from `_support` like this: `from _support import ...`. Do not use `from tests.integration._support`.

## tests/integration/test_pack_flow.py
Each test calls `root = make_workspace(monkeypatch, tmp_path)` first.
- `test_init_creates_workspace`: `cli(["init", str(root)])` → `0`, `"Workspace ready at"` in out, `(root/"skills").is_dir()`.
- `test_new_scaffolds_pack_with_two_pinned_cases`:
  - `pack = new_pack(root)`.
  - `(pack/"SKILL.md").is_file()`.
  - `cases = (pack/"evals"/"cases.yaml").read_text()` contains `"should-trigger-1"` and `"no-trigger-unrelated"`.
  - `history_rows(pack) == []`.
- `test_new_then_ingest_strict_ok`: `cli(["ingest", str(new_pack(root))])` → `0`, `"OK  memo"` in out.
- `test_new_rejects_invalid_name`: `cli(["new", "Bad Name"])` → `code != 0`, and `not (root/"skills"/"Bad Name").exists()`.
- `test_example_pdf_writes_pack_and_fixtures`:
  - `pack = example_pack(root)`.
  - `(pack/"SKILL.md").is_file()`, `(pack/"evals"/"cases.yaml").is_file()`, `(pack/"evals"/"goldens"/"extract-hello.txt").is_file()`.
  - `cli(["ingest", str(pack)])` → `0`, `"OK  pdf"` in out.
- `test_example_unknown_name_fails`: `cli(["example", "nope-not-real", "--dest", str(root/"x")])` → `code != 0`, and `not (root/"x"/"SKILL.md").exists()`.
- `test_import_local_folder_copies_skill`:
  - Write `tmp_path/"src"/"notes"/"SKILL.md"` = `"---\nname: notes\ndescription: Summarize meeting notes into action items when the user pastes notes.\n---\n# notes\n"`.
  - `cli(["import", str(tmp_path/"src"/"notes")])` → `0`, `"imported  notes"` in out, `(root/"skills"/"notes"/"SKILL.md").is_file()`.

## tests/integration/test_check_gate.py
Unless a test says otherwise, it uses `root, pack, api = live_check(monkeypatch, tmp_path, harness)`. Then `code, out = cli(["check", str(pack)])`, and at the end `FAKE_KEY not in out`.
- `test_check_green_exit_0_writes_history`:
  - `harness = FakeHarness(skill="memo")` → `code == 0`.
  - out contains `"GREEN"`, `"PASS  should-trigger-1"` and `"PASS  no-trigger-unrelated"`.
  - `len(harness.calls) == 2`.
  - `len(api.urls) == 1` and `api.urls[0].endswith("/decisions")`. Only the trigger case is judged; no-trigger is skipped without HTTP.
  - `rows = run_rows(pack)`; `len(rows) == 1`; `rows[0]["passed"] is True`; `rows[0]["gate"] == "green"`; `rows[0]["run_id"]`; `[t["id"] for t in rows[0]["report"]["tasks"]] == ["should-trigger-1", "no-trigger-unrelated"]`.
  - `FAKE_KEY not in json.dumps(history_rows(pack))`.
- `test_check_red_when_skill_not_triggered_exit_1`:
  - `FakeHarness(skill=None)` → `1`.
  - `"RED"` and `"FAIL  should-trigger-1"` in out; `"PASS  no-trigger-unrelated"` in out.
  - `run_rows(pack)[-1]["passed"] is False` and `["gate"] == "red"`.
- `test_check_json_payload_matches_history`:
  - `cli_json(["check", str(pack), "--json"])` → `0`.
  - `payload["passed"] is True`, `payload["gate"] == "green"`, `payload["task_count"] == 2`, `payload["harness"] == "cursor-agent"`, `payload["failed_task_ids"] == []`.
  - `run_rows(pack)[-1]["report"]["passed"] is True`.
- `test_check_expect_fail_red_suite_exits_0`: `skill=None`, `["check", str(pack), "--expect-fail"]` → `0`, and `"Suite failed as expected (intentional fail)."` in out.
- `test_check_expect_fail_green_suite_exits_1`: `skill="memo"`, `--expect-fail` → `1`, and `"Expected this suite to fail, but the gate was green."` in out.
- `test_check_records_workspace_outputs`:
  - `FakeHarness(skill="memo", writes={"output/notes.md": "# Notes\nhello integration\n"})`.
  - `cli_json(["check", str(pack), "--json"])` → `0`.
  - `task = payload["tasks"][0]`; `task["id"] == "should-trigger-1"`.
  - `row = next(o for o in task["outputs"] if o["path"] == "output/notes.md")`; `"hello integration" in str(row.get("body"))`.
  - The same row is present in `run_rows(pack)[-1]["report"]["tasks"][0]["outputs"]`.
  - `not (pack/"output").exists()`: outputs stay in the sandbox, never in the pack.
- `test_check_harness_error_is_not_retried` (parametrize `(exit_code, passed, gate)` ∈ `(1, False, "red")`, `(2, None, None)`):
  - `FakeHarness(skill="memo", raises=HarnessError("agent crashed", exit_code=exit_code))` → `code == exit_code`.
  - `"agent crashed"` in out; `len(harness.calls) == 1` (no retry); `api.urls == []`.
  - `row = run_rows(pack)[-1]`; `row["passed"] is passed`; `row["gate"] == gate`; `row["error"]["message"] == "agent crashed"`.
- `test_check_agent_timeout_exit_2_hides_prompt`:
  - `raises=subprocess.TimeoutExpired(["agent", "SECRET-PROMPT-XYZ"], 5)` → `2`.
  - `"The agent timed out."` in out; `"SECRET-PROMPT-XYZ" not in out`.
  - `run_rows(pack)[-1]["passed"] is None`.
- `test_check_keyless_exit_2_writes_no_history`:
  - Do **not** call `live_check`. Run `root = make_workspace(...)`, then `pack = new_pack(root)`, then `cli(["check", str(pack)])` → `2`.
  - `"No agent is available"` in out; `history_rows(pack) == []`.
- `test_check_missing_judge_key_exit_2_agent_never_runs`:
  - `make_workspace`, `enable_live(monkeypatch, root, judge_key=False)`, `new_pack`.
  - `harness = FakeHarness(skill="memo", raises=AssertionError("must not run"))`, then `install_harness`.
  - `api = install_decision_api(monkeypatch, DecisionAPI())`.
  - check → `2`; `"API key"` in out; `harness.calls == []`; `api.urls == []`; `history_rows(pack) == []`.
- `test_check_no_judge_flag_skips_decision_api_exit_0`: `skill="memo"`, `["check", str(pack), "--no-judge"]` → `0`, and `api.urls == []`.
- `test_check_single_case_tryout`:
  - `skill="memo"`, `["check", str(pack), "--case", "should-trigger-1"]` → `0`.
  - `len(harness.calls) == 1`; `run_rows(pack)[-1]["tryout"] is True`.
- `test_run_command_mirrors_check`: `skill="memo"`, `cli(["run", str(pack)])` → `0`; `"Prefer `skillgate check` for CI."` and `"GREEN"` in out.
- `test_pdf_example_without_outputs_is_red_and_expect_fail_passes`:
  - `make_workspace`, `enable_live`, `pack = example_pack(root)`.
  - `harness = FakeHarness(skill="pdf")` (it writes no files), `install_harness`, `install_decision_api(DecisionAPI())`.
  - `cli(["check", str(pack)])` → `1`, `"RED"` in out.
  - `cli(["check", str(pack), "--expect-fail"])` → `0`.
  - `len(harness.calls) == 16`, meaning 8 cases × 2 runs.
- `test_green_check_unlocks_deploy`:
  - `skill="memo"`; check → `0`.
  - `cli(["deploy", str(pack), "--target", "cursor"])` → `0`.
  - `(tmp_path/"cursor-skills"/"memo"/"SKILL.md").is_file()`; `not (tmp_path/"cursor-skills"/"memo"/"evals").exists()`; `(pack/"evals"/"deploys.jsonl").is_file()`.
- `test_red_check_blocks_deploy`:
  - `skill=None`; check → `1`.
  - `cli(["deploy", str(pack), "--target", "cursor"])` → `1`.
  - `not (tmp_path/"cursor-skills"/"memo").exists()`.

## tests/integration/test_judge_retry.py
Every test uses `harness = FakeHarness(skill="memo")` and `live_check(..., api=DecisionAPI(...))`, then runs `cli(["check", str(pack)])`. Every test also asserts `FAKE_KEY not in out` and `FAKE_KEY not in json.dumps(history_rows(pack))`.
- `test_judge_503_then_200_is_retried_and_green`:
  - `DecisionAPI([503])` → `0`.
  - `len(api.urls) == 2`; `"GREEN"` in out; `len(harness.calls) == 2` (the agent is not re-run).
- `test_judge_429_honors_retry_after`:
  - Before the check, record sleeps: `sleeps: list[float] = []`, then `monkeypatch.setattr("skillgate_ai.http_retry.sleep", sleeps.append)`.
  - `DecisionAPI([429], retry_after="0")` → `0`.
  - `len(api.urls) == 2`; `sleeps == [0.0]`.
- `test_judge_transport_error_then_success`: `DecisionAPI([httpx.ConnectError("boom")])` → `0`, and `len(api.urls) == 2`.
- `test_judge_503_exhausted_exit_2_not_scored`:
  - setenv `SKILLGATE_HTTP_RETRY_ATTEMPTS=3`; `DecisionAPI(default=503)` → `2`.
  - `len(api.urls) == 3`; `"NOT SCORED  should-trigger-1"` in out.
  - `run_rows(pack)[-1]["passed"] is None`.
- `test_judge_401_is_not_retried_exit_2`: `DecisionAPI(default=401)` → `2`, and `len(api.urls) == 1`.
- `test_judge_quota_429_is_not_retried_exit_2`: `DecisionAPI(default=429, error_code="insufficient_quota")` → `2`, and `len(api.urls) == 1`.

## tests/integration/test_cli_subprocess.py
- Module helpers:
  - `SKILLGATE = shutil.which("skillgate", path=str(Path(sys.executable).parent))`.
  - `pytestmark = [pytest.mark.integration, pytest.mark.skipif(SKILLGATE is None, reason="skillgate entry point not installed in this venv")]`.
- `def _env(tmp_path: Path) -> dict[str, str]`:
  - Start from `{k: v for k, v in os.environ.items() if v}`. The root conftest blanks every key var at import, so the empty ones drop out.
  - Then set `SKILLGATE_ROOT=tmp_path/"ws"`, `HOME=tmp_path/"home"` (created), `CODEX_HOME=tmp_path/"codex-home"` (created), `SKILLGATE_MODE=local`, `NO_COLOR=1`.
  - Set `PATH=f"{Path(sys.executable).parent}{os.pathsep}/usr/bin{os.pathsep}/bin"`, so no signed-in `agent`, `claude` or `codex` binary is found on a dev machine.
- `def _run(tmp_path, *args) -> subprocess.CompletedProcess[str]`: `subprocess.run([SKILLGATE, *args], env=_env(tmp_path), cwd=tmp_path/"ws", capture_output=True, text=True, timeout=120, check=False)`. Create `tmp_path/"ws"` first.
- `test_subprocess_example_ingest_keyless_check_exits_2`:
  - `pack = tmp_path/"ws"/"skills"/"pdf"`.
  - `example pdf --dest <pack>` → rc `0`, `"Wrote"` in stdout.
  - `ingest <pack>` → rc `0`, `"OK  pdf"` in stdout.
  - `before = len(history_rows(pack))`.
  - `check <pack>` → rc `2`, `"No agent is available"` in stdout + stderr.
  - `len(history_rows(pack)) == before`.
- `test_subprocess_check_missing_pack_exits_2`: `check <tmp_path/"ws"/"nope">` → rc `2`; `"Not a skill pack or suite"` in stdout + stderr.
- `test_subprocess_check_json_keyless_emits_error_object`:
  - After `example pdf --dest <pack>`, run `check <pack> --json` → rc `2`.
  - `payload = json.loads(proc.stdout)`; `payload["exit_code"] == 2`; `"No agent is available" in payload["error"]`.
- `test_subprocess_expect_fail_does_not_mask_exit_2`: `example pdf-sabotaged --dest <ws/skills/pdf-sabotaged>`, then `check <that> --expect-fail` → rc `2`. Cannot-run is never turned into a pass.

## tests/integration/test_live_smoke.py
- `pytestmark = [pytest.mark.integration, pytest.mark.skipif(os.environ.get("SKILLGATE_LIVE_SMOKE") != "1", reason="set SKILLGATE_LIVE_SMOKE=1 to run the live smoke")]`.
- Module docstring: the root `conftest.py` blanks every API-key env var when it is imported. So keys and the judge provider must already be set up in a workspace vault: run `skillgate keys set …` and `skillgate judge provider set …` in that workspace, then point `SKILLGATE_LIVE_SMOKE_ROOT` at it. The smoke never runs in CI.
- `@pytest.mark.timeout(960)` on `test_live_check_pdf_single_case`:
  - `raw = os.environ.get("SKILLGATE_LIVE_SMOKE_ROOT", "")`. If it is empty or `not Path(raw).is_dir()`, call `pytest.skip("set SKILLGATE_LIVE_SMOKE_ROOT to a workspace with keys")`.
  - `if not get_llm_config(Path(raw)).has_any_key: pytest.skip("no agent key in SKILLGATE_LIVE_SMOKE_ROOT")`.
  - `skillgate = shutil.which("skillgate", path=str(Path(sys.executable).parent))`; skip if it is `None`.
  - `pack = tmp_path/"pdf"`; `shutil.copytree(ROOT/"skills"/"pdf", pack)` with `ROOT = Path(__file__).resolve().parents[2]`; `before = len(history_rows(pack))`.
  - `env = {k: v for k, v in os.environ.items() if v} | {"SKILLGATE_ROOT": raw}`. Keep the real `PATH` and `HOME`.
  - `proc = subprocess.run([skillgate, "check", str(pack), "--case", "extract-hello", "--json"], env=env, capture_output=True, text=True, timeout=900, check=False)`.
  - `assert proc.returncode in (0, 1), proc.stdout + proc.stderr`. This is the only range allowed in this spec, because the live model is nondeterministic.
  - `payload = json.loads(proc.stdout)`; `[t["id"] for t in payload["tasks"]] == ["extract-hello"]`.
  - `len(history_rows(pack)) == before + 1`.

## pyproject.toml
Replace the `markers` line with:
```toml
markers = [
    "slow: integration tests (git install, etc.)",
    "integration: CLI-to-gate E2E under tests/integration (fake agent + fake decision HTTP; live smoke opt-in)",
]
```

## .github/workflows/gate.yml
- In the `test` job, change `- run: pytest -q` to `- run: pytest -q -m "not integration"`.
- Insert this job directly after `test` and before `gate`. Use 2-space indent under `jobs:`, with no `env:` and no secrets:
```yaml
  integration:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e ".[dev]"
      - name: Integration tests (no network; live smoke skipped)
        run: pytest -q -m integration tests/integration
```

## Acceptance criteria
- `pytest -q` (everything) passes. `pytest -q -m integration tests/integration` passes, collects at least 40 cases, and finishes in under 60 s locally. `pytest -q -m "not integration"` collects 0 tests from `tests/integration/`.
- `pytest -q -m integration tests/integration -rs` reports `test_live_check_pdf_single_case` as SKIPPED when `SKILLGATE_LIVE_SMOKE` is unset.
- `git grep -n "monkeypatch.setattr" tests/integration` shows only these targets: `skillgate_ai.gate.live_harness_or_error`, `skillgate_ai.openai_http.httpx.post`, `skillgate_ai.http_retry.sleep`, and the ones inside `enable_cursor_agent`.
- `tests/integration/` contains exactly these files: `_support.py`, `test_pack_flow.py`, `test_check_gate.py`, `test_judge_retry.py`, `test_cli_subprocess.py`, `test_live_smoke.py`. It has no `conftest.py` and no `__init__.py`.
- No test opens a real socket. With `DecisionAPI` absent, any judge HTTP would fail (it hits the real `httpx.post` with a fake key), so a missing install shows up as a red or exit-2 test, not a silent network call.
- `ruff check`, `ruff format --check`, `mypy src`, `cd web && pnpm test`, `skillgate check skills/pdf` (exit 2 keyless locally without keys) and `skillgate check skills/pdf-sabotaged --expect-fail` all behave exactly as they did on `main`.
- `git diff main -- src/` is empty, unless a commit lists a bug under **Bugs fixed** in the PR body.
- The PR body lists the step commits, the integration test count and runtime, any **Bugs fixed**, and any **Spec deviations** with observed output.

## Explicit non-goals
- No retry added to `run_check`, `run_eval` or the harnesses. No new env vars in `src/`.
- No Docker or `--sandbox docker` coverage. No coverage of `skillgate ui` or `compare`, and no git-URL import (that is `slow`).
- No moving, deleting or deduplicating existing tests (`test_gate.py`, `test_check_cli.py`, `test_qa_cli_fixes.py`, `test_http_retry.py`).
- No changes to `tests/conftest.py` and no new dependencies.
