import { describe, expect, it } from "vitest"

import { CHECKING_MIN_MS, initialHoldPhase, resultHoldPlan } from "./eval-result-hold"

describe("resultHoldPlan", () => {
  it("does not replay Checking when a finished run remounts", () => {
    const plan = resultHoldPlan({
      target: "pass",
      reducedMotion: false,
      sawChecking: false,
      elapsedMs: null,
    })
    expect(plan.showCheckingFirst).toBe(false)
    expect(plan.waitMs).toBe(0)
    expect(initialHoldPhase(plan.showCheckingFirst)).toBe("settled")
  })

  it("holds Checking for the minimum time after this run actually checked", () => {
    const plan = resultHoldPlan({
      target: "fail",
      reducedMotion: false,
      sawChecking: true,
      elapsedMs: 0,
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

  it("skips Checking on a completed historical run", () => {
    const plan = resultHoldPlan({
      target: "pass",
      reducedMotion: false,
      sawChecking: false,
      elapsedMs: null,
      hold: false,
    })
    expect(plan.showCheckingFirst).toBe(false)
    expect(plan.waitMs).toBe(0)
    expect(initialHoldPhase(plan.showCheckingFirst)).toBe("settled")
  })
})
