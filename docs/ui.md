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

**Compare** (sidebar tab) has CLI equivalents: `skillgate compare models` (arms via `--arm 'Label:codex'`, spend cap via `--max-spend-usd`), `skillgate compare versions --run …`, `skillgate compare list`, `skillgate compare show`, and `skillgate compare cancel` while a job is running.

The React app in `web/` is the only Skill Gate UI (`@skillgate/ui`). `skillgate ui` serves that build. Home is the first screen. Paid screens (cloud sign-in, billing, shared history, hosted judge, sandboxes) are slots: off here, supplied by the hosted app. Import from `~/.cursor/skills`, `~/.codex/skills`, and `~/.claude/skills`, or use packs under `skills/`. Evaluate lists skills that already live in those folders (**Pick a skill**). Paste and zip are not on that screen; `skillgate skill paste` and `skillgate import` still do them. Then checks, with agent and model tucked in an accordion, and one **Run**. Nothing evaluates until you press it. Run is disabled until `skillgate login` (Settings → Sign in). The optional judge is that one Settings card: base URL, model, and API key. Test uses the same call as `skillgate judge provider test`. Results use the same drawn mark, Result | Check | What happened, and the built-in checks.

**Deploy** copies a green-gated skill (skill files only, not `evals/`) into those same agent folders. Install stays disabled without an agent (`skillgate login` or Settings → Sign in), even after a passing check. The optional judge key lives in this project’s `.skillgate/keys`, or CI/Docker can set `SKILLGATE_*` (always read). `skillgate check` still exits 0, 1, or 2 with no account.

The result panel names who scored the run in plain words (`Scored by the judge`, or `Scored by OpenAI` / `Jev` / `AWS` / `Other` if you picked a provider in Settings, or `Checks scored this run.`). Checking → slide → drawn Passed/Failed is unchanged.

## Intentional red path

1. On the picker, open the muted **See a failing check** card (`skills/pdf-sabotaged`).
2. Press Run (needs `skillgate login` or a key) → Failed, exit 1, description paste (PDF-shaped, not grocery/dinner).
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

## UI / CLI parity

Everything the local UI can do has a CLI command. New API writes must update this table and `WRITE_ROUTE_CLI` in `cli_parity.py`.

| UI action | API | CLI |
| --- | --- | --- |
| Save a judge key (optional) | `PUT /api/settings/keys/{name}` | `skillgate keys set` |
| Clear a judge key | `DELETE /api/settings/keys/{name}` | `skillgate keys clear` |
| List keys | `GET /api/settings/keys` | `skillgate keys list` |
| Save judge base URL and model | `PUT /api/settings/judge` | `skillgate judge provider set` |
| Test the judge | `POST /api/judge/ping` | `skillgate judge provider test` |
| Show the judge | `GET /api/settings/judge` | `skillgate judge provider show` |
| Import from agent folders | `POST /api/skills/import` | `skillgate import --only` |
| Paste SKILL.md or import a zip (CLI only; Evaluate does not show this) | `POST /api/skills/paste`, `POST /api/skills/upload` | `skillgate skill paste` / `skillgate new` |
| Edit SKILL.md or pack files | `POST /api/skills/pack-file`, `POST /api/skills/pack-upload`, `POST /api/skills/apply-fix`, `POST /api/evals/generate` | `skillgate skill write` |
| List skills | `GET /api/skills` | `skillgate list` |
| Add a check | `POST /api/evals/pin` | `skillgate case add` |
| Import dataset (CSV / JSONL / YAML) | `POST /api/evals/import-dataset` | `skillgate case import` |
| Edit a check | `POST /api/evals/pin` | `skillgate case edit` |
| Remove a check | `POST /api/evals/pin` | `skillgate case remove` |
| List checks | `GET /api/evals/dataset` | `skillgate case list` |
| Use this skill’s sample files | `POST /api/evals/fixture-bind` | `skillgate case bind` |
| Add a question for every test case | Checks editor → pin | `skillgate judge add-question` (`--choices` for pick one) |
| Edit Fail vs warn | Checks editor → pin | `skillgate judge set-question` |
| Remove an extra question | Checks editor → pin | `skillgate judge remove-question` |
| Run | `POST /api/runs` | `skillgate check` |
| Run one check / try-out | `POST /api/runs` (`checks`, `tryout`) | `skillgate check --case` |
| Skip / stop a run | `POST /api/runs/{run_id}/skip`, `POST /api/runs/{run_id}/kill` | `skillgate check` (Ctrl+C) |
| History | `GET /api/history` | `skillgate history` |
| One run | `GET /api/runs/{run_id}` | `skillgate history show` |
| Compare list | `GET /api/compare` | `skillgate compare list` |
| Compare detail | `GET /api/compare/{compare_id}` | `skillgate compare show` |
| Compare models | `POST /api/compare/models` | `skillgate compare models` |
| Compare versions | `POST /api/compare/versions` | `skillgate compare versions` |
| Cancel compare | `POST /api/compare/{compare_id}/cancel` | `skillgate compare cancel` |
| Deploy | `POST /api/deploy` | `skillgate deploy` |
| Sign in | `POST /api/login/{agent}` | `skillgate login` (`cursor` / `codex` / `claude`) |
| Agent status | `GET /api/login/status` | `skillgate login --status` |
