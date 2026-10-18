# Skill pack layout

A pack is a folder with `SKILL.md` (agentskills spec) plus optional `scripts/`, `evals/`, and other resources. Skill Gate does not invent a parallel blob store.

The local wizard (`skillgate ui`) writes this same layout: `name` in frontmatter equals the folder basename, and `evals/cases.yaml` is schema 1.


```
my-skill/
  SKILL.md
  scripts/agent_entry.py     # optional skill scripts the live harness can run
  evals/
    cases.yaml               # schema: 1 — the source of record
    fixtures/                # inputs (PDFs, CSV, …)
    goldens/                 # expected outputs
    history/                 # append-only JSONL from `skillgate check`
```

## Bulk import

Add many checks at once with `skillgate case import <skill-path> <file>` (CSV, JSONL, or YAML list). Columns match `skillgate case add` (`id`, `prompt`, `expected` / `contains`, `output` / `output_path`, `input` / fixture paths, `should_trigger`, and so on). Missing ids are generated from the prompt. Validation runs for every row before anything is written; `--dry-run` prints a preview table. When an id already exists, use `--on-conflict skip|replace|fail` (default `fail`). Sample files: [`docs/samples/dataset-import.csv`](samples/dataset-import.csv), [`docs/samples/dataset-import.jsonl`](samples/dataset-import.jsonl).

## `evals/cases.yaml` (schema 1)

```yaml
schema: 1
skill: pdf
cases:
  - id: extract-hello
    status: pinned          # only pinned cases run
    prompt: Extract the text from hello.pdf …
    should_trigger: true
    input:
      files:
        - src: evals/fixtures/hello.pdf
          dest: hello.pdf
    golden:
      output_path: output/extracted.txt
      path: evals/goldens/extract-hello.txt
      kind: text            # text | json | bytes
    contains:
      - Hello Skill Gate
  - id: no-trigger-unrelated
    status: pinned
    prompt: Write a pytest for a FastAPI /health endpoint.
    should_trigger: false
    golden: null
```

Paths in `files[].src` and `golden.path` are **relative to the skill folder**.

## Optional output file

Set `output_optional: true` when a check can pass with no output file. You give the judge `contains` as reference text. The file and the reply can omit that sentence.

A missing or empty file passes. Skill Gate checks a present file the same way as a required file. Skill Gate still fails a binary file saved where text is expected.

```yaml
  - id: ask-before-editing-tests
    status: pinned
    prompt: Fix the failing tests. Do not edit tests/.
    should_trigger: true
    output_optional: true
    contains:
      - The agent leaves tests/ unchanged and asks which behavior you want.
    golden:
      output_path: changes.diff
      path: evals/goldens/ask-before-editing-tests.txt
      kind: text
```

Omit `output_optional` to keep the output file required. On a saved check, run `skillgate case edit <skill> --id ask-before-editing-tests --output-optional true`.

Optional `judge:` on the pack or a case adds extra scoring questions **on top of** Skill Gate’s six. Built-in ids cannot be reused; they can only change Fail vs warn (`on_fail`). Seed packs keep their original case ids.

Pick who scores in Settings or `skillgate judge provider set`. Keys stay in `.skillgate/keys` — never ambient `OPENAI_API_KEY` / `AWS_*` unless `--key-env`.

`skillgate check <pack>` expands pinned cases into scorers:

- `skill_trigger` — description-only match (progressive disclosure)
- `task_completion` — expected output path / contains / min_pages
- `rubric` — optional extra checks

## History

`skillgate check` appends one JSONL line under `<pack>/evals/history/YYYYMMDD.jsonl` (same payload as `report_to_dict`). `*.jsonl` is gitignored. If the pack is mounted read-only, history is skipped on `EACCES`.

## Live check

`skillgate check` always runs a live agent harness (Cursor Agent, Codex CLI, or Claude Code). No agent → exit 2; install a CLI and run `skillgate login`, or add a matching key in Settings / `skillgate keys set`. Deterministic scorers (file exists, contains, page count, skill trigger) still grade the live run’s files.
