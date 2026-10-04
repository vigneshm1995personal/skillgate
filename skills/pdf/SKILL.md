---
name: pdf
description: Process PDF files — extract text, merge or split documents, rotate pages, and create new PDFs with Python (pypdf, reportlab). Use this skill whenever the user mentions a .pdf file, invoices, combining documents, extracting text from a PDF, or asking to produce a PDF.
license: Apache-2.0
metadata:
  author: skillgate-ai
  version: "0.1"
---

# PDF skill

Clean-room Apache-2.0 adaptation of the public Agent Skills *shape* (a `SKILL.md` folder) for PDF work. Instructions below are original; they are not a copy of proprietary document-skill text.

## When to use

Use this skill for: extract text, merge PDFs, create a PDF, rotate pages. If the user names a `.pdf` file, start here.

## How to work

Prefer bundled scripts over ad-hoc code. Run them from the workspace root. Create `output/` if the user asks for a path there.

### Extract text

```bash
python3 .skillgate/skills/pdf/scripts/extract_text.py INPUT.pdf output/extracted.txt
```

### Merge

```bash
python3 .skillgate/skills/pdf/scripts/merge_pdfs.py output/merged.pdf INPUT1.pdf INPUT2.pdf
```

### Create

```bash
python3 .skillgate/skills/pdf/scripts/create_pdf.py output/status.pdf --title "Title" --body "Sentence."
```

### Rotate

```bash
python3 .skillgate/skills/pdf/scripts/rotate_pdf.py INPUT.pdf output/rotated.pdf --degrees 90
```

If a task names a different output path, pass that path instead.

There is also `scripts/agent_entry.py`: it reads `SKILLGATE_TASK` and routes to the scripts above. Live Cursor Agent should follow this file the same way.
