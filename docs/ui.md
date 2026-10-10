# Local UI (`skillgate ui`)

Optional loopback UI next to the CLI. **No Skill Gate account.** The gate is still `skillgate check` exiting 0 or 1.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cd web && pnpm install && pnpm build && cd ..
skillgate ui              # http://127.0.0.1:8765
skillgate ui --root . --open
```

During UI development, leave the API running and use Vite’s proxy:

```bash
skillgate ui              # API + built UI on 8765
# in another terminal:
pnpm --dir web dev        # http://127.0.0.1:5173  (proxies /api → 8765)
```

This is a **local process**, not hosted `serve`. Default bind is `127.0.0.1:8765` (not 8477). There is no login.

**Skills list first.** Import from `~/.cursor/skills`, `~/.codex/skills`, and `~/.claude/skills`, or use packs under `skills/`. Open a skill to read `SKILL.md`, edit checks, then **press Run**. Nothing evaluates until you press it. No key uses the built-in checker — that is not a live model. A key in Settings runs live. Results use the same drawn mark, Result | Check | What happened, and five answers.

**Deploy** copies a green-gated skill into those same agent folders. Keys stay in this project’s `.env` (Settings). `skillgate check` still exits 0 or 1 with no account.

The result panel names who scored the run in plain words (`OpenAI (your key)` or `Built-in checker`). Checking → slide → drawn Passed/Failed is unchanged.

## Intentional red path

1. On the picker, open the muted **See a failing check** card (`skills/pdf-sabotaged`).
2. Run live (or the built-in checker if you skipped a key) → Failed, exit 1, corrected description paste (PDF-shaped, not grocery/dinner).
3. Apply the paste on **this same pack**, then re-run → Passed, exit 0.

CI still uses `skillgate check`; the UI calls the same `run_check` engine.

## Docker stays the CLI gate

The UI is **not** in the image default argv. Do not `EXPOSE` a port.

```bash
# UI (host Python)
skillgate ui

# Gate (unchanged)
docker compose run --rm --no-TTY skillgate
PACK=./skills/pdf-sabotaged docker compose run --rm --no-TTY skillgate   # exit 1
```

Image `ENTRYPOINT` is `skillgate`; `CMD` is `check /pack`.
