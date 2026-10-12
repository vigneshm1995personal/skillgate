export type CompareArm = {
  arm_id: string
  label?: string
  subtitle?: string
  passed_count?: number
  task_count?: number
  usage?: { tokens_total?: number | null; cost_usd?: number | null }
  duration_sec?: number | null
  run_id?: string
}

export type CompareCase = {
  case_id: string
  disagreement?: boolean
  results?: Record<
    string,
    { passed?: boolean | null; usage?: { tokens_total?: number | null } }
  >
}

export type ComparePayload = {
  compare_id?: string
  mode?: string
  status?: string
  skill?: string
  arms?: CompareArm[]
  cases?: CompareCase[]
  spend?: { stopped_reason?: string | null }
  error?: { message?: string; hint?: string }
}

export function disagreementCount(cases: CompareCase[] | undefined): number {
  return (cases ?? []).filter((row) => row.disagreement).length
}

export function passLabel(passed: boolean | null | undefined): string {
  if (passed === true) {
    return "Pass"
  }
  if (passed === false) {
    return "Fail"
  }
  return "—"
}

export function armChecksLine(arm: CompareArm): string {
  if (arm.passed_count == null || arm.task_count == null) {
    return "—"
  }
  return `${arm.passed_count}/${arm.task_count} Pass`
}
