# Local UI (`skillgate ui`)

Optional loopback UI next to the CLI. **No Skill Gate account.** The gate is still `skillgate check` exiting 0 or 1.

```bash
pip install -e .          # or pip install skillgate-ai
skillgate ui              # http://127.0.0.1:8765
skillgate ui --pack skills/pdf-sabotaged
skillgate ui --root . --open
```

This is a **local process**, not hosted `serve`. Default bind is `127.0.0.1:8765` (not 8477). There is no login.

**First-time setup** is local + your API key (or Skip). The wizard does not run checks. After setup: **Want to add your first skill?** Yes writes a skill and opens the skill page. Try the pdf example opens `skills/pdf` with no auto-run. Not now goes to the skills list.

**The skill page is the product:** the skill, its checks (customer headlines), and **Run live** with your API key. `skillgate check` with a key present also runs live (exit 0/1). No key uses the built-in checker — that is not a live model. **Run live** with no key is HTTP 409. Labels are short paths like `skills/pdf`, not absolute machine paths.

The wizard **Your API key** step and the skill-page key details write `OPENAI_API_KEY` (and the other live keys). An OpenAI key scores live checks; other keys only run them. The result panel names who scored the run in plain words (`OpenAI (your key)` or `Built-in checker`). Checking → slide → drawn Passed/Failed is unchanged.

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
