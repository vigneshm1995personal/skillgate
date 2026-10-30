import { cn } from "cn"

import type { EvalMarkMode } from "@/components/dashboard/eval-result-shell"

export function EvalResultMark({
  kind,
  mode,
}: {
  kind: "pass" | "fail" | "review"
  mode: EvalMarkMode
}) {
  return (
    <div
      className={cn(
        "eval-result-mark",
        kind === "pass" ? "text-success" : kind === "review" ? "text-warning" : "text-destructive",
        kind === "fail" && "fail",
        mode === "play" ? "play" : "complete"
      )}
      role="img"
      aria-label={kind === "pass" ? "Passed" : kind === "review" ? "Needs review" : "Failed"}
    >
      <svg viewBox="0 0 72 72" aria-hidden="true">
        <circle
          cx="36"
          cy="36"
          r="32"
          fill="none"
          stroke="currentColor"
          strokeWidth="3"
        />
        {kind === "fail" ? (
          <path
            d="M24 24 L48 48 M48 24 L24 48"
            fill="none"
            stroke="currentColor"
            strokeWidth="4"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        ) : (
          <path
            d="M22 37 l10 10 18-22"
            fill="none"
            stroke="currentColor"
            strokeWidth="4"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        )}
      </svg>
    </div>
  )
}
