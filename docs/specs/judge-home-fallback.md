# Judge & Keys Home Fallback (`~/.skillgate`)

## 1. Summary

`skillgate check`, `skillgate judge provider show`, `skillgate judge test`, and the local UI will now use a decision model and API keys saved in your home folder (`~/.skillgate/judge` and `~/.skillgate/keys`) when the current project hasn't set its own. A brand-new project with no `.skillgate/` folder will no longer exit 2 with "Pick a decision model before running a live check." if a judge is already chosen in `~/.skillgate/judge`. Project files still win. A project judge that is chosen beats the home judge, and a project key beats a home key with the same name. `SKILLGATE_JUDGE*` and `SKILLGATE_*_API_KEY` env vars work exactly as before. Every write (`judge provider set`, `keys set`, `keys clear`, UI `PUT /api/settings/judge`, UI key save/clear) still goes only to `{project}/.skillgate/`. Nothing ever writes to `~/.skillgate`. If neither the project nor home has a chosen judge, you get the same message as today, with exit code 2.

## 2. Precedence tables

### 2.1 Definitions

- **Project root**: the `root` argument passed to the loader. When `root is None`, it is `paths.project_root()`, which honours `SKILLGATE_ROOT`. `gate.run_check` already turns `root` into `config_root_for(suite_path)` when neither `root` nor `SKILLGATE_ROOT` is set (`gate.py:126-133`). That root then flows into `get_llm_config(project)`. **No change to root resolution.**
- **Home dir**: `Path.home() / ".skillgate"`, read fresh on every call (never cached at import time) so tests can monkeypatch `HOME` / `USERPROFILE`.
- **Selects a provider** (the file-level test that decides fall-through): the file exists, parses as a JSON object, and its normalized `provider` is **not** in `{"", "auto", "skip"}`.
  - This is deliberately **not** `JudgeProviderSettings.chosen`. A project file holding a removed id (`aws`, `other`, …) or an unknown id still counts as selecting a provider. It does **not** fall through to home, so today's `REMOVED_SETUP` / `NOT_A_DECISION_MODEL` errors keep showing for that project.
  - A file that is missing, unreadable, not JSON, or not a dict counts as "does not select".
- **Same-file dedupe**: if `project/.skillgate` and the home dir resolve to the same path (for example, running in `~` with no `skills/`), read it once. It counts as **project**.

### 2.2 Effective judge settings (`load_judge_settings`, which `get_llm_config` / `resolve_judge` / `judge provider show` / `GET /api/settings/judge` use)

| Step | Source | Used when | Result |
|---|---|---|---|
| 1 | **Env** `SKILLGATE_JUDGE` (`auto`/`openai`/`skip`), `SKILLGATE_JUDGE_BACKEND`, `SKILLGATE_JUDGE_MODEL`, `SKILLGATE_JUDGE_WHY`, `…_TIMEOUT_SEC`, `…_MIN_CONFIDENCE`, `…_REASONING_EFFORT` | Always applied **after** file resolution, in `get_llm_config` (`cfg.judge_pref` etc.) and `resolve_judge` | Unchanged. In `resolve_judge`, `endpoint_id = pref if pref not in {"", "auto"} else cfg.judge_provider`. So `SKILLGATE_JUDGE=openai` forces openai whatever either file says, and `SKILLGATE_JUDGE=skip` still raises `NEEDS_DECISION_MODEL` for live harnesses. `SKILLGATE_JUDGE=auto` or unset defers to steps 2–4. |
| 2 | **Project** `{project}/.skillgate/judge` | File selects a provider (§2.1) | Return the project settings **whole** |
| 3 | **Home** `~/.skillgate/judge` | Project does not select **and** the home file selects a provider | Return the home settings **whole** (no merging fields between files) |
| 4 | Fallback | Neither selects | Return the project file's parsed settings if it parsed (for example, an explicit `{"provider":"auto"}`), else `JudgeProviderSettings()`. `provider="auto"`, `chosen=False` → `resolve_judge` raises `NEEDS_DECISION_MODEL`, exit 2; `judge provider show` prints the message and exits 2. |

Notes:
- Env never changes which **file** is picked. It only overrides `judge_pref` / backend / model in `LLMConfig`, exactly as today.
- `cfg.judge_chosen` / `judge_provider` / `judge_region` / `judge_endpoint` / `judge_provider_model` / `judge_key_env` / `judge_account_id` all come from the one settings object chosen above. `_openai_from_cfg`'s `chosen` check therefore works the same for a home openai judge as for a project one.
- `key_env` stored in a home judge file is carried into `cfg.judge_key_env`, the same as a project one. It does **not** auto-bind ambient env (no change: binding still happens only through `--key-env` → `bind_key_env`).

### 2.3 Effective API keys (`resolve_provider_keys`, used by `get_llm_config`, `key_presence`, `keys list`, the UI keys payload, and `has_any_key`)

Merge order. A later layer overwrites an earlier one, except the home layer, which only fills gaps:

| Apply order | Source | Rule |
|---|---|---|
| 1 | **Home vault** `~/.skillgate/keys` | Base layer. Only `PROVIDER_KEY_NAMES` with non-empty values (same `_read_env_file` parsing). |
| 2 | **Project vault** `{project}/.skillgate/keys` | Overwrites home for the same name. |
| 3 | **`SKILLGATE_*` env overlay** (`SKILLGATE_KEY_ENV`) | Overwrites both vaults when non-empty (unchanged). |
| 4 | **Bound ambient** env (`bind_key_env` / `--key-env`) | Overwrites everything when non-empty (unchanged). |

Effective winner for one name, highest first: bound ambient > `SKILLGATE_*` > project vault > home vault. This matches the required "project vault, env overlay, bound ambient, then home fills gaps only". Home never overrides a value that any other layer set.

Product side effect (intended and documented): home-vault **agent** keys (`CURSOR_API_KEY`, `CODEX_API_KEY`, `ANTHROPIC_API_KEY`) also become visible to `has_any_key` and harness selection, because they go through the same `resolve_provider_keys`.

## 3. Exact code changes

### 3.1 `src/skillgate_ai/paths.py`

Add:

```python
def user_skillgate_dir() -> Path:
    """Per-user fallback folder `~/.skillgate` (read-only fallback; never written)."""
    return Path.home() / ".skillgate"
```

- No `.resolve()` at definition time and no module-level constant, so `HOME` stays monkeypatchable. Callers resolve when comparing paths.
- **Do not change** `project_root()` or `config_root_for()`.

### 3.2 `src/skillgate_ai/keys.py`

1. Add `home_keys_path() -> Path`, returning `user_skillgate_dir() / KEYS_FILENAME`. Import `user_skillgate_dir` from `skillgate_ai.paths`. `paths` has no `keys` import, so this creates no import cycle.
2. Add `read_home_vault(root: str | Path) -> dict[str, str]`:
   - If `home_keys_path().expanduser().resolve() == keys_path(root)`, return `{}` (same-file dedupe; the project read already covers it).
   - Else return `_read_env_file(home_keys_path())`. On `OSError` from `resolve()`, return `{}`.
3. Pull the env layers out into a private helper with no behaviour change:
   ```python
   def _env_overlay() -> dict[str, str]:
       # SKILLGATE_* then bound ambient — exact code currently in resolve_provider_keys
   ```
4. `resolve_provider_keys(root)` becomes:
   ```python
   found = dict(read_home_vault(root))
   found.update(read_vault(root))
   found.update(_env_overlay())
   return found
   ```
   Update the docstring to: "Home vault (gaps only), project vault, SKILLGATE_* overlay, --key-env ambient names. Never bare provider env."
5. **Unchanged**: `read_vault`, `_write_vault`, `set_vault_key`, `clear_vault_key`. They stay project-only. `set_vault_key` must keep calling `read_vault(root)` (project) and never `resolve_provider_keys`, so home keys are never copied into the project file.
6. `key_presence(root)`: add a `from_home` flag. Existing flags keep their meaning:
   ```python
   vault = read_vault(root)
   home = read_home_vault(root)
   overlay = _env_overlay()
   resolved = resolve_provider_keys(root)
   ...
   in_vault = name in vault
   from_home = name in home and not in_vault and name not in overlay
   from_env = bool(resolved.get(name)) and not in_vault and not from_home
   keys[name] = {"set": ..., "from_vault": in_vault, "from_env": from_env, "from_home": from_home}
   ```
   `from_vault` keeps meaning "in the project vault", even when env overrides it, exactly as today. `tests/test_keys.py:71-72` and `tests/test_api_local.py:171,639` must still pass.
7. `public_key_presence`, `list_key_names`: no code change (they inherit through `key_presence`).

### 3.3 `src/skillgate_ai/judge_settings.py`

1. Move the parse logic out of `load_judge_settings` into
   `_read_judge_file(path: Path, *, migrate: bool) -> JudgeProviderSettings | None`:
   - Returns `None` when the file is missing, unreadable, not JSON, or not a dict (today's branches that return `JudgeProviderSettings()`).
   - Otherwise builds `JudgeProviderSettings` with exactly today's normalization.
   - Calls `_rewrite_judge_file(path, settings)` for the legacy `decisions_path` migration **only when `migrate=True`**. Home files are read with `migrate=False`, so Skill Gate never writes to `~/.skillgate`.
   - If `_account_id` raises `SkillGateError` for a malformed home `account_id`, catch it **for home reads only** and treat the home file as "does not select" (return `None`). Project reads keep raising as today.
2. Add `_selects_provider(settings: JudgeProviderSettings | None) -> bool`: `settings is not None and settings.provider not in {"", "auto", "skip"}`.
3. Add `home_judge_settings_path() -> Path`, returning `user_skillgate_dir() / JUDGE_FILENAME`.
4. Add `load_project_judge_settings(root: str | Path | None = None) -> JudgeProviderSettings`. This is the **old** `load_judge_settings` behaviour (project file only, `migrate=True`, default when missing). Nothing in `src/` needs it today. It exists so tests can assert on the project file alone, and for any future write-adjacent read.
5. Change `load_judge_settings(root=None)` to return the **effective** settings:
   ```python
   project_path = judge_settings_path(root)  # root None → project_root() → honours SKILLGATE_ROOT
   project = _read_judge_file(project_path, migrate=True)
   if _selects_provider(project):
       return project
   home_path = home_judge_settings_path()
   if _same_file(home_path, project_path):
       return project or JudgeProviderSettings()
   home = _read_judge_file(home_path, migrate=False)  # SkillGateError from account_id → None
   if _selects_provider(home):
       return home
   return project or JudgeProviderSettings()
   ```
   `_same_file` compares `expanduser().resolve()` and treats `OSError` as not-same.
   Update the module docstring: "`{project}/.skillgate/judge`, falling back to `~/.skillgate/judge` when the project has none chosen."
   - **Decision:** change `load_judge_settings` itself instead of adding a separate `load_judge_settings_effective`. Every current caller (`config.get_llm_config`, `cli/cmd_judge_provider.judge_provider_show`, `api.get_judge_settings`) wants the effective value. Changing the function fixes all three with no call-site edits, and no caller can be missed.
6. **Unchanged**: `judge_settings_path`, `save_judge_settings` (still writes only `judge_settings_path(root)`), `_rewrite_judge_file`, `decision_judges`, `JudgeProviderSettings` (no new fields, so `to_public_dict` and the UI payload shape are unchanged).

### 3.4 `src/skillgate_ai/config.py`

- `get_llm_config(root)`: **no code change.** It already calls `resolve_provider_keys(root or project_root())` and `load_judge_settings(root or project_root())`, and both are now home-aware. All `SKILLGATE_JUDGE*` handling (`_judge_pref`, `_judge_backend`, `_opt("SKILLGATE_JUDGE_MODEL")`, `_env_bool("SKILLGATE_JUDGE_WHY")`) is untouched.
- `load_env` is untouched. Do **not** load `~/.env`.

### 3.5 `src/skillgate_ai/judge.py`

- `resolve_judge`: **no change.** It reads `cfg.judge_provider` / `cfg.judge_pref`, which are now home-aware upstream. The `NEEDS_DECISION_MODEL` path and message are unchanged.

### 3.6 `src/skillgate_ai/cli/cmd_judge_provider.py`

- `judge_provider_show`: **no code change.** `load_judge_settings(root)` is now effective. Output (`format_provider_selection`) and exit codes are unchanged: 0 when a provider is selected, 2 with `NEEDS_DECISION_MODEL_HINT` otherwise.
- `judge_provider_set`: **no change.** Writes `{project_root()}/.skillgate/judge` only. Docstring stays "Write `.skillgate/judge`."
- `_run_judge_test`: no change (inherits through `get_llm_config`).

### 3.7 `src/skillgate_ai/cli/cmd_keys.py`

- `keys_list`: label the source correctly so a home key isn't reported as an env key:
  ```python
  if meta["from_vault"]:
      source = "Settings"
  elif meta.get("from_home"):
      source = "~/.skillgate/keys"
  else:
      source = "SKILLGATE_* / --key-env"
  ```
- `keys_set` / `keys_clear`: no change. `keys_clear` keeps checking `read_vault(root)` (project only), so clearing a name that exists only in home still prints "No … in Settings." and exits 1. It never touches home.

### 3.8 Web API (`src/skillgate_ai/api.py`, `src/skillgate_ai/api_payloads.py`)

- `GET /api/settings/judge` (`api.py:233-239`): no code change. It now returns the effective (possibly home) settings through `load_judge_settings(state.root)`.
- `PUT /api/settings/judge` (`api.py:241-263`): no change. It writes the project file through `save_judge_settings(state.root, …)`.
- `POST /api/judge/ping`, `api_runs`, `api_skills`, `api_compare` `has_any_key` checks: no change (they inherit through `get_llm_config`).
- `keys_payload` (`api_payloads.py:74-84`): no code change. Each entry gains the extra `from_home` boolean from `key_presence`. This is additive JSON, and the React app ignores unknown fields. **No `web/` change and no `web_static/` rebuild.**

### 3.9 `tests/conftest.py`

Add an autouse fixture so the whole suite can **never** read the developer's real `~/.skillgate`. Once 3.2 and 3.3 land, every existing test that calls `load_judge_settings` / `resolve_provider_keys` would otherwise pick up the real home files.

```python
@pytest.fixture(autouse=True)
def _isolate_user_home(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Never let pytest read the developer's ~/.skillgate judge or keys."""
    home = tmp_path_factory.mktemp("user-home")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home
```

Place it next to `_isolate_codex_home`. Existing HOME-dependent code is safe with this:
- `deploy.py` honours the `SKILLGATE_*_SKILLS` overrides.
- `helper.CONFIG_DIR` is computed at import time, before fixtures run.
- `launchd` tests should already patch their target. If one breaks, patch that test, not the fixture.

### 3.10 Explicitly not changed (investigated)

- **`paths.config_root_for`**: walks up from the pack and returns the first match in this order: workspace (`skills/`), then nearest `.skillgate/keys`, then pack. Known pre-existing quirk: for a standalone pack under `$HOME` (no `skills/` above it) and an existing `~/.skillgate/keys`, the walk returns `$HOME` as the config root. Today that accidentally makes `~/.skillgate/judge` the "project" file. After this change that case is still correct, because the same-file dedupe treats it as project. Leave `config_root_for` alone in this PR. Excluding `Path.home()` from the `nearest_keys` match is a follow-up.
- **`gate.run_check`**: root resolution is unchanged. It calls `get_llm_config(project)` with the resolved `project`, and home fallback applies on top.
- **`load_judge_settings(None)` / `get_llm_config(None)`**: the project root comes from `project_root()`, which already honours `SKILLGATE_ROOT`. `SKILLGATE_ROOT` has **no** effect on the home path.

## 4. Tests

New file: **`tests/test_judge_home_fallback.py`**. Each test uses two sibling `tmp_path` dirs, `home/` and `proj/`. The project is **not** inside the fake home, so `config_root_for` can't walk up into it. Each test sets:

```python
monkeypatch.setenv("HOME", str(home))
monkeypatch.setenv("USERPROFILE", str(home))
monkeypatch.setenv("SKILLGATE_ROOT", str(proj))
```

Helpers write `home/.skillgate/judge` as JSON and `.skillgate/keys` as `NAME=value` lines (mode 0600). No test touches the real `~`. The autouse conftest fixture is the backstop.

Judge settings:
1. `test_home_judge_used_when_project_has_no_skillgate_dir`: only `home/.skillgate/judge = {"provider":"openai"}`. Assert `load_judge_settings(proj).provider == "openai"` and `.chosen`. Assert `get_llm_config(proj).judge_provider == "openai"` and `judge_chosen is True`. Assert `load_project_judge_settings(proj).provider == "auto"`.
2. `test_home_judge_used_with_root_none`: same setup, call `load_judge_settings()` / `get_llm_config()` with no argument (root from `SKILLGATE_ROOT`). Expect openai.
3. `test_cli_show_sees_home_judge`: `CliRunner().invoke(app, ["judge", "provider", "show"])` → `exit_code == 0`, and `"openai"` appears in `plain_text(output)`. `"Pick a decision model"` does not appear.
4. `test_project_judge_overrides_home`: home openai, project `{"provider":"jev"}`. Expect `jev` from `load_judge_settings`, `get_llm_config`, and CLI show.
5. `test_project_auto_falls_through_to_home`: project `{"provider":"auto"}`, home openai → openai. Repeat (parametrize) with project `{"provider":""}`, `{"provider":"skip"}`, invalid JSON `"{"`, and a JSON list `[]` → all give openai.
6. `test_project_removed_id_does_not_fall_through`: project `{"provider":"aws"}`, home openai. `load_judge_settings(proj).provider == "aws"`, and `resolve_judge(get_llm_config(proj), harness_name="cursor-agent")` raises `SkillGateError` with `REMOVED_SETUP`.
7. `test_neither_selects_still_needs_decision_model`: no files (and, parametrized, both files `{"provider":"auto"}`). `load_judge_settings(proj).provider == "auto"`. `resolve_judge(get_llm_config(proj), harness_name="cursor-agent")` raises `SkillGateError` with `message == NEEDS_DECISION_MODEL` and `exit_code == 2`. CLI show gives exit 2 and the message.
8. `test_home_auto_not_used`: home `{"provider":"auto"}`, no project file → `auto`.
9. `test_env_pref_overrides_home_judge`: home `{"provider":"jev"}`, `SKILLGATE_JUDGE=openai`, plus `SKILLGATE_OPENAI_API_KEY=sk-x`. `resolve_judge` builds the openai endpoint (assert the type or name used in existing `test_judge_providers.py`). With `SKILLGATE_JUDGE=skip`, it raises `NEEDS_DECISION_MODEL` even though home is chosen.
10. `test_home_legacy_decisions_path_not_rewritten`: home file contains `"decisions_path": "x"`. Take the file bytes and mtime before calling `load_judge_settings(proj)`, then assert both are unchanged afterwards (no write to home). Counterpart: the same content in the project file **is** rewritten (existing behaviour).
11. `test_home_bad_account_id_ignored`: home `{"provider":"clef","account_id":"bad id!"}`, no project → `auto` with no exception.
12. `test_project_root_is_home_reads_once`: `SKILLGATE_ROOT=home`, only `home/.skillgate/judge` openai → openai. Monkeypatch `_read_judge_file` with a counting wrapper and assert it ran once.
13. `test_set_writes_project_only`: home openai, run CLI `judge provider set jev`. Afterwards `proj/.skillgate/judge` exists with `jev`, and the home file bytes are unchanged.

Keys:
14. `test_project_key_wins_over_home`: home `OPENAI_API_KEY=home-k`, project `OPENAI_API_KEY=proj-k` → `resolve_provider_keys(proj)["OPENAI_API_KEY"] == "proj-k"`.
15. `test_home_fills_missing_keys_only`: home `OPENAI_API_KEY=home-k` and `JEV_API_KEY=home-j`, project `JEV_API_KEY=proj-j` → OPENAI is `home-k` and JEV is `proj-j`. `get_llm_config(proj).openai_api_key == "home-k"`.
16. `test_env_overlay_beats_home`: home `OPENAI_API_KEY=home-k`, `SKILLGATE_OPENAI_API_KEY=env-k` → `env-k`. Bound ambient: `bind_key_env(["OPENAI_API_KEY"])` with `OPENAI_API_KEY=amb-k` → `amb-k`.
17. `test_key_presence_from_home`: home-only OPENAI → `{"set": True, "from_vault": False, "from_env": False, "from_home": True}`. Project + home → `from_vault True` and `from_home False`. Home + env overlay → `from_env True` and `from_home False`.
18. `test_keys_list_labels_home`: CLI `keys list` prints `OPENAI_API_KEY  (~/.skillgate/keys)`.
19. `test_keys_set_does_not_copy_home_keys`: home has OPENAI; CLI `keys set JEV_API_KEY j`. The project keys file contains only `JEV_API_KEY=j`, and the home file bytes are unchanged.
20. `test_keys_clear_home_only_name`: home has OPENAI; CLI `keys clear OPENAI_API_KEY` → exit 1 with "No OPENAI_API_KEY in Settings.", and the home file is unchanged.

API (in the same file, using the existing `test_api_local.py` client fixture or pattern):
21. `test_api_get_judge_returns_home`: `GET /api/settings/judge` → `judge.provider == "openai"`, `chosen True`. `PUT` with `{"provider":"jev"}` writes the project file, and the home file is unchanged.

Regression: run the full suite. In particular, `tests/test_keys.py`, `test_api_local.py`, `test_judge_cli.py`, `test_judge_providers.py`, `test_judge_setup.py`, `test_decision_judges_only.py`, `test_openai_judge_docs.py`, and `test_oss_surface.py` (the docs-assert tests) must stay green with no edits to their assertions.

## 5. README / doc updates

Add the same short block in three places, with wording matched to each file's tone:

**docs/judge.md**: new subsection right after the `--key-env` paragraph (line ~102), titled `### Where settings are read from`:

```markdown
### Where settings are read from

Skill Gate reads the decision model from `.skillgate/judge` in this project. If that file is missing, or no model is picked there (`auto`), it uses `~/.skillgate/judge`. `SKILLGATE_JUDGE=openai` still overrides both files.

Keys come from `.skillgate/keys` in this project, then `SKILLGATE_*` env vars, then names passed with `--key-env`. `~/.skillgate/keys` only fills in key names that none of those set. A project key always wins over a home key with the same name.

`skillgate judge provider set`, `skillgate keys set`, and Settings in `skillgate ui` always write to this project's `.skillgate/`. Skill Gate never writes `~/.skillgate`. To share one decision model across projects, create `~/.skillgate/judge` and `~/.skillgate/keys` yourself, for example by running `skillgate judge provider set` and `skillgate keys set` once with `SKILLGATE_ROOT=$HOME`.
```

Also update the line-95 bullet to: "With none selected **in this project or in `~/.skillgate/judge`**, `show` prints `Pick a decision model before running a live check.` and exits 2."

**README.md**:
- In `## Set up a decision model` (line ~93), add a one-paragraph version of the block above after the intro sentence. Link to `docs/judge.md#where-settings-are-read-from`.
- Edit the line-174 bullet the same way as docs/judge.md line 95.

**docs/quickstart.md**: after the `skillgate judge provider set <endpoint>` code block in `## Keys` (line ~68), add:

```markdown
Already picked a decision model in another project? Put it in `~/.skillgate/judge` (and its key in `~/.skillgate/keys`). Every project without its own pick uses it. A project's own `.skillgate/judge` and `.skillgate/keys` always win. See [Where settings are read from](judge.md#where-settings-are-read-from).
```

Keep the line-71 sentence, but change "With none selected" to "With none selected here or in `~/.skillgate/judge`".

## 6. Acceptance criteria

- [ ] `paths.user_skillgate_dir()` exists and reads `Path.home()` on every call.
- [ ] `load_judge_settings(root)` returns the project settings when the project selects a provider, else the home settings when home selects one, else the project file's parsed value or the default `auto`.
- [ ] A project file with provider `auto` / `skip` / `""`, or an invalid file, falls through to home. A project file with a removed or unknown id does **not**.
- [ ] Skill Gate never writes `~/.skillgate/*` (legacy `decisions_path` migration is skipped for home; all `save_*` / `set_*` / `clear_*` stay project-only).
- [ ] `resolve_provider_keys` = home (gaps) < project vault < `SKILLGATE_*` < bound ambient. `read_vault` stays project-only.
- [ ] `key_presence` adds `from_home`. Existing `from_vault` / `from_env` semantics and tests are unchanged.
- [ ] `skillgate keys list` labels home keys `~/.skillgate/keys`.
- [ ] `SKILLGATE_JUDGE*` / `SKILLGATE_*_API_KEY` behaviour is byte-for-byte unchanged.
- [ ] With no chosen judge anywhere: same message `Pick a decision model before running a live check.`, exit 2, for `check`, `judge provider show`, and `judge test`.
- [ ] Autouse `_isolate_user_home` fixture added. New `tests/test_judge_home_fallback.py` covers §4.
- [ ] `pytest -q`, `ruff check`, `ruff format --check`, and `mypy src` all pass.
- [ ] `skillgate check skills/pdf` and `skillgate check skills/pdf-sabotaged --expect-fail` behave as before.
- [ ] README.md, docs/judge.md, and docs/quickstart.md updated per §5.
- [ ] Smoke procedure §8 passes.

## 7. DO-NOT-TOUCH

- No typing or lint refactors beyond what new code needs. No renaming existing functions. No module splits or moves.
- No CI / workflow / Dockerfile / pre-commit / lockfile / `pyproject.toml` changes.
- No `web/` source changes and no `web_static/` rebuild. The only API change is the additive `from_home` field.
- Do not change `SKILLGATE_*` env semantics, `_judge_pref` accepted values, `resolve_judge` logic, or error messages and hints.
- Do not change `project_root()`, `config_root_for()`, `gate.run_check` root resolution, or `load_env` (no `~/.env`).
- Do not merge vaults or judge files on write. Do not add a `--global` / `--home` flag or a `SKILLGATE_HOME` env var.
- Do not merge fields between project and home judge files. The winner is used whole.
- Do not bind ambient env from a home judge's `key_env`.
- No unrelated behaviour, copy, or output-format changes (`judge provider show` output stays identical).

## 8. Smoke test procedure

Run from the repo root after `pip install -e ".[dev]"`. A fake key is fine, because `show` and `resolve_judge` don't call the network.

```bash
REPO="$PWD"
SG="$REPO/.venv/bin/skillgate"
PY="$REPO/.venv/bin/python"
SMOKE="$(mktemp -d)"
mkdir -p "$SMOKE/home/.skillgate" "$SMOKE/proj"
printf '{"provider": "openai"}\n' > "$SMOKE/home/.skillgate/judge"
printf 'OPENAI_API_KEY=sk-smoke-not-real\n' > "$SMOKE/home/.skillgate/keys"
chmod 600 "$SMOKE/home/.skillgate/judge" "$SMOKE/home/.skillgate/keys"
shasum "$SMOKE/home/.skillgate/judge" "$SMOKE/home/.skillgate/keys" > "$SMOKE/home.sha"
cd "$SMOKE/proj"
run() { env -u SKILLGATE_ROOT -u SKILLGATE_JUDGE -u SKILLGATE_OPENAI_API_KEY HOME="$SMOKE/home" USERPROFILE="$SMOKE/home" "$@"; }

# 1. Home judge is seen in a fresh project (no .skillgate/ here)
test ! -e .skillgate && echo "OK fresh project"
run "$SG" judge provider show; echo "exit=$?"
#    expect: "the judge" / "openai" / model / base URL, exit=0, and NOT "Pick a decision model"

# 2. Effective config and judge resolve (no network)
run "$PY" -c 'from skillgate_ai.config import get_llm_config as g; from skillgate_ai.judge import resolve_judge as r; c=g(); print(c.judge_provider, c.judge_chosen, bool(c.openai_api_key)); print(type(r(c, harness_name="cursor-agent")).__name__)'
#    expect: "openai True True" then a judge class name (no SkillGateError)

# 3. Home key is labelled
run "$SG" keys list
#    expect: "OPENAI_API_KEY  (~/.skillgate/keys)"

# 4. Project auto falls through to home
mkdir -p .skillgate && printf '{"provider": "auto"}\n' > .skillgate/judge
run "$SG" judge provider show; echo "exit=$?"     # expect openai, exit=0

# 5. Project choice overrides home, and writes stay project-local
run "$SG" judge provider set jev; echo "exit=$?"  # expect exit=0
run "$SG" judge provider show; echo "exit=$?"     # expect jev, exit=0
cat .skillgate/judge                               # expect "provider": "jev"
shasum -c "$SMOKE/home.sha"                        # expect both files OK (home untouched)

# 6. Neither chosen → unchanged error
rm -f .skillgate/judge "$SMOKE/home/.skillgate/judge"
run "$SG" judge provider show; echo "exit=$?"
#    expect: "Pick a decision model before running a live check." and exit=2

cd "$REPO" && rm -rf "$SMOKE"
```

Pass criteria: steps 1, 2, 4, and 5 exit 0 with the expected provider. Step 3 shows the home label. Step 5's `shasum -c` reports OK. Step 6 exits 2 with the unchanged message.
