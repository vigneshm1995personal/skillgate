import { useEffect, useState } from "react"

import { Field, FieldDescription, FieldLabel } from "@/components/ui/field"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { api, ApiError } from "@/lib/api"

type JudgeRow = {
  id: string
  label: string
  detail: string
  needs_endpoint: boolean
}

type SavedJudge = {
  provider: string
  region: string | null
  model: string | null
  base_url: string | null
  key_env?: string[]
}

const NOT_SELECTED = "auto"

export function JudgeSection({ disabled }: { disabled?: boolean }) {
  const [judges, setJudges] = useState<JudgeRow[] | null>(null)
  const [saved, setSaved] = useState<SavedJudge | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    let cancelled = false
    Promise.all([api.decisionJudges(), api.settingsJudge()])
      .then(([catalog, settings]) => {
        if (cancelled) {
          return
        }
        setJudges(catalog.judges)
        setSaved(settings.judge)
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Could not load judges.")
          setJudges([])
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  const decisionIds = new Set((judges ?? []).map((row) => row.id))
  const savedId = saved?.provider || NOT_SELECTED
  const selectedId = decisionIds.has(savedId) ? savedId : NOT_SELECTED
  const stale = Boolean(saved && savedId !== NOT_SELECTED && !decisionIds.has(savedId))
  const selected = judges?.find((row) => row.id === selectedId)
  const items = [
    { value: NOT_SELECTED, label: "Not selected" },
    ...(judges ?? []).map((row) => ({ value: row.id, label: row.label })),
  ]

  async function pick(next: string) {
    if (!saved || next === selectedId) {
      return
    }
    if (next !== NOT_SELECTED && !decisionIds.has(next)) {
      return
    }
    setSaving(true)
    setError(null)
    const keepModel = decisionIds.has(saved.provider)
    try {
      const result = await api.setSettingsJudge({
        provider: next,
        region: saved.region,
        model: keepModel ? saved.model : null,
        base_url: saved.base_url,
        key_env: saved.key_env ?? [],
      })
      setSaved(result.judge)
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "Could not save the judge.")
    } finally {
      setSaving(false)
    }
  }

  if (!judges && !error) {
    return <p className="text-sm text-muted-foreground">Loading…</p>
  }

  return (
    <Field data-disabled={disabled || saving || undefined}>
      <FieldLabel htmlFor="judge-select">Decision model</FieldLabel>
      <Select
        items={items}
        value={selectedId}
        disabled={Boolean(disabled || saving)}
        onValueChange={(next) => {
          if (typeof next === "string") {
            void pick(next)
          }
        }}
      >
        <SelectTrigger id="judge-select" className="w-full">
          <SelectValue />
        </SelectTrigger>
        <SelectContent alignItemWithTrigger={false} side="bottom">
          <SelectGroup>
            {items.map((item) => (
              <SelectItem key={item.value} value={item.value}>
                {item.label}
              </SelectItem>
            ))}
          </SelectGroup>
        </SelectContent>
      </Select>
      {saving ? <FieldDescription>Saving…</FieldDescription> : null}
      {stale ? (
        <FieldDescription>
          The saved judge is not a decision model. Pick one to use it on the next run.
        </FieldDescription>
      ) : null}
      {selected?.detail ? <FieldDescription>{selected.detail}</FieldDescription> : null}
      {error ? <FieldDescription>{error}</FieldDescription> : null}
    </Field>
  )
}
