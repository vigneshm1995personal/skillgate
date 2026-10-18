import { useEffect, useState } from "react"

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion"
import { api, ApiError } from "@/lib/api"
import type { ExtraQuestion } from "@/lib/judge-spec"

type CheckRow = {
  id: string
  label: string
  builtin: boolean
  prompt: string
}

export function BuiltInChecks({ skill }: { skill?: string | null }) {
  const [rows, setRows] = useState<CheckRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setRows(null)
    setError(null)
    api
      .listChecks(skill)
      .then((data) => {
        if (!cancelled) {
          setRows(data.checks.filter((row) => row.builtin))
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Could not load checks.")
          setRows([])
        }
      })
    return () => {
      cancelled = true
    }
  }, [skill])

  if (error) {
    return <p className="text-sm text-muted-foreground">{error}</p>
  }
  if (!rows) {
    return <p className="text-sm text-muted-foreground">Loading…</p>
  }
  if (rows.length === 0) {
    return <p className="text-sm text-muted-foreground">No built-in checks loaded.</p>
  }
  return (
    <Accordion id="builtin-checks" className="rounded-lg border px-3">
      {rows.map((row) => (
        <AccordionItem key={row.id} value={row.id}>
          <AccordionTrigger id={`check-prompt-${row.id}`}>
            {row.label}
          </AccordionTrigger>
          <AccordionContent>
            <pre
              id={`check-prompt-body-${row.id}`}
              className="max-h-80 overflow-auto rounded-lg border bg-muted p-3 font-mono text-xs whitespace-pre-wrap"
            >
              {row.prompt}
            </pre>
          </AccordionContent>
        </AccordionItem>
      ))}
    </Accordion>
  )
}

export function CheckPromptPreview({ question }: { question: ExtraQuestion }) {
  const [open, setOpen] = useState(false)
  const [prompt, setPrompt] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const ask = question.ask.trim()
  const choicesKey = JSON.stringify(question.choices ?? [])
  const levelsKey = JSON.stringify(question.levels ?? [])

  useEffect(() => {
    if (!open) {
      return
    }
    if (!ask) {
      setPrompt(null)
      setError(null)
      setLoading(false)
      return
    }
    let cancelled = false
    setLoading(true)
    setPrompt(null)
    setError(null)
    api
      .previewCheck(question)
      .then((row) => {
        if (!cancelled) {
          setPrompt(row.prompt)
          setLoading(false)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setPrompt(null)
          setError(
            err instanceof ApiError ? err.message : "Could not load the judge prompt."
          )
          setLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [open, ask, question, choicesKey, levelsKey])

  return (
    <details
      className="rounded-lg border px-3"
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary className="cursor-pointer rounded-md py-2 text-sm font-medium focus-visible:outline-2 focus-visible:outline-offset-2">
        Judge prompt
      </summary>
      <div className="pb-3">
        {!ask ? (
          <p className="text-sm text-muted-foreground">
            Add the question to see the judge prompt.
          </p>
        ) : loading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : error ? (
          <p className="text-sm text-muted-foreground">{error}</p>
        ) : (
          <pre className="max-h-80 overflow-auto rounded-lg border bg-muted p-3 font-mono text-xs whitespace-pre-wrap">
            {prompt}
          </pre>
        )}
      </div>
    </details>
  )
}
