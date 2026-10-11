import { useMemo, useState } from "react"
import { CheckIcon, ChevronDownIcon, XIcon } from "lucide-react"

import { cn } from "cn"
import { AssistantMarkdown } from "@/components/dashboard/assistant-markdown"
import { Spinner } from "@/components/ui/spinner"
import {
  countHarnessCommands,
  harnessPhaseLabel,
  harnessPhaseRank,
  pickTimelineSteps,
  type TimelineStep,
} from "@/lib/parse-transcript-steps"
import type { OtlpSpan } from "@/lib/types"

function StepIcon({ status }: { status: TimelineStep["status"] }) {
  if (status === "fail") {
    return (
      <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-destructive/10 text-destructive">
        <XIcon className="size-3.5" />
      </span>
    )
  }
  if (status === "pass") {
    return (
      <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-success/10 text-success">
        <CheckIcon className="size-3.5" />
      </span>
    )
  }
  return (
    <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground">
      <span className="size-1.5 rounded-full bg-muted-foreground/70" />
    </span>
  )
}

function TimelineStepRow({
  step,
  isLast,
}: {
  step: TimelineStep
  isLast: boolean
}) {
  const [open, setOpen] = useState(false)
  return (
    <div className="flex min-w-0 gap-3">
      <div className="flex flex-col items-center">
        <StepIcon status={step.status} />
        {!isLast ? (
          <span className="mt-1 w-px flex-1 bg-border" aria-hidden />
        ) : null}
      </div>
      <div className={cn("min-w-0 flex-1 overflow-hidden", !isLast && "pb-4")}>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex w-full min-w-0 items-start justify-between gap-2 rounded-lg text-left transition-colors hover:bg-muted/40 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
        >
          <span className="min-w-0 flex-1 overflow-hidden">
            <span className="block text-sm font-medium break-words">{step.title}</span>
            {step.subtitle ? (
              <span className="block font-mono text-xs text-muted-foreground break-words whitespace-normal">
                {step.subtitle}
              </span>
            ) : null}
          </span>
          {step.detail ? (
            <ChevronDownIcon
              className={cn(
                "mt-1 size-3.5 shrink-0 text-muted-foreground transition-transform",
                open && "rotate-180"
              )}
            />
          ) : null}
        </button>
        {open && step.detail ? (
          <div className="mt-2 max-h-40 max-w-full overflow-auto rounded-lg border bg-muted/40 p-2.5">
            {step.title === "Assistant" ? (
              <AssistantMarkdown text={step.detail} />
            ) : (
              <pre className="font-mono text-[11px] leading-relaxed break-words whitespace-pre-wrap text-muted-foreground">
                {step.detail}
              </pre>
            )}
          </div>
        ) : null}
      </div>
    </div>
  )
}

export function RunTimeline({
  transcript,
  passed,
  spans,
  running = false,
  phaseKey,
}: {
  transcript?: string | null
  passed?: boolean | null
  spans?: OtlpSpan[] | null
  /** Check still executing: empty state shows the sandbox/agent phase. */
  running?: boolean
  /** Identity of the running check; the phase label never moves backward for it. */
  phaseKey?: string | null
}) {
  // Monotonic phase: hold the furthest phase seen for this check so a poll
  // that briefly returns an older snapshot can't flip the label backward.
  const rawPhase = harnessPhaseLabel(transcript)
  const [heldPhase, setHeldPhase] = useState({ key: phaseKey ?? null, label: rawPhase })
  let phaseLabel = rawPhase
  if (heldPhase.key !== (phaseKey ?? null)) {
    setHeldPhase({ key: phaseKey ?? null, label: rawPhase })
  } else if (harnessPhaseRank(rawPhase) > harnessPhaseRank(heldPhase.label)) {
    setHeldPhase({ key: heldPhase.key, label: rawPhase })
  } else if (harnessPhaseRank(heldPhase.label) > harnessPhaseRank(rawPhase)) {
    phaseLabel = heldPhase.label
  }
  const steps = useMemo(
    () => pickTimelineSteps({ transcript, spans, passed }),
    [transcript, spans, passed]
  )
  const commandCount = useMemo(() => {
    const fromSpans = (spans ?? []).filter(
      (span) => span.name.startsWith("tool.") || span.name === "skill.select"
    ).length
    return fromSpans || countHarnessCommands(transcript)
  }, [spans, transcript])
  const [logOpen, setLogOpen] = useState(false)
  const hasTranscript = Boolean(transcript?.trim())
  const hasLog = hasTranscript || (spans?.length ?? 0) > 0

  if (!hasLog && !running) {
    return null
  }

  return (
    <div
      id="run-timeline"
      className="flex min-w-0 max-w-full flex-col gap-3 overflow-hidden rounded-xl border bg-card p-3"
    >
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-medium">What happened</p>
        {steps.length ? (
          <span className="text-xs text-muted-foreground">
            {steps.length} step{steps.length === 1 ? "" : "s"}
          </span>
        ) : null}
      </div>

      {steps.length ? (
        <div className="flex flex-col">
          {steps.map((step, index) => (
            <TimelineStepRow
              key={step.id}
              step={step}
              isLast={index === steps.length - 1}
            />
          ))}
          {running ? (
            <p
              id="run-timeline-phase"
              className="flex items-center gap-2 pl-10 text-xs text-muted-foreground"
            >
              <Spinner className="size-3" />
              Agent is working…
            </p>
          ) : null}
        </div>
      ) : running ? (
        <p
          id="run-timeline-phase"
          role="status"
          className="flex items-center gap-2 text-sm text-muted-foreground"
        >
          <Spinner className="size-3.5" />
          {phaseLabel}
        </p>
      ) : (
        <p id="run-timeline-empty" className="text-sm text-muted-foreground">
          {hasTranscript
            ? "No agent steps were recorded for this check. The log below has the full output."
            : "No agent steps were recorded for this check."}
        </p>
      )}

      {hasTranscript ? (
        <div className="border-t pt-2">
          <button
            type="button"
            onClick={() => setLogOpen((v) => !v)}
            className="flex w-full items-center gap-2 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
          >
            <ChevronDownIcon
              className={cn(
                "size-3.5 transition-transform",
                logOpen && "rotate-180"
              )}
            />
            Show full log
            {commandCount ? ` (${commandCount} commands)` : ""}
          </button>
          {logOpen ? (
            <pre className="mt-2 max-h-48 max-w-full overflow-auto rounded-lg border bg-muted/40 p-3 font-mono text-xs break-words whitespace-pre-wrap">
              {transcript}
            </pre>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
