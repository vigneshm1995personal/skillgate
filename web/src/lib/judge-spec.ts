export const BUILTIN_QUESTIONS = [
  {
    id: "task_completion",
    ask: "Did it finish the task?",
    explain: "The agent completed what the test case asked for.",
    defaultOnFail: "block",
  },
  {
    id: "correctness",
    ask: "Is the answer right?",
    explain: "The result matches what this test case expected.",
    defaultOnFail: "block",
  },
  {
    id: "instruction_adherence",
    ask: "Did it follow the skill?",
    explain: "It stayed inside the instructions in this skill.",
    defaultOnFail: "block",
  },
  {
    id: "evidence_action_validity",
    ask: "Did it use the right inputs?",
    explain: "It used the files and actions this test case allows.",
    defaultOnFail: "block",
  },
  {
    id: "result_quality",
    ask: "Is the result usable?",
    explain: "The output is something you could keep, not just a file that exists.",
    defaultOnFail: "block",
  },
  {
    id: "path_efficiency",
    ask: "Did it take a direct path?",
    explain: "A miss here warns you. It does not fail the test case by itself.",
    defaultOnFail: "warn",
  },
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
  removed_extra_ids?: string[]
}

export function duplicateExtraIds(extras: ExtraQuestion[] | undefined): string[] {
  const seen = new Set<string>()
  const dupes: string[] = []
  for (const extra of extras ?? []) {
    const id = (extra.id || "").trim()
    if (!id) {
      continue
    }
    if (seen.has(id)) {
      dupes.push(id)
    }
    seen.add(id)
  }
  return dupes
}

export function totalQuestionCount(pack?: JudgeBlock | null, check?: JudgeBlock | null): number {
  const extras =
    (pack?.extra_questions?.length ?? 0) + (check?.extra_questions?.length ?? 0)
  return BUILTIN_QUESTIONS.length + extras
}
