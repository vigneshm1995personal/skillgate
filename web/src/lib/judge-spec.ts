export const BUILTIN_QUESTIONS = [
  { id: "task_completion", ask: "Got the job done?", defaultOnFail: "block" },
  { id: "correctness", ask: "Got it right?", defaultOnFail: "block" },
  { id: "instruction_adherence", ask: "Followed the rules?", defaultOnFail: "block" },
  {
    id: "evidence_action_validity",
    ask: "Used the right evidence/actions?",
    defaultOnFail: "block",
  },
  { id: "result_quality", ask: "Delivered a good result?", defaultOnFail: "block" },
  { id: "path_efficiency", ask: "Path", defaultOnFail: "warn" },
] as const

export const MAX_SCORING_QUESTIONS = 20

export type ExtraQuestion = {
  id: string
  type: "predicate" | "choice" | "score"
  ask: string
  on_fail?: "block" | "warn"
  choices?: Array<{ value: string; description?: string; pass?: boolean }>
  levels?: string[]
  pass_if?: { gte?: number }
}

export type JudgeBlock = {
  min_confidence?: number | null
  on_fail?: Record<string, "block" | "warn">
  extra_questions?: ExtraQuestion[]
  score_no_trigger?: boolean
}

export function totalQuestionCount(pack?: JudgeBlock | null, check?: JudgeBlock | null): number {
  const extras =
    (pack?.extra_questions?.length ?? 0) + (check?.extra_questions?.length ?? 0)
  return BUILTIN_QUESTIONS.length + extras
}
