import { describe, expect, it } from "vitest"

import { absoluteTime, relativeTime } from "./time"

describe("absoluteTime", () => {
  it("turns an ISO stamp into a readable datetime, not the raw string", () => {
    const raw = "2026-10-11T13:04:00.000Z"
    const label = absoluteTime(raw)
    expect(label).toBeTruthy()
    expect(label).not.toBe(raw)
    expect(label).not.toMatch(/T13:04:00/)
    expect(label).toMatch(/2026/)
  })

  it("returns undefined when the value is missing", () => {
    expect(absoluteTime(null)).toBeUndefined()
    expect(absoluteTime("")).toBeUndefined()
  })
})

describe("relativeTime", () => {
  it("keeps a dash for empty values", () => {
    expect(relativeTime(null)).toBe("—")
  })
})
