import { useEffect, useRef, useState, type ReactNode } from "react"

import {
  CHECKING_MIN_MS,
  EVAL_MOTION_MS,
  resultHoldPlan,
} from "@/lib/eval-result-hold"
import type { SuiteResultKind } from "@/lib/eval-row-state"

export { CHECKING_MIN_MS, EVAL_MOTION_MS }

export type EvalResultTarget = Exclude<SuiteResultKind, "idle">
export type EvalMarkMode = "idle" | "play" | "complete"

type Phase = "checking" | "crossfade" | "play" | "settled"

function prefersReducedMotion() {
  return Boolean(
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  )
}

function markMode(phase: Phase): EvalMarkMode {
  if (phase === "play") {
    return "play"
  }
  if (phase === "settled") {
    return "complete"
  }
  return "idle"
}

export function EvalResultShell({
  target,
  checking,
  children,
  onResultVisible,
}: {
  target: EvalResultTarget
  checking: ReactNode
  children: (opts: { mode: EvalMarkMode }) => ReactNode
  onResultVisible?: (visible: boolean) => void
}) {
  const sawChecking = useRef(true)
  const checkingShownAt = useRef<number | null>(Date.now())
  const slideTimer = useRef(0)
  const [phase, setPhase] = useState<Phase>("checking")

  useEffect(() => {
    onResultVisible?.(phase !== "checking")
  }, [onResultVisible, phase])

  useEffect(() => {
    if (target === "checking") {
      sawChecking.current = true
      checkingShownAt.current = Date.now()
      setPhase("checking")
      return
    }

    const reduced = prefersReducedMotion()
    const elapsed = checkingShownAt.current
      ? Date.now() - checkingShownAt.current
      : null
    const plan = resultHoldPlan({
      target,
      reducedMotion: reduced,
      sawChecking: sawChecking.current,
      elapsedMs: elapsed,
    })
    if (plan.showCheckingFirst && !sawChecking.current) {
      sawChecking.current = true
      checkingShownAt.current = Date.now()
      setPhase("checking")
    }
    const holdTimer = window.setTimeout(() => {
      if (reduced || !plan.showCheckingFirst) {
        setPhase("settled")
        return
      }
      setPhase("crossfade")
      slideTimer.current = window.setTimeout(() => {
        setPhase("play")
      }, EVAL_MOTION_MS)
    }, plan.waitMs)

    return () => {
      window.clearTimeout(holdTimer)
      window.clearTimeout(slideTimer.current)
    }
  }, [target])

  return (
    <div className="eval-result-stage" id="eval-result-stage">
      {phase === "checking" || phase === "crossfade" ? (
        <div
          className={
            phase === "crossfade"
              ? "eval-result-panel eval-result-leave"
              : "eval-result-panel"
          }
        >
          {checking}
        </div>
      ) : null}
      {phase !== "checking" ? (
        <div
          className={
            phase === "crossfade"
              ? "eval-result-panel eval-result-enter"
              : "eval-result-panel"
          }
        >
          {children({ mode: markMode(phase) })}
        </div>
      ) : null}
    </div>
  )
}
