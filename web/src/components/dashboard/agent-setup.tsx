import { useEffect, useState } from "react"

import { EvalConfigFields } from "@/components/dashboard/eval-config-fields"
import { FieldGroup } from "@/components/ui/field"
import { api } from "@/lib/api"
import {
  knownModelsForHarness,
  type EvalConfigDraft,
  type SupportedModelsMeta,
} from "@/lib/eval-config"
import { agentSessionLabel } from "@/lib/login-status"
import type { AgentAuthRow, HarnessPref } from "@/lib/types"

const AGENTS = [
  { id: "cursor-agent", label: "Cursor" },
  { id: "codex", label: "Codex" },
  { id: "claude", label: "Claude Code" },
] as const

type AgentId = (typeof AGENTS)[number]["id"]

export function AgentSetup({
  harnessPref,
  setHarnessPref,
  resolvedHarness,
  evalConfig,
  setEvalConfig,
  disabled,
  supportedModels,
  supportedModelsMeta,
  defaultTimeoutSec,
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
}) {
  const [rows, setRows] = useState<AgentAuthRow[] | null>(null)
  const [statusError, setStatusError] = useState(false)

  useEffect(() => {
    let cancelled = false
    api
      .loginStatus()
      .then((data) => {
        if (!cancelled) {
          setRows(data.harnesses)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setStatusError(true)
          setRows([])
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  function pick(next: AgentId) {
    const allowed = knownModelsForHarness(next, next, supportedModels)
    setHarnessPref(next)
    if (evalConfig.model.trim() && !allowed.includes(evalConfig.model.trim())) {
      setEvalConfig({ ...evalConfig, model: "" })
    }
  }

  return (
    <FieldGroup>
      <fieldset className="flex flex-col gap-2" disabled={disabled}>
        <legend className="text-sm font-medium">Agent</legend>
        <div className="flex flex-col gap-2">
          {AGENTS.map((agent) => {
            const row = rows?.find((item) => item.kind === agent.id)
            const selected =
              harnessPref === agent.id ||
              (harnessPref === "auto" && resolvedHarness === agent.id)
            const status = !rows
              ? "Loading…"
              : statusError || !row
                ? "Status unavailable"
                : agentSessionLabel(row)
            return (
              <label
                key={agent.id}
                className="flex cursor-pointer items-center gap-3 rounded-lg border px-3 py-2 has-[:focus-visible]:border-ring has-[:focus-visible]:ring-3 has-[:focus-visible]:ring-ring/50"
              >
                <input
                  id={`harness-${agent.id}`}
                  type="radio"
                  name="eval-agent"
                  value={agent.id}
                  checked={selected}
                  disabled={disabled}
                  onChange={() => pick(agent.id)}
                  className="size-4 accent-foreground"
                />
                <span className="text-sm font-medium">{agent.label}</span>
                <span className="ml-auto text-sm text-muted-foreground">
                  {status}
                </span>
              </label>
            )
          })}
        </div>
      </fieldset>
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
  )
}
