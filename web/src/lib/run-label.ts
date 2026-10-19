import { agentLabel } from "@/lib/agent-label"

const AGENT_NAMES: Record<string, string> = {
  "cursor-agent": agentLabel("cursor-agent"),
  codex: agentLabel("codex"),
  claude: agentLabel("claude"),
}

export function runButtonTotal(opts: {
  running: boolean
  taskCount: number
  checks: { bank_status?: string | null }[]
}): number {
  if (opts.running) {
    return opts.taskCount
  }
  return opts.checks.filter((check) => check.bank_status === "pinned").length
}

export function runButtonLabel(opts: {
  running: boolean
  completed: number
  total: number
  agent: string
}): string {
  const name = AGENT_NAMES[opts.agent] || ""
  const onAgent = name ? ` on ${name}` : ""
  if (opts.running) {
    return `${opts.completed} of ${opts.total} done${onAgent}`
  }
  if (opts.total === 0) {
    return name ? `Run on ${name}` : "Run"
  }
  const cases = opts.total === 1 ? "1 case" : `${opts.total} cases`
  return `Run ${cases}${onAgent}`
}
