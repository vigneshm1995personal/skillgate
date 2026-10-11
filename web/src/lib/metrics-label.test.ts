import { describe, expect, it } from "vitest"

import {
  checkUsageLine,
  pathEfficiencySoftRow,
  pathOpenedCaption,
} from "./metrics-label"

describe("checkUsageLine", () => {
  it("matches the row's Not checked when tokens and steps are empty", () => {
    expect(checkUsageLine(null, { path: { steps: 0, had_path: false } })).toBe(
      "Not checked"
    )
    expect(checkUsageLine(undefined, undefined)).toBe("Not checked")
  })

  it("keeps recorded tokens and steps", () => {
    expect(
      checkUsageLine(
        { tokens_total: 1200 },
        { path: { steps: 3, had_path: true } }
      )
    ).toMatch(/1\.2k tok/)
  })
})

describe("path labels", () => {
  it("calls an efficient path Direct, not Efficient", () => {
    expect(pathEfficiencySoftRow({ choice: "Efficient" }).chip).toBe("Direct")
    expect(pathOpenedCaption("Efficient")).toBe("Direct")
  })
})
