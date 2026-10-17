import { useEffect, useState } from "react"

import { EvalConfigFields } from "@/components/dashboard/eval-config-fields"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Field, FieldGroup, FieldTitle } from "@/components/ui/field"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { api } from "@/lib/api"
import {
  knownModelsForHarness,
  type EvalConfigDraft,
  type SupportedModelsMeta,
} from "@/lib/eval-config"
import { agentSessionLabel } from "@/lib/login-status"
import type { AgentAuthRow, HarnessPref } from "@/lib/types"

const AGENTS: Array<{ value: HarnessPref; label: string; login: string }> = [
  { value: "cursor-agent", label: "Cursor", login: "cursor" },
  { value: "codex", label: "Codex", login: "codex" },
  { value: "claude", label: "Claude Code", login: "claude" },
]

export function AgentSetup({
  harnessPref,
  setHarnessPref,
  resolvedHarness,
  evalConfig,
  setEvalConfig,
  disabled,
  supportedModels,
  supportedModelsMeta,
  availableHarnesses,
  harnesses,
}: {
  harnessPref: HarnessPref
  setHarnessPref: (next: HarnessPref) => void
  resolvedHarness: string
  evalConfig: EvalConfigDraft
  setEvalConfig: (next: EvalConfigDraft) => void
  disabled?: boolean
  supportedModels?: Record<string, string[]> | null
  supportedModelsMeta?: SupportedModelsMeta | null
  availableHarnesses?: string[] | null
  harnesses?: AgentAuthRow[] | null
}) {
  const selected: HarnessPref =
    harnessPref === "auto"
      ? resolvedHarness === "codex" ||
        resolvedHarness === "claude" ||
        resolvedHarness === "cursor-agent"
        ? resolvedHarness
        : "cursor-agent"
      : harnessPref
  const rows = harnesses ?? []

  return (
    <FieldGroup>
      <Field data-disabled={disabled || undefined}>
        <FieldTitle id="harness-label">Agent</FieldTitle>
        <ToggleGroup
          id="harness-select"
          aria-labelledby="harness-label"
          spacing={2}
          variant="outline"
          value={[selected]}
          disabled={disabled}
          onValueChange={(value) => {
            const next = value[0]
            if (next !== "cursor-agent" && next !== "codex" && next !== "claude") {
              return
            }
            const allowed = knownModelsForHarness(next, next, supportedModels)
            setHarnessPref(next)
            const current = evalConfig.model.trim()
            if (current && !allowed.includes(current)) {
              setEvalConfig({ ...evalConfig, model: "" })
            }
          }}
        >
          {AGENTS.map((agent) => {
            const row = rows.find((item) => item.agent === agent.login)
            const session = row ? agentSessionLabel(row) : "not signed in"
            const installed =
              !availableHarnesses ||
              availableHarnesses.includes(
                agent.value === "cursor-agent" ? "cursor-agent" : agent.value
              )
            return (
              <ToggleGroupItem
                key={agent.value}
                value={agent.value}
                disabled={disabled || (agent.value === "claude" && availableHarnesses ? !installed : false)}
              >
                <span className="flex items-center gap-2">
                  {agent.label}
                  <Badge variant={session === "signed in" ? "secondary" : "outline"}>
                    {session}
                  </Badge>
                </span>
              </ToggleGroupItem>
            )
          })}
        </ToggleGroup>
      </Field>
      <EvalConfigFields
        key={selected}
        value={evalConfig}
        onChange={setEvalConfig}
        harnessPref={selected}
        resolvedHarness={resolvedHarness}
        disabled={disabled}
        supportedModels={supportedModels}
        supportedModelsMeta={supportedModelsMeta}
        modelOnly
      />
    </FieldGroup>
  )
}

export function JudgeSection({ onOpenSettings }: { onOpenSettings: () => void }) {
  const [ready, setReady] = useState<boolean | null>(null)
  const [model, setModel] = useState("")

  useEffect(() => {
    let live = true
    void Promise.all([api.settingsKeys(), api.settingsJudge()])
      .then(([keys, judge]) => {
        if (!live) {
          return
        }
        const keySet = Boolean(
          keys.keys.OPENAI_API_KEY?.set || keys.keys.AI_GATEWAY_API_KEY?.set
        )
        setReady(keySet || Boolean(judge.judge.base_url || judge.judge.model))
        setModel(judge.judge.model || "")
      })
      .catch(() => {
        if (live) {
          setReady(false)
        }
      })
    return () => {
      live = false
    }
  }, [])

  if (ready === null) {
    return <p className="text-sm text-muted-foreground">Checking the judge…</p>
  }
  if (!ready) {
    return (
      <div className="flex flex-col items-start gap-2">
        <p className="text-sm">No judge is set.</p>
        <Button variant="outline" size="sm" onClick={onOpenSettings}>
          Open Settings
        </Button>
      </div>
    )
  }
  return (
    <p className="text-sm">
      The judge in Settings scores these checks.
      {model ? ` Model ${model}.` : ""}
    </p>
  )
}
