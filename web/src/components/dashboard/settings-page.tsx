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

type JudgeChoice = "auto" | "openai" | "jev" | "clef"

const JUDGE_CHOICES: { value: JudgeChoice; label: string }[] = [
  { value: "auto", label: "File checks only" },
  { value: "openai", label: "OpenAI Decisions" },
  { value: "jev", label: "Jev" },
  { value: "clef", label: "Clef" },
]

function knownProvider(value: string | null | undefined): JudgeChoice | "" {
  if (value === "auto" || value === "openai" || value === "jev" || value === "clef") {
    return value
  }
  return ""
}

function keyForProvider(provider: JudgeChoice | ""): SettingsKeyId | null {
  if (provider === "openai") {
    return "OPENAI_API_KEY"
  }
  if (provider === "jev") {
    return "JEV_API_KEY"
  }
  if (provider === "clef") {
    return "CLOUDFLARE_API_TOKEN"
  }
  return null
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
  const [provider, setProvider] = useState<JudgeChoice | "">("")
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
      const saved = knownProvider(judgeData.judge.provider)
      setProvider(saved)
      setRemovedProvider(Boolean(judgeData.judge.provider) && saved === "")
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
    if (provider === "") {
      throw new ApiError("Pick who scores before you save.")
    }
    const value = judgeDraft.trim()
    const keyName = keyForProvider(provider)
    if (value && keyName) {
      const data = await api.setSettingsKey(keyName, value)
      setKeys(data.keys)
      setJudgeDraft("")
    }
    await api.setSettingsJudge({
      provider,
      base_url: provider === "jev" ? baseUrl.trim() || null : null,
      model: provider === "openai" ? null : model.trim() || null,
      account_id: provider === "clef" ? accountId.trim() || null : null,
    })
  }

  const onSaveJudge = async () => {
    setBusy(true)
    try {
      await persistJudgeSetup()
      await refreshStatus()
      toast.add({ title: "Judge saved", type: "success" })
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Could not save the judge."
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
      const keyName = keyForProvider(provider)
      if (keyName && latest?.[keyName]?.from_vault) {
        const data = await api.clearSettingsKey(keyName)
        latest = data.keys
      }
      if (latest) {
        setKeys(latest)
      }
      setJudgeDraft("")
      setProvider("auto")
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

  const keyName = keyForProvider(provider)
  const presence = keyName && keys ? (keys[keyName] ?? EMPTY_PRESENCE) : EMPTY_PRESENCE
  const showKey = keyName !== null

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Settings"
        description="Sign in with Cursor, Codex, or Claude Code. A judge key is optional."
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
          <CardTitle>Judge key (optional)</CardTitle>
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
                <FieldLabel htmlFor="settings-judge-provider">Who scores</FieldLabel>
                <Select
                  items={JUDGE_CHOICES}
                  value={provider || null}
                  onValueChange={(next) => {
                    if (next === "auto" || next === "openai" || next === "jev" || next === "clef") {
                      setProvider(next)
                      setRemovedProvider(false)
                    }
                  }}
                >
                  <SelectTrigger id="settings-judge-provider" className="w-full">
                    <SelectValue placeholder="Pick who scores" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      {JUDGE_CHOICES.map((item) => (
                        <SelectItem key={item.value} value={item.value}>
                          {item.label}
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  </SelectContent>
                </Select>
                {removedProvider ? (
                  <FieldDescription>
                    The saved scoring provider was removed. Pick File checks only, OpenAI
                    Decisions, Jev, or Clef.
                  </FieldDescription>
                ) : null}
              </Field>
              {provider === "jev" ? (
                <Field orientation="vertical">
                  <FieldLabel htmlFor="settings-judge-base-url">Base URL</FieldLabel>
                  <Input
                    id="settings-judge-base-url"
                    type="url"
                    autoComplete="off"
                    value={baseUrl}
                    placeholder="https://openrouter.ai/api/v1"
                    onChange={(event) => setBaseUrl(event.target.value)}
                  />
                </Field>
              ) : null}
              {provider === "jev" || provider === "clef" ? (
                <Field orientation="vertical">
                  <FieldLabel htmlFor="settings-judge-model">Model</FieldLabel>
                  <Input
                    id="settings-judge-model"
                    autoComplete="off"
                    value={model}
                    placeholder={provider === "clef" ? "clef" : "typesafe/jev-1.14"}
                    onChange={(event) => setModel(event.target.value)}
                  />
                </Field>
              ) : null}
              {provider === "clef" ? (
                <Field orientation="vertical">
                  <FieldLabel htmlFor="settings-judge-account-id">Account id</FieldLabel>
                  <Input
                    id="settings-judge-account-id"
                    autoComplete="off"
                    value={accountId}
                    placeholder="Cloudflare account id"
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
                  disabled={busy || testing || provider === ""}
                  onClick={() => void onSaveJudge()}
                >
                  {busy ? <Spinner data-icon="inline-start" /> : null}
                  Save
                </Button>
                <Button
                  id="btn-settings-test-judge"
                  variant="outline"
                  size="sm"
                  disabled={busy || testing || provider === ""}
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
