import { useEffect, useRef, useState, type ReactNode } from "react"

import { initialHoldPhase, resultHoldPlan } from "@/lib/eval-result-hold"
import type { SuiteResultKind } from "@/lib/eval-row-state"

export const CHECKING_MIN_MS = 700
export const EVAL_MOTION_MS = 350

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
  hold = true,
}: {
  target: EvalResultTarget
  checking: ReactNode
  children: (opts: { mode: EvalMarkMode }) => ReactNode
  onResultVisible?: (visible: boolean) => void
  hold?: boolean
}) {
  const didShowChecking = useRef(target === "checking")
  const checkingShownAt = useRef<number | null>(
    target === "checking" ? Date.now() : null
  )
  const slideTimer = useRef(0)
  const [phase, setPhase] = useState<Phase>(() =>
    initialHoldPhase(
      resultHoldPlan({
        target,
        reducedMotion: false,
        sawChecking: target === "checking",
        elapsedMs: null,
        hold,
      }).showCheckingFirst
    )
  )

  useEffect(() => {
    onResultVisible?.(phase !== "checking")
  }, [onResultVisible, phase])

  useEffect(() => {
    if (target === "checking") {
      didShowChecking.current = true
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
      sawChecking: didShowChecking.current,
      elapsedMs: elapsed,
      hold,
    })
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
  }, [hold, target])

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
