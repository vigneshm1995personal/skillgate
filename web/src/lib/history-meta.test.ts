import { describe, expect, it } from "vitest"

import { historyMeta } from "./history-meta"

describe("historyMeta", () => {
  it("shows Auto instead of a removed demo harness", () => {
    expect(
      historyMeta({
        kind: "run",
        skill: "pdf",
        harness: "demo",
      }).config
    ).toBe("Auto")
  })

  it("capitalizes Install to Cursor", () => {
    expect(
      historyMeta({
        kind: "deploy",
        skill: "pdf",
        target: "cursor",
      }).config
    ).toBe("Install to Cursor")
  })
})
