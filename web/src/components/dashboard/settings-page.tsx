import { useEffect, useState } from "react"

import { PageHeader } from "@/components/dashboard/chrome"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field"
import { Spinner } from "@/components/ui/spinner"
import { toast } from "@/components/ui/toast"
import { JudgeSetupCard } from "@/components/dashboard/judge-setup-form"
import { agentLabel } from "@/lib/agent-label"
import { api, ApiError } from "@/lib/api"
import { useDashboard } from "@/lib/dashboard-provider"
import { DECISION_ONE_LINE } from "@/lib/judge-setup"
import { agentSessionLabel } from "@/lib/login-status"
import { productMode, slotOn } from "@/lib/mode"
import { settingsSurface } from "@/slots/resolve"
import { useSkillGateSlots } from "@/slots/context"
import type { AgentAuthRow } from "@/lib/types"

const FALLBACK_AGENTS: AgentAuthRow[] = [
  {
    name: agentLabel("cursor"),
    kind: "cursor-agent",
    agent: "cursor",
    status: "none",
    auth: "none",
    installed: false,
    install: "Install this agent's CLI, then sign in.",
    command: "skillgate login cursor",
  },
  {
    name: agentLabel("codex"),
    kind: "codex",
    agent: "codex",
    status: "none",
    auth: "none",
    installed: false,
    install: "Install this agent's CLI, then sign in.",
    command: "skillgate login codex",
  },
  {
    name: agentLabel("claude"),
    kind: "claude",
    agent: "claude",
    status: "none",
    auth: "none",
    installed: false,
    install: "Install this agent's CLI, then sign in.",
    command: "skillgate login claude",
  },
]

export function SettingsPage() {
  const { status } = useDashboard()
  const slots = useSkillGateSlots()
  const HostedSettings = slots.Settings
  const Billing = slots.Billing
  const billing = Billing && slotOn(status, "billing") ? <Billing /> : null
  if (
    settingsSurface(productMode(status), Boolean(HostedSettings)) === "hosted" &&
    HostedSettings
  ) {
    return (
      <>
        <HostedSettings />
        {billing}
      </>
    )
  }
  return (
    <>
      <LocalSettings />
      {billing}
    </>
  )
}

function LocalSettings() {
  const { status, refreshStatus } = useDashboard()
  const [agents, setAgents] = useState<AgentAuthRow[]>(FALLBACK_AGENTS)
  const [loadError, setLoadError] = useState("")
  const [loginBusy, setLoginBusy] = useState<string | null>(null)

  const load = async () => {
    try {
      const loginData = await api.loginStatus()
      if (loginData.harnesses?.length) {
        setAgents(loginData.harnesses)
      }
      setLoadError("")
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Could not load Settings."
      setLoadError(message)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const onSignIn = async (agent: string) => {
    setLoginBusy(agent)
    try {
      const data = await api.startLogin(agent)
      if (data.needs_terminal && data.command && navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(data.command)
      }
      toast.add({
        title: data.message,
        type: data.ok ? "success" : "error",
      })
      await load()
      await refreshStatus()
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Could not start Sign in."
      toast.add({ title: message, type: "error" })
    } finally {
      setLoginBusy(null)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Settings"
        description="Sign in with an agent."
      />
      <Card>
        <CardHeader>
          <CardTitle>Agents</CardTitle>
          <CardDescription>
            Sign in with an agent. Same as{" "}
            <code>skillgate login</code>.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {loadError ? (
            <p className="text-sm text-destructive">{loadError}</p>
          ) : null}
          <FieldGroup>
            {agents.map((row) => {
              const session = agentSessionLabel(row)
              return (
                <Field key={row.agent} orientation="vertical">
                  <div className="flex flex-wrap items-center gap-2">
                    <FieldLabel>{row.name}</FieldLabel>
                    <Badge
                      id={`settings-login-${row.agent}-state`}
                      variant={session === "signed in" ? "secondary" : "outline"}
                    >
                      {session === "signed in" ? "signed in" : "not signed in"}
                    </Badge>
                  </div>
                  {!row.installed ? (
                    <FieldDescription>Not installed. Install this agent's CLI, then sign in.</FieldDescription>
                  ) : (
                    <FieldDescription>
                      Run <code>{row.command}</code> in your terminal, or Sign in here.
                    </FieldDescription>
                  )}
                  <div className="flex flex-wrap gap-2">
                    <Button
                      id={`btn-settings-login-${row.agent}`}
                      size="sm"
                      variant="outline"
                      disabled={loginBusy === row.agent}
                      onClick={() => void onSignIn(row.agent)}
                    >
                      {loginBusy === row.agent ? (
                        <Spinner data-icon="inline-start" />
                      ) : null}
                      Sign in
                    </Button>
                  </div>
                </Field>
              )
            })}
          </FieldGroup>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Decision model</CardTitle>
          <CardDescription>{DECISION_ONE_LINE}</CardDescription>
        </CardHeader>
        <CardContent>
          <JudgeSetupCard idPrefix="settings-judge" />
        </CardContent>
      </Card>
      <p className="text-xs text-muted-foreground" id="settings-build">
        Skill Gate {status?.version || "0.6.0"}
        {status?.build ? ` · ${status.build}` : ""}
      </p>
    </div>
  )
}
