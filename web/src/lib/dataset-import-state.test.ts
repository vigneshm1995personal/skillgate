import { describe, expect, it } from "vitest"

import { datasetImportFooter } from "@/lib/dataset-import-state"

describe("datasetImportFooter", () => {
  it("blocks import when any row has an error", () => {
    const result = datasetImportFooter([
      { row: 1, id: "a", prompt: "ok", action: "add" },
      {
        row: 2,
        id: "b",
        prompt: "",
        action: "skip",
        error: "Each row needs a prompt.",
      },
    ])
    expect(result.canImport).toBe(false)
    expect(result.hint).toBe("Fix 1 row to import")
  })

  it("allows import when every row is clean", () => {
    const result = datasetImportFooter([
      { row: 1, id: "csv-smoke", prompt: "Extract text", action: "add" },
    ])
    expect(result.canImport).toBe(true)
    expect(result.hint).toBeNull()
  })

  it("counts multiple error rows in the hint", () => {
    const result = datasetImportFooter([
      { row: 1, id: "a", prompt: "x", action: "add" },
      { row: 2, id: "a", prompt: "y", action: "skip", error: "Duplicate id" },
      { row: 3, id: "b", prompt: "", action: "skip", error: "Missing prompt" },
    ])
    expect(result.canImport).toBe(false)
    expect(result.hint).toBe("Fix 2 rows to import")
  })
})
