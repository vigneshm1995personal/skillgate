import { useState } from "react"

import { cn } from "cn"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { RunTimeline } from "@/components/dashboard/run-timeline"
import {
  CHECK_QUESTION_ORDER,
  checkHeadline,
  extraFailWhy,
  happenedLine,
  lowConfidenceWarning,
  missingJudgeAnswersLine,
  openedCheckAnswers,
  pathOpenedLine,
} from "@/lib/check-results"
import {
  taskChip,
  taskState,
} from "@/lib/eval-row-state"
import { formatCost, formatTokens, taskMetricsLine } from "@/lib/metrics-label"
import { useTickingElapsed } from "@/lib/use-elapsed"
import { useDashboard } from "@/lib/dashboard-provider"
import type { LiveState, TaskResult, VsBaseline } from "@/lib/types"
import { Spinner } from "@/components/ui/spinner"

export function ChecksResultsTable({
  tasks,
  runKey,
  running,
  live,
  onPromote,
  onRunCheck,
}: {
  tasks: TaskResult[]
  runKey: string
  running: boolean
  live?: LiveState | null
  onPromote: (task: TaskResult) => void
  onRunCheck?: (task: TaskResult) => void
}) {
  const hasKey = Boolean(useDashboard().status?.has_key)
  const runningIndex = tasks.findIndex((task) => taskState(task) === "running")
  const [open, setOpen] = useState<number | null>(
    runningIndex >= 0 ? runningIndex : null
  )
  const [lastRunKey, setLastRunKey] = useState(runKey)
  const [lastRunning, setLastRunning] = useState(runningIndex)
  if (runKey !== lastRunKey) {
    setLastRunKey(runKey)
    setOpen(runningIndex >= 0 ? runningIndex : null)
    setLastRunning(runningIndex)
  } else if (runningIndex !== lastRunning) {
    setLastRunning(runningIndex)
    if (runningIndex >= 0) {
      setOpen(runningIndex)
    }
  }

  return (
    <div className="max-w-full min-w-0 overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b text-left">
            <th className="py-2 pr-3 font-medium">Result</th>
            <th className="py-2 pr-3 font-medium">Check</th>
            <th className="py-2 font-medium">What happened</th>
          </tr>
        </thead>
        <tbody>
          {tasks.map((task, index) => {
            const chip = taskChip(task)
            const state = taskState(task)
            const done = state === "done"
            const isRunning = state === "running"
            const expandable = done || isRunning
            const hid = `check-detail-${runKey}-${index}`
            const isOpen = open === index
            const mark =
              chip === "pass"
                ? "PASS"
                : chip === "fail"
                  ? "FAIL"
                  : chip === "running"
                    ? "Running"
                    : chip === "skipped"
                      ? "Skipped"
                      : "Queued"
            const happened =
              chip === "running"
                ? "In progress"
                : chip === "queued"
                  ? "Queued"
                  : happenedLine(task)
            const toggle = () => {
              if (!expandable) {
                return
              }
              setOpen(isOpen ? null : index)
            }
            return (
              <CheckPair
                key={`${task.id}-${index}`}
                task={task}
                index={index}
                hid={hid}
                mark={mark}
                chip={chip}
                happened={happened}
                expandable={expandable}
                isOpen={isOpen}
                isRunning={isRunning}
                done={done}
                skipped={Boolean(task.skipped)}
                running={running}
                live={live}
                onToggle={toggle}
                onPromote={onPromote}
                onRunCheck={onRunCheck}
                hasKey={hasKey}
              />
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function CheckPair({
  task,
  index,
  hid,
  mark,
  chip,
  happened,
  expandable,
  isOpen,
  isRunning,
  done,
  skipped,
  running,
  live,
  onToggle,
  onPromote,
  onRunCheck,
  hasKey,
}: {
  task: TaskResult
  index: number
  hid: string
  mark: string
  chip: ReturnType<typeof taskChip>
  happened: string
  expandable: boolean
  isOpen: boolean
  isRunning: boolean
  done: boolean
  skipped: boolean
  running: boolean
  live?: LiveState | null
  onToggle: () => void
  onPromote: (task: TaskResult) => void
  onRunCheck?: (task: TaskResult) => void
  hasKey: boolean
}) {
  return (
    <>
      <tr
        className={cn(
          "check-row border-b",
          expandable && "cursor-pointer hover:bg-muted/40"
        )}
        tabIndex={expandable ? 0 : undefined}
        aria-expanded={expandable ? (isOpen ? "true" : "false") : undefined}
        aria-controls={expandable ? hid : undefined}
        onClick={expandable ? onToggle : undefined}
        onKeyDown={
          expandable
            ? (event) => {
                if (event.key !== "Enter" && event.key !== " ") {
                  return
                }
                event.preventDefault()
                onToggle()
              }
            : undefined
        }
      >
        <td
          className={cn(
            "w-[5.5rem] py-2 pr-3 align-top font-semibold whitespace-nowrap",
            chip === "pass" && "text-success",
            chip === "fail" && "text-destructive",
            (chip === "queued" || chip === "running" || chip === "skipped") &&
              "text-muted-foreground font-medium"
          )}
        >
          <button
            type="button"
            className="check-toggle p-0 text-left font-semibold text-inherit"
            tabIndex={-1}
            aria-expanded={expandable ? (isOpen ? "true" : "false") : undefined}
            aria-controls={expandable ? hid : undefined}
            aria-label={isOpen ? "Hide details" : "Show details"}
            disabled={!expandable}
            onClick={(event) => {
              event.stopPropagation()
              if (expandable) {
                onToggle()
              }
            }}
          >
            {chip === "running" ? (
              <span className="inline-flex items-center gap-1">
                <Spinner className="size-3" />
                {mark}
              </span>
            ) : (
              mark
            )}
          </button>
          {task.vs_baseline?.hard === true ? (
            <Badge
              id={`check-regressed-${index}`}
              variant="destructive"
              className="mt-1"
            >
              Regressed
            </Badge>
          ) : null}
        </td>
        <td className="py-2 pr-3 align-top">{checkHeadline(task)}</td>
        <td className="py-2 align-top">{happened}</td>
      </tr>
      <tr id={hid} className="check-detail" hidden={!isOpen}>
        <td colSpan={3} className="bg-muted/20 px-1 py-3">
          {isRunning ? (
            <LiveTailPanel live={live} task={task} />
          ) : done ? (
            <OpenedDetails
              task={task}
              index={index}
              happened={happened}
              skipped={skipped}
              running={running}
              onPromote={onPromote}
              onRunCheck={onRunCheck}
              hasKey={hasKey}
            />
          ) : null}
        </td>
      </tr>
    </>
  )
}

function OpenedDetails({
  task,
  index,
  happened,
  skipped,
  running,
  onPromote,
  onRunCheck,
  hasKey,
}: {
  task: TaskResult
  index: number
  happened: string
  skipped: boolean
  running: boolean
  onPromote: (task: TaskResult) => void
  onRunCheck?: (task: TaskResult) => void
  hasKey: boolean
}) {
  const answers = openedCheckAnswers(task)
  const noAnswers = missingJudgeAnswersLine(task)
  const path = pathOpenedLine(task)
  const warning = lowConfidenceWarning(task)
  const extraWhy = extraFailWhy(task)
  const failReason =
    !skipped && task.passed === false && !noAnswers
      ? extraWhy && extraWhy !== happened
        ? extraWhy
        : null
      : null
  const drops = CHECK_QUESTION_ORDER.filter((id) =>
    Boolean(task.vs_baseline?.cell_drops?.includes(id))
  )
  const deltas = baselineDeltaFragments(task.vs_baseline)
  const over =
    task.metrics?.blocking === true || task.metrics?.status === "fail"
  const budgetReason = task.metrics?.reasons?.[0]
  return (
    <div className="flex max-w-full min-w-0 flex-col gap-3 overflow-hidden">
      {answers.length ? (
        <dl className="check-answers m-0">
          {answers.map((item) => (
            <div key={item.id} className="mb-2">
              <dt className="font-medium">{item.label}</dt>
              <dd className="text-muted-foreground m-0">{item.answer}</dd>
            </div>
          ))}
        </dl>
      ) : noAnswers ? (
        <p className="text-muted-foreground">{noAnswers}</p>
      ) : null}
      {path ? (
        <div>
          <p className="font-medium">How it ran</p>
          <p className="text-muted-foreground">{path}</p>
        </div>
      ) : null}
      {drops.map((id) => (
        <p
          key={id}
          id={`check-cell-drop-${index}-${id}`}
          className="text-muted-foreground text-xs"
        >
          Down vs baseline
        </p>
      ))}
      {warning ? (
        <p className="text-muted-foreground" id={`check-unsure-${index}`}>
          {warning}
        </p>
      ) : null}
      {failReason ? <p className="fail-why">{failReason}</p> : null}
      {task.transcript || (task.spans?.length ?? 0) > 0 ? (
        <RunTimeline
          transcript={task.transcript}
          passed={task.passed}
          spans={task.spans}
        />
      ) : null}
      <div id="task-metrics" className="flex flex-col gap-2">
        {taskMetricsLine(task.usage, task.metrics) || deltas.length ? (
        <p className="text-muted-foreground text-sm tabular-nums">
          {[taskMetricsLine(task.usage, task.metrics), ...deltas]
            .filter(Boolean)
            .join(" · ")}
        </p>
        ) : null}
        {over && budgetReason ? (
          <Alert variant="destructive">
            <AlertTitle>Over budget</AlertTitle>
            <AlertDescription>{budgetReason}</AlertDescription>
          </Alert>
        ) : null}
      </div>
      <div className="flex flex-wrap gap-2">
      {onRunCheck && !running ? (
        <Button
          id={`btn-run-check-${index}`}
          type="button"
          variant="outline"
          size="xs"
          className="w-fit"
          disabled={!hasKey}
          onClick={(event) => {
            event.stopPropagation()
            onRunCheck(task)
          }}
        >
          Run this check
        </Button>
      ) : null}
      {donePromote(task, skipped, running) ? (
        <Button
          id={`btn-promote-${index}`}
          type="button"
          variant="outline"
          size="xs"
          className="w-fit"
          disabled={running}
          onClick={(event) => {
            event.stopPropagation()
            onPromote(task)
          }}
        >
          Promote to check
        </Button>
      ) : null}
      </div>
    </div>
  )
}

function donePromote(task: TaskResult, skipped: boolean, running: boolean) {
  return task.passed === false && !skipped && !running
}

function baselineDeltaFragments(vs?: VsBaseline | null): string[] {
  if (!vs) {
    return []
  }
  const parts: string[] = []
  if (typeof vs.delta_tokens === "number") {
    const sign = vs.delta_tokens >= 0 ? "+" : "−"
    parts.push(`${sign}${Math.abs(vs.delta_tokens)} tok vs baseline`)
  }
  if (typeof vs.delta_steps === "number") {
    const abs = Math.abs(vs.delta_steps)
    const sign = vs.delta_steps >= 0 ? "+" : "−"
    const unit = abs === 1 ? "step" : "steps"
    parts.push(`${sign}${abs} ${unit}`)
  }
  return parts
}

function LiveTailPanel({
  live,
  task,
}: {
  live?: LiveState | null
  task: TaskResult
}) {
  const tail = live?.tail ?? []
  const liveTranscript = tail.map((line) => line.text).join("\n")
  const durableTranscript = (live?.transcript || task.transcript || "").trim()
  const transcript =
    durableTranscript.length > liveTranscript.trim().length
      ? durableTranscript
      : liveTranscript.trim()
  const spans = live?.spans?.length ? live.spans : task.spans
  const elapsed = useTickingElapsed(live)
  const lineCount =
    tail.length ||
    (transcript
      ? transcript.split("\n").filter((line: string) => line.trim()).length
      : 0)

  return (
    <div className="flex max-w-full min-w-0 flex-col gap-3 overflow-hidden">
      <div className="text-muted-foreground flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
        <span className="max-w-full min-w-0 truncate">
          {checkHeadline(task)}
        </span>
        <span id="live-elapsed" className="tabular-nums">
          Elapsed {formatElapsed(elapsed)}
        </span>
        {liveUsageLabel(live) ? (
          <span id="live-usage">{liveUsageLabel(live)}</span>
        ) : (
          <span id="live-usage" className="hidden" />
        )}
        <span>{lineCount} lines</span>
        {live?.stalled ? (
          <span className="font-medium text-amber-600">
            Stalled · {live.stall_reason}
          </span>
        ) : null}
      </div>
      {task.prompt ? <p className="text-sm break-words">{task.prompt}</p> : null}
      <RunTimeline
        transcript={transcript}
        passed={null}
        spans={spans}
        running
        phaseKey={task.id}
      />
    </div>
  )
}

function formatElapsed(seconds?: number | null) {
  if (seconds == null) {
    return "—"
  }
  const total = Math.max(0, Math.round(seconds))
  const minutes = Math.floor(total / 60)
  const rest = total % 60
  return minutes > 0
    ? `${minutes}m ${String(rest).padStart(2, "0")}s`
    : `${rest}s`
}

function liveUsageLabel(usage?: LiveState | null) {
  const tokens = formatTokens(usage?.tokens_total)
  const cost = formatCost(usage?.cost_usd)
  return [tokens ? `${tokens} tok` : null, cost].filter(Boolean).join(" · ")
}
