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
import { isLocalMode } from "@/lib/mode"
import type { SettingsKeyId, SettingsKeyPresence } from "@/lib/types"

const KEY_ROWS: Array<{
  name: SettingsKeyId
  label: string
  hint: string
  slug: "cursor" | "codex" | "openai" | "other" | "anthropic"
}> = [
  {
    name: "CURSOR_API_KEY",
    label: "Cursor",
    hint: "Runs checks in Cursor",
    slug: "cursor",
  },
  {
    name: "CODEX_API_KEY",
    label: "Codex",
    hint: "Runs checks in Codex",
    slug: "codex",
  },
  {
    name: "OPENAI_API_KEY",
    label: "OpenAI",
    hint: "Runs live checks. Scores them when OpenAI is the scoring provider, or when Auto has this key. Not read from your shell unless you pass --key-env.",
    slug: "openai",
  },
  {
    name: "Other",
    label: "Other",
    hint: "Runs live checks. Scores them when Other is selected.",
    slug: "other",
  },
  {
    name: "ANTHROPIC_API_KEY",
    label: "Anthropic",
    hint: "Claude / Anthropic",
    slug: "anthropic",
  },
]

const EMPTY_PRESENCE: SettingsKeyPresence = {
  set: false,
  from_vault: false,
  from_env: false,
}

const EMPTY_DRAFTS: Record<SettingsKeyId, string> = {
  CURSOR_API_KEY: "",
  CODEX_API_KEY: "",
  OPENAI_API_KEY: "",
  Other: "",
  ANTHROPIC_API_KEY: "",
  JEV_API_KEY: "",
  AWS_ACCESS_KEY_ID: "",
  AWS_SECRET_ACCESS_KEY: "",
  AWS_SESSION_TOKEN: "",
}

const PROVIDER_ITEMS = [
  { value: "auto", label: "Auto (OpenAI when a key is set)" },
  { value: "openai", label: "OpenAI" },
  { value: "jev", label: "Jev" },
  { value: "aws", label: "AWS" },
  { value: "compatible", label: "Other (OpenAI-compatible)" },
]

const PROVIDER_KEYS: Record<string, SettingsKeyId[]> = {
  openai: ["OPENAI_API_KEY"],
  jev: ["JEV_API_KEY"],
  aws: ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"],
  compatible: ["Other"],
}

export function SettingsPage() {
  const { status, refreshStatus } = useDashboard()
  const [keys, setKeys] = useState<Record<SettingsKeyId, SettingsKeyPresence> | null>(
    null
  )
  const [drafts, setDrafts] = useState<Record<SettingsKeyId, string>>(EMPTY_DRAFTS)
  const [busy, setBusy] = useState<SettingsKeyId | null>(null)
  const [loadError, setLoadError] = useState("")
  const [provider, setProvider] = useState("auto")
  const [region, setRegion] = useState("")
  const [model, setModel] = useState("")
  const [baseUrl, setBaseUrl] = useState("")
  const [pingBusy, setPingBusy] = useState(false)
  const [providerBusy, setProviderBusy] = useState(false)

  const load = async () => {
    try {
      const [keyData, judgeData] = await Promise.all([
        api.settingsKeys(),
        api.settingsJudge(),
      ])
      setKeys(keyData.keys)
      setProvider(judgeData.judge.provider || "auto")
      setRegion(judgeData.judge.region || "")
      setModel(judgeData.judge.model || "")
      setBaseUrl(judgeData.judge.base_url || "")
      setLoadError("")
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Could not load Settings."
      setLoadError(message)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const onSave = async (name: SettingsKeyId) => {
    const value = drafts[name]
    setBusy(name)
    try {
      const data = await api.setSettingsKey(name, value)
      setKeys((current) => ({
        ...(current ?? {
          CURSOR_API_KEY: EMPTY_PRESENCE,
          CODEX_API_KEY: EMPTY_PRESENCE,
          OPENAI_API_KEY: EMPTY_PRESENCE,
          Other: EMPTY_PRESENCE,
          ANTHROPIC_API_KEY: EMPTY_PRESENCE,
          JEV_API_KEY: EMPTY_PRESENCE,
          AWS_ACCESS_KEY_ID: EMPTY_PRESENCE,
          AWS_SECRET_ACCESS_KEY: EMPTY_PRESENCE,
          AWS_SESSION_TOKEN: EMPTY_PRESENCE,
        }),
        ...data.keys,
      }))
      setDrafts((current) => ({ ...current, [name]: "" }))
      await refreshStatus()
      toast.add({ title: "Key saved", type: "success" })
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Could not save that key."
      toast.add({ title: message, type: "error" })
    } finally {
      setBusy(null)
    }
  }

  const onClear = async (name: SettingsKeyId) => {
    setBusy(name)
    try {
      const data = await api.clearSettingsKey(name)
      setKeys((current) => ({
        ...(current ?? {
          CURSOR_API_KEY: EMPTY_PRESENCE,
          CODEX_API_KEY: EMPTY_PRESENCE,
          OPENAI_API_KEY: EMPTY_PRESENCE,
          Other: EMPTY_PRESENCE,
          ANTHROPIC_API_KEY: EMPTY_PRESENCE,
          JEV_API_KEY: EMPTY_PRESENCE,
          AWS_ACCESS_KEY_ID: EMPTY_PRESENCE,
          AWS_SECRET_ACCESS_KEY: EMPTY_PRESENCE,
          AWS_SESSION_TOKEN: EMPTY_PRESENCE,
        }),
        ...data.keys,
      }))
      setDrafts((current) => ({ ...current, [name]: "" }))
      await refreshStatus()
      toast.add({ title: "Key cleared", type: "success" })
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Could not clear that key."
      toast.add({ title: message, type: "error" })
    } finally {
      setBusy(null)
    }
  }

  const saveProvider = async (nextProvider: string) => {
    setProviderBusy(true)
    try {
      const data = await api.setSettingsJudge({
        provider: nextProvider,
        region: region || null,
        model: model || null,
        base_url: baseUrl || null,
      })
      setProvider(data.judge.provider)
      toast.add({ title: "Scoring provider saved", type: "success" })
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Could not save scoring provider."
      toast.add({ title: message, type: "error" })
    } finally {
      setProviderBusy(false)
    }
  }

  const testConnection = async () => {
    setPingBusy(true)
    try {
      await saveProvider(provider)
      const data = await api.pingJudge()
      toast.add({
        title: data.message || (data.ok ? "Connected." : "Could not connect."),
        type: data.ok ? "success" : "error",
      })
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Could not test the scoring provider."
      toast.add({ title: message, type: "error" })
    } finally {
      setPingBusy(false)
    }
  }

  const qaOpen = status?.auth_open_reason === "qa"

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Settings"
        description={
          isLocalMode(status)
            ? "Bring your own model keys. Saved on this machine. No Skill Gate account."
            : "Bring your own model keys. Skill Gate stores them encrypted for this user and uses them instead of server env when present."
        }
      />
      <Card>
        <CardHeader>
          <CardTitle>Model keys</CardTitle>
          <CardDescription>
            {isLocalMode(status)
              ? "Keys stay on this machine. Clearing a key removes it from this project."
              : qaOpen
                ? "QA is sign-in free. Keys save under the shared qa-open identity on the qa database — not production, not a browser cookie."
                : "Keys belong to your signed-in account. They override process env for your requests only. Clearing a key does not unset a server env var."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {loadError ? (
            <p className="text-sm text-destructive">{loadError}</p>
          ) : null}
          {!keys && !loadError ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Spinner />
              Loading…
            </div>
          ) : null}
          {keys ? (
            <FieldGroup>
              {KEY_ROWS.map((row) => {
                const presence = keys[row.name] ?? EMPTY_PRESENCE
                const saving = busy === row.name
                return (
                  <Field key={row.name} orientation="vertical">
                    <div className="flex flex-wrap items-center gap-2">
                      <FieldLabel htmlFor={`settings-${row.slug}-input`}>
                        {row.label}
                      </FieldLabel>
                      <Badge
                        id={`settings-${row.slug}-state`}
                        variant={presence.set ? "secondary" : "outline"}
                      >
                        {presence.set ? "Set" : "Not set"}
                      </Badge>
                    </div>
                    <FieldDescription>{row.hint}</FieldDescription>
                    {presence.from_env && !presence.from_vault ? (
                      <FieldDescription>
                        {isLocalMode(status)
                          ? "Set in the process environment. Clear only removes a key saved for this project."
                          : "Set on the server. Clear only removes a saved user key."}
                      </FieldDescription>
                    ) : null}
                    <Input
                      id={`settings-${row.slug}-input`}
                      type="password"
                      autoComplete="off"
                      value={drafts[row.name]}
                      placeholder={
                        presence.set ? "Set — paste to replace" : "Paste key"
                      }
                      onChange={(event) =>
                        setDrafts((current) => ({
                          ...current,
                          [row.name]: event.target.value,
                        }))
                      }
                    />
                    <div className="flex flex-wrap gap-2">
                      <Button
                        id={`btn-settings-save-${row.slug}`}
                        size="sm"
                        disabled={saving || !drafts[row.name].trim()}
                        onClick={() => void onSave(row.name)}
                      >
                        {saving ? <Spinner data-icon="inline-start" /> : null}
                        Save
                      </Button>
                      <Tooltip>
                        <TooltipTrigger
                          render={
                            <span className="inline-flex">
                              <Button
                                id={`btn-settings-clear-${row.slug}`}
                                variant="outline"
                                size="sm"
                                disabled={saving || !presence.from_vault}
                                onClick={() => void onClear(row.name)}
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
                )
              })}
            </FieldGroup>
          ) : null}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Scoring provider</CardTitle>
          <CardDescription>
            Who scores live checks. Keys stay on this machine. Not read from your shell unless you pass --key-env.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <FieldGroup>
            <Field>
              <FieldLabel htmlFor="settings-judge-provider">Provider</FieldLabel>
              <Select
                items={PROVIDER_ITEMS}
                value={provider}
                onValueChange={(next) => {
                  if (typeof next !== "string") {
                    return
                  }
                  setProvider(next)
                  void saveProvider(next)
                }}
              >
                <SelectTrigger id="settings-judge-provider" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    {PROVIDER_ITEMS.map((item) => (
                      <SelectItem key={item.value} value={item.value}>
                        {item.label}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
            </Field>
            {provider === "aws" ? (
              <>
                <Field>
                  <FieldLabel htmlFor="settings-judge-region">Region</FieldLabel>
                  <Input
                    id="settings-judge-region"
                    value={region}
                    placeholder="us-east-1"
                    onChange={(event) => setRegion(event.target.value)}
                    onBlur={() => void saveProvider(provider)}
                  />
                </Field>
                <Field>
                  <FieldLabel htmlFor="settings-judge-model">Model</FieldLabel>
                  <Input
                    id="settings-judge-model"
                    value={model}
                    placeholder="Model id"
                    onChange={(event) => setModel(event.target.value)}
                    onBlur={() => void saveProvider(provider)}
                  />
                </Field>
              </>
            ) : null}
            {provider === "jev" || provider === "compatible" ? (
              <Field>
                <FieldLabel htmlFor="settings-judge-base-url">Base URL</FieldLabel>
                <Input
                  id="settings-judge-base-url"
                  value={baseUrl}
                  placeholder="https://"
                  onChange={(event) => setBaseUrl(event.target.value)}
                  onBlur={() => void saveProvider(provider)}
                />
              </Field>
            ) : null}
            {(PROVIDER_KEYS[provider] ?? []).map((name) => {
              const slug = name.toLowerCase().replace(/_/g, "-")
              const presence = keys?.[name] ?? EMPTY_PRESENCE
              const saving = busy === name
              const labels: Record<string, string> = {
                JEV_API_KEY: "Jev",
                AWS_ACCESS_KEY_ID: "AWS access key",
                AWS_SECRET_ACCESS_KEY: "AWS secret",
                AWS_SESSION_TOKEN: "AWS session token",
                OPENAI_API_KEY: "OpenAI",
                Other: "Other",
              }
              return (
                <Field key={name} orientation="vertical">
                  <FieldLabel htmlFor={`settings-${slug}-input`}>
                    {labels[name] ?? name}
                  </FieldLabel>
                  <Input
                    id={`settings-${slug}-input`}
                    type="password"
                    autoComplete="off"
                    value={drafts[name]}
                    placeholder={presence.set ? "Set — paste to replace" : "Paste key"}
                    onChange={(event) =>
                      setDrafts((current) => ({
                        ...current,
                        [name]: event.target.value,
                      }))
                    }
                  />
                  <div className="flex flex-wrap gap-2">
                    <Button
                      size="sm"
                      disabled={saving || !drafts[name].trim()}
                      onClick={() => void onSave(name)}
                    >
                      {saving ? <Spinner data-icon="inline-start" /> : null}
                      Save
                    </Button>
                  </div>
                </Field>
              )
            })}
            <div className="flex flex-wrap gap-2">
              <Button
                id="btn-settings-judge-test"
                variant="outline"
                size="sm"
                disabled={pingBusy || providerBusy}
                onClick={() => void testConnection()}
              >
                {pingBusy ? <Spinner data-icon="inline-start" /> : null}
                Test connection
              </Button>
            </div>
          </FieldGroup>
        </CardContent>
      </Card>
      <p className="text-xs text-muted-foreground" id="settings-build">
        Skill Gate {status?.version || "0.6.0"}
        {status?.build ? ` · ${status.build}` : ""}
      </p>
    </div>
  )
}
