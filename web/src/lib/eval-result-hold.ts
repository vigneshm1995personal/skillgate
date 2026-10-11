export const EVAL_MOTION_MS = 350
export const CHECKING_MIN_MS = 700

export type EvalHoldTarget = "checking" | "pass" | "fail" | "error"

export function resultHoldPlan({
  target,
  reducedMotion,
  sawChecking,
  elapsedMs,
}: {
  target: EvalHoldTarget
  reducedMotion: boolean
  sawChecking: boolean
  elapsedMs: number | null
}): { showCheckingFirst: boolean; waitMs: number } {
  if (target === "checking") {
    return { showCheckingFirst: true, waitMs: 0 }
  }
  if (reducedMotion) {
    return { showCheckingFirst: false, waitMs: 0 }
  }
  const elapsed = sawChecking && elapsedMs != null ? elapsedMs : 0
  return {
    showCheckingFirst: true,
    waitMs: Math.max(0, CHECKING_MIN_MS - elapsed),
  }
}
