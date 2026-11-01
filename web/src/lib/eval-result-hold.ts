export const EVAL_MOTION_MS = 350
export const CHECKING_MIN_MS = 700

export type EvalHoldTarget = "checking" | "pass" | "fail" | "error" | "review"

export function resultHoldPlan({
  target,
  reducedMotion,
  sawChecking,
  elapsedMs,
  hold = true,
}: {
  target: EvalHoldTarget
  reducedMotion: boolean
  sawChecking: boolean
  elapsedMs: number | null
  hold?: boolean
}): { showCheckingFirst: boolean; waitMs: number } {
  if (target === "checking") {
    return { showCheckingFirst: true, waitMs: 0 }
  }
  const allowHold = hold && sawChecking
  if (reducedMotion || !allowHold) {
    return { showCheckingFirst: false, waitMs: 0 }
  }
  const elapsed = elapsedMs != null ? elapsedMs : 0
  return {
    showCheckingFirst: true,
    waitMs: Math.max(0, CHECKING_MIN_MS - elapsed),
  }
}

export function initialHoldPhase(
  showCheckingFirst: boolean
): "checking" | "settled" {
  return showCheckingFirst ? "checking" : "settled"
}
