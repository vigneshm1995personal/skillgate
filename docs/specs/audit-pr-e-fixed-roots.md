# Audit PR E — restricted fixed roots + explicit opt-in (phase 2)

**Parent:** `docs/specs/audit-pr-e.md` · **Branch:** `cursor/audit-pr-e` · **No barrier models / dismissals / suppressions**

## Goal

Stop env-pin **taint laundering**. Filesystem **reads** only under:

| Root kind | `FsAnchor` | How it is fixed |
|-----------|------------|-----------------|
| Workspace | `WORKSPACE` | `project_root()` (cwd walk or `SKILLGATE_ROOT` when that env names the **workspace container**, e.g. Docker/UI — never a pack dir injected from a user path) |
| Agent install dirs | `AGENT_CURSOR` / `AGENT_CODEX` / `AGENT_CLAUDE` | `cursor_skills_root()` et al. |
| Config / keys tree | `CONFIG` | `config_root_for(None)` or nearest walk result with `.skillgate/keys` under workspace policy |
| User opt-in | `ALLOW_ROOT` | **Only** `--allow-root <dir>` on `skillgate check` and/or **one line** in `~/.skillgate/allow-root` (user home). Never pack `.skillgate/`, never repo `.env`, never auto-pin from `register_standalone_pack_for_cli`. |

User `skill_path` is resolved to a realpath for **classification only**. All `contained_fs` / `pack_io` I/O uses `(anchor, rel_parts)`. **No** `(…, ())` mount fallback on arbitrary dirs. **No** writing user realpaths into `SKILLGATE_ROOT`.

## Remove / forbid

| Item | Action |
|------|--------|
| `pack_layout.pinned_skillgate_root` | **Delete** (context manager + all callers) |
| `pack_layout.loose_mount_at_pinned_root` | **Delete** |
| `trusted_roots._pin_skillgate_root` | **Delete** |
| `trusted_roots.register_standalone_pack_for_cli` | **Delete** |
| `pack_access_root` branches that `_pin_skillgate_root`, return `SKILLGATE_ENV, ()`, or accept `anchor_path_uncreated` / `discovery_is_directory` arbitrary dirs | **Delete** |
| `gate.run_check` → `register_standalone_pack_for_cli` | **Remove**; pass allow-root from CLI instead |
| `pack_io` → `register_standalone_pack_for_cli` | **Remove** |

## New / changed files & functions

| File | Functions / changes |
|------|---------------------|
| `src/skillgate_ai/fs_anchor.py` | Add `FsAnchor.CONFIG`, `FsAnchor.ALLOW_ROOT`; extend `anchor_base()` |
| `src/skillgate_ai/allow_root.py` | **New:** `set_cli_allow_root(path)`, `get_cli_allow_root()`, `read_user_allow_root_file() -> str \| None` (reads only `~/.skillgate/allow-root`), `allow_root_realpaths() -> tuple[str, ...]` |
| `src/skillgate_ai/pack_layout.py` | Replace pin-based `discovery_*` with **cwd-walk classifiers** `layout_has_skills_dir(root_real: str)`, `layout_skill_pack_at_root(root_real: str)`, `layout_keys_file(root_real: str)`, `layout_pack_markers(root_real: str) -> tuple[bool,bool,bool]`, `layout_is_directory(root_real: str)` using **fixed suffix joins** under `root_real` for classification only (no env mutation). Keep `relative_segments_under`, `strict_skill_pack_at`, `loose_pack_mount_at` (anchor + segments only). Remove `anchor_path_uncreated`. |
| `src/skillgate_ai/trusted_roots.py` | Rewrite `pack_access_root`: try `WORKSPACE`, `SKILLGATE_ENV` (env workspace only), each agent (single segment + `strict_skill_pack_at`), `CONFIG` via `config_root_for(resolved)` containment, each `ALLOW_ROOT` entry; else `PathTraversalError` with message: *Path is outside workspace, agent, config, or allow-root. For a pack elsewhere run: `skillgate check --allow-root <parent-dir>` or add the directory to `~/.skillgate/allow-root`.* Remove `_is_pack_mount` env-pin tail. |
| `src/skillgate_ai/paths.py` | `_has_workspace_skills` / `is_skill_pack` / `config_root_for` walk use new `layout_*` helpers. `project_root()`: `SKILLGATE_ROOT` only when already set in environment (caller/operator), not from pack registration. |
| `src/skillgate_ai/cli/cmd_gate.py` | `check_pack`: `--allow-root` `Path \| None`; call `set_cli_allow_root` before `run_check`. |
| `src/skillgate_ai/gate.py` | Remove `register_standalone_pack_for_cli`; optional `allow_root` param or rely on module state set by CLI. |
| `src/skillgate_ai/pack_io.py` | Remove standalone registration. |
| `.github/workflows/codeql.yml` | **Enforce:** poll until open alerts for `scan_ref` have `most_recent_instance.commit_sha == merge_sha` **and** a completed CodeQL analysis for **this workflow run** is ingested (match `merge_sha`, not branch head); timeout → fail closed; count all high/critical/error severity rules. |

## Tests (exact names & assertions)

| Test | File | Assert |
|------|------|--------|
| `test_pack_access_under_workspace` | `tests/test_trusted_roots.py` | (keep) pack under workspace → `FsAnchor.WORKSPACE`, rel ends with `skills/pdf`. |
| `test_agent_skill_immediate_child` | `tests/test_trusted_roots.py` | **New.** Under mocked agent root `tmp/.../skills/foo` with `SKILL.md`+`evals` → `FsAnchor.AGENT_CURSOR`, `("foo",)`. |
| `test_rejects_nested_agent_path` | `tests/test_trusted_roots.py` | **New.** `.../skills/foo/bar` → `PathTraversalError`. |
| `test_rejects_etc_without_allow_root` | `tests/test_trusted_roots.py` | **New.** `pack_access_root("/etc")` → `PathTraversalError`; message mentions `--allow-root` or `~/.skillgate/allow-root`. |
| `test_allow_root_cli_parent` | `tests/test_trusted_roots.py` | **New.** Standalone pack + `set_cli_allow_root(tmp_path)` (or parent) → `FsAnchor.ALLOW_ROOT`, correct rel; **no** `SKILLGATE_ROOT` env mutation to pack path. |
| `test_pack_cannot_opt_in_via_repo_env` | `tests/test_trusted_roots.py` | **New.** Pack writes fake allow file under pack `.skillgate/` or sets repo `.env` — must **not** grant access; still rejected without user opt-in. |
| `test_rejects_outside_all_roots` | `tests/test_trusted_roots.py` | (keep) `/etc/passwd` rejected. |
| `test_sibling_prefix_under_workspace` | `tests/test_trusted_roots.py` | (keep) |
| Mount characterization | `tests/test_mount_classification.py` | Update `test_standalone_classification_unchanged` to use `set_cli_allow_root` instead of `register_standalone_pack_for_cli`; update `test_empty_work_dir_pins_for_contained_path` to use workspace parent + rel path (no env pin). |
| Harness Docker | existing | `SKILLGATE_ROOT` workspace container unchanged when env set by image. |

## Step order

1. Commit this spec.
2. Add `allow_root.py` + `FsAnchor` variants + tests (red).
3. Remove pin/discovery/env registration; implement `layout_*` + strict `pack_access_root`.
4. Wire CLI `--allow-root`; README + remove sanitizer bullet from `audit-pr-e.md`.
5. Fix `codeql.yml` enforce polling.
6. Full `pytest`, coverage ≥ 84%, push; poll until GAS **CodeQL** + `enforce` + `all-gates` green.

## Acceptance criteria

- 0 open **high/critical** (and `severity == error`) CodeQL on `refs/pull/99/merge` for analyzed merge commit.
- GitHub Advanced Security **CodeQL** check SUCCESS; `codeql / enforce` + `all-gates` + `lint` green.
- Coverage ≥ 84.0%; `dict[str, Any]` ≤ 516; no module > 600 lines.
- No `pinned_skillgate_root`, no `register_standalone_pack_for_cli`, no pack-driven `SKILLGATE_ROOT` writes.

## DO-NOT-TOUCH

`plugin/**`, `src/skillgate_ai/mcp/**`, `tests/test_wire_shapes.py`, `src/skillgate_ai/judge_settings.py`, HTTP/MCP JSON wire shapes, `fail_under=84`, no version bump, no CodeQL barrier extensions.

## User-visible behavior

- **`skillgate check <packdir>`** outside workspace/agent/config **fails** unless the user passes **`--allow-root <dir>`** (parent or pack root) or lists the directory in **`~/.skillgate/allow-root`** (one absolute path per file, user home only).
- **`SKILLGATE_ROOT`** remains for operators (Docker, UI) as the **workspace root**, not a smuggled pack mount.
- Nested agent skill paths still rejected.