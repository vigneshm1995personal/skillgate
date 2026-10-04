# Skill pack layout

A pack is a folder with `SKILL.md` (agentskills spec) plus optional `scripts/`, `evals/`, and other resources. Skill Gate does not invent a parallel blob store.

```
my-skill/
  SKILL.md
  scripts/agent_entry.py     # demo harness runs this when the skill triggers
  evals/
    cases.yaml               # schema: 1 — the source of record
    fixtures/                # inputs (PDFs, CSV, …)
    goldens/                 # expected outputs
    history/                 # append-only JSONL from `skillgate check`
```

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

`skillgate check <pack>` expands pinned cases into scorers:

- `skill_trigger` — description-only match (progressive disclosure)
- `task_completion` — expected output path / contains / min_pages
- `rubric` — optional extra checks

## History

`skillgate check` appends one JSONL line under `<pack>/evals/history/YYYYMMDD.jsonl` (same payload as `report_to_dict`). `*.jsonl` is gitignored. If the pack is mounted read-only, history is skipped on `EACCES`.

## Demo harness

With no BYOLLM key, `check` uses the demo harness: tokenize name+description, then run `scripts/agent_entry.py` in a tempdir sandbox. Same scorers as a live run.
