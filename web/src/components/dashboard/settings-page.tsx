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
import { isLocalMode } from "@/lib/mode"
import type { SettingsKeyId, SettingsKeyPresence } from "@/lib/types"

const KEY_ROWS: Array<{
  name: SettingsKeyId
  label: string
  hint: string
  slug: "cursor" | "codex" | "openai" | "gateway" | "anthropic"
}> = [
  {
    name: "CURSOR_API_KEY",
    label: "Cursor",
    hint: "Cursor Agent harness",
    slug: "cursor",
  },
  {
    name: "CODEX_API_KEY",
    label: "Codex",
    hint: "Codex CLI",
    slug: "codex",
  },
  {
    name: "OPENAI_API_KEY",
    label: "OpenAI",
    hint: "Scores live checks. Other keys only run them.",
    slug: "openai",
  },
  {
    name: "AI_GATEWAY_API_KEY",
    label: "OpenAI-compatible",
    hint: "Optional HTTP base for an OpenAI-compatible key",
    slug: "gateway",
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

export function SettingsPage() {
  const { status, refreshStatus } = useDashboard()
  const [keys, setKeys] = useState<Record<SettingsKeyId, SettingsKeyPresence> | null>(
    null
  )
  const [drafts, setDrafts] = useState<Record<SettingsKeyId, string>>({
    CURSOR_API_KEY: "",
    CODEX_API_KEY: "",
    OPENAI_API_KEY: "",
    AI_GATEWAY_API_KEY: "",
    ANTHROPIC_API_KEY: "",
  })
  const [busy, setBusy] = useState<SettingsKeyId | null>(null)
  const [loadError, setLoadError] = useState("")

  const load = async () => {
    try {
      const data = await api.settingsKeys()
      setKeys(data.keys)
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
          AI_GATEWAY_API_KEY: EMPTY_PRESENCE,
          ANTHROPIC_API_KEY: EMPTY_PRESENCE,
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
          AI_GATEWAY_API_KEY: EMPTY_PRESENCE,
          ANTHROPIC_API_KEY: EMPTY_PRESENCE,
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
    </div>
  )
}
