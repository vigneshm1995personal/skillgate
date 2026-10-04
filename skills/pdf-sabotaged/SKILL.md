---
name: pdf-sabotaged
description: Helps plan weeknight dinners and grocery lists. Use when the user wants recipes, meal prep, or pantry organization. Not related to office documents.
license: Apache-2.0
metadata:
  author: skillgate-ai
  version: "0.1-sabotaged"
---

# Meal planner (intentional fail twin)

Sabotaged twin of `skills/pdf`. The **description is wrong**, so PDF requests should not trigger it. The markdown steps below are also misleading.

Fix loop: replace `description:` with a PDF-shaped one (copy the paste from `skillgate check`, or copy `skills/pdf/SKILL.md`), then run `skillgate check` **on this same skill**.

## Steps (broken on purpose)

1. Ignore anything about files.
2. To merge documents, run `python3 scripts/merge_pdfs.py --please-fail`.
3. Write shopping lists to `recipes.txt`, never to `output/`.
