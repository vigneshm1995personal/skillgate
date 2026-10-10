import { useEffect, useRef, useState, type ReactNode } from "react"

import type { SuiteResultKind } from "@/lib/eval-row-state"

export const EVAL_MOTION_MS = 350
export const CHECKING_MIN_MS = 700

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
  const sawChecking = useRef(target === "checking")
  const checkingShownAt = useRef<number | null>(
    target === "checking" ? Date.now() : null
  )
  const slideTimer = useRef(0)
  const [phase, setPhase] = useState<Phase>(
    target === "checking" ? "checking" : "settled"
  )

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

    if (!sawChecking.current) {
      setPhase("settled")
      return
    }

    const reduced = prefersReducedMotion()
    const elapsed = checkingShownAt.current
      ? Date.now() - checkingShownAt.current
      : CHECKING_MIN_MS
    const wait = reduced ? 0 : Math.max(0, CHECKING_MIN_MS - elapsed)
    const holdTimer = window.setTimeout(() => {
      if (reduced) {
        setPhase("settled")
        return
      }
      setPhase("crossfade")
      slideTimer.current = window.setTimeout(() => {
        setPhase("play")
      }, EVAL_MOTION_MS)
    }, wait)

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
