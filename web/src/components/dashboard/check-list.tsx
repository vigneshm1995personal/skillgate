import { CheckInputControls } from "@/components/dashboard/check-input"
import {
  PackScoringExtras,
  ScoringQuestions,
} from "@/components/dashboard/scoring-questions"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Spinner } from "@/components/ui/spinner"
import { Textarea } from "@/components/ui/textarea"
import {
  canPinCheck,
  expectedFieldValue,
  isPinnedCheck,
  expectedWithoutTargetWarning,
  noTriggerOutputWarning,
  showsExpectedOutputFields,
} from "@/lib/case-pack"
import { useDashboard } from "@/lib/dashboard-provider"
import { checkHeadline, scorerCodeToPlain } from "@/lib/check-results"
import { harnessDisplayName } from "@/lib/eval-config"
import { checkUsageLine } from "@/lib/metrics-label"
import { runForCheck } from "@/lib/skill-run-state"
import {
  skillOutputPath,
  type CaseBudgets,
  type Check,
  type PackFile,
  type RunRecord,
  type SkillPayload,
  type TaskMetrics,
  type TaskResult,
  type Usage,
  type VsBaseline,
} from "@/lib/types"

type CheckStatus = "pending" | "running" | "pass" | "fail"

export function CheckList({
  checks,
  running,
  skill,
  packFiles,
  inherit = true,
  lastResult,
  tryoutResult,
  updateCheck,
  removeCheck,
  onSkill,
  onPin,
  onRunCheck,
  packJudge,
  onPackJudge,
}: {
  checks: Check[]
  running: boolean
  skill?: SkillPayload | null
  packFiles?: PackFile[]
  inherit?: boolean
  lastResult: RunRecord | null
  tryoutResult?: RunRecord | null
  updateCheck: (index: number, patch: Partial<Check>) => void
  removeCheck: (index: number) => void
  onSkill?: (skill: SkillPayload) => void
  onPin?: (index: number) => void
  onRunCheck?: (check: Check) => void
  packJudge?: Check["judge"]
  onPackJudge?: (next: Check["judge"]) => void
}) {
  const hasKey = Boolean(useDashboard().status?.has_key)
  const skillName = skill?.name
  return (
    <div id="check-list" className="flex flex-col gap-3">
      {onPackJudge ? (
        <div className="flex flex-col gap-3 rounded-xl border p-4">
          <PackScoringExtras
            packJudge={packJudge}
            disabled={running}
            onPackJudge={onPackJudge}
          />
        </div>
      ) : null}
      {checks.map((check, index) => {
        const checkRun = runForCheck(check, lastResult, tryoutResult)
        const status = statusForCheck(check, index, checkRun, skillName)
        const canPin = canPinCheck(check)
        const task = matchTask(check, index, checkRun, skillName)
        const overBudget = task?.metrics?.status === "fail"
        const ignoredOutput = noTriggerOutputWarning(check)
        const expectedOrphan = expectedWithoutTargetWarning(check)
        return (
          <div
            key={check.id ?? index}
            className="flex flex-col gap-3 rounded-xl border p-4"
          >
            <div className="flex items-center justify-between gap-2">
              <div className="flex min-w-0 items-center gap-2">
                <p className="text-xs font-medium text-muted-foreground">
                  Check {index + 1}
                </p>
                <CheckStatusBadge
                  status={status}
                  id={`check-status-${index}`}
                />
                {overBudget ? (
                  <Badge
                    id={`check-budget-badge-${index}`}
                    variant="destructive"
                  >
                    Over budget
                  </Badge>
                ) : null}
                {task?.vs_baseline?.hard ? (
                  <Badge
                    id={`check-regressed-badge-${index}`}
                    variant="destructive"
                  >
                    Regressed
                  </Badge>
                ) : null}
                {isPinnedCheck(check) ? (
                  <Badge variant="secondary">Saved</Badge>
                ) : null}
              </div>
              <div className="flex shrink-0 items-center gap-1">
                {onRunCheck ? (
                  <Button
                    id={`btn-run-check-${index}`}
                    variant="outline"
                    size="xs"
                    disabled={running || !hasKey}
                    onClick={() => onRunCheck(check)}
                  >
                    Run this check
                  </Button>
                ) : null}
              {check.locked ? null : (
              <Button
                variant="ghost"
                size="xs"
                disabled={running}
                onClick={() => removeCheck(index)}
              >
                Remove
              </Button>
              )}
              </div>
            </div>
            <CheckLiveProgress
              index={index}
              check={check}
              running={checkRun?.status === "running"}
              skillName={skillName}
              lastResult={checkRun}
            />
            {task && (task.status === "done" || task.metrics || task.usage) ? (
              <CheckMetrics
                index={index}
                usage={task.usage}
                metrics={task.metrics}
                vsBaseline={task.vs_baseline}
              />
            ) : null}
            <FieldGroup>
              <Field data-disabled={running || undefined}>
                <FieldLabel htmlFor={`check-prompt-${index}`}>
                  Prompt
                </FieldLabel>
                <Textarea
                  id={`check-prompt-${index}`}
                  value={check.prompt}
                  disabled={running || Boolean(check.locked)}
                  onChange={(event) =>
                    updateCheck(index, { prompt: event.target.value })
                  }
                  rows={3}
                />
              </Field>
              <Field
                orientation="horizontal"
                data-disabled={running || undefined}
              >
                <Checkbox
                  id={`check-trigger-${index}`}
                  checked={check.should_trigger !== false}
                  disabled={running || Boolean(check.locked)}
                  onCheckedChange={(checked) =>
                    updateCheck(index, {
                      should_trigger: checked === true,
                    })
                  }
                />
                <FieldLabel htmlFor={`check-trigger-${index}`}>
                  This should trigger the skill
                </FieldLabel>
              </Field>
              {showsExpectedOutputFields(check) ? (
                <>
                  <Field data-disabled={running || undefined}>
                    <FieldLabel htmlFor={`check-expected-${index}`}>
                      Expected
                    </FieldLabel>
                    <Input
                      id={`check-expected-${index}`}
                      value={expectedFieldValue(check)}
                      placeholder="Hello Skill Gate"
                      disabled={running || Boolean(check.locked)}
                      onChange={(event) => {
                        const contains = event.target.value
                        updateCheck(index, {
                          contains,
                          ...(!(check.output_path || "").trim() && contains.trim()
                            ? { output_path: skillOutputPath(skill) }
                            : {}),
                        })
                      }}
                    />
                  </Field>
                  <Field data-disabled={running || undefined}>
                    <FieldLabel htmlFor={`check-output-${index}`}>
                      Output file (optional)
                    </FieldLabel>
                    <Input
                      id={`check-output-${index}`}
                      value={check.output_path ?? ""}
                      placeholder={skillOutputPath(skill)}
                      disabled={running || Boolean(check.locked)}
                      onChange={(event) =>
                        updateCheck(index, {
                          output_path: event.target.value,
                        })
                      }
                    />
                  </Field>
                  {expectedOrphan ? (
                    <p className="text-sm text-muted-foreground">{expectedOrphan}</p>
                  ) : null}
                </>
              ) : ignoredOutput ? (
                <p className="text-sm text-muted-foreground">{ignoredOutput}</p>
              ) : null}
              <CheckInputControls
                check={check}
                index={index}
                skill={skill ?? null}
                packFiles={packFiles ?? skill?.pack_files ?? []}
                inherit={inherit}
                disabled={running}
                onUpdate={(patch) => updateCheck(index, patch)}
                onSkill={onSkill}
              />
              <BudgetFields
                index={index}
                check={check}
                disabled={running}
                onUpdate={(patch) => updateCheck(index, patch)}
              />
              <ScoringQuestions
                index={index}
                packJudge={packJudge}
                checkJudge={check.judge}
                disabled={running}
                onCheckJudge={(next) => updateCheck(index, { judge: next })}
              />
              {onPin && check.bank_status !== "pinned" ? (
                <div className="flex justify-end">
                  <Button
                    id={index === 0 ? "btn-pin-case" : `btn-pin-case-${index}`}
                    variant="outline"
                    size="sm"
                    disabled={running || !canPin}
                    onClick={() => onPin(index)}
                  >
                    Save to Dataset
                  </Button>
                </div>
              ) : null}
            </FieldGroup>
          </div>
        )
      })}
    </div>
  )
}

function BudgetFields({
  index,
  check,
  disabled,
  onUpdate,
}: {
  index: number
  check: Check
  disabled: boolean
  onUpdate: (patch: Partial<Check>) => void
}) {
  const tokensValue =
    check.budgets?.tokens_total == null ? "" : String(check.budgets.tokens_total)
  const stepsValue =
    check.budgets?.max_steps == null ? "" : String(check.budgets.max_steps)
  return (
    <>
      <Field data-disabled={disabled || undefined}>
        <FieldLabel htmlFor={`check-budget-tokens-${index}`}>
          Token budget (optional)
        </FieldLabel>
        <Input
          id={`check-budget-tokens-${index}`}
          type="number"
          min={1}
          inputMode="numeric"
          placeholder="No budget"
          value={tokensValue}
          disabled={disabled}
          onChange={(event) =>
            onUpdate({
              budgets: patchBudget(check.budgets, "tokens_total", event.target.value),
            })
          }
        />
        <FieldDescription>
          Leave empty to only show the numbers after a run. A number here blocks Deploy if this case goes over.
        </FieldDescription>
      </Field>
      <Field data-disabled={disabled || undefined}>
        <FieldLabel htmlFor={`check-budget-steps-${index}`}>
          Step budget (optional)
        </FieldLabel>
        <Input
          id={`check-budget-steps-${index}`}
          type="number"
          min={1}
          inputMode="numeric"
          placeholder="No budget"
          value={stepsValue}
          disabled={disabled}
          onChange={(event) =>
            onUpdate({
              budgets: patchBudget(check.budgets, "max_steps", event.target.value),
            })
          }
        />
      </Field>
    </>
  )
}

function CheckMetrics({
  index,
  usage,
  metrics,
  vsBaseline,
}: {
  index: number
  usage?: Usage | null
  metrics?: TaskMetrics | null
  vsBaseline?: VsBaseline | null
}) {
  const over = metrics?.status === "fail"
  const reason = metrics?.reasons?.[0]
  const deltas = baselineDeltaFragments(vsBaseline)
  return (
    <div className="flex flex-col gap-2">
      <p
        id={`check-metrics-${index}`}
        className="text-sm text-muted-foreground tabular-nums"
      >
        {checkUsageLine(usage, metrics)}
        {deltas.length ? ` · ${deltas.join(" · ")}` : ""}
      </p>
      {over && reason ? (
        <Alert id={`check-budget-fail-${index}`} variant="destructive">
          <AlertTitle>Over budget</AlertTitle>
          <AlertDescription>{reason}</AlertDescription>
        </Alert>
      ) : null}
    </div>
  )
}

function patchBudget(
  current: CaseBudgets | null | undefined,
  key: keyof CaseBudgets,
  raw: string
): CaseBudgets | null {
  const next: CaseBudgets = { ...(current ?? {}) }
  const trimmed = raw.trim()
  if (!trimmed) {
    next[key] = null
  } else {
    const parsed = Number(trimmed)
    next[key] = Number.isFinite(parsed) && parsed > 0 ? Math.floor(parsed) : null
  }
  if (next.tokens_total == null && next.max_steps == null) {
    return null
  }
  return next
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

function CheckLiveProgress({
  index,
  check,
  running,
  skillName,
  lastResult,
}: {
  index: number
  check: Check
  running: boolean
  skillName?: string | null
  lastResult: RunRecord | null
}) {
  if (!isRunningCheck(check, index, running, skillName, lastResult)) {
    return null
  }

  const task = matchTask(check, index, lastResult, skillName)
  const completed =
    lastResult?.completed_count ?? lastResult?.report?.completed_count ?? 0
  const total =
    lastResult?.task_count ??
    lastResult?.report?.task_count ??
    lastResult?.report?.tasks?.length ??
    0
  const currentId =
    lastResult?.current_task_id ?? lastResult?.report?.current_task_id ?? null
  const harness = lastResult?.report?.harness || lastResult?.harness || "live"
  const isCurrent = Boolean(
    currentId && (check.id === currentId || task?.id === currentId)
  )
  const taskStatus = task?.status
  const failures = task?.failures?.filter(Boolean) ?? []
  const scores = task?.scores ?? []
  const transcript = (task?.transcript || "").trim()
  const counts = total ? `${completed}/${total} done` : null

  let title = "Starting evaluations"
  if (taskStatus === "running" || isCurrent) {
    title = "Running now"
  } else if (taskStatus === "queued") {
    title = "Queued"
  } else if (taskStatus === "done" && task?.passed === false) {
    title = "Failed so far"
  } else if (taskStatus === "done" && task?.passed === true) {
    title = "Passed so far"
  }

  const headline = checkHeadline(task || check)
  const agent = harnessDisplayName(harness, harness)
  const detailParts = [
    counts,
    agent && agent !== "—" ? agent : null,
    isCurrent ? headline : null,
    !isCurrent && currentId && taskStatus !== "done"
      ? `Waiting on ${headline}`
      : null,
  ].filter(Boolean)

  return (
    <Alert id={`check-progress-${index}`}>
      {taskStatus === "running" || isCurrent ? <Spinner /> : null}
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription>
        <div className="flex flex-col gap-2">
          <p>{detailParts.join(" · ") || "Waiting for harness progress."}</p>
          {failures.length ? (
            <div className="flex flex-col gap-1">
              <p className="font-medium text-foreground">Failures so far</p>
              {failures.map((failure, failureIndex) => (
                <p key={`${index}-fail-${failureIndex}`}>
                  {scorerCodeToPlain(failure, check.prompt || check.id || "")}
                </p>
              ))}
            </div>
          ) : null}
          {scores.length ? (
            <div className="flex flex-col gap-1">
              <p className="font-medium text-foreground">Scorers so far</p>
              {scores.map((score, scoreIndex) => (
                <div
                  key={`${score.scorer ?? "score"}-${scoreIndex}`}
                  className="flex items-center gap-2"
                >
                  <span>
                    {score.headline || score.detail || score.scorer || "Scorer"}
                  </span>
                  {typeof score.passed === "boolean" ? (
                    <Badge variant={score.passed ? "secondary" : "destructive"}>
                      {score.passed ? "Pass" : "Fail"}
                    </Badge>
                  ) : null}
                </div>
              ))}
            </div>
          ) : null}
          {transcript ? (
            <pre className="max-h-40 overflow-auto rounded-lg border bg-muted/40 p-3 font-mono text-xs whitespace-pre-wrap text-foreground">
              {transcript}
            </pre>
          ) : null}
        </div>
      </AlertDescription>
    </Alert>
  )
}

function CheckStatusBadge({ status, id }: { status: CheckStatus; id: string }) {
  const label =
    status === "pass"
      ? "Pass"
      : status === "fail"
        ? "Fail"
        : status === "running"
          ? "Running"
          : "Pending"
  const variant =
    status === "fail"
      ? "destructive"
      : status === "pass"
        ? "secondary"
        : "outline"
  return (
    <Badge id={id} variant={variant} className="shrink-0">
      {label}
    </Badge>
  )
}

function isRunningCheck(
  check: Check,
  index: number,
  running: boolean,
  skillName: string | null | undefined,
  lastResult: RunRecord | null
): boolean {
  const runSkill = lastResult?.report?.skill || lastResult?.skill
  const sameSkill = !skillName || !runSkill || runSkill === skillName
  const live = sameSkill && (running || lastResult?.status === "running")
  if (!live) {
    return false
  }
  const task = matchTask(check, index, lastResult, skillName)
  const currentId =
    lastResult?.current_task_id ?? lastResult?.report?.current_task_id ?? null
  if (task?.status === "running") {
    return true
  }
  if (currentId && (check.id === currentId || task?.id === currentId)) {
    return true
  }
  return !currentId && index === 0
}

function statusForCheck(
  check: Check,
  index: number,
  lastResult: RunRecord | null,
  skillName?: string | null
): CheckStatus {
  const task = matchTask(check, index, lastResult, skillName)
  if (!task) {
    return "pending"
  }
  if (task.status === "running") {
    return "running"
  }
  if (task.status === "queued") {
    return "pending"
  }
  if (typeof task.passed === "boolean") {
    return task.passed ? "pass" : "fail"
  }
  return "pending"
}

function matchTask(
  check: Check,
  index: number,
  lastResult: RunRecord | null,
  skillName?: string | null
): TaskResult | null {
  if (!lastResult) {
    return null
  }
  const runSkill = lastResult.report?.skill || lastResult.skill
  if (skillName && runSkill && runSkill !== skillName) {
    return null
  }
  const tasks = lastResult.report?.tasks
  if (!tasks?.length) {
    return null
  }
  if (check.id) {
    const byId = tasks.find((task) => task.id === check.id)
    if (byId) {
      return byId
    }
  }
  const byIndex = tasks[index]
  if (byIndex && (byIndex.prompt ?? "").trim() === check.prompt.trim()) {
    return byIndex
  }
  return null
}
