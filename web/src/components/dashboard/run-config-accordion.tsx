import { EvalConfigFields } from "@/components/dashboard/eval-config-fields"
import { Field, FieldGroup, FieldTitle } from "@/components/ui/field"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import {
  knownModelsForHarness,
  plainRunSetup,
  type EvalConfigDraft,
  type SupportedModelsMeta,
} from "@/lib/eval-config"
import type { HarnessPref } from "@/lib/types"

export function RunConfigAccordion({
  harnessPref,
  setHarnessPref,
  resolvedHarness,
  evalConfig,
  setEvalConfig,
  disabled,
  supportedModels,
  supportedModelsMeta,
  defaultTimeoutSec,
  availableHarnesses,
}: {
  harnessPref: HarnessPref
  setHarnessPref: (next: HarnessPref) => void
  resolvedHarness: string
  evalConfig: EvalConfigDraft
  setEvalConfig: (next: EvalConfigDraft) => void
  disabled?: boolean
  supportedModels?: Record<string, string[]> | null
  supportedModelsMeta?: SupportedModelsMeta | null
  defaultTimeoutSec?: number | null
  availableHarnesses?: string[] | null
}) {
  const claudeReady = (availableHarnesses || []).includes("claude")

  const summary = plainRunSetup(harnessPref, evalConfig, resolvedHarness)

  return (
    <div id="run-config-accordion" className="flex flex-col gap-3">
      <p id="run-config-summary" className="text-sm text-muted-foreground">
        {summary}
      </p>
      <FieldGroup>
        <Field data-disabled={disabled || undefined}>
          <FieldTitle id="harness-label">Agent</FieldTitle>
          <p className="text-sm text-muted-foreground">
            Choose for me uses the agent you are signed in to.
          </p>
          <ToggleGroup
            id="harness-select"
            aria-labelledby="harness-label"
            spacing={2}
            variant="outline"
            value={[harnessPref]}
            onValueChange={(value) => {
              const next = value[0]
              if (
                next === "auto" ||
                next === "cursor-agent" ||
                next === "codex" ||
                next === "claude"
              ) {
                const allowed = knownModelsForHarness(
                  next,
                  next === "auto" ? resolvedHarness : next,
                  supportedModels
                )
                setHarnessPref(next as HarnessPref)
                const current = evalConfig.model.trim()
                if (current && !allowed.includes(current)) {
                  setEvalConfig({ ...evalConfig, model: "" })
                }
              }
            }}
            disabled={disabled}
          >
            <ToggleGroupItem value="auto">Choose for me</ToggleGroupItem>
            <ToggleGroupItem value="cursor-agent">Cursor</ToggleGroupItem>
            <ToggleGroupItem value="codex">Codex</ToggleGroupItem>
            <ToggleGroupItem
              value="claude"
              disabled={!claudeReady}
              title={claudeReady ? "Claude" : "Sign in with Claude first"}
            >
              {claudeReady ? "Claude" : "Claude, sign in first"}
            </ToggleGroupItem>
          </ToggleGroup>
        </Field>
        <EvalConfigFields
          key={harnessPref}
          value={evalConfig}
          onChange={setEvalConfig}
          harnessPref={harnessPref}
          resolvedHarness={resolvedHarness}
          disabled={disabled}
          supportedModels={supportedModels}
          supportedModelsMeta={supportedModelsMeta}
          defaultTimeoutSec={defaultTimeoutSec}
        />
      </FieldGroup>
    </div>
  )
}
