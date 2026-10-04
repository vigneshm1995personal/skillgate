# Phase 3 proof matrix

Live evidence captured **2026-10-04** on this Ubuntu 24.04.4 cloud-agent VM (Python 3.12.3). Every row was run, not inferred from diffs. Repo stays **PRIVATE**.

Fix applied during proof: Docker bind-mounts the pack at `/pack`, so the folder basename is `pack` while `SKILL.md` `name:` is `pdf` / `pdf-sabotaged`. Ingest now treats basename `pack` as the documented container mount (agentskills name==folder still enforced for any other folder). Test: `tests/test_ingest.py::test_generic_pack_mount_allows_skill_name`. After the fix: `docker run` pdf **exit 0**, sabotaged **exit 1**.

| # | Item | Result | Expected | Actual | Evidence |
| --- | --- | --- | --- | --- | --- |
| 1 | `pip install -e .` | **PASS** | 0 | 0 | [01-pip-install.log](01-pip-install.log) |
| 2 | `skillgate --help` / `skillgate version` | **PASS** | 0 / `0.3.0` | 0 / `0.3.0` | [02-help.log](02-help.log), [02-version.log](02-version.log) |
| 3 | `skillgate check skills/pdf-sabotaged` | **PASS** | 1 (RED 1/8) | 1 | [03-check-sabotaged.log](03-check-sabotaged.log) |
| 4 | `skillgate check skills/pdf-sabotaged --expect-fail` | **PASS** | 0 | 0 | [04-check-sabotaged-expect-fail.log](04-check-sabotaged-expect-fail.log) |
| 5 | `skillgate check skills/pdf` | **PASS** | 0 (GREEN 8/8) | 0 | [05-check-pdf.log](05-check-pdf.log) |
| 6 | `evals/history/` JSONL write after a check | **PASS** | jsonl grows | `skills/pdf/evals/history/20261004.jsonl` and sabotaged twin written (gitignored) | [06-history.log](06-history.log) |
| 7 | Every shipped CLI command | **PASS** | see below | see below | [07-list.log](07-list.log), [07-ingest.log](07-ingest.log), [07-run.log](07-run.log), [07-deploy.log](07-deploy.log), [07-cli-all-help.log](07-cli-all-help.log) |
| 8 | `pytest -q` | **PASS** | 0 | 0 — **35 passed** | [08-pytest.log](08-pytest.log) |
| 9 | AST / deny-list (no vault/siwv/web/remote_harness) | **PASS** | 0 | 0 — 5 tests | [09-ast-deny.log](09-ast-deny.log) |
| 10 | ripgrep leaked strings | **PASS** | no hosted files, no secret values | hosted files absent; hits are deny-list/docs/blocklist only | [10-leak-scan.log](10-leak-scan.log) |
| 11 | Docker build + run red/green | **PASS** | build 0; pdf 0; sabotaged 1 | build 0; pdf 0; sabotaged 1; compose same | [11-docker-build.log](11-docker-build.log), [11-docker-run-green.log](11-docker-run-green.log), [11-docker-run-red.log](11-docker-run-red.log), [11-compose-green.log](11-compose-green.log), [11-compose-red.log](11-compose-red.log), [11-docker-inspect.log](11-docker-inspect.log) |
| 12 | Copy-paste workflow YAML present and matches CLI | **PASS** | `skillgate check` | parsed; `pip install skillgate-ai==0.3.0` + `skillgate check .` | [12-workflow.log](12-workflow.log) |
| 13 | `docs/quickstart.md` as written (fresh venv) | **PASS** | sabotaged 1, pdf 0, expect-fail 0 | 1 / 0 / 0 from `.venv/bin/skillgate` | [13-quickstart.log](13-quickstart.log) |
| 14 | pyproject has no FastAPI/psycopg/cryptography/sentry required deps | **PASS** | none of those | none; required = typer/rich/pyyaml/pydantic/httpx/python-dotenv/pypdf/reportlab | [14-pyproject.log](14-pyproject.log) |

## Item 7 — every CLI command that exists

Shipped commands (`skillgate --help`): `version`, `ingest`, `check`, `run`, `deploy`, `list`. There is **no** `serve`.

| Command | Exit | Notes |
| --- | --- | --- |
| `skillgate --help` | 0 | lists the six commands |
| `skillgate version` | 0 | `0.3.0` |
| `skillgate ingest skills/pdf` | 0 | `OK  pdf` |
| `skillgate check` | 1 / 0 / 0 | items 3–5 |
| `skillgate run skills/pdf` | 0 | GREEN 8/8 |
| `skillgate deploy skills/pdf --target cursor` | 0 | `SKILLGATE_CURSOR_SKILLS=/tmp/skillgate-proof-skills` → 16 files |
| `skillgate list` | 0 | `pdf`, `pdf-sabotaged` |
| `skillgate serve` | 2 | `No such command 'serve'` |

## Item 10 — leak scan classification

**Absent on disk:** `auth_siwv.py`, `vault.py`, `store.py`, `store_postgres.py`, `web.py`, `web/`, `eval_slice.py`, `remote_harness/`, `Dockerfile.vercel`, `docs/vercel-hosting.md`, `docs/neon-store.md`, `db-creds.env`.

**Needles that appear only as deny-list / “not in this package” docs / sandbox env blocklist:**

- `SIWV`, `auth_siwv`, `Dockerfile.vercel` — extract plan, README/quickstart “not included”, `scripts/extract-from-skillgate-ai.sh` DENY array, `tests/test_oss_surface.py`
- `SKILLGATE_SECRETS_KEY` — `sandbox.py` blocked-env set (do not leak keys into the skill process); `tests/test_dockerfile.py` asserts it is not `ARG`/`ENV` in the image; extract plan
- `DATABASE_URL` / Neon / Vercel Sandbox — extract plan + README/quickstart stating they stay private

**Not found:** `neon.tech` hostnames, `postgres://` connection strings, `SKILLGATE_SECRETS_KEY=` assignments, JWT-like blobs.

## Item 11 — Docker (installed and run here)

This VM had no Docker CLI. Installed `docker.io`, `docker-compose-v2`, `docker-buildx`. No systemd: started `dockerd` on a unix socket (storage-driver `vfs` because overlay2 + `--icc=false` + `--iptables=false` is invalid). Inspect: `user=appuser entry=["skillgate"] cmd=["check","/pack"]`.

First `docker run -v …/pdf:/pack` failed with `Skill name 'pdf' must match the folder name 'pack'` — that is the ingest fix above. Rebuild then:

```
docker build -t skillgate:test --target runtime .     # EXIT:0
docker run --rm -v $PWD/skills/pdf:/pack skillgate:test              # EXIT:0 GREEN 8/8
docker run --rm -v $PWD/skills/pdf-sabotaged:/pack skillgate:test    # EXIT:1 RED 1/8
docker compose run --rm --no-TTY skillgate                           # EXIT:0
PACK=./skills/pdf-sabotaged docker compose run --rm --no-TTY skillgate  # EXIT:1
```

## Item 12 — workflow vs CLI

Copy-paste Action in `docs/quickstart.md` uses `skillgate check .` (CLI `check` takes a pack directory). Dist name `skillgate-ai==0.3.0` matches `pyproject.toml`. Until PyPI publish, this repo’s CI (`.github/workflows/gate.yml`) uses `pip install -e .` and `skillgate check skills/pdf` because **this** repo is the tool, not a single pack. Both invoke the same `check` command.

## Item 13 — quickstart as written

Host lacked `python3-venv`; installed `python3.12-venv` so `python3 -m venv .venv` works as documented (environment gap, not a docs bug). Fresh `.venv`: `pip install -e .` → `skillgate version` = `0.3.0` → sabotaged exit 1 → pdf exit 0 → `--expect-fail` exit 0. Binary: `/workspace/.venv/bin/skillgate`.

## Item 14 — required deps

```
typer>=0.12
rich>=13.7
pyyaml>=6.0
pydantic>=2.7
httpx>=0.27
python-dotenv>=1.0
pypdf>=4.2
reportlab>=4.2
```

No FastAPI, uvicorn, psycopg, cryptography, or sentry in required or optional deps (`dev` = pytest + ruff only).
