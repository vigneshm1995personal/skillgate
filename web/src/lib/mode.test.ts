import { describe, expect, it } from "vitest"

import { isLocalMode, productMode, slotOn } from "@/lib/mode"
import type { StatusPayload } from "@/lib/types"

const localStatus = {
  mode: "local",
  slots: {
    signIn: false,
    billing: false,
    sharedHistory: false,
    hostedJudge: false,
    sandboxes: false,
    tryoutCaps: false,
    generateChecks: false,
    gitPublish: false,
    suggestUpdates: false,
    analyticsHome: false,
  },
} as StatusPayload

describe("mode slots", () => {
  it("fails closed in local when status is missing", () => {
    expect(productMode(null)).toBe("local")
    expect(isLocalMode(null)).toBe(true)
    expect(slotOn(null, "signIn")).toBe(false)
    expect(slotOn(undefined, "analyticsHome")).toBe(false)
    expect(slotOn(localStatus, "generateChecks")).toBe(false)
    expect(slotOn(localStatus, "sharedHistory")).toBe(false)
    expect(slotOn(localStatus, "gitPublish")).toBe(false)
  })

  it("shows paid slots in cloud when the server says so", () => {
    const cloud = {
      mode: "cloud",
      slots: { ...localStatus.slots, generateChecks: true, sharedHistory: true },
    } as StatusPayload
    expect(slotOn(cloud, "generateChecks")).toBe(true)
    expect(slotOn(cloud, "sharedHistory")).toBe(true)
    expect(slotOn(cloud, "signIn")).toBe(false)
  })
})
