export function agentRunName(pref: string, resolvedHarness?: string): string {
  const key = pref === "auto" ? resolvedHarness || "" : pref
  if (key === "cursor-agent") {
    return "Cursor"
  }
  if (key === "codex") {
    return "Codex"
  }
  if (key === "claude") {
    return "Claude Code"
  }
  return "an agent"
}

export function runButtonLabel(
  count: number,
  agentName: string,
  running?: { done: number; total: number } | null
): string {
  if (running) {
    return `${running.done}/${running.total} done`
  }
  const noun = count === 1 ? "case" : "cases"
  return `Run ${count} ${noun} on ${agentName}`
}
