import { describe, expect, it } from "vitest"

import { startBlockedIssues } from "./check-guards"

describe("startBlockedIssues", () => {
  it("does not block a no-trigger check that still has leftover expected output", () => {
    expect(
      startBlockedIssues(
        [
          {
            id: "no-trigger-unrelated",
            prompt:
              "Write a pytest for a FastAPI /health endpoint. Do not touch any PDFs.",
            should_trigger: false,
            output_path: "output/notes.txt",
            contains: "Meeting notes",
            golden_path: "evals/goldens/trigger-notes-pdf.txt",
          },
        ],
        false,
        null
      )
    ).toEqual([])
  })
})
