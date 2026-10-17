import { AlertTriangleIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/spinner"
import type { LiveState } from "@/lib/types"

export function StallRadar({
  id = "stall-radar",
  live,
  stalled,
  elapsedSec,
  tail,
  evaluating,
  busy,
  peek,
  skipLabel = "Skip check",
  killLabel = "Kill run",
  peekLabel = "Peek last lines",
  onPeek,
  onSkip,
  onKill,
}: {
  id?: string
  live?: LiveState | null
  stalled?: boolean
  elapsedSec?: number | null
  tail?: LiveState["tail"]
  evaluating: boolean
  busy: "skip" | "kill" | null
  peek: boolean
  skipLabel?: string
  killLabel?: string
  peekLabel?: string
  onPeek: () => void
  onSkip: () => void
  onKill: () => void
}) {
  if (!evaluating || !(stalled ?? live?.stalled)) {
    return null
  }
  const reason =
    live?.stall_reason === "repeating"
      ? "The run keeps printing the same line."
      : `No new output for ${Math.round(live?.silent_for_sec ?? 0)}s.`
  const preview = (tail ?? live?.tail ?? [])
    .slice(-5)
    .map((line) => line.text)
    .join("\n")
  return (
    <div
      id={id}
      role="status"
      className="flex flex-col gap-2 rounded-xl border border-amber-500/40 bg-amber-500/10 px-3 py-2.5"
    >
      <div className="flex items-start gap-2">
        <AlertTriangleIcon className="mt-0.5 size-4 shrink-0 text-amber-600" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-amber-700">
            Possible stall on {live?.task_id}
            {elapsedSec != null ? (
              <span className="sr-only"> {Math.round(elapsedSec)}s elapsed</span>
            ) : null}
          </p>
          <p className="text-sm text-amber-700/90">
            {reason} You can skip this check and keep the run going, or kill the
            whole run.
          </p>
        </div>
      </div>
      {peek ? (
        <pre className="max-h-32 max-w-full overflow-auto rounded-lg border border-amber-500/30 bg-background/60 p-2 font-mono text-xs break-words whitespace-pre-wrap">
          {preview || "(no output yet)"}
        </pre>
      ) : null}
      <div className="flex flex-wrap items-center gap-2">
        <Button
          id="btn-skip-check"
          type="button"
          size="sm"
          variant="outline"
          disabled={busy !== null}
          onClick={onSkip}
        >
          {busy === "skip" ? <Spinner data-icon="inline-start" /> : null}
          {skipLabel}
        </Button>
        <Button
          id="btn-kill-run"
          type="button"
          size="sm"
          variant="outline"
          disabled={busy !== null}
          onClick={onKill}
        >
          {busy === "kill" ? <Spinner data-icon="inline-start" /> : null}
          {killLabel}
        </Button>
        <Button
          id="btn-peek-tail"
          type="button"
          size="sm"
          variant="ghost"
          onClick={onPeek}
        >
          {peek ? "Hide last lines" : peekLabel}
        </Button>
      </div>
    </div>
  )
}
