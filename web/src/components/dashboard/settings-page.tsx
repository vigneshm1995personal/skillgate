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
import { Input } from "@/components/ui/input"
import { Spinner } from "@/components/ui/spinner"
import { toast } from "@/components/ui/toast"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { api, ApiError } from "@/lib/api"
import { useDashboard } from "@/lib/dashboard-provider"
import { agentSessionLabel } from "@/lib/login-status"
import { isLocalMode, productMode, slotOn } from "@/lib/mode"
import { settingsSurface } from "@/slots/resolve"
import { useSkillGateSlots } from "@/slots/context"
import type { AgentAuthRow, SettingsKeyId, SettingsKeyPresence } from "@/lib/types"

const FALLBACK_AGENTS: AgentAuthRow[] = [
  {
    name: "Cursor",
    kind: "cursor-agent",
    agent: "cursor",
    status: "none",
    auth: "none",
    installed: false,
    install: "curl https://cursor.com/install -fsS | bash",
    command: "skillgate login cursor",
  },
  {
    name: "Codex",
    kind: "codex",
    agent: "codex",
    status: "none",
    auth: "none",
    installed: false,
    install: "npm install -g @openai/codex",
    command: "skillgate login codex",
  },
  {
    name: "Claude Code",
    kind: "claude",
    agent: "claude",
    status: "none",
    auth: "none",
    installed: false,
    install: "npm install -g @anthropic-ai/claude-code",
    command: "skillgate login claude",
  },
]

const EMPTY_PRESENCE: SettingsKeyPresence = {
  set: false,
  from_vault: false,
  from_env: false,
}

const JUDGE_KEY_NAMES: SettingsKeyId[] = ["OPENAI_API_KEY", "AI_GATEWAY_API_KEY"]

function judgePresence(
  keys: Record<SettingsKeyId, SettingsKeyPresence> | null
): SettingsKeyPresence {
  const rows = JUDGE_KEY_NAMES.map((name) => keys?.[name] ?? EMPTY_PRESENCE)
  return {
    set: rows.some((row) => row.set),
    from_vault: rows.some((row) => row.from_vault),
    from_env: rows.some((row) => row.from_env),
  }
}

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
  const [keys, setKeys] = useState<Record<SettingsKeyId, SettingsKeyPresence> | null>(
    null
  )
  const [agents, setAgents] = useState<AgentAuthRow[]>(FALLBACK_AGENTS)
  const [judgeDraft, setJudgeDraft] = useState("")
  const [busy, setBusy] = useState(false)
  const [loadError, setLoadError] = useState("")
  const [loginBusy, setLoginBusy] = useState<string | null>(null)

  const load = async () => {
    try {
      const [keyData, loginData] = await Promise.all([
        api.settingsKeys(),
        api.loginStatus(),
      ])
      setKeys(keyData.keys)
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

  const onSaveJudge = async () => {
    const value = judgeDraft.trim()
    if (!value) {
      return
    }
    setBusy(true)
    try {
      const data = await api.setSettingsKey("OPENAI_API_KEY", value)
      setKeys(data.keys)
      setJudgeDraft("")
      await refreshStatus()
      toast.add({ title: "Key saved", type: "success" })
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Could not save that key."
      toast.add({ title: message, type: "error" })
    } finally {
      setBusy(false)
    }
  }

  const onClearJudge = async () => {
    setBusy(true)
    try {
      let latest = keys
      for (const name of JUDGE_KEY_NAMES) {
        if (!(latest?.[name]?.from_vault)) {
          continue
        }
        const data = await api.clearSettingsKey(name)
        latest = data.keys
      }
      if (latest) {
        setKeys(latest)
      }
      setJudgeDraft("")
      await refreshStatus()
      toast.add({ title: "Key cleared", type: "success" })
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Could not clear that key."
      toast.add({ title: message, type: "error" })
    } finally {
      setBusy(false)
    }
  }

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

  const presence = judgePresence(keys)

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Settings"
        description="Sign in with Cursor, Codex, or Claude Code. A judge key is optional."
      />
      <Card>
        <CardHeader>
          <CardTitle>Model keys</CardTitle>
          <CardDescription>
            Sign in with Cursor, Codex, or Claude Code. Same as{" "}
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
                    <FieldDescription>Not installed. {row.install}</FieldDescription>
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
          <CardTitle>Judge key (optional)</CardTitle>
          <CardDescription>
            Scores checks. Skip it to run without the judge.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {!keys && !loadError ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Spinner />
              Loading…
            </div>
          ) : null}
          {keys ? (
            <FieldGroup>
              <Field orientation="vertical">
                <div className="flex flex-wrap items-center gap-2">
                  <FieldLabel htmlFor="settings-judge-key-input">Judge key</FieldLabel>
                  <Badge
                    id="settings-judge-key-state"
                    variant={presence.set ? "secondary" : "outline"}
                  >
                    {presence.set ? "Set" : "Not set"}
                  </Badge>
                </div>
                {presence.from_env && !presence.from_vault ? (
                  <FieldDescription>
                    {isLocalMode(status)
                      ? "Set in the process environment. Clear only removes a key saved for this project."
                      : "Set on the server. Clear only removes a saved user key."}
                  </FieldDescription>
                ) : null}
                <Input
                  id="settings-judge-key-input"
                  type="password"
                  autoComplete="off"
                  value={judgeDraft}
                  placeholder={presence.set ? "Set — paste to replace" : "Paste key"}
                  onChange={(event) => setJudgeDraft(event.target.value)}
                />
                <div className="flex flex-wrap gap-2">
                  <Button
                    id="btn-settings-save-judge"
                    size="sm"
                    disabled={busy || !judgeDraft.trim()}
                    onClick={() => void onSaveJudge()}
                  >
                    {busy ? <Spinner data-icon="inline-start" /> : null}
                    Save
                  </Button>
                  <Tooltip>
                    <TooltipTrigger
                      render={
                        <span className="inline-flex">
                          <Button
                            id="btn-settings-clear-judge"
                            variant="outline"
                            size="sm"
                            disabled={busy || !presence.from_vault}
                            onClick={() => void onClearJudge()}
                          >
                            Clear
                          </Button>
                        </span>
                      }
                    />
                    <TooltipContent>
                      {presence.from_vault
                        ? isLocalMode(status)
                          ? "Remove the key saved for this project"
                          : "Remove the saved user key"
                        : isLocalMode(status)
                          ? "Clear only removes a key saved for this project"
                          : "Clear only removes a saved user key"}
                    </TooltipContent>
                  </Tooltip>
                </div>
              </Field>
            </FieldGroup>
          ) : null}
        </CardContent>
      </Card>
      <p className="text-xs text-muted-foreground" id="settings-build">
        Skill Gate {status?.version || "0.6.0"}
        {status?.build ? ` · ${status.build}` : ""}
      </p>
    </div>
  )
}
