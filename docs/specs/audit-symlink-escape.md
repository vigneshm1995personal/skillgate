# Spec: Symlink escape in workspace skill catalog (re-audit issue #1)

## 1. Problem summary

`catalog_entries()` and `find_skill()` accept a workspace skill folder, or its `SKILL.md`, even when it is a symlink whose resolved target is outside the project root. They resolve the path but never check where it ends up. As a result, `skills/evil -> /anywhere/outside` (or `skills/evil/SKILL.md -> /etc/whatever`) shows up in `/api/skills` as a "this project" skill. Its `SKILL.md` body is returned by `/api/skills/{name}`, and every file under the outside target can be read through `/api/skills/{name}/pack-file` and `/pack-raw`. `pack.py` only checks that files stay inside the *skill* root, and here the skill root is already outside the project.

## 2. Files and functions to change

| File | Function | Lines (current) | Change |
|---|---|---|---|
| `src/skillgate_ai/catalog.py` | new `_workspace_skill_dir` | insert after `_iter_skill_dirs` (after line 57) | New helper (§3). |
| `src/skillgate_ai/catalog.py` | `catalog_entries.add` (nested) | 71–77 | When `source == "workspace"`, run the path through `_workspace_skill_dir(path, root)`. If it returns `None`, return without adding. Use the helper's return value as `resolved`. Leave the rest of `add()` unchanged. |
| `src/skillgate_ai/catalog.py` | `find_skill`, path branch | 176–179 | Keep the `is_under_root` check at 176. Replace `if (resolved / "SKILL.md").is_file(): return resolved` with `contained = _workspace_skill_dir(resolved, root)` and `if contained is not None: return contained`. |
| `src/skillgate_ai/catalog.py` | `find_skill`, plain-name branch | 180–183 | Replace the bare `.is_file()` and `.resolve()` with `contained = _workspace_skill_dir(workspace_skills_root(root) / text, root)` and `if contained is not None: return contained`. If it is `None`, fall through to the `catalog_entries` loop, which also skips the entry. The result is the existing `"Skill … was not found."` error (HTTP 400). |

Not changed:
- `_iter_skill_dirs` (lines 46–57): signature and behavior stay as they are. Agent-folder enumeration and `import_from_agent_folders` / `agent_source_status` also use it.
- Agent sources in `catalog_entries` (lines 108–121): out of scope (§5).
- `_immediate_agent_skill` short-circuit in `find_skill` (line 174): agent skills are outside the project by design.

## 3. Shared helper

Put it in **`src/skillgate_ai/catalog.py`** as a private helper. It is only used there, so it does not belong in `paths.py`. It reuses `is_under_root`, which `catalog.py` already imports from `paths.py`.

```python
def _workspace_skill_dir(path: Path, root: Path) -> Path | None:
    """Resolved skill folder when it and its SKILL.md stay inside ``root``; else None."""
    try:
        resolved = path.resolve()
        skill_md = (resolved / "SKILL.md").resolve()
    except OSError:
        return None
    if not is_under_root(resolved, root) or not is_under_root(skill_md, root):
        return None
    if not skill_md.is_file():
        return None
    return resolved
```

- `root` is the resolved project root. `catalog_entries` already does `root = root.expanduser().resolve()` at line 66. `find_skill` passes `root` through, and `is_under_root` resolves both sides itself.
- No changes to `paths.py`. `is_under_root` (lines 84–89) is already correct: it resolves both sides and catches `ValueError` and `OSError`.

## 4. Behavior

- **Containment rule (workspace-sourced skills only):** a skill is accepted only if `Path.resolve()` of the skill folder **and** `Path.resolve()` of its `SKILL.md` both pass `is_under_root(..., root)`. Otherwise the skill is **skipped silently**: no error, no log, no entry.
- **Symlinks inside the root keep working.** For example, `skills/alias -> skills/real` or `skills/x/SKILL.md -> ../shared/SKILL.md` within the project still resolve inside `root` and are accepted. Dedup through `seen` (line 73) still collapses an alias and its target into one entry, keyed by the resolved path.
- **Root-level pack** (`add(root, "workspace")`, line 101): goes through the same helper. A root `SKILL.md` that links outside is skipped.
- **No `skills/` folder** (lines 103–105, children of `root`): same helper, same rule.
- **`skills/` itself symlinked outside the root:** every child resolves outside `root`, so the workspace catalog is empty. This is intended, secure default behavior. Call it out in the PR description.
- **Workspace symlink into an agent folder** (for example `skills/foo -> ~/.cursor/skills/foo`): no longer listed as `workspace`. With `include_agents=True` it still appears through the agent-source loop with `source="cursor"`. That is the correct label, and the agent loop is unchanged.
- **`find_skill` plain name** (`NAME_RE` match, for example `"evil"`): looks up `workspace_skills_root(root) / name` through the helper. If it escapes, it falls through to the `catalog_entries(root, include_agents=True)` loop. The workspace entry is gone from that list, so it raises `SkillGateError("Skill 'evil' was not found.")`, which becomes HTTP 400 through `api.py:103-109`. A real agent-folder skill with the same slug is still found by that loop. Agent behavior is unchanged.
- **`find_skill` path-like input** (contains `/`, `\`, `..`, or is absolute): order is unchanged. The `_immediate_agent_skill` check comes first, then the existing `is_under_root(resolved, root)` check, which raises "outside this project". The final accept now uses the helper, so a contained folder whose `SKILL.md` links outside falls through to the name lookup and then "not found".
- Error messages and status codes stay the same. No new error strings.

## 5. Other path-walk sites (from grep)

**In scope:** none beyond `catalog.py`. All UI and catalog workspace-skill enumeration goes through `catalog_entries` / `find_skill`. Callers that inherit the fix with no edits:
- `api_skills.py:85, 152, 169, 174, 181, 215, 242, 251, 271, 282`
- `api_evals.py:33, 71, 116, 161, 169`
- `api_runs.py:50`
- `api_compare.py:68, 82, 134, 196`
- `api_shims.py:69`
- `checks_show.py:146`
- `api_payloads.py:385, 417`
- `api_intake.py:208`
- `api.py:146`
- `compare/store.py:24`
- `cli/pack_history.py:72`

**Already guarded (no action):**
- `pack.py:617-627` `_path_under_skill`, `pack.py:650-654` `_rel_to_skill` (used by `list_pack_files` rglob at 68), `pack_files.py:61-67` `file_inside_skill`: resolve, then `relative_to(skill_root)`. These are safe once the skill root is trusted, which this fix ensures.
- `sync.py:106-121` `_reject_symlinks`: applied after `_skill_names` (`sync.py:125-133`) and in `api_intake.py:165, 176`.
- `server.py:76-78`, `api_intake.py:32-33`: resolve plus `relative_to`.
- `workspace_outputs.py:150`: `os.walk(..., followlinks=False)`.

**Out of scope (follow-up issues, do not fix in this PR):**
1. `catalog.py:108-121` and `_iter_skill_dirs` for agent sources: a symlink in `~/.cursor/skills` (or the Codex/Claude folders) can point anywhere. Consider containing to the agent root.
2. `catalog.py:213-233` `import_from_agent_folders` → `copy_pack(skill_dir, …)`: copies a symlinked agent skill's outside target into the workspace. Check how `copy_skill_pack` (`pack.py:496+`) handles symlinks.
3. `ingest.py:159` `discover_skills`: `iterdir()` plus `is_dir()` follows symlinks with no containment. Used by the CLI `check` path, not the UI.
4. `skill_tools.py:44` `_scripts_blob`: `scripts.rglob("*")` reads files with no containment check, so a symlinked script can pull in outside content.

## 6. New tests

All symlink-creating tests wrap `os.symlink` in `try/except (OSError, NotImplementedError): pytest.skip("symlinks not supported here")`, matching `tests/test_sync.py:169-173`. Each sets `SKILLGATE_CURSOR_SKILLS`, `SKILLGATE_CODEX_SKILLS`, and `SKILLGATE_CLAUDE_SKILLS` to `tmp_path` subfolders, as `test_pack_path_outside_project_is_rejected` does (`tests/test_ui_security.py:66-68`), so real agent folders don't leak in. Skills are created with `write_skill_md(folder, name=..., description=..., body=...)`.

### `tests/test_ui_security.py` (append, reuse `_client`)

Add `import os` and `import pytest` at the top.

1. **`test_symlinked_skill_dir_outside_root_is_rejected`**
   - Setup: `outside = tmp_path / "outside" / "evil"`, `write_skill_md(outside, name="evil", description="Outside.", body="# SECRET\n")`, and `(outside / "secret.txt").write_text("leak")`. Create `workspace = tmp_path / "project"` and `(workspace / "skills").mkdir(parents=True)`. Then `os.symlink(outside, workspace / "skills" / "evil")`.
   - Assert: `GET /api/skills` returns 200 and no item has `slug == "evil"`. `GET /api/skills/evil` returns a status in `{400, 404}`. `GET /api/skills/evil/pack-file?path=secret.txt` and `GET /api/skills/evil/pack-raw?path=SKILL.md` each return a status in `{400, 404}`.

2. **`test_symlinked_skill_md_outside_root_is_rejected`**
   - Setup: `outside_md = tmp_path / "outside" / "SKILL.md"` containing `"---\nname: evil\ndescription: Outside.\n---\n# SECRET\n"`. Make `workspace/skills/evil/` a real directory, then `os.symlink(outside_md, workspace / "skills" / "evil" / "SKILL.md")`.
   - Assert: `GET /api/skills` has no `slug == "evil"`. `GET /api/skills/evil` returns a status in `{400, 404}`, and `"SECRET"` does not appear in `res.text`.

3. **`test_symlinked_skill_inside_root_is_allowed`**
   - Setup: `real = workspace / "shared" / "pdf-tools"` with `write_skill_md(real, name="pdf-tools", ...)`, then `os.symlink(real, workspace / "skills" / "pdf-tools")`.
   - Assert: `GET /api/skills` contains an item with `slug == "pdf-tools"`, and `GET /api/skills/pdf-tools` returns 200.

### `tests/test_catalog.py` (new file, unit level, no FastAPI)

The tests call `catalog_entries` and `find_skill` from `skillgate_ai.catalog` directly. A module-level autouse fixture sets the three `SKILLGATE_*_SKILLS` env vars to `tmp_path` subfolders.

1. `test_catalog_entries_skips_symlinked_dir_outside_root`: the `skills/evil` symlink to outside is not in `catalog_entries(root)`, nor in `catalog_entries(root, include_agents=True)`.
2. `test_catalog_entries_skips_symlinked_skill_md_outside_root`: a real `skills/evil/` whose `SKILL.md` symlinks outside is not listed.
3. `test_catalog_entries_keeps_symlink_inside_root`: `skills/alias -> <root>/shared/alias` is listed with `source == "workspace"` and `absolute == str((root / "shared" / "alias").resolve())`.
4. `test_catalog_entries_skips_root_skill_md_outside_root`: root has no `skills/` and a `SKILL.md` symlinked outside, so `catalog_entries(root) == []`.
5. `test_catalog_entries_dedupes_alias_and_target`: `skills/real/` plus `skills/alias -> skills/real` gives exactly one entry.
6. `test_find_skill_plain_name_rejects_symlink_outside_root`: `pytest.raises(SkillGateError, match="not found")` for `find_skill(root, "evil")`.
7. `test_find_skill_relative_path_rejects_symlink_outside_root`: `find_skill(root, "skills/evil")` raises `SkillGateError` ("outside this project").
8. `test_find_skill_path_rejects_skill_md_outside_root`: with a real `skills/evil/` and an outside `SKILL.md` symlink, `find_skill(root, "skills/evil")` raises `SkillGateError`.
9. `test_find_skill_plain_name_allows_symlink_inside_root`: `find_skill(root, "alias") == (root / "shared" / "alias").resolve()`.
10. `test_find_skill_agent_skill_unaffected`: a real skill at `$SKILLGATE_CURSOR_SKILLS/agentonly` resolves through `find_skill(root, "agentonly")`. This is a regression guard for the agent path.

## 7. Implementation steps

1. Create `tests/test_catalog.py` with tests 1–10, then run `pytest -q tests/test_catalog.py`. Tests 1, 2, 4, 6, 7 and 8 must **fail**; 3, 5, 9 and 10 must pass.
2. Append the 3 tests to `tests/test_ui_security.py` and run them. Tests 1 and 2 must **fail**; test 3 must pass.
3. Add `_workspace_skill_dir` to `catalog.py` right after `_iter_skill_dirs`.
4. Edit `catalog_entries.add` (lines 71–77): for `source == "workspace"`, gate through the helper and use its return value as `resolved`. Other sources keep `path.resolve()` and the existing `SKILL.md` check.
5. Edit `find_skill` lines 178–179 (path branch) to use the helper.
6. Edit `find_skill` lines 180–183 (plain-name branch) to use the helper and fall through when it returns `None`.
7. Run `pytest -q tests/test_catalog.py tests/test_ui_security.py`; all must pass.
8. Run the full checks: `pytest -q`, `ruff check`, `ruff format --check`, `mypy src`, `skillgate check skills/pdf`, `skillgate check skills/pdf-sabotaged --expect-fail`.
9. Commit on `cursor/audit-symlink-escape` with a single focused commit. Push only when everything is green.

## 8. Acceptance criteria

- A workspace skill folder symlinked to a target outside the project root does not appear in `catalog_entries()` or `/api/skills`, and is not reachable through `find_skill` or any `/api/skills/{name}*` route.
- A workspace `SKILL.md` symlinked outside the project root has the same effect: the skill is not listed or reachable, and its contents never appear in any API response.
- Symlinks that resolve inside the project root keep working, and an alias and its target produce one catalog entry.
- Agent-folder skills (Cursor, Codex, Claude) are listed and found exactly as before.
- Error text and HTTP status codes are unchanged: 400 for `SkillGateError`, 404 for `FileNotFoundError`.
- `_iter_skill_dirs`, `paths.py`, `pack.py`, `sync.py`, and `ingest.py` have no diff.
- All 13 new tests pass, and the existing suite, `ruff check`, `ruff format --check`, and `mypy src` are green.
- The diff only touches `src/skillgate_ai/catalog.py`, `tests/test_ui_security.py`, and `tests/test_catalog.py`, plus `docs/specs/audit-symlink-escape.md` if this spec is committed.

## 9. Do not touch

- No refactors of `catalog.py` beyond the lines listed in §2: no reordering, renaming, or extracting other helpers.
- No typing or lint changes to existing code; new code only has to pass the existing `ruff` and `mypy` config.
- No module splits and no moving functions between modules.
- No version bumps (`pyproject.toml`, `__version__`, CHANGELOG version headers).
- No CI changes (`.github/workflows/*`, `pre-commit` config, lockfile).
- No changes to `http_retry` or its tests.
- No mypy config changes (`pyproject.toml [tool.mypy]`, `mypy.ini`).
- No fixes for the out-of-scope sites in §5; they go in follow-up issues.
- No changes to `paths.is_under_root`, `_iter_skill_dirs`, agent-source enumeration, or `import_from_agent_folders`.
