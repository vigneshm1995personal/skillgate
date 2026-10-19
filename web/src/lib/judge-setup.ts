/** Decision-model fields. Labels and model lists come from the API. */

export const DECISION_ONE_LINE =
  "A decision model scores each live check, and one is required."

export type DecisionJudge = {
  id: string
  label: string
  detail: string
  fields?: string[]
  advanced?: string[]
  models?: string[]
  model_free?: boolean
  defaults?: Record<string, string>
  key_name?: string | null
  key_label?: string
}

export type JudgeDraft = {
  baseUrl: string
  model: string
  accountId: string
}

const NOT_SELECTED = "auto"

export function showsField(option: DecisionJudge | undefined, name: string): boolean {
  return Boolean(option?.fields?.includes(name))
}

export function judgeSaveBody(
  option: DecisionJudge | undefined,
  provider: string,
  draft: JudgeDraft
): {
  provider: string
  base_url: string | null
  model: string | null
  account_id: string | null
  region: null
} {
  const chosen = provider !== "" && provider !== NOT_SELECTED
  const fields = new Set(chosen ? (option?.fields ?? []) : [])
  return {
    provider: provider || NOT_SELECTED,
    base_url: fields.has("base_url") ? draft.baseUrl.trim() || null : null,
    model: fields.has("model") ? draft.model.trim() || null : null,
    account_id: fields.has("account_id") ? draft.accountId.trim() || null : null,
    region: null,
  }
}

export function switchSaveBody(
  judges: DecisionJudge[],
  next: string,
  savedProvider: string,
  saved: JudgeDraft
) {
  const option = judges.find((row) => row.id === next)
  return judgeSaveBody(option, next, draftForSelection(option, savedProvider, saved, next))
}

export function draftForSelection(
  option: DecisionJudge | undefined,
  savedProvider: string,
  saved: JudgeDraft,
  next: string
): JudgeDraft {
  if (!option || next === NOT_SELECTED || next === "") {
    return { baseUrl: "", model: "", accountId: "" }
  }
  const defaults = option.defaults ?? {}
  if (savedProvider === next) {
    return {
      baseUrl: saved.baseUrl || defaults.base_url || "",
      model: saved.model || defaults.model || option.models?.[0] || "",
      accountId: saved.accountId,
    }
  }
  return {
    baseUrl: defaults.base_url || "",
    model: defaults.model || option.models?.[0] || "",
    accountId: "",
  }
}

/** Prefixes that belong to one option. Anything else is not guessed. */
export function keyOwner(secret: string): string | null {
  const token = secret.trim()
  if (token.startsWith("sk-or-")) {
    return "jev"
  }
  if (token.startsWith("sk-")) {
    return "openai"
  }
  return null
}

export function mismatchCopy(
  provider: string,
  secret: string,
  judges: DecisionJudge[]
): { message: string; switchTo: string } | null {
  const owner = keyOwner(secret)
  if (!owner || owner === provider || provider === "custom" || provider === NOT_SELECTED) {
    return null
  }
  const label = judges.find((row) => row.id === owner)?.label
  if (!label) {
    return null
  }
  return {
    switchTo: owner,
    message:
      `This looks like an ${label} key. ` +
      `Switch to ${label} with \`skillgate judge provider set ${owner}\`.`,
  }
}
