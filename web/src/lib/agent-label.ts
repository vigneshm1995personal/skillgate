/** Display names for agent ids. Ids stay; these words do not name a vendor. */
export const AGENT_LABELS: Record<string, string> = {
  cursor: "Editor agent",
  "cursor-agent": "Editor agent",
  codex: "Terminal agent",
  claude: "Code agent",
  "claude-code": "Code agent",
}

export function agentLabel(kind?: string | null): string {
  const key = (kind || "").trim().toLowerCase()
  return AGENT_LABELS[key] || "Agent"
}

/** Rewrite stored harness words in a label. Patterns stay out of rendered text. */
export function scrubAgentNames(label: string): string {
  return label
    .replace(/\bcursor-agent\b/gi, AGENT_LABELS["cursor-agent"])
    .replace(/\bclaude-code\b/gi, AGENT_LABELS.claude)
    .replace(/\bClaude Code\b/g, AGENT_LABELS.claude)
    .replace(/\bCursor\b/g, AGENT_LABELS.cursor)
    .replace(/\bCodex\b/g, AGENT_LABELS.codex)
    .replace(/\bClaude\b/g, AGENT_LABELS.claude)
    .replace(/\bcursor\b/g, AGENT_LABELS.cursor)
    .replace(/\bcodex\b/g, AGENT_LABELS.codex)
    .replace(/\bclaude\b/g, AGENT_LABELS.claude)
}
