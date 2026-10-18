---
name: receipt-extractor
description: Extract the merchant, date, and total from a plain-text receipt. Use when the user shares a receipt and wants those fields.
license: Apache-2.0
metadata:
  author: skillgate-ai
  version: "0.1"
---

# Receipt extractor

Read a plain-text receipt. Return the merchant (first line), the date, and the total. If there is no total line, set total to null. Do not guess a number.

## How to work

```bash
python3 .skillgate/skills/receipt-extractor/scripts/agent_entry.py
```

The script reads the `.txt` file named in the task and writes JSON.
