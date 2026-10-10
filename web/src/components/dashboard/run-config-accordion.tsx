import { EvalConfigFields } from "@/components/dashboard/eval-config-fields"
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion"
import { Field, FieldGroup, FieldTitle } from "@/components/ui/field"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import {
  draftConfigSummary,
  knownModelsForHarness,
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

  const summary = draftConfigSummary(harnessPref, evalConfig, resolvedHarness)

  return (
    <Accordion defaultValue={[]} id="run-config-accordion">
      <AccordionItem value="run-config" className="rounded-lg border px-2">
        <AccordionTrigger className="py-1.5 hover:no-underline">
          <span className="flex min-w-0 flex-1 items-center gap-2 pr-2">
            <span className="sr-only">Run config </span>
            <span
              id="run-config-summary"
              className="min-w-0 flex-1 truncate text-left text-sm font-normal text-muted-foreground"
            >
              {summary}
            </span>
          </span>
        </AccordionTrigger>
        <AccordionContent>
          <FieldGroup>
            <Field data-disabled={disabled || undefined}>
              <FieldTitle id="harness-label">Harness</FieldTitle>
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
                <ToggleGroupItem value="auto">Auto</ToggleGroupItem>
                <ToggleGroupItem value="cursor-agent">Cursor</ToggleGroupItem>
                <ToggleGroupItem value="codex">Codex</ToggleGroupItem>
                <ToggleGroupItem
                  value="claude"
                  disabled={!claudeReady}
                  title={claudeReady ? "Claude Code" : "Set ANTHROPIC_API_KEY"}
                >
                  {claudeReady ? "Claude" : "Claude · Coming next"}
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
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  )
}
