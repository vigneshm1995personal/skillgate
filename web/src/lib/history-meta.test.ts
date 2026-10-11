import { describe, expect, it } from "vitest"

import { historyMeta } from "./history-meta"

describe("historyMeta", () => {
  it("does not alias a removed demo harness to Auto", () => {
    expect(
      historyMeta({
        kind: "run",
        skill: "pdf",
        harness: "demo",
      }).config
    ).not.toBe("Auto")
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
