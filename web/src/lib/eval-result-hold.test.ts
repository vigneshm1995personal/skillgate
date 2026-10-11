import { describe, expect, it } from "vitest"

import { CHECKING_MIN_MS, resultHoldPlan } from "./eval-result-hold"

describe("resultHoldPlan", () => {
  it("holds Checking even when the run is already done", () => {
    const plan = resultHoldPlan({
      target: "pass",
      reducedMotion: false,
      sawChecking: false,
      elapsedMs: null,
    })
    expect(plan.showCheckingFirst).toBe(true)
    expect(plan.waitMs).toBe(CHECKING_MIN_MS)
  })

  it("skips the hold when motion is reduced", () => {
    const plan = resultHoldPlan({
      target: "fail",
      reducedMotion: true,
      sawChecking: false,
      elapsedMs: null,
    })
    expect(plan.showCheckingFirst).toBe(false)
    expect(plan.waitMs).toBe(0)
  })
})
