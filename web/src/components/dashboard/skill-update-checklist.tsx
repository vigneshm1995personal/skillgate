import { useState } from "react"
import { CopyIcon } from "lucide-react"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Field,
  FieldContent,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field"
import { Spinner } from "@/components/ui/spinner"
import { happenedLine, plainAdviceCopy } from "@/lib/check-results"
import { runBelongsToSkill } from "@/lib/eval-row-state"
import { useDashboard } from "@/lib/dashboard-provider"

export function SkillUpdateChecklist() {
  const {
    gateRunning,
    lastResult,
    skill,
    status,
    suggestBusy,
    suggestError,
    suggestByRunId,
    requestSkillUpdates,
    copySkillUpdates,
  } = useDashboard()
  const [done, setDone] = useState<Record<string, boolean>>({})
  const report = lastResult?.report
  const evaluating = gateRunning || lastResult?.status === "running"
  const taskCount = report?.tasks?.length ?? 0
  const canSuggest =
    !evaluating &&
    Boolean(lastResult?.id) &&
    runBelongsToSkill(lastResult, skill?.name) &&
    (lastResult?.status === "done" ||
      (lastResult?.status === "error" && taskCount > 0))
  const happenedByTask = new Set(
    (report?.tasks ?? []).map((task) => happenedLine(task))
  )
  const runId = lastResult?.id
  const payload = runId ? suggestByRunId[runId] ?? null : null
  const hasKey = Boolean(status?.has_key)
  const items = payload?.items ?? []

  if (!canSuggest) {
    return null
  }

  return (
    <Card id="skill-update-checklist">
      <CardHeader>
        <CardTitle>Suggested skill updates</CardTitle>
        <CardDescription>
          Review this checklist. Nothing is written to the skill until you edit it.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {suggestError ? (
          <Alert>
            <AlertTitle>{suggestError.message}</AlertTitle>
            {suggestError.hint ? (
              <AlertDescription>{suggestError.hint}</AlertDescription>
            ) : null}
          </Alert>
        ) : null}
        {payload?.summary ? (
          <p id="skill-update-summary" className="text-sm text-muted-foreground">
            {payload.summary}
          </p>
        ) : null}
        {payload && items.length === 0 ? (
          <p id="skill-update-empty" className="text-sm text-muted-foreground">
            No evidence-backed skill edits for this run.
          </p>
        ) : null}
        {items.length > 0 ? (
          <FieldGroup id="skill-update-list">
            {items.map((item) => {
              const itemId = `skill-update-item-${item.id}`
              const checked = Boolean(done[item.id])
              return (
                <Field key={item.id} orientation="horizontal">
                  <Checkbox
                    id={itemId}
                    checked={checked}
                    onCheckedChange={(value) => {
                      setDone((prev) => ({
                        ...prev,
                        [item.id]: value === true,
                      }))
                    }}
                  />
                  <FieldContent>
                    <FieldLabel htmlFor={itemId} className="font-medium">
                      <span className="flex min-w-0 flex-wrap items-center gap-2">
                        <span>{plainAdviceCopy(item.title)}</span>
                        <Badge
                          variant={
                            item.kind === "fix" ? "destructive" : "outline"
                          }
                        >
                          {item.kind === "fix" ? "Fix" : "Polish"}
                        </Badge>
                      </span>
                    </FieldLabel>
                    {item.detail && !happenedByTask.has(item.detail) ? (
                      <FieldDescription>
                        {plainAdviceCopy(item.detail)}
                      </FieldDescription>
                    ) : null}
                  </FieldContent>
                </Field>
              )
            })}
          </FieldGroup>
        ) : null}
      </CardContent>
      <CardFooter className="flex flex-wrap gap-2">
        <Button
          id="btn-suggest-skill-updates"
          variant="outline"
          size="lg"
          disabled={!hasKey || suggestBusy}
          title={
            hasKey
              ? undefined
              : "Add AI_GATEWAY_API_KEY to suggest skill updates."
          }
          onClick={() => void requestSkillUpdates({ force: Boolean(payload) })}
        >
          {suggestBusy ? <Spinner data-icon="inline-start" /> : null}
          Suggest skill updates
        </Button>
        {items.length > 0 ? (
          <Button
            id="btn-copy-skill-updates"
            variant="outline"
            size="lg"
            onClick={() => void copySkillUpdates()}
          >
            <CopyIcon data-icon="inline-start" />
            Copy checklist
          </Button>
        ) : null}
      </CardFooter>
    </Card>
  )
}
