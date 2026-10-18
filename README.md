<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="web/public/sg-mark-dark.svg">
    <img alt="skillgate" src="web/public/sg-mark-light.svg" width="96" height="96">
  </picture>
</p>

<h1 align="center">skillgate</h1>

<p align="center">A local gate for agent skills.</p>

<p align="center">
  <a href="https://pypi.org/project/skillgate-ai/"><img alt="PyPI" src="https://img.shields.io/pypi/v/skillgate-ai"></a>
  <a href="https://pypi.org/project/skillgate-ai/"><img alt="Python 3.11+" src="https://img.shields.io/badge/python-3.11%2B-blue"></a>
  <a href="https://github.com/vigneshm1995personal/skillgate/actions/workflows/gate.yml"><img alt="CI" src="https://img.shields.io/github/actions/workflow/status/vigneshm1995personal/skillgate/gate.yml?branch=main&label=CI"></a>
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/github/license/vigneshm1995personal/skillgate"></a>
</p>

skillgate checks an agent skill that lives in a folder on your machine. A pack is `SKILL.md` plus `evals/`. `skillgate check` exits 0 when the run passes, 1 when it fails, and 2 when it cannot run. Live checks are scored only by a decision model you select. Requires Python 3.11+. The package name is `skillgate-ai` (`pip install skillgate` is a different project).

<p align="center">
  <img alt="Local UI on the pdf example, before a live check" src="docs/screenshots/readme-hero-light.png" width="880">
</p>

## Quickstart

In an empty directory:

```bash
pip install skillgate-ai
skillgate examples install
skillgate check skills/json-response
skillgate check skills/json-response-sabotaged
```

`skillgate examples install` writes six skills under `skills/`. Files already in that folder stay as they are. `skills/json-response` exits 0 when the live run is green. `skills/json-response-sabotaged` exits 1: the JSON checks fail, and the unrelated check can pass. Both checks exit 2 until an agent is available and a decision model is selected. Use `skillgate login` or `skillgate keys set` for the agent, and `skillgate judge provider set` for the decision model. These commands match release 0.7.7.

The same steps in the local UI:

```bash
skillgate ui
```

Open http://127.0.0.1:8765. Click **Skills**. On Skill Repository, click **Examples**, then **Install**. The toast reads `Installed 6 examples (47 files).` Open `json-response`, click **Evaluate this skill**, then **Run**. The button reads `Run 3 cases`. Until you sign in or add a key, the line above it is `Next: sign in or add a key in Settings, then press Run.` Repeat for `json-response-sabotaged` to see the failing checks.

## Features

- One pack on disk, checked with `skillgate check`
- Exit 0 (pass), 1 (fail), or 2 (not ready)
- Live checks scored only by a decision model
- Custom scoring questions on top of the built-in questions
- `--expect-fail` for a pack that should fail
- Deploy copies skill files after a passing check
- Local UI with `skillgate ui`
- Compare two versions of the same dataset

## Usage

From the quickstart directory:

```bash
skillgate examples list
skillgate examples install json-response
skillgate check skills/json-response --case flatten-orders
skillgate check skills/json-response-sabotaged --expect-fail
skillgate example pdf
skillgate check skills/pdf
skillgate ingest skills/pdf
skillgate example pdf-sabotaged
skillgate check skills/pdf-sabotaged --expect-fail
skillgate deploy skills/pdf
skillgate judge provider show
skillgate judge add-question --ask "Did the answer follow the requested format?"
skillgate compare versions skills/pdf --dry-run
skillgate ui
```

`--expect-fail` exits 0 only when the live run is red. `skillgate deploy` copies the skill files after this pack already has a passing check. It does not run check for you. Deploy stays blocked until an agent is available, even after a green check. `skillgate ui` serves the local UI at http://127.0.0.1:8765. A version compare takes two `--run` ids or two `--git` refs.

Create a workspace and a skill:

```bash
skillgate init
skillgate new notes-helper
```

## Writing a dataset

A dataset is `evals/cases.yaml` plus small files in `evals/fixtures/` and expected files in `evals/goldens/`. The folder name, the `name` in `SKILL.md`, and `skill` in `cases.yaml` are the same string. Start with 3 to 6 pinned cases: one behavior, one edge, and one unrelated prompt (`should_trigger: false`). Keep the expected sentence out of the prompt. The examples do this: `json-response` flattens an API body, `readme-writer` turns a brief into a README, `log-summarizer` counts errors, `sql-writer` writes a query from a schema, and `receipt-extractor` reads a fictional receipt. `json-response-sabotaged` uses the same JSON cases and fails them.

Check a dataset on disk, then run it:

```bash
skillgate ingest skills/json-response
skillgate case list skills/json-response
skillgate check skills/json-response
```

In the UI, open the skill from Skill Repository and click **Evaluate this skill**, then **Run**.

The full guide, with a copy-paste pack and the mistakes that reject a dataset, is [Writing a dataset](docs/writing-a-dataset.md). The same page is on the docs site: [Writing a dataset](https://www.skill-gate-ai.app/docs/writing-a-dataset).

## Docker

```bash
docker compose run --rm --no-TTY skillgate
```

The image entrypoint is `skillgate`. The default command is `check /pack`. With nothing configured, that exits 2.

## Documentation

[Documentation](https://www.skill-gate-ai.app/docs)

## Contributing

Issues and pull requests are welcome.

## License

Apache License 2.0. See [LICENSE](LICENSE).
