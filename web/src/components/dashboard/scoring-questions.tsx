import { useEffect, useState } from "react"

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion"
import { Button } from "@/components/ui/button"
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { api } from "@/lib/api"
import {
  BUILTIN_QUESTIONS,
  MAX_SCORING_QUESTIONS,
  duplicateExtraIds,
  totalQuestionCount,
  type ExtraQuestion,
  type JudgeBlock,
} from "@/lib/judge-spec"

type JudgePromptRow = {
  id: string
  sentence: string
  prompt: string
  builtin: boolean
  readonly: boolean
}

export function BuiltinChecks() {
  const [rows, setRows] = useState<JudgePromptRow[]>([])
  const [error, setError] = useState("")

  useEffect(() => {
    let live = true
    void api
      .judgeChecks()
      .then((data) => {
        if (live) {
          setRows(data.checks)
        }
      })
      .catch(() => {
        if (live) {
          setError("Could not load the checks.")
        }
      })
    return () => {
      live = false
    }
  }, [])

  if (error) {
    return <p className="text-sm text-destructive">{error}</p>
  }
  return (
    <Accordion id="builtin-checks" className="gap-1">
      {rows.map((question) => (
        <AccordionItem key={question.id} value={question.id} className="border-b-0">
          <AccordionTrigger id={`builtin-${question.id}`}>
            {question.sentence}
          </AccordionTrigger>
          <AccordionContent>
            <Textarea
              id={`check-prompt-${question.id}`}
              readOnly
              value={question.prompt}
              rows={Math.min(12, Math.max(4, question.prompt.split("\n").length))}
              spellCheck={false}
              aria-label={`${question.sentence} prompt`}
              className="font-mono text-xs"
            />
          </AccordionContent>
        </AccordionItem>
      ))}
    </Accordion>
  )
}

const TYPE_ITEMS = [
  { value: "predicate", label: "Yes/No" },
  { value: "choice", label: "Pick one" },
  { value: "score", label: "Score" },
]

export function ScoringQuestions({
  index,
  packJudge,
  checkJudge,
  disabled,
  onCheckJudge,
}: {
  index: number
  packJudge?: JudgeBlock | null
  checkJudge?: JudgeBlock | null
  disabled?: boolean
  onCheckJudge: (next: JudgeBlock | null) => void
}) {
  const onFail = {
    ...(packJudge?.on_fail ?? {}),
    ...(checkJudge?.on_fail ?? {}),
  }
  const extras = checkJudge?.extra_questions ?? []
  const total = totalQuestionCount(packJudge, checkJudge)
  return (
    <div className="flex flex-col gap-3" id={`scoring-questions-${index}`}>
      <p className="text-xs font-medium text-muted-foreground">
        Questions for this test case
      </p>
      <FieldDescription>
        Optional. These run on this test case only, after the checks listed above.
      </FieldDescription>
      <FieldGroup>
        {BUILTIN_QUESTIONS.map((question) => {
          const value = onFail[question.id] ?? question.defaultOnFail
          return (
            <Field key={question.id} data-disabled={disabled || undefined}>
              <FieldLabel htmlFor={`builtin-${question.id}-${index}`}>
                {question.ask}
              </FieldLabel>
              <ToggleGroup
                value={[value]}
                onValueChange={(next) => {
                  const picked = Array.isArray(next) ? next[0] : next
                  if (picked !== "block" && picked !== "warn") {
                    return
                  }
                  onCheckJudge({
                    ...(checkJudge ?? {}),
                    on_fail: { ...(checkJudge?.on_fail ?? {}), [question.id]: picked },
                  })
                }}
                disabled={disabled}
                size="sm"
              >
                <ToggleGroupItem
                  id={`builtin-${question.id}-${index}`}
                  value="block"
                >
                  Fail the check
                </ToggleGroupItem>
                <ToggleGroupItem value="warn">Warn only</ToggleGroupItem>
              </ToggleGroup>
            </Field>
          )
        })}
        {duplicateExtraIds(extras).length ? (
          <FieldDescription>
            Two questions share an id. Pick a new id before saving.
          </FieldDescription>
        ) : null}
        {extras.map((extra, extraIndex) => (
          <ExtraQuestionFields
            key={`${extra.id}-${extraIndex}`}
            index={index}
            extraIndex={extraIndex}
            extra={extra}
            disabled={disabled}
            onChange={(next) => {
              const list = extras.map((item, i) => (i === extraIndex ? next : item))
              onCheckJudge({ ...(checkJudge ?? {}), extra_questions: list })
            }}
            onRemove={() => {
              const list = extras.filter((_, i) => i !== extraIndex)
              onCheckJudge({
                ...(checkJudge ?? {}),
                extra_questions: list.length ? list : undefined,
              })
            }}
          />
        ))}
      </FieldGroup>
      <div className="flex justify-end">
        <Button
          id={index === 0 ? "btn-add-scoring-question" : `btn-add-scoring-question-${index}`}
          variant="outline"
          size="sm"
          disabled={disabled || total >= MAX_SCORING_QUESTIONS}
          onClick={() => {
            onCheckJudge({
              ...(checkJudge ?? {}),
              extra_questions: [
                ...extras,
                {
                  id: `extra_${extras.length + 1}`,
                  type: "predicate",
                  ask: "",
                  on_fail: "block",
                  pass_if: { gte: 0.8 },
                },
              ],
            })
          }}
        >
          Add a question for this test case
        </Button>
      </div>
    </div>
  )
}

export function PackScoringExtras({
  packJudge,
  disabled,
  onPackJudge,
}: {
  packJudge?: JudgeBlock | null
  disabled?: boolean
  onPackJudge: (next: JudgeBlock | null) => void
}) {
  const extras = packJudge?.extra_questions ?? []
  return (
    <div className="flex flex-col gap-2">
      <p className="text-sm font-medium">Your questions for every test case</p>
      <FieldDescription>
        Optional. The judge asks these about every test case, after the checks above.
      </FieldDescription>
      <Accordion className="gap-1">
      {extras.map((extra, extraIndex) => (
        <AccordionItem key={`pack-${extra.id}-${extraIndex}`} value={`pack-${extraIndex}`} className="border-b-0">
          <AccordionTrigger>{extra.ask.trim() || "New check"}</AccordionTrigger>
          <AccordionContent>
        <ExtraQuestionFields
          index={-1}
          extraIndex={extraIndex}
          extra={extra}
          disabled={disabled}
          onChange={(next) => {
            const list = extras.map((item, i) => (i === extraIndex ? next : item))
            const removed =
              extra.id && next.id !== extra.id
                ? [...(packJudge?.removed_extra_ids ?? []), extra.id]
                : packJudge?.removed_extra_ids
            onPackJudge({
              ...(packJudge ?? {}),
              extra_questions: list,
              removed_extra_ids: removed,
            })
          }}
          onRemove={() => {
            const list = extras.filter((_, i) => i !== extraIndex)
            const removed = extra.id
              ? [...(packJudge?.removed_extra_ids ?? []), extra.id]
              : packJudge?.removed_extra_ids
            onPackJudge(
              list.length || removed?.length
                ? { ...(packJudge ?? {}), extra_questions: list, removed_extra_ids: removed }
                : null
            )
          }}
        />
          </AccordionContent>
        </AccordionItem>
      ))}
      </Accordion>
      <div className="flex justify-end">
        <Button
          id="btn-add-pack-scoring-question"
          variant="outline"
          size="sm"
          disabled={disabled || totalQuestionCount(packJudge, null) >= MAX_SCORING_QUESTIONS}
          onClick={() => {
            onPackJudge({
              ...(packJudge ?? {}),
              extra_questions: [
                ...extras,
                {
                  id: `pack_extra_${extras.length + 1}`,
                  type: "predicate",
                  ask: "",
                  on_fail: "block",
                  pass_if: { gte: 0.8 },
                },
              ],
            })
          }}
        >
          Add a question for every test case
        </Button>
      </div>
    </div>
  )
}

function CustomPrompt({
  extra,
  extraIndex,
  disabled,
  onChange,
}: {
  extra: ExtraQuestion
  extraIndex: number
  disabled?: boolean
  onChange: (next: ExtraQuestion) => void
}) {
  const [prompt, setPrompt] = useState(extra.ask)

  useEffect(() => {
    if (!extra.id.trim() || !extra.ask.trim()) {
      setPrompt(extra.ask)
      return
    }
    let live = true
    const handle = window.setTimeout(() => {
      void api
        .previewJudgeCheck(extra)
        .then((row) => {
          if (live) {
            setPrompt(row.prompt)
          }
        })
        .catch(() => {
          if (live) {
            setPrompt(extra.ask)
          }
        })
    }, 200)
    return () => {
      live = false
      window.clearTimeout(handle)
    }
  }, [extra])

  return (
    <Textarea
      id={`check-prompt-${extra.id || extraIndex}`}
      readOnly={false}
      disabled={disabled}
      value={prompt}
      spellCheck={false}
      rows={Math.min(12, Math.max(3, prompt.split("\n").length))}
      aria-label="Judge prompt"
      className="font-mono text-xs"
      onChange={(event) => {
        const next = event.target.value
        setPrompt(next)
        if (extra.type !== "choice" && extra.type !== "score") {
          onChange({ ...extra, ask: next })
          return
        }
        const [first, ...rest] = next.split("\n")
        if (extra.type === "score") {
          const levelLine = rest.find((line) => line.startsWith("Levels: "))
          const levels = levelLine
            ? levelLine
                .replace(/^Levels:\s*/, "")
                .split(",")
                .map((item) => item.trim())
                .filter(Boolean)
            : extra.levels
          onChange({ ...extra, ask: first.trim(), levels })
          return
        }
        const choices = rest
          .map((line) => {
            const splitAt = line.indexOf(": ")
            if (splitAt === -1) {
              const value = line.trim()
              return value ? { value, pass: false } : null
            }
            return {
              value: line.slice(0, splitAt).trim(),
              description: line.slice(splitAt + 2).trim(),
              pass: false,
            }
          })
          .filter((row): row is { value: string; description?: string; pass: boolean } =>
            Boolean(row && row.value)
          )
        onChange({
          ...extra,
          ask: first.trim(),
          choices: choices.length
            ? choices.map((row, index) => ({
                ...row,
                pass: extra.choices?.[index]?.pass ?? index === 0,
              }))
            : extra.choices,
        })
      }}
    />
  )
}

function ExtraQuestionFields({
  index,
  extraIndex,
  extra,
  disabled,
  onChange,
  onRemove,
}: {
  index: number
  extraIndex: number
  extra: ExtraQuestion
  disabled?: boolean
  onChange: (next: ExtraQuestion) => void
  onRemove: () => void
}) {
  return (
    <div className="flex flex-col gap-2 rounded-lg border p-3">
      <Field data-disabled={disabled || undefined}>
        <FieldLabel htmlFor={`check-prompt-${extra.id || extraIndex}`}>Prompt</FieldLabel>
        <CustomPrompt
          extra={extra}
          extraIndex={extraIndex}
          disabled={disabled}
          onChange={onChange}
        />
      </Field>
      <Field data-disabled={disabled || undefined}>
        <FieldLabel htmlFor={`extra-id-${index}-${extraIndex}`}>Short name</FieldLabel>
        <Input
          id={`extra-id-${index}-${extraIndex}`}
          value={extra.id}
          disabled={disabled}
          onChange={(event) => onChange({ ...extra, id: event.target.value })}
        />
      </Field>
      <Field data-disabled={disabled || undefined}>
        <FieldLabel htmlFor={`extra-type-${index}-${extraIndex}`}>Type</FieldLabel>
        <Select
          items={TYPE_ITEMS}
          value={extra.type}
          disabled={disabled}
          onValueChange={(next) => {
            if (next === "predicate" || next === "choice" || next === "score") {
              const nextExtra: ExtraQuestion = { ...extra, type: next }
              if (next === "choice" && (!extra.choices || extra.choices.length < 2)) {
                nextExtra.choices = [
                  { value: "yes", pass: true },
                  { value: "no", pass: false },
                ]
              }
              onChange(nextExtra)
            }
          }}
        >
          <SelectTrigger id={`extra-type-${index}-${extraIndex}`} className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              {TYPE_ITEMS.map((item) => (
                <SelectItem key={item.value} value={item.value}>
                  {item.label}
                </SelectItem>
              ))}
            </SelectGroup>
          </SelectContent>
        </Select>
      </Field>
      <ToggleGroup
        value={[extra.on_fail ?? "block"]}
        disabled={disabled}
        size="sm"
        onValueChange={(next) => {
          const picked = Array.isArray(next) ? next[0] : next
          if (picked === "block" || picked === "warn") {
            onChange({ ...extra, on_fail: picked })
          }
        }}
      >
        <ToggleGroupItem value="block">Fail the check</ToggleGroupItem>
        <ToggleGroupItem value="warn">Warn only</ToggleGroupItem>
      </ToggleGroup>
      {extra.type === "choice" ? (
        <Field data-disabled={disabled || undefined}>
          <FieldLabel htmlFor={`extra-choices-${index}-${extraIndex}`}>
            Choices (one per line)
          </FieldLabel>
          <Textarea
            id={`extra-choices-${index}-${extraIndex}`}
            disabled={disabled}
            value={(extra.choices ?? []).map((row) => row.value).join("\n")}
            onChange={(event) => {
              const values = event.target.value
                .split("\n")
                .map((item) => item.trim())
                .filter(Boolean)
              onChange({
                ...extra,
                choices: values.map((value, choiceIndex) => ({
                  value,
                  pass: choiceIndex === 0,
                })),
              })
            }}
          />
        </Field>
      ) : null}
      <div className="flex justify-end">
        <Button variant="ghost" size="xs" disabled={disabled} onClick={onRemove}>
          Remove
        </Button>
      </div>
    </div>
  )
}
