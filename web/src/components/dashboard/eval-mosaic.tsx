import { useMemo, useState } from "react"
import { Tooltip as TooltipPrimitive } from "@base-ui/react/tooltip"
import { cn } from "cn"

import { TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import type { AnalyticsRun } from "@/lib/types"

const WEEKS = 53

const DAY_LABELS = ["", "Mon", "", "Wed", "", "Fri", ""]

type Level = "empty" | "pass-1" | "pass-2" | "pass-3" | "fail-1" | "fail-2"

const LEVEL_CELL: Record<Level, string> = {
  empty: "bg-muted",
  "pass-1": "bg-success/35",
  "pass-2": "bg-success/65",
  "pass-3": "bg-success",
  "fail-1": "bg-destructive/35",
  "fail-2": "bg-destructive/65",
}

const CELL =
  "block size-[11px] rounded-[2px] outline-1 -outline-offset-1 outline-foreground/[0.06]"

const dateFormat = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
  year: "numeric",
})
const monthFormat = new Intl.DateTimeFormat(undefined, { month: "short" })

type Day = {
  date: Date
  pass: number
  fail: number
  error: number
  latest: AnalyticsRun | null
}

function dayKey(date: Date) {
  return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`
}

function levelOf(day: Day): Level {
  const total = day.pass + day.fail + day.error
  if (total === 0) {
    return "empty"
  }
  const rate = day.pass / total
  if (rate === 1) return "pass-3"
  if (rate >= 0.75) return "pass-2"
  if (rate >= 0.5) return "pass-1"
  if (rate > 0) return "fail-1"
  return "fail-2"
}

function dayLabel(day: Day) {
  const date = dateFormat.format(day.date)
  if (day.pass + day.fail + day.error === 0) {
    return `No evals on ${date}`
  }
  const parts = [date, `${day.pass} pass`, `${day.fail} fail`]
  if (day.error > 0) {
    parts.push(`${day.error} error`)
  }
  return parts.join(" · ")
}

function buildWeeks(runs: AnalyticsRun[]): Day[][] {
  const byDay = new Map<string, Day>()
  for (const run of runs) {
    const time = run.created_at ? Date.parse(run.created_at) : NaN
    if (Number.isNaN(time)) {
      continue
    }
    const at = new Date(time)
    const key = dayKey(at)
    let day = byDay.get(key)
    if (!day) {
      day = { date: at, pass: 0, fail: 0, error: 0, latest: null }
      byDay.set(key, day)
    }
    if (run.status === "error" || run.passed == null) {
      day.error += 1
    } else if (run.passed) {
      day.pass += 1
    } else {
      day.fail += 1
    }
    if (!day.latest || Date.parse(day.latest.created_at ?? "") < time) {
      day.latest = run
    }
  }

  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const startOffset = (WEEKS - 1) * 7 + today.getDay()
  const weeks: Day[][] = []
  for (let week = 0; week < WEEKS; week += 1) {
    const days: Day[] = []
    for (let weekday = 0; weekday < 7; weekday += 1) {
      const date = new Date(
        today.getFullYear(),
        today.getMonth(),
        today.getDate() - startOffset + week * 7 + weekday
      )
      if (date > today) {
        break
      }
      const hit = byDay.get(dayKey(date))
      days.push(
        hit
          ? { ...hit, date }
          : { date, pass: 0, fail: 0, error: 0, latest: null }
      )
    }
    weeks.push(days)
  }
  return weeks
}

function monthLabels(weeks: Day[][]) {
  const labels: Array<{ col: number; label: string }> = []
  weeks.forEach((week, col) => {
    const month = week[0].date.getMonth()
    if (col === 0 || month !== weeks[col - 1][0].date.getMonth()) {
      labels.push({ col, label: monthFormat.format(week[0].date) })
    }
  })
  if (labels.length > 1 && labels[1].col - labels[0].col < 3) {
    labels.shift()
  }
  return labels
}

function scrollToLatest(node: HTMLDivElement | null) {
  if (node) {
    node.scrollLeft = node.scrollWidth
  }
}

export function EvalMosaic({
  runs,
  onOpen,
}: {
  runs: AnalyticsRun[]
  onOpen: (run: AnalyticsRun) => void
}) {
  const [tooltip] = useState(() => TooltipPrimitive.createHandle<Day>())
  const weeks = useMemo(() => buildWeeks(runs), [runs])
  const months = monthLabels(weeks)
  const columns = { gridTemplateColumns: `repeat(${weeks.length}, 11px)` }

  return (
    <div ref={scrollToLatest} className="overflow-x-auto pb-1">
      <div
        role="group"
        aria-label="Eval pass and fail activity by day over the last year"
        className="grid w-max grid-cols-[auto_auto] gap-x-1.5 gap-y-1 text-[10px] leading-none text-muted-foreground"
      >
        <span aria-hidden="true" />
        <div aria-hidden="true" className="grid gap-[2px]" style={columns}>
          {months.map((month) => (
            <span
              key={month.col}
              className="whitespace-nowrap"
              style={{ gridColumnStart: month.col + 1, gridRowStart: 1 }}
            >
              {month.label}
            </span>
          ))}
        </div>

        <div
          aria-hidden="true"
          className="grid grid-rows-[repeat(7,11px)] gap-[2px] leading-[11px]"
        >
          {DAY_LABELS.map((label, index) => (
            <span key={index}>{label}</span>
          ))}
        </div>
        <div className="grid grid-flow-col grid-rows-[repeat(7,11px)] auto-cols-[11px] gap-[2px]">
          {weeks.flatMap((week) =>
            week.map((day) => {
              const level = levelOf(day)
              const latest = day.latest
              const key = dayKey(day.date)
              if (!latest) {
                return (
                  <TooltipTrigger
                    key={key}
                    handle={tooltip}
                    payload={day}
                    render={<span aria-hidden="true" />}
                    className={cn(CELL, LEVEL_CELL[level])}
                  />
                )
              }
              return (
                <TooltipTrigger
                  key={key}
                  type="button"
                  handle={tooltip}
                  payload={day}
                  aria-label={dayLabel(day)}
                  onClick={() => onOpen(latest)}
                  className={cn(
                    CELL,
                    LEVEL_CELL[level],
                    "p-0 transition-opacity hover:opacity-80 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-ring motion-reduce:transition-none"
                  )}
                />
              )
            })
          )}
        </div>
      </div>

      <TooltipPrimitive.Root handle={tooltip}>
        {({ payload }) =>
          payload ? (
            <TooltipContent>
              <span className="flex flex-col gap-0.5">
                <span className="font-medium">{dayLabel(payload)}</span>
                {payload.latest &&
                payload.pass + payload.fail + payload.error === 1 ? (
                  <span className="text-background/70">
                    {payload.latest.skill || "Unknown skill"} ·{" "}
                    {payload.latest.harness || "Unknown harness"}
                  </span>
                ) : null}
              </span>
            </TooltipContent>
          ) : null
        }
      </TooltipPrimitive.Root>
    </div>
  )
}

const LEGEND_PASS: Level[] = ["empty", "pass-1", "pass-2", "pass-3"]
const LEGEND_FAIL: Level[] = ["fail-1", "fail-2"]

function LegendCells({ levels }: { levels: Level[] }) {
  return (
    <span aria-hidden="true" className="flex gap-[2px]">
      {levels.map((level) => (
        <span key={level} className={cn(CELL, LEVEL_CELL[level])} />
      ))}
    </span>
  )
}

export function MosaicLegend() {
  return (
    <div
      role="img"
      aria-label="Legend: muted means no evals; lighter to stronger green means more of that day's runs passed; red means most runs failed"
      className="flex items-center justify-end gap-3 text-xs text-muted-foreground"
    >
      <span className="flex items-center gap-1.5">
        <span>Less</span>
        <LegendCells levels={LEGEND_PASS} />
        <span>More</span>
      </span>
      <span className="flex items-center gap-1.5">
        <LegendCells levels={LEGEND_FAIL} />
        <span>Fail</span>
      </span>
    </div>
  )
}
