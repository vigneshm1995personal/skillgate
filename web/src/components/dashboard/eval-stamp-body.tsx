import type { ReactNode } from "react"
import { CheckIcon } from "lucide-react"
import { cn } from "cn"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty"
import { EvalResultMark } from "@/components/dashboard/eval-result-mark"
import { GateBadge, stampBadgeProps } from "@/components/dashboard/chrome"
import type { EvalMarkMode } from "@/components/dashboard/eval-result-shell"
import { plainConfigDiff } from "@/lib/eval-config"
import { useDashboard } from "@/lib/dashboard-provider"
import { isLiveHarness, type ConfigDiffEntry, type RunRecord } from "@/lib/types"

export function RunChecksEmpty() {
  return (
    <Empty>
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <CheckIcon />
        </EmptyMedia>
        <EmptyTitle>Run checks to set the gate</EmptyTitle>
        <EmptyDescription>
          Select a skill on Evaluate, then Start.
        </EmptyDescription>
      </EmptyHeader>
    </Empty>
  )
}

export function EvalCheckingPanel({
  completed,
  total,
  skillName,
  modelValue,
  timeoutValue,
  semver,
  staleLabel,
  connectionLost,
}: {
  completed: number
  total: number
  skillName?: string | null
  modelValue: string
  timeoutValue?: number | null
  semver?: string | null
  staleLabel?: string | null
  connectionLost: boolean
}) {
  return (
    <div className="flex flex-col gap-2">
      <p className="font-display text-5xl font-medium tracking-tight">
        Checking
      </p>
      <div className={cn("eval-check-progress", !total && "is-busy")}>
        <i
          style={
            total
              ? {
                  width: `${Math.max(12, Math.round((completed / Math.max(total, 1)) * 100))}%`,
                }
              : undefined
          }
        />
      </div>
      <p
        className="text-sm text-muted-foreground"
        id="run-progress"
        aria-live="polite"
      >
        {total ? `${completed}/${total} checks` : "Running your checks"}
      </p>
      <div className="flex flex-wrap items-center gap-2">
        {skillName ? <Badge variant="secondary">{skillName}</Badge> : null}
        {modelValue && modelValue !== "—" ? (
          <Badge variant="outline">{String(modelValue)}</Badge>
        ) : null}
        {timeoutValue != null ? (
          <Badge variant="outline">{timeoutValue}s</Badge>
        ) : null}
        {semver ? <Badge variant="outline">v{semver}</Badge> : null}
      </div>
      {staleLabel ? (
        <Alert id="run-stale">
          <AlertTitle>Stale — no server activity for {staleLabel}</AlertTitle>
          <AlertDescription>
            This run is not live. It stops after 10 minutes with no progress.
          </AlertDescription>
        </Alert>
      ) : null}
      {connectionLost ? (
        <Alert id="connection-lost">
          <AlertTitle>Connection lost — reconnecting</AlertTitle>
          <AlertDescription>
            The Gate is still running on the server. It will resume when
            the network returns or this tab is visible again.
          </AlertDescription>
        </Alert>
      ) : null}
    </div>
  )
}

export function EvalErrorPanel({
  message,
  hint,
  stampLine,
}: {
  message: string
  hint?: string | null
  stampLine: string
}) {
  const { setStage } = useDashboard()
  const showSettings = /settings/i.test(`${message} ${hint || ""}`)
  return (
    <Alert variant="destructive">
      <AlertTitle>Couldn’t finish this run</AlertTitle>
      <AlertDescription>
        {message}
        {hint ? <p className="mt-2 whitespace-pre-wrap">{hint}</p> : null}
        {showSettings ? (
          <p className="mt-2">
            <Button
              id="btn-open-settings-error"
              variant="link"
              size="xs"
              onClick={() => setStage("settings")}
            >
              Open Settings
            </Button>
          </p>
        ) : null}
        <RunDetails stampLine={stampLine} />
        <p className="mt-2">Get a passing run to unlock Deploy.</p>
      </AlertDescription>
    </Alert>
  )
}

export function EvalPassFailPanel({
  kind,
  mode,
  deployAllowed,
  passed,
  total,
  scoredBy,
  coverageLine,
  passWarnings,
  errorNote,
  baseline,
  stampLine,
  stampMetrics,
  configDiff,
}: {
  kind: "pass" | "fail"
  mode: EvalMarkMode
  deployAllowed: boolean
  passed: number
  total: number
  scoredBy: string
  coverageLine: string
  passWarnings: string[]
  errorNote?: string | null
  baseline: ReactNode
  stampLine: string
  stampMetrics: string | null
  configDiff: ConfigDiffEntry[]
}) {
  const headline = kind === "pass" ? "Passed" : "Failed"
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col items-center gap-2 pt-2 text-center">
        <EvalResultMark kind={kind} mode={mode} />
        <p
          className={cn(
            "font-display text-5xl font-medium tracking-tight",
            kind === "pass" ? "text-success" : "text-destructive"
          )}
        >
          {headline}
          <span className="text-foreground">
            {" "}
            · {passed}/{total} checks
          </span>
        </p>
        {scoredBy ? (
          <p className="text-sm text-muted-foreground">{scoredBy}</p>
        ) : null}
        <GateBadge {...stampBadgeProps(kind)} />
      </div>
      {errorNote ? (
        <Alert variant="destructive">
          <AlertTitle>Stopped</AlertTitle>
          <AlertDescription>{errorNote}</AlertDescription>
        </Alert>
      ) : null}
      <p className="text-sm text-muted-foreground" id="gate-coverage-blocked">
        {coverageLine}
      </p>
      {deployAllowed && passWarnings.length ? (
        <p className="text-sm text-muted-foreground" id="gate-pass-warnings">
          {passWarnings.join(" ")}
        </p>
      ) : null}
      {baseline}
      {stampMetrics ? (
        <p className="text-sm text-muted-foreground" id="run-usage">
          {stampMetrics}
        </p>
      ) : null}
      <RunDetails stampLine={stampLine} configDiff={configDiff} />
    </div>
  )
}

function RunDetails({
  stampLine,
  configDiff = [],
}: {
  stampLine?: string
  configDiff?: ConfigDiffEntry[]
}) {
  if (!stampLine && !configDiff.length) {
    return null
  }
  return (
    <Accordion defaultValue={[]}>
      <AccordionItem value="run-details" className="border-0">
        <AccordionTrigger className="py-1.5 text-muted-foreground hover:no-underline">
          Run details
        </AccordionTrigger>
        <AccordionContent>
          {stampLine ? (
            <p className="text-sm" id="run-config">
              {stampLine}
            </p>
          ) : null}
          {configDiff.length ? (
            <Alert id="config-diff">
              <AlertTitle>Settings changed from the last run</AlertTitle>
              <AlertDescription>{plainConfigDiff(configDiff)}</AlertDescription>
            </Alert>
          ) : null}
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  )
}

export function gateCoverageLine(
  lastResult: RunRecord,
  deployAllowed: boolean,
  reportPassed: boolean | null | undefined,
  harness: string | null | undefined
): string {
  if (deployAllowed) {
    return "Checks passed — Deploy is unlocked."
  }
  if (reportPassed === true && !isLiveHarness(harness)) {
    return "Get a passing run to unlock Deploy."
  }
  if (reportPassed === true && isLiveHarness(harness)) {
    return (
      lastResult.gate_reason ||
      "Checks passed. Deploy stays blocked until a completion check passes with a file from this skill."
    )
  }
  if (isRegressionCopy(lastResult.gate_reason) || lastResult.regression?.hard) {
    return (
      lastResult.gate_reason ||
      lastResult.regression?.reason ||
      "Get a passing run to unlock Deploy."
    )
  }
  return "Get a passing run to unlock Deploy."
}

function isRegressionCopy(reason?: string | null): boolean {
  const text = (reason || "").trim()
  if (text === "This check passed on the baseline and failed on this run.") {
    return true
  }
  return /^\d+ checks regressed vs baseline\.$/.test(text)
}
