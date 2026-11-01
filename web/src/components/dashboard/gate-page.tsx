import { CopyIcon } from "lucide-react"
import { useState } from "react"
import { cn } from "cn"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ChecksResultsTable } from "@/components/dashboard/checks-results-table"
import { StallRadar } from "@/components/dashboard/gate-stall-radar"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Separator } from "@/components/ui/separator"
import { Skeleton } from "@/components/ui/skeleton"
import { Spinner } from "@/components/ui/spinner"
import { toast } from "@/components/ui/toast"
import { PageHeader } from "@/components/dashboard/chrome"
import { EvalResultShell } from "@/components/dashboard/eval-result-shell"
import {
  EvalCheckingPanel,
  EvalErrorPanel,
  EvalPassFailPanel,
  gateCoverageLine,
  RunChecksEmpty,
} from "@/components/dashboard/eval-stamp-body"
import { PromoteCheckDialog } from "@/components/dashboard/promote-check-dialog"
import { SkillUpdateChecklist } from "@/components/dashboard/skill-update-checklist"
import { api } from "@/lib/api"
import { useDashboard } from "@/lib/dashboard-provider"
import { slotOn } from "@/lib/mode"
import {
  customerRunDetails,
  friendlyModelName,
  harnessDisplayName,
  stampRunConfig,
  userPickedModel,
} from "@/lib/eval-config"
import {
  customerGateCopy,
  hidePassFileWarning,
  plainAdviceCopy,
  stripRepeatedHeadline,
  scoredByLine,
  suiteUnsureWarning,
} from "@/lib/check-results"
import {
  failedHudCount,
  queuedTasksFromChecks,
  runBelongsToSkill,
  suiteResultKind,
  suiteStampReady,
} from "@/lib/eval-row-state"
import { TRYOUT_LABEL, isTryoutRun } from "@/lib/skill-run-state"
import {
  costMetricDisplay,
  pathMetricDisplay,
  runMetricsLine,
  tokenMetricDisplay,
} from "@/lib/metrics-label"
import {
  isLiveHarness,
  type HistoryPayload,
  type RunRecord,
  type TaskMetrics,
  type TaskResult,
  type Usage,
} from "@/lib/types"

export function GateSkillLine({ name }: { name: string }) {
  return (
    <p id="gate-skill" className="text-sm font-medium">
      {name}
    </p>
  )
}

export function GatePage({ embedded = false }: { embedded?: boolean }) {
  const {
    running,
    gateRunning,
    tryoutRunning,
    connectionLost,
    lastResult,
    liveGateResult,
    tryoutResult,
    lastAdvice,
    copiedFix,
    deployAllowed,
    copyFix,
    runAfterPossiblePaste,
    runThisCheck,
    setStage,
    status,
    skill,
    checks,
    seeding,
    resolvedHarness,
    skillHistory,
    pinBaseline,
    viewingPinnedHistory,
  } = useDashboard()
  const [promoteTask, setPromoteTask] = useState<TaskResult | null>(null)
  const [stallPeek, setStallPeek] = useState(false)
  const [controlBusy, setControlBusy] = useState<"skip" | "kill" | null>(null)
  const [resultVisible, setResultVisible] = useState(false)
  const skillScoped =
    viewingPinnedHistory ||
    runBelongsToSkill(
      lastResult,
      skill?.slug || skill?.id || skill?.name
    )
  const scopedResult =
    skillScoped && !isTryoutRun(lastResult) ? lastResult : null
  const report = scopedResult?.report
  const live = scopedResult?.live ?? null
  const viewingHistorical = viewingPinnedHistory
  const waitingForSkillRun = Boolean(skill) && seeding && !scopedResult && !liveGateResult
  const ciUrl = (status?.ci.url || "").trim()
  const completed = scopedResult?.completed_count ?? report?.completed_count ?? 0
  const total =
    scopedResult?.task_count ??
    report?.task_count ??
    report?.tasks?.length ??
    checks.length
  const passed = report?.passed_count ?? 0
  const failed = failedHudCount(scopedResult, report)
  const evaluating = gateRunning || scopedResult?.status === "running"
  const kind = suiteResultKind(
    scopedResult,
    report?.passed,
    evaluating,
    Boolean(report?.tasks?.length)
  )
  const rawHarness =
    report?.harness ||
    scopedResult?.harness ||
    (scopedResult || evaluating ? resolvedHarness : "")
  const harnessName = rawHarness
    ? harnessDisplayName(rawHarness, rawHarness)
    : "—"
  const runConfig =
    stampRunConfig(scopedResult?.config, report?.config) || null
  const stampLine =
    customerRunDetails(runConfig) || (harnessName !== "—" ? harnessName : "")
  const modelRaw = runConfig?.model || scopedResult?.model || ""
  const modelValue =
    userPickedModel(runConfig) ||
    (["codex", "claude", "claude-code"].includes(rawHarness) && modelRaw)
      ? friendlyModelName(modelRaw) || modelRaw || "—"
      : "—"
  const timeoutValue =
    runConfig?.timeout_effective ??
    runConfig?.timeout_sec ??
    scopedResult?.timeout_sec
  const configDiff = scopedResult?.config_diff ?? []
  const passWarnings = (() => {
    const base = (scopedResult?.gate_warnings ?? [])
      .map(customerGateCopy)
      .filter(Boolean)
      .filter((item) => !hidePassFileWarning(item, report))
    const unsure = suiteUnsureWarning(report)
    if (unsure && !base.some((item) => item.includes("unsure"))) {
      return [...base, unsure]
    }
    return base
  })()
  const scoredBy = scoredByLine(report)
  const stampMetrics =
    suiteStampReady(scopedResult) && report
      ? runMetricsLine({
          usage: report.usage,
          metrics: report.metrics,
          tasks: report.tasks,
        })
      : null
  const hasGateRun =
    !waitingForSkillRun &&
    (evaluating ||
      scopedResult?.status === "done" ||
      scopedResult?.status === "error" ||
      Boolean(report?.tasks?.length))
  const displayTasks = report?.tasks?.length
    ? report.tasks
    : evaluating && checks.length
      ? queuedTasksFromChecks(checks)
      : []
  const showSuiteMetrics =
    resultVisible && suiteStampReady(scopedResult) && Boolean(report)
  const errorNote =
    scopedResult?.status === "error"
      ? [
          customerGateCopy(scopedResult?.error?.message || ""),
          customerGateCopy(scopedResult?.error?.hint || ""),
        ]
          .filter(Boolean)
          .join(" ")
      : ""

  const controlRun = async (action: "skip" | "kill") => {
    const id = scopedResult?.id
    if (!id) {
      return
    }
    setControlBusy(action)
    try {
      const res =
        action === "skip" ? await api.skipRun(id) : await api.killRun(id)
      toast.add({
        title: res.requested
          ? action === "skip"
            ? "Skipping this check…"
            : "Killing the run…"
          : "That action was already requested.",
        type: "success",
      })
    } catch (err) {
      toast.add({
        title: customerGateCopy(
          err instanceof Error ? err.message : "Could not reach that run."
        ) || "Could not reach that run.",
        type: "error",
      })
    } finally {
      setControlBusy(null)
    }
  }

  return (
    <div className="flex max-w-full min-w-0 flex-col gap-8 overflow-x-clip">
      {skill?.name ? <GateSkillLine name={skill.name} /> : null}
      {embedded ? null : (
        <PageHeader
          title="Gate"
          description="Blocked keeps Deploy locked. Ready unlocks Deploy."
          action={
            <Button
              variant="outline"
              size="lg"
              render={<a href={ciUrl} target="_blank" rel="noreferrer" />}
            >
              CI Action
            </Button>
          }
        />
      )}

      {waitingForSkillRun ? (
        <Card>
          <CardHeader>
            <CardTitle>Result</CardTitle>
            <CardDescription>
              Loading the last eval for {skill?.name ?? "this skill"}.
            </CardDescription>
          </CardHeader>
          <CardContent id="gate" className="flex flex-col gap-3">
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-8 w-2/3" />
          </CardContent>
        </Card>
      ) : !hasGateRun ? (
        <Card>
          <CardHeader>
            <CardTitle>Gate</CardTitle>
            <CardDescription>One run sets Deploy.</CardDescription>
          </CardHeader>
          <CardContent id="gate">
            <RunChecksEmpty />
          </CardContent>
        </Card>
      ) : (
        <div
          className={cn(
            "grid items-start gap-4",
            showSuiteMetrics && "xl:grid-cols-2"
          )}
        >
          <Card>
            <CardHeader>
              <CardTitle>Result</CardTitle>
              <CardDescription>
                {viewingHistorical
                  ? `This is an older run. Deploy still follows the latest result.`
                  : `The latest result for ${skill?.name ?? "the selected skill"} sets Deploy.`}
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-4" id="gate">
              {viewingHistorical ? (
                <Alert>
                  <AlertTitle>Older run</AlertTitle>
                  <AlertDescription>
                    Showing {lastResult?.id}
                    {lastResult?.created_at
                      ? ` · ${lastResult.created_at.replace("T", " ").replace("+00:00", " UTC")}`
                      : ""}
                    . Deploy still follows the latest result.
                  </AlertDescription>
                </Alert>
              ) : null}
              {kind === "idle" ? (
                <RunChecksEmpty />
              ) : (
                <EvalResultShell
                  key={scopedResult?.id ?? "gate-run"}
                  target={kind}
                  hold={!viewingHistorical}
                  onResultVisible={setResultVisible}
                  checking={
                    <EvalCheckingPanel
                      completed={completed}
                      total={total}
                      skillName={report?.skill || skill?.name}
                      modelValue={String(modelValue)}
                      timeoutValue={timeoutValue}
                      semver={skill?.semver || scopedResult?.semver}
                      staleLabel={
                        scopedResult?.stale
                          ? formatElapsed(scopedResult.idle_sec ?? null)
                          : null
                      }
                      connectionLost={connectionLost}
                    />
                  }
                >
                  {({ mode }) =>
                    kind === "error" ? (
                      <EvalErrorPanel
                        message={
                          customerGateCopy(
                            scopedResult?.error?.message || "Run failed"
                          )
                        }
                        hint={customerGateCopy(scopedResult?.error?.hint || "")}
                        stampLine={stampLine}
                      />
                    ) : kind === "pass" || kind === "fail" || kind === "review" ? (
                      <EvalPassFailPanel
                        kind={kind}
                        mode={mode}
                        deployAllowed={deployAllowed}
                        passed={passed}
                        total={total}
                        scoredBy={scoredBy}
                        coverageLine={
                          scopedResult
                            ? customerGateCopy(
                                gateCoverageLine(
                                  scopedResult,
                                  deployAllowed,
                                  report?.passed,
                                  report?.harness || scopedResult.harness
                                )
                              )
                            : "Get a passing run to unlock Deploy."
                        }
                        passWarnings={passWarnings}
                        errorNote={errorNote || null}
                        baseline={
                          scopedResult ? (
                            <GateBaselineStamp
                              lastResult={scopedResult}
                              skillHistory={skillHistory}
                              skillName={
                                skill?.name || scopedResult.skill || report?.skill
                              }
                              onPin={pinBaseline}
                            />
                          ) : null
                        }
                        stampLine={stampLine}
                        stampMetrics={stampMetrics || null}
                        configDiff={configDiff}
                      />
                    ) : null
                  }
                </EvalResultShell>
              )}
              {ciUrl ? (
                <p
                  className="flex flex-wrap items-center gap-2 text-sm"
                  id="ci-gate-line"
                >
                  <span className="text-muted-foreground">GitHub Actions:</span>
                  <CiGateChip
                    href={ciUrl}
                    evaluating={evaluating}
                    conclusion={status?.ci.conclusion}
                  />
                </p>
              ) : null}
            </CardContent>
            <CardFooter>
              <Button
                id="btn-continue-deploy"
                size="lg"
                className="w-full"
                disabled={!deployAllowed}
                onClick={() => setStage("deploy")}
              >
                Deploy
              </Button>
            </CardFooter>
          </Card>

          {showSuiteMetrics ? (
            <GateMetricsCard
              passed={passed}
              failed={failed}
              total={total}
              hasReport={Boolean(report)}
              usage={report?.usage}
              metrics={report?.metrics}
              tasks={report?.tasks}
              runLine={harnessName}
            />
          ) : null}
        </div>
      )}

      {tryoutResult ? (
        <Card id="single-check-tryout">
          <CardHeader>
            <CardTitle>Single check</CardTitle>
            <CardDescription>{TRYOUT_LABEL}</CardDescription>
          </CardHeader>
          <CardContent className="flex max-w-full min-w-0 flex-col gap-4 overflow-x-clip">
            {(tryoutResult.report?.tasks ?? []).length ? (
              <ChecksResultsTable
                key={tryoutResult.id ?? "tryout"}
                tasks={tryoutResult.report?.tasks ?? []}
                runKey={tryoutResult.id ?? "tryout"}
                running={tryoutRunning}
                live={tryoutResult.live}
                onPromote={setPromoteTask}
              />
            ) : tryoutRunning ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Spinner />
                {TRYOUT_LABEL}
              </div>
            ) : (
              <p className="text-sm text-destructive">
                {tryoutResult.error?.message || TRYOUT_LABEL}
              </p>
            )}
          </CardContent>
        </Card>
      ) : null}

      {evaluating || hasGateRun ? (
        <Card className="max-w-full min-w-0 overflow-x-clip">
          <CardHeader>
            <CardTitle>{evaluating ? "This run" : "Checks"}</CardTitle>
            <CardDescription>
              {evaluating
                ? "Live progress and each check’s evidence."
                : "Expand a check to see why it passed or failed."}
            </CardDescription>
          </CardHeader>
          <CardContent
            id="task-list"
            className="flex max-w-full min-w-0 flex-col gap-4 overflow-x-clip"
          >
            <StallRadar
              id="stall-radar"
              live={live}
              stalled={live?.stalled}
              elapsedSec={live?.elapsed_sec}
              tail={live?.tail}
              evaluating={evaluating}
              busy={controlBusy}
              peek={stallPeek}
              skipLabel="Skip check"
              killLabel="Kill run"
              peekLabel="Peek last lines"
              onPeek={() => setStallPeek((value) => !value)}
              onSkip={() => void controlRun("skip")}
              onKill={() => void controlRun("kill")}
            />
            {displayTasks.length ? (
              <ChecksResultsTable
                key={scopedResult?.id ?? `${skill?.name ?? "run"}-${total}`}
                tasks={displayTasks}
                runKey={scopedResult?.id ?? `${skill?.name ?? "run"}-${total}`}
                running={gateRunning}
                live={live}
                onPromote={setPromoteTask}
                onRunCheck={(task) => {
                  const match =
                    checks.find((check) => check.id && check.id === task.id) ||
                    (task.prompt
                      ? checks.find((check) => check.prompt === task.prompt)
                      : undefined)
                  if (match) {
                    void runThisCheck(match)
                    return
                  }
                  void runThisCheck({
                    id: task.id,
                    prompt: task.prompt || task.id,
                    should_trigger: task.expect_skill != null,
                  })
                }}
              />
            ) : evaluating ? (
              <div className="flex flex-col gap-2">
                <Skeleton className="h-14 w-full" />
                <Skeleton className="h-14 w-full" />
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                No checks run yet.
              </p>
            )}
          </CardContent>
        </Card>
      ) : null}

      {slotOn(status, "suggestUpdates") ? (
        <SkillUpdateChecklist key={scopedResult?.id ?? "none"} />
      ) : null}

      {lastAdvice && !evaluating && hasGateRun ? (
        <Card id="fix">
          <CardHeader>
            <CardTitle>{plainAdviceCopy(lastAdvice.headline)}</CardTitle>
            <CardDescription>{plainAdviceCopy(lastAdvice.why)}</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            {lastAdvice.demo_note ? (
              <Alert>
                <AlertDescription>
                  {stripRepeatedHeadline(lastAdvice.demo_note, lastAdvice.headline)}
                </AlertDescription>
              </Alert>
            ) : null}
            <p className="text-sm">
              <span className="font-medium">What to change: </span>
              {plainAdviceCopy(lastAdvice.change)}
            </p>
            {lastAdvice.paste ? (
              <div className="flex flex-col gap-1">
                <p className="text-sm font-medium">Suggested new description</p>
                <pre
                  id="paste-fix"
                  className="max-h-64 max-w-full overflow-auto rounded-xl border bg-muted/40 p-3 font-mono text-xs break-words whitespace-pre-wrap"
                >
                  {lastAdvice.paste}
                </pre>
              </div>
            ) : null}
          </CardContent>
          <CardFooter className="flex flex-wrap gap-2">
            {lastAdvice.paste ? (
              <Button id="btn-copy" size="lg" onClick={() => void copyFix()}>
                <CopyIcon data-icon="inline-start" />
                {copiedFix
                  ? "Copied into the skill — now click Run"
                  : "Copy this into the skill"}
              </Button>
            ) : null}
            <Button
              id="btn-fix-run"
              variant={copiedFix ? "default" : "outline"}
              disabled={running || checks.length === 0 || !status?.has_key}
              title={
                !status?.has_key
                  ? "Add a key in Settings, then press Run."
                  : checks.length === 0
                  ? "Add at least one check before starting evaluations."
                  : undefined
              }
              onClick={() => void runAfterPossiblePaste()}
            >
              {running ? <Spinner data-icon="inline-start" /> : null}
              Run
            </Button>
          </CardFooter>
        </Card>
      ) : null}

      <PromoteCheckDialog
        task={promoteTask}
        open={promoteTask != null}
        onOpenChange={(open) => {
          if (!open) {
            setPromoteTask(null)
          }
        }}
      />
    </div>
  )
}

function CiGateChip({
  href,
  evaluating,
  conclusion,
}: {
  href: string
  evaluating: boolean
  conclusion?: string | null
}) {
  const value = String(conclusion || "").toLowerCase()
  let label = "Not reported"
  let variant: "outline" | "secondary" | "destructive" = "outline"
  if (evaluating) {
    label = "Running"
  } else if (
    value === "success" ||
    value === "pass" ||
    value === "passed" ||
    value === "green"
  ) {
    label = "Pass"
    variant = "secondary"
  } else if (
    value === "failure" ||
    value === "fail" ||
    value === "failed" ||
    value === "red"
  ) {
    label = "Fail"
    variant = "destructive"
  }

  return (
    <Badge
      variant={variant}
      render={
        <a
          href={href}
          target="_blank"
          rel="noreferrer"
          aria-busy={evaluating || undefined}
          aria-label={
            evaluating
              ? "Open GitHub Actions. CI is running."
              : `Open GitHub Actions. CI status: ${label}.`
          }
        />
      }
    >
      {evaluating ? <Spinner data-icon="inline-start" /> : null}
      {label}
    </Badge>
  )
}

function GateMetricsCard({
  passed,
  failed,
  total,
  hasReport,
  usage,
  metrics,
  tasks,
  runLine,
}: {
  passed: number
  failed: number
  total: number
  hasReport: boolean
  usage?: Usage | null
  metrics?: { path?: TaskMetrics["path"] } | null
  tasks?: Array<{ metrics?: TaskMetrics | null }> | null
  runLine: string
}) {
  const passRate = total
    ? `${Math.round((passed / Math.max(total, 1)) * 100)}%`
    : "—"
  const tokens = tokenMetricDisplay(usage)
  const path = pathMetricDisplay(metrics, tasks)
  const cost = costMetricDisplay(usage)
  return (
    <Card>
      <CardHeader>
        <CardTitle>Metrics</CardTitle>
        <CardDescription>
          Check outcomes plus tokens, path, and cost when this run recorded them.
        </CardDescription>
      </CardHeader>
      <CardContent id="gate-metrics" className="flex min-w-0 flex-col gap-5">
        <section
          className="flex flex-col gap-3"
          aria-labelledby="gate-metrics-outcome"
        >
          <h3 id="gate-metrics-outcome" className="text-sm font-medium">
            Outcome
          </h3>
          <div id="metric-pass-rate" className="min-w-0">
            <p className="text-xs text-muted-foreground">Pass rate</p>
            <p className="font-heading text-3xl font-medium tracking-tight tabular-nums">
              {passRate}
            </p>
          </div>
          <div className="grid min-w-0 grid-cols-3 gap-3">
            <Metric
              id="metric-passed"
              label="Passed"
              value={hasReport ? String(passed) : "—"}
              tone={hasReport && passed > 0 ? "success" : undefined}
            />
            <Metric
              id="metric-failed"
              label="Failed"
              value={hasReport ? String(failed) : "—"}
              tone={hasReport && failed > 0 ? "destructive" : undefined}
            />
            <Metric
              id="metric-checks"
              label="Checks"
              value={total ? String(total) : "—"}
            />
          </div>
        </section>
        {tokens.recorded || path.recorded || cost.recorded ? <Separator /> : null}
        <section
          className="flex flex-col gap-3"
          aria-labelledby="gate-metrics-usage"
        >
          {tokens.recorded || path.recorded || cost.recorded ? (
            <>
          <h3 id="gate-metrics-usage" className="text-sm font-medium">
            Usage
          </h3>
          <div className="grid min-w-0 grid-cols-1 gap-4 rounded-xl bg-muted/30 p-3 sm:grid-cols-3">
            {tokens.recorded ? (
            <Metric
              id="metric-tokens"
              label="Tokens"
              value={tokens.value}
              hint={tokens.hint || undefined}
            />
            ) : null}
            {path.recorded ? (
            <Metric
              id="metric-path"
              label="Steps"
              value={path.value}
              hint={path.hint || undefined}
            />
            ) : null}
            {cost.recorded ? (
            <Metric
              id="metric-cost"
              label="Cost"
              value={cost.value}
              hint={cost.hint || undefined}
            />
            ) : null}
          </div>
            </>
          ) : null}
        </section>
        {runLine ? (
          <>
            <Separator />
            <p id="metric-run" className="text-xs text-muted-foreground">
              {runLine}
            </p>
          </>
        ) : null}
      </CardContent>
    </Card>
  )
}

function Metric({
  id,
  label,
  value,
  hint,
  empty,
  tone,
}: {
  id?: string
  label: string
  value: string
  hint?: string
  empty?: boolean
  tone?: "success" | "destructive"
}) {
  return (
    <div id={id} className="min-w-0">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p
        className={cn(
          "mt-1 font-heading text-lg font-medium tracking-tight tabular-nums",
          empty && "text-muted-foreground",
          !empty && tone === "success" && "text-success",
          !empty && tone === "destructive" && "text-destructive"
        )}
      >
        {value}
      </p>
      {hint ? (
        <p className="mt-0.5 text-xs text-muted-foreground">{hint}</p>
      ) : null}
    </div>
  )
}

function GateBaselineStamp({
  lastResult,
  skillHistory,
  skillName,
  onPin,
}: {
  lastResult: RunRecord
  skillHistory: HistoryPayload | null
  skillName?: string | null
  onPin: (opts: {
    skill: string
    run_id?: string | null
    follow_deploy?: boolean
  }) => Promise<boolean>
}) {
  const [busy, setBusy] = useState<"pin" | "follow" | null>(null)
  const baseline = lastResult.baseline ?? skillHistory?.baseline ?? null
  const regression = lastResult.regression
  const gone = regression?.reason === "Baseline run is gone — pin a new one."
  const mismatch = regression?.status === "uncomparable"
  const hard = regression?.hard === true
  const isThisBaseline = Boolean(
    baseline?.run_id && lastResult.id && baseline.run_id === lastResult.id
  )
  const liveDone =
    lastResult.status === "done" &&
    isLiveHarness(lastResult.report?.harness || lastResult.harness)
  const canFollow =
    baseline?.source === "manual" &&
    skillHistory?.last_deploy?.status === "installed"
  const shortId = shortRunId(baseline?.run_id)
  const baselineLine = gone
    ? "Baseline run is gone — pin a new one."
    : isThisBaseline
      ? "This run is the baseline."
      : baseline
        ? `${baseline.source === "manual" ? "Baseline: pinned" : "Baseline: last Deploy"}${shortId ? ` · ${shortId}` : ""}`
        : null

  const pin = async (followDeploy = false) => {
    const skill = (skillName || "").trim()
    if (!skill) {
      return
    }
    setBusy(followDeploy ? "follow" : "pin")
    try {
      await onPin(
        followDeploy
          ? { skill, follow_deploy: true }
          : { skill, run_id: lastResult.id }
      )
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="flex flex-col gap-3">
      {hard ? (
        <Alert id="gate-regression" variant="destructive">
          <AlertTitle>Regressed vs baseline</AlertTitle>
          <AlertDescription>
            {lastResult.gate_reason ||
              regression?.reason ||
              "This check passed on the baseline and failed on this run."}
          </AlertDescription>
        </Alert>
      ) : null}
      {mismatch ? (
        <Alert id="gate-baseline-mismatch">
          <AlertTitle>Baseline</AlertTitle>
          <AlertDescription>
            {regression?.reason ||
              "Baseline is from a different Dataset. Pin a new baseline after this Dataset passes."}
          </AlertDescription>
        </Alert>
      ) : null}
      {baselineLine ? (
        <p className="text-sm text-muted-foreground" id="gate-baseline">
          {baselineLine}
        </p>
      ) : null}
      {liveDone && skillName && lastResult.id ? (
        <div className="flex flex-wrap gap-2">
          <Button
            id="btn-pin-baseline"
            type="button"
            variant="outline"
            size="sm"
            disabled={busy !== null || isThisBaseline}
            onClick={() => void pin(false)}
          >
            {isThisBaseline ? "This is the baseline" : "Pin as baseline"}
          </Button>
          {canFollow ? (
            <Button
              id="btn-baseline-follow-deploy"
              type="button"
              variant="outline"
              size="sm"
              disabled={busy !== null}
              onClick={() => void pin(true)}
            >
              Use last Deploy
            </Button>
          ) : null}
        </div>
      ) : null}
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

function shortRunId(id?: string | null): string {
  const text = (id || "").trim()
  if (text.length <= 8) {
    return text
  }
  return text.slice(0, 8)
}
