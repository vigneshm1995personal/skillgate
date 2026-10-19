import { useEffect, useState } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field"
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
import {
  draftForSelection,
  judgeSaveBody,
  mismatchCopy,
  showsField,
  type DecisionJudge,
  type JudgeDraft,
} from "@/lib/judge-setup"
import { isLocalMode } from "@/lib/mode"
import type { SettingsKeyId, SettingsKeyPresence } from "@/lib/types"

const NOT_SELECTED = "auto"
const REMOVED_ENDPOINTS = new Set(["other", "compatible", "aws", "unknown", "skip"])
const EMPTY_PRESENCE: SettingsKeyPresence = {
  set: false,
  from_vault: false,
  from_env: false,
}

const controlClass =
  "h-8 w-full min-w-0 rounded-md border border-input bg-transparent px-2.5 text-sm text-foreground outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"

type FormProps = {
  idPrefix: string
  selectId?: string
  judges: DecisionJudge[]
  provider: string
  onProvider: (next: string) => void
  draft: JudgeDraft
  onDraft: (next: JudgeDraft) => void
  keyDraft: string
  onKeyDraft: (value: string) => void
  keyLabel: string
  keySet: boolean
  showKey: boolean
  keyHint?: string
  removedNote?: string
  testMessage?: string
  testOk?: boolean
  switchTo?: string
  onSwitch?: (id: string) => void
  onSave: () => void
  onTest: () => void
  onClear: () => void
  busy?: boolean
  testing?: boolean
  disabled?: boolean
  clearDisabled?: boolean
  clearHint?: string
}

function buttonId(idPrefix: string, action: "save" | "test" | "clear"): string {
  if (idPrefix === "settings-judge") {
    return `btn-settings-${action}-judge`
  }
  return `btn-${idPrefix}-${action}`
}

export function JudgeSetupForm({
  idPrefix,
  selectId,
  judges,
  provider,
  onProvider,
  draft,
  onDraft,
  keyDraft,
  onKeyDraft,
  keyLabel,
  keySet,
  showKey,
  keyHint,
  removedNote,
  testMessage,
  testOk,
  switchTo,
  onSwitch,
  onSave,
  onTest,
  onClear,
  busy,
  testing,
  disabled,
  clearDisabled,
  clearHint,
}: FormProps) {
  const selected = judges.find((row) => row.id === provider)
  const locked = Boolean(disabled || busy || testing)
  const items = [
    { value: NOT_SELECTED, label: "Not selected" },
    ...judges.map((row) => ({ value: row.id, label: row.label })),
  ]
  const advanced = (selected?.advanced ?? []).filter((name) => showsField(selected, name))
  const plain = (selected?.fields ?? []).filter(
    (name) => name !== "key" && !advanced.includes(name)
  )
  const switchLabel = judges.find((row) => row.id === switchTo)?.label

  const setField = (name: keyof JudgeDraft, value: string) => {
    onDraft({ ...draft, [name]: value })
  }

  return (
    <FieldGroup data-disabled={locked || undefined}>
      <Field orientation="vertical">
        <FieldLabel htmlFor={selectId || `${idPrefix}-provider`}>Decision model</FieldLabel>
        <select
          id={selectId || `${idPrefix}-provider`}
          className={controlClass}
          value={provider || NOT_SELECTED}
          disabled={locked}
          onChange={(event) => onProvider(event.target.value)}
        >
          {items.map((item) => (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          ))}
        </select>
        {removedNote ? <FieldDescription>{removedNote}</FieldDescription> : null}
        {selected?.detail ? <FieldDescription>{selected.detail}</FieldDescription> : null}
      </Field>
      {plain.map((name) => (
        <SetupField
          key={name}
          name={name}
          idPrefix={idPrefix}
          option={selected}
          draft={draft}
          disabled={locked}
          onChange={setField}
        />
      ))}
      {advanced.length ? (
        <details open className="flex flex-col gap-5">
          <summary className="cursor-pointer text-sm font-medium">Advanced</summary>
          {advanced.map((name) => (
            <SetupField
              key={name}
              name={name}
              idPrefix={idPrefix}
              option={selected}
              draft={draft}
              disabled={locked}
              onChange={setField}
            />
          ))}
        </details>
      ) : null}
      {showKey ? (
        <Field orientation="vertical">
          <div className="flex flex-wrap items-center gap-2">
            <FieldLabel htmlFor={`${idPrefix}-key-input`}>{keyLabel || "API key"}</FieldLabel>
            <Badge
              id={idPrefix === "settings-judge" ? "settings-judge-key-state" : `${idPrefix}-key-state`}
              variant={keySet ? "secondary" : "outline"}
            >
              {keySet ? "Set" : "Not set"}
            </Badge>
          </div>
          {keyHint ? <FieldDescription>{keyHint}</FieldDescription> : null}
          <Input
            id={`${idPrefix}-key-input`}
            type="password"
            autoComplete="off"
            value={keyDraft}
            disabled={locked}
            placeholder={keySet ? "Set — enter a replacement" : keyLabel || "API key"}
            onChange={(event) => onKeyDraft(event.target.value)}
          />
        </Field>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <Button
          id={buttonId(idPrefix, "save")}
          size="sm"
          disabled={locked || !provider}
          onClick={onSave}
        >
          {busy ? <Spinner data-icon="inline-start" /> : null}
          Save
        </Button>
        <Button
          id={buttonId(idPrefix, "test")}
          variant="outline"
          size="sm"
          disabled={locked || !provider}
          onClick={onTest}
        >
          {testing ? <Spinner data-icon="inline-start" /> : null}
          Test
        </Button>
        <Tooltip>
          <TooltipTrigger
            render={
              <span className="inline-flex">
                <Button
                  id={buttonId(idPrefix, "clear")}
                  variant="outline"
                  size="sm"
                  disabled={locked || clearDisabled}
                  onClick={onClear}
                >
                  Clear
                </Button>
              </span>
            }
          />
          <TooltipContent>{clearHint}</TooltipContent>
        </Tooltip>
        {switchTo && switchLabel && onSwitch ? (
          <Button
            id={`${idPrefix}-switch`}
            variant="outline"
            size="sm"
            disabled={locked}
            onClick={() => onSwitch(switchTo)}
          >
            {`Switch to ${switchLabel}`}
          </Button>
        ) : null}
      </div>
      {testMessage ? (
        <p
          id={`${idPrefix}-test`}
          className={testOk ? "text-sm text-success" : "text-sm text-destructive"}
        >
          {testMessage}
        </p>
      ) : null}
    </FieldGroup>
  )
}

function SetupField({
  name,
  idPrefix,
  option,
  draft,
  disabled,
  onChange,
}: {
  name: string
  idPrefix: string
  option: DecisionJudge | undefined
  draft: JudgeDraft
  disabled: boolean
  onChange: (name: keyof JudgeDraft, value: string) => void
}) {
  if (name === "base_url") {
    return (
      <Field orientation="vertical">
        <FieldLabel htmlFor={`${idPrefix}-base-url`}>Base URL</FieldLabel>
        <Input
          id={`${idPrefix}-base-url`}
          type="url"
          autoComplete="off"
          disabled={disabled}
          value={draft.baseUrl}
          placeholder="https://example.com/v1"
          onChange={(event) => onChange("baseUrl", event.target.value)}
        />
      </Field>
    )
  }
  if (name === "account_id") {
    return (
      <Field orientation="vertical">
        <FieldLabel htmlFor={`${idPrefix}-account-id`}>Account id</FieldLabel>
        <Input
          id={`${idPrefix}-account-id`}
          autoComplete="off"
          disabled={disabled}
          value={draft.accountId}
          placeholder="account id"
          onChange={(event) => onChange("accountId", event.target.value)}
        />
      </Field>
    )
  }
  if (name === "model") {
    const models = option?.models ?? []
    const free = Boolean(option?.model_free) || models.length === 0
    return (
      <Field orientation="vertical">
        <FieldLabel htmlFor={`${idPrefix}-model`}>Model</FieldLabel>
        {free ? (
          <Input
            id={`${idPrefix}-model`}
            autoComplete="off"
            disabled={disabled}
            value={draft.model}
            placeholder="model"
            onChange={(event) => onChange("model", event.target.value)}
          />
        ) : (
          <select
            id={`${idPrefix}-model`}
            className={controlClass}
            disabled={disabled}
            value={draft.model}
            onChange={(event) => onChange("model", event.target.value)}
          >
            {models.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        )}
      </Field>
    )
  }
  return null
}

export function JudgeSetupCard({
  idPrefix,
  selectId,
  disabled,
}: {
  idPrefix: string
  selectId?: string
  disabled?: boolean
}) {
  const { status, refreshStatus } = useDashboard()
  const [keys, setKeys] = useState<Record<string, SettingsKeyPresence> | null>(null)
  const [judges, setJudges] = useState<DecisionJudge[]>([])
  const [provider, setProvider] = useState(NOT_SELECTED)
  const [savedProvider, setSavedProvider] = useState(NOT_SELECTED)
  const [savedDraft, setSavedDraft] = useState<JudgeDraft>({
    baseUrl: "",
    model: "",
    accountId: "",
  })
  const [draft, setDraft] = useState<JudgeDraft>({ baseUrl: "", model: "", accountId: "" })
  const [keyDraft, setKeyDraft] = useState("")
  const [removedNote, setRemovedNote] = useState("")
  const [testMessage, setTestMessage] = useState("")
  const [testOk, setTestOk] = useState(false)
  const [switchTo, setSwitchTo] = useState("")
  const [busy, setBusy] = useState(false)
  const [testing, setTesting] = useState(false)
  const [loadError, setLoadError] = useState("")

  const load = async () => {
    try {
      const [keyData, judgeData, catalog] = await Promise.all([
        api.settingsKeys(),
        api.settingsJudge(),
        api.decisionJudges(),
      ])
      setKeys(keyData.keys)
      const listed = catalog.judges
      setJudges(listed)
      const known = new Set(listed.map((row) => row.id))
      const saved = (judgeData.judge.provider || NOT_SELECTED).trim().toLowerCase()
      const nextDraft = {
        baseUrl: judgeData.judge.base_url || "",
        model: judgeData.judge.model || "",
        accountId: judgeData.judge.account_id || "",
      }
      setSavedDraft(nextDraft)
      if (!saved || saved === NOT_SELECTED) {
        setProvider(NOT_SELECTED)
        setSavedProvider(NOT_SELECTED)
        setRemovedNote("")
        setDraft({ baseUrl: "", model: "", accountId: "" })
      } else if (REMOVED_ENDPOINTS.has(saved) || !known.has(saved)) {
        setProvider("")
        setSavedProvider(saved)
        setRemovedNote("The saved scoring setup was removed. Pick a decision model.")
        setDraft(nextDraft)
      } else {
        const option = listed.find((row) => row.id === saved)
        const filled = draftForSelection(option, saved, nextDraft, saved)
        setProvider(saved)
        setSavedProvider(saved)
        setRemovedNote("")
        setDraft(filled)
      }
      setLoadError("")
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.message : "Could not load Settings.")
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const selected = judges.find((row) => row.id === provider)
  const keyName = selected?.key_name?.trim() ? (selected.key_name as SettingsKeyId) : null
  const presence = keyName && keys ? (keys[keyName] ?? EMPTY_PRESENCE) : EMPTY_PRESENCE
  const chosen = provider !== "" && provider !== NOT_SELECTED

  const applyProvider = (next: string) => {
    setProvider(next)
    setRemovedNote("")
    setSwitchTo("")
    const option = judges.find((row) => row.id === next)
    setDraft(draftForSelection(option, savedProvider, savedDraft, next))
  }

  const persist = async () => {
    const value = keyDraft.trim()
    if (value && keyName) {
      const data = await api.setSettingsKey(keyName, value)
      setKeys(data.keys)
      setKeyDraft("")
    }
    const saved = await api.setSettingsJudge(judgeSaveBody(selected, provider, draft))
    const next = {
      baseUrl: saved.judge.base_url || "",
      model: saved.judge.model || "",
      accountId: saved.judge.account_id || "",
    }
    setSavedProvider(saved.judge.provider || NOT_SELECTED)
    setSavedDraft(next)
    setDraft(next)
  }

  const onSave = async () => {
    setBusy(true)
    try {
      await persist()
      await refreshStatus()
      toast.add({ title: "Saved", type: "success" })
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Could not save."
      toast.add({ title: message, type: "error" })
    } finally {
      setBusy(false)
    }
  }

  const onTest = async () => {
    setTesting(true)
    setTestMessage("")
    setSwitchTo("")
    const mismatched = mismatchCopy(provider, keyDraft, judges)
    if (mismatched) {
      setTestOk(false)
      setSwitchTo(mismatched.switchTo)
      setTestMessage(mismatched.message)
      setTesting(false)
      return
    }
    try {
      await persist()
      await refreshStatus()
      const result = await api.pingJudge()
      setTestOk(result.ok)
      setSwitchTo(result.switch_to || "")
      setTestMessage(
        result.message || (result.ok ? "The judge answered." : "The judge did not answer.")
      )
    } catch (err) {
      setTestOk(false)
      setTestMessage(err instanceof ApiError ? err.message : "Could not test the judge.")
    } finally {
      setTesting(false)
    }
  }

  const onClear = async () => {
    setBusy(true)
    try {
      if (keyName && keys?.[keyName]?.from_vault) {
        const data = await api.clearSettingsKey(keyName)
        setKeys(data.keys)
      }
      setKeyDraft("")
      setProvider(NOT_SELECTED)
      setRemovedNote("")
      setDraft({ baseUrl: "", model: "", accountId: "" })
      setSavedDraft({ baseUrl: "", model: "", accountId: "" })
      setSavedProvider(NOT_SELECTED)
      setTestMessage("")
      setSwitchTo("")
      await api.setSettingsJudge({
        provider: NOT_SELECTED,
        base_url: null,
        model: null,
        account_id: null,
        region: null,
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

  if (loadError) {
    return <p className="text-sm text-destructive">{loadError}</p>
  }
  if (!keys) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Spinner />
        Loading…
      </div>
    )
  }

  const local = isLocalMode(status)
  const keyHint =
    presence.from_env && !presence.from_vault
      ? local
        ? "Set in the process environment. Clear only removes a key saved for this project."
        : "Set on the server. Clear only removes a saved user key."
      : undefined
  const clearHint = presence.from_vault
    ? local
      ? "Remove the key saved for this project"
      : "Remove the saved user key"
    : local
      ? "Clear only removes a key saved for this project"
      : "Clear only removes a saved user key"

  return (
    <JudgeSetupForm
      idPrefix={idPrefix}
      selectId={selectId}
      judges={judges}
      provider={provider || NOT_SELECTED}
      onProvider={applyProvider}
      draft={draft}
      onDraft={setDraft}
      keyDraft={keyDraft}
      onKeyDraft={setKeyDraft}
      keyLabel={selected?.key_label || "API key"}
      keySet={presence.set}
      showKey={Boolean(keyName)}
      keyHint={keyHint}
      removedNote={removedNote}
      testMessage={testMessage}
      testOk={testOk}
      switchTo={switchTo}
      onSwitch={applyProvider}
      onSave={() => void onSave()}
      onTest={() => void onTest()}
      onClear={() => void onClear()}
      busy={busy}
      testing={testing}
      disabled={disabled}
      clearDisabled={
        !presence.from_vault &&
        !draft.baseUrl.trim() &&
        !draft.model.trim() &&
        !draft.accountId.trim() &&
        !removedNote &&
        !chosen
      }
      clearHint={clearHint}
    />
  )
}
