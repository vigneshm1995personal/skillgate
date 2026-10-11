import { Button } from "@/components/ui/button"
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import {
  BUILTIN_QUESTIONS,
  MAX_SCORING_QUESTIONS,
  totalQuestionCount,
  type ExtraQuestion,
  type JudgeBlock,
} from "@/lib/judge-spec"

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
      <p className="text-xs font-medium text-muted-foreground">Scoring questions</p>
      <FieldDescription>
        Skill Gate always asks the first six. Yours run in the same scoring request.
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
          Add scoring question
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
      <p className="text-xs font-medium text-muted-foreground">Skill-wide extras</p>
      <FieldDescription>
        These questions run on every check in this skill, after Skill Gate’s six.
      </FieldDescription>
      {extras.map((extra, extraIndex) => (
        <ExtraQuestionFields
          key={`pack-${extra.id}-${extraIndex}`}
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
      ))}
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
          Add skill-wide question
        </Button>
      </div>
    </div>
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
        <FieldLabel htmlFor={`extra-ask-${index}-${extraIndex}`}>Ask</FieldLabel>
        <Input
          id={`extra-ask-${index}-${extraIndex}`}
          value={extra.ask}
          disabled={disabled}
          onChange={(event) => onChange({ ...extra, ask: event.target.value })}
        />
      </Field>
      <Field data-disabled={disabled || undefined}>
        <FieldLabel htmlFor={`extra-id-${index}-${extraIndex}`}>Id</FieldLabel>
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
              onChange({ ...extra, type: next })
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
      <div className="flex justify-end">
        <Button variant="ghost" size="xs" disabled={disabled} onClick={onRemove}>
          Remove
        </Button>
      </div>
    </div>
  )
}
