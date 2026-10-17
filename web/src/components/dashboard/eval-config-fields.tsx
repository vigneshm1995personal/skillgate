import { useState } from "react"

import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
  FieldLegend,
  FieldSet,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import {
  DEFAULT_LIVE_TIMEOUT_SEC,
  MODEL_CUSTOM_VALUE,
  MODEL_DEFAULT_VALUE,
  emptyCatalogHint,
  knownModelsForHarness,
  modelSelectValue,
  modelsForHarness,
  resolveModelHarness,
  unsupportedModelHint,
  type EvalConfigDraft,
  type ReasoningEffort,
  type SupportedModelsMeta,
} from "@/lib/eval-config"

const REASONING: ReasoningEffort[] = ["low", "medium", "high", "ultra"]

export function EvalConfigFields({
  value,
  onChange,
  harnessPref,
  resolvedHarness,
  disabled,
  supportedModels,
  supportedModelsMeta,
  defaultTimeoutSec,
}: {
  value: EvalConfigDraft
  onChange: (next: EvalConfigDraft) => void
  harnessPref: string
  resolvedHarness: string
  disabled?: boolean
  supportedModels?: Record<string, string[]> | null
  supportedModelsMeta?: SupportedModelsMeta | null
  defaultTimeoutSec?: number | null
}) {
  const showReasoning = harnessPref === "codex" || resolvedHarness === "codex"
  const [customPicked, setCustomPicked] = useState(false)
  const modelItems = modelsForHarness(
    harnessPref,
    resolvedHarness,
    supportedModels
  )
  const selectedModel = customPicked
    ? MODEL_CUSTOM_VALUE
    : modelSelectValue(value.model, modelItems)
  const customOpen = selectedModel === MODEL_CUSTOM_VALUE
  const known = knownModelsForHarness(
    harnessPref,
    resolvedHarness,
    supportedModels
  )
  const customRaw = value.model.trim()
  const modelHint =
    customOpen && customRaw
      ? unsupportedModelHint(harnessPref, resolvedHarness, known)
      : null
  const modelPlaceholder =
    resolveModelHarness(harnessPref, resolvedHarness) === "codex"
      ? "gpt-5.6-luna"
      : known[0] || "model id"

  const emptyHint =
    !modelHint && known.length === 0
      ? emptyCatalogHint(harnessPref, resolvedHarness, supportedModelsMeta)
      : null

  return (
    <FieldSet id="eval-config" disabled={disabled}>
      <FieldLegend className="sr-only">Run config</FieldLegend>
      <FieldGroup>
        <Field
          data-disabled={disabled || undefined}
          data-invalid={modelHint ? true : undefined}
        >
          <FieldLabel htmlFor="eval-model">Model</FieldLabel>
          <Select
            items={modelItems}
            value={selectedModel}
            disabled={disabled}
            onValueChange={(next) => {
              if (typeof next !== "string") {
                return
              }
              if (next === MODEL_DEFAULT_VALUE) {
                setCustomPicked(false)
                onChange({ ...value, model: "" })
                return
              }
              if (next === MODEL_CUSTOM_VALUE) {
                const listed = known.includes(value.model.trim())
                setCustomPicked(true)
                onChange({
                  ...value,
                  model: listed ? "" : value.model,
                })
                return
              }
              setCustomPicked(false)
              onChange({ ...value, model: next })
            }}
          >
            <SelectTrigger
              id="eval-model"
              className="w-full"
              disabled={disabled}
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent alignItemWithTrigger={false} side="bottom">
              <SelectGroup>
                {modelItems.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectGroup>
            </SelectContent>
          </Select>
          {customOpen ? (
            <Input
              id="eval-model-custom"
              value={value.model}
              placeholder={modelPlaceholder}
              disabled={disabled}
              aria-invalid={modelHint ? true : undefined}
              onChange={(event) =>
                onChange({ ...value, model: event.target.value })
              }
            />
          ) : null}
          {modelHint ? (
            <FieldDescription id="eval-model-unsupported">
              {modelHint}
            </FieldDescription>
          ) : emptyHint ? (
            <FieldDescription id="eval-model-empty">{emptyHint}</FieldDescription>
          ) : null}
        </Field>
        <Field data-disabled={disabled || undefined}>
          <FieldLabel htmlFor="eval-timeout">Timeout (seconds)</FieldLabel>
          <Input
            id="eval-timeout"
            type="number"
            min={1}
            max={3600}
            value={value.timeoutSec}
            placeholder={String(defaultTimeoutSec ?? DEFAULT_LIVE_TIMEOUT_SEC)}
            disabled={disabled}
            onChange={(event) =>
              onChange({ ...value, timeoutSec: event.target.value })
            }
          />
        </Field>
        <Field data-disabled={disabled || undefined}>
          <FieldLabel htmlFor="eval-temperature">Temperature</FieldLabel>
          <Input
            id="eval-temperature"
            type="number"
            min={0}
            max={2}
            step={0.1}
            value={value.temperature}
            disabled={disabled}
            onChange={(event) =>
              onChange({ ...value, temperature: event.target.value })
            }
          />
        </Field>
        {showReasoning ? (
          <Field data-disabled={disabled || undefined}>
            <FieldLabel id="eval-reasoning-label">Codex reasoning</FieldLabel>
            <ToggleGroup
              id="eval-reasoning"
              aria-labelledby="eval-reasoning-label"
              spacing={2}
              variant="outline"
              value={[value.reasoningEffort]}
              disabled={disabled}
              onValueChange={(next) => {
                const effort = next[0]
                if (
                  effort === "low" ||
                  effort === "medium" ||
                  effort === "high" ||
                  effort === "ultra"
                ) {
                  onChange({ ...value, reasoningEffort: effort })
                }
              }}
            >
              {REASONING.map((effort) => (
                <ToggleGroupItem key={effort} value={effort}>
                  {effort}
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
          </Field>
        ) : null}
      </FieldGroup>
    </FieldSet>
  )
}
