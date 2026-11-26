# Audit PR E — fixed trusted roots (option 1)

**Parent:** `docs/specs/audit-pr-e.md` · **Branch:** `cursor/audit-pr-e` · **No barrier models / dismissals / suppressions**

## Trusted-root model

Filesystem sinks never use a user-supplied path as `base_path`. Allowed anchors:

| Anchor | Source | Relative segments |
|--------|--------|-------------------|
| **Workspace** | `SKILLGATE_ROOT` when set, else cwd-walk `project_root()` (skills/ or keys or pack parent) | Pack path as segments under workspace (`skills/pdf`, or `()` when workspace is the pack mount) |
| **Agent roots** | `cursor_skills_root()`, `codex_skills_root()`, `claude_skills_root()` | Single immediate child folder name only (direct `SKILL.md` install) |
| **CLI standalone** | `register_standalone_pack_for_cli(pack)` in `run_check` sets `SKILLGATE_ROOT` to the pack realpath when the pack is not already under the discovered workspace (Docker `check /pack`, local `check ./skills/pdf` unchanged) |

User input (`skill_path`, API name, CLI arg) is resolved to a target realpath, then **classified** into `(fixed_anchor, rel_parts)`. All `contained_fs` / `pack_io` I/O uses only that tuple. No `(resolved_pack, ())` fallback.

## Files / functions

| File | Change |
|------|--------|
| `src/skillgate_ai/trusted_roots.py` | **New:** `workspace_anchor`, `register_standalone_pack_for_cli`, `pack_access_root`, `normalize_pack_target`, agent matching |
| `src/skillgate_ai/paths.py` | Thin wrappers; `skill_pack_root` delegates to `pack_access_root`; remove permissive directory fallbacks |
| `src/skillgate_ai/contained_fs.py` | Keep inline guards; callers only pass fixed anchors (no API change) |
| `src/skillgate_ai/pack_io.py` | Unchanged signatures |
| `src/skillgate_ai/gate.py` | Call `register_standalone_pack_for_cli` when target is a pack dir |
| `src/skillgate_ai/catalog.py` | `find_skill` / `_immediate_agent_skill` use fixed roots only |
| `src/skillgate_ai/pack/pathsafe.py` | `resolve_pack_root` via strict `pack_access_root` |
| `src/skillgate_ai/ingest.py`, `pack/listing.py`, `api_skills.py` | No direct `os.path` on user paths; already via pack_io |

## Tests

| Test | File | Assertions |
|------|------|------------|
| `test_pack_access_under_workspace` | `tests/test_trusted_roots.py` | `SKILLGATE_ROOT` + pack under workspace → anchor is workspace, correct rel |
| `test_standalone_pack_registers_skillgate_root` | same | CLI register sets env; `pack_access_root` → `(()` rel at pack mount |
| `test_agent_skill_immediate_child` | same | Under `~/.cursor/skills/foo` → anchor agent root, rel `("foo",)` |
| `test_rejects_nested_agent_path` | same | `~/.cursor/skills/foo/bar` → `PathTraversalError` |
| `test_rejects_outside_all_roots` | same | `/etc/passwd` → error |
| `test_sibling_prefix_anchor` | same | `/tmp/a` vs `/tmp/ab` under workspace anchor |
| `test_contained_fs_rejects_prefix_sibling_after_realpath` | `tests/test_paths.py` | (existing) |
| `test_contained_path_rejects_symlink_escape` | `tests/test_paths.py` | (existing) |
| Existing harness Docker / SKILLGATE_ROOT tests | `tests/test_harness_auth.py` etc. | Stay green |

## Step order

1. Add `trusted_roots.py` + tests (red)
2. Rewire `pack_access_root` / `skill_pack_root`; remove `(resolved, ())`
3. `gate.run_check` registration for standalone CLI pack
4. Tighten `catalog.find_skill` agent path branch
5. Full `pytest`, `mypy`, push; wait CodeQL `enforce` + GitHub **CodeQL** check

## Acceptance

- 0 open **high/critical** `py/path-injection` on merge ref for analyzed merge commit
- `gate` `all-gates` + GitHub Advanced Security **CodeQL** success
- Coverage ≥ 84%, `dict[str, Any]` ≤ 516, no module > 600 lines

## DO-NOT-TOUCH

`plugin/**`, `src/skillgate_ai/mcp/**`, `tests/test_wire_shapes.py`, `src/skillgate_ai/judge_settings.py`, HTTP/MCP JSON shapes, `fail_under=84`, no version bump, **no CodeQL barrier extensions**

## User-visible behavior

- Pack paths outside workspace and agent skill folders are rejected (CLI/API/catalog), except CLI `check <packdir>` which registers standalone via `SKILLGATE_ROOT` for that process (unchanged Docker `/pack` with image env).
- Nested paths under agent roots (not immediate child) rejected.
- Relative non-existent pack paths must resolve under workspace after register; same error style as today.