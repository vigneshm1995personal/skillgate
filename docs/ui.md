# Local UI (`skillgate ui`)

Optional loopback wizard next to the CLI. **No Skill Gate account.** The gate is still `skillgate check` exiting 0 or 1.

```bash
pip install -e .          # or pip install skillgate-ai
skillgate ui              # http://127.0.0.1:8765
skillgate ui --pack skills/pdf-sabotaged
skillgate ui --root . --open
```

This is a **local process**, not hosted `serve`. Default bind is `127.0.0.1:8765` (not 8477). There is no login.

**New skill** is two steps: name the skill, describe it, then **Create and run check**. That writes a skill under `skills/`, adds example checks, and runs the built-in checker (no API key). A **Passed** screen shows `n/n` checks. **Run check** (and `skillgate check` without `--live`) always uses the built-in checker — even if an API key is in the environment. **Run live** is the only control that uses your API key. After Passed or Failed you can **Add a key for live checks** (or skip); the same optional form stays collapsed on the skill page. Labels in the UI are short paths like `skills/pdf`, not absolute machine paths.

## Intentional red path

1. On the picker, open the muted **See a failing check** card (`skills/pdf-sabotaged`).
2. Run check → Failed, exit 1, corrected description paste (PDF-shaped, not grocery/dinner).
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
