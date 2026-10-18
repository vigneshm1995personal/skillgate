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
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
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

type ScoringMode = "auto" | "decision"

const REMOVED_ENDPOINTS = new Set(["other", "compatible", "aws", "unknown"])

const SCORING_CHOICES: { value: ScoringMode; label: string }[] = [
  { value: "auto", label: "File checks only" },
  { value: "decision", label: "Decision model" },
]

const ENDPOINT_KEYS: Record<string, SettingsKeyId> = {
  openai: "OPENAI_API_KEY",
  jev: "JEV_API_KEY",
  clef: "CLOUDFLARE_API_TOKEN",
}

function savedScoring(value: string | null | undefined): {
  mode: ScoringMode | ""
  endpoint: string
  removed: boolean
} {
  const provider = (value || "auto").trim().toLowerCase()
  if (!provider || provider === "auto") {
    return { mode: "auto", endpoint: "", removed: false }
  }
  if (REMOVED_ENDPOINTS.has(provider)) {
    return { mode: "", endpoint: "", removed: true }
  }
  return { mode: "decision", endpoint: provider, removed: false }
}

function keyForEndpoint(endpoint: string): SettingsKeyId | null {
  return ENDPOINT_KEYS[endpoint.trim().toLowerCase()] ?? null
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
  const [mode, setMode] = useState<ScoringMode | "">("")
  const [endpoint, setEndpoint] = useState("")
  const [removedProvider, setRemovedProvider] = useState(false)
  const [baseUrl, setBaseUrl] = useState("")
  const [model, setModel] = useState("")
  const [accountId, setAccountId] = useState("")
  const [testMessage, setTestMessage] = useState("")
  const [testing, setTesting] = useState(false)
  const [busy, setBusy] = useState(false)
  const [loadError, setLoadError] = useState("")
  const [loginBusy, setLoginBusy] = useState<string | null>(null)

  const load = async () => {
    try {
      const [keyData, loginData, judgeData] = await Promise.all([
        api.settingsKeys(),
        api.loginStatus(),
        api.settingsJudge(),
      ])
      setKeys(keyData.keys)
      const saved = savedScoring(judgeData.judge.provider)
      setMode(saved.mode)
      setEndpoint(saved.endpoint)
      setRemovedProvider(saved.removed)
      setBaseUrl(judgeData.judge.base_url || "")
      setModel(judgeData.judge.model || "")
      setAccountId(judgeData.judge.account_id || "")
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

  const persistJudgeSetup = async () => {
    if (mode === "") {
      throw new ApiError("Pick file checks only or a decision model.")
    }
    const providerId = mode === "auto" ? "auto" : endpoint.trim().toLowerCase()
    if (mode === "decision" && !providerId) {
      throw new ApiError("A decision model needs an endpoint.")
    }
    const value = judgeDraft.trim()
    const keyName = keyForEndpoint(providerId)
    if (value && keyName) {
      const data = await api.setSettingsKey(keyName, value)
      setKeys(data.keys)
      setJudgeDraft("")
    }
    await api.setSettingsJudge({
      provider: providerId,
      base_url: mode === "decision" ? baseUrl.trim() || null : null,
      model: mode === "decision" ? model.trim() || null : null,
      account_id: mode === "decision" ? accountId.trim() || null : null,
    })
  }

  const onSaveJudge = async () => {
    setBusy(true)
    try {
      await persistJudgeSetup()
      await refreshStatus()
      toast.add({ title: "Saved", type: "success" })
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Could not save."
      toast.add({ title: message, type: "error" })
    } finally {
      setBusy(false)
    }
  }

  const onTestJudge = async () => {
    setTesting(true)
    setTestMessage("")
    try {
      await persistJudgeSetup()
      await refreshStatus()
      const result = await api.pingJudge()
      const message = /no scoring provider/i.test(result.message)
        ? "No scoring provider. File checks only."
        : result.message || (result.ok ? "The judge answered." : "The judge did not answer.")
      setTestMessage(message)
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Could not test the judge."
      setTestMessage(message)
    } finally {
      setTesting(false)
    }
  }

  const onClearJudge = async () => {
    setBusy(true)
    try {
      let latest = keys
      const keyName = keyForEndpoint(endpoint)
      if (keyName && latest?.[keyName]?.from_vault) {
        const data = await api.clearSettingsKey(keyName)
        latest = data.keys
      }
      if (latest) {
        setKeys(latest)
      }
      setJudgeDraft("")
      setMode("auto")
      setEndpoint("")
      setRemovedProvider(false)
      setBaseUrl("")
      setModel("")
      setAccountId("")
      setTestMessage("")
      await api.setSettingsJudge({
        provider: "auto",
        base_url: null,
        model: null,
        account_id: null,
      })
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

  const keyName = mode === "decision" ? keyForEndpoint(endpoint) : null
  const presence = keyName && keys ? (keys[keyName] ?? EMPTY_PRESENCE) : EMPTY_PRESENCE
  const showKey = keyName !== null

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Settings"
        description="Sign in with Cursor, Codex, or Claude Code. A decision model is optional."
      />
      <Card>
        <CardHeader>
          <CardTitle>Agents</CardTitle>
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
          <CardTitle>Decision model (optional)</CardTitle>
          <CardDescription>
            Pick a decision model, or leave scoring off and run file checks only.
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
                <FieldLabel htmlFor="settings-judge-provider">Scoring</FieldLabel>
                <Select
                  items={SCORING_CHOICES}
                  value={mode || null}
                  onValueChange={(next) => {
                    if (next === "auto" || next === "decision") {
                      setMode(next)
                      setRemovedProvider(false)
                    }
                  }}
                >
                  <SelectTrigger id="settings-judge-provider" className="w-full">
                    <SelectValue placeholder="File checks only or a decision model" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      {SCORING_CHOICES.map((item) => (
                        <SelectItem key={item.value} value={item.value}>
                          {item.label}
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  </SelectContent>
                </Select>
                {removedProvider ? (
                  <FieldDescription>
                    The saved scoring setup was removed. Pick file checks only or a decision
                    model.
                  </FieldDescription>
                ) : null}
              </Field>
              {mode === "decision" ? (
                <Field orientation="vertical">
                  <FieldLabel htmlFor="settings-judge-endpoint">Endpoint</FieldLabel>
                  <Input
                    id="settings-judge-endpoint"
                    autoComplete="off"
                    value={endpoint}
                    placeholder="endpoint"
                    onChange={(event) => setEndpoint(event.target.value)}
                  />
                </Field>
              ) : null}
              {mode === "decision" ? (
                <Field orientation="vertical">
                  <FieldLabel htmlFor="settings-judge-base-url">Base URL</FieldLabel>
                  <Input
                    id="settings-judge-base-url"
                    type="url"
                    autoComplete="off"
                    value={baseUrl}
                    placeholder="https://example.com/v1"
                    onChange={(event) => setBaseUrl(event.target.value)}
                  />
                </Field>
              ) : null}
              {mode === "decision" ? (
                <Field orientation="vertical">
                  <FieldLabel htmlFor="settings-judge-model">Model</FieldLabel>
                  <Input
                    id="settings-judge-model"
                    autoComplete="off"
                    value={model}
                    placeholder="model"
                    onChange={(event) => setModel(event.target.value)}
                  />
                </Field>
              ) : null}
              {mode === "decision" ? (
                <Field orientation="vertical">
                  <FieldLabel htmlFor="settings-judge-account-id">Account id</FieldLabel>
                  <Input
                    id="settings-judge-account-id"
                    autoComplete="off"
                    value={accountId}
                    placeholder="account id"
                    onChange={(event) => setAccountId(event.target.value)}
                  />
                </Field>
              ) : null}
              {showKey ? (
                <Field orientation="vertical">
                  <div className="flex flex-wrap items-center gap-2">
                    <FieldLabel htmlFor="settings-judge-key-input">API key</FieldLabel>
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
                    placeholder={presence.set ? "Set — enter a replacement" : "Optional"}
                    onChange={(event) => setJudgeDraft(event.target.value)}
                  />
                </Field>
              ) : null}
              <div className="flex flex-wrap gap-2">
                <Button
                  id="btn-settings-save-judge"
                  size="sm"
                  disabled={busy || testing || mode === ""}
                  onClick={() => void onSaveJudge()}
                >
                  {busy ? <Spinner data-icon="inline-start" /> : null}
                  Save
                </Button>
                <Button
                  id="btn-settings-test-judge"
                  variant="outline"
                  size="sm"
                  disabled={busy || testing || mode === ""}
                  onClick={() => void onTestJudge()}
                >
                  {testing ? <Spinner data-icon="inline-start" /> : null}
                  Test
                </Button>
                <Tooltip>
                  <TooltipTrigger
                    render={
                      <span className="inline-flex">
                        <Button
                          id="btn-settings-clear-judge"
                          variant="outline"
                          size="sm"
                          disabled={
                            busy ||
                            testing ||
                            (!presence.from_vault &&
                              !baseUrl.trim() &&
                              !model.trim() &&
                              !accountId.trim() &&
                              !removedProvider)
                          }
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
              {testMessage ? (
                <p id="settings-judge-test" className="text-sm text-muted-foreground">
                  {testMessage}
                </p>
              ) : null}
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
