import type {
  AnalyticsPayload,
  AuthMePayload,
  Check,
  DatasetView,
  DeployAttempt,
  DeployTarget,
  FixtureBindResponse,
  GenerateResponse,
  SkillUpdatesPayload,
  HistoryPayload,
  PackPreview,
  PromoteDraft,
  RunControlResponse,
  RunRecord,
  SettingsKeyId,
  SettingsKeysPayload,
  SkillDetailPayload,
  SkillPayload,
  StatusPayload,
  TaskResult,
  CatalogError,
} from "@/lib/types"

import type { EvalRunConfig } from "@/lib/eval-config"

export class ApiError extends Error {
  hint?: string
  runId?: string
  config?: EvalRunConfig | null
  model?: string | null
  timeout_sec?: number | null
  temperature?: number | null
  reasoning_effort?: string | null
  harness?: string | null
  status?: number

  constructor(
    message: string,
    hint?: string,
    extra?: {
      runId?: string
      config?: EvalRunConfig | null
      model?: string | null
      timeout_sec?: number | null
      temperature?: number | null
      reasoning_effort?: string | null
      harness?: string | null
      status?: number
    }
  ) {
    super(message)
    this.name = "ApiError"
    this.hint = hint
    this.runId = extra?.runId
    this.config = extra?.config
    this.model = extra?.model
    this.timeout_sec = extra?.timeout_sec
    this.temperature = extra?.temperature
    this.reasoning_effort = extra?.reasoning_effort
    this.harness = extra?.harness
    this.status = extra?.status
  }
}

function asOptionalString(value: unknown): string | undefined {
  return typeof value === "string" && value ? value : undefined
}

function asOptionalNumber(value: unknown): number | null | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined
}

function detailFromBody(data: unknown): {
  message: string
  hint?: string
  runId?: string
  config?: EvalRunConfig | null
  model?: string | null
  timeout_sec?: number | null
  temperature?: number | null
  reasoning_effort?: string | null
  harness?: string | null
} {
  if (!data || typeof data !== "object") {
    return { message: "Something went wrong." }
  }
  const detail = (data as { detail?: unknown }).detail
  if (typeof detail === "string") {
    return { message: detail }
  }
  if (detail && typeof detail === "object") {
    const record = detail as {
      message?: unknown
      hint?: unknown
      run_id?: unknown
      config?: unknown
      model?: unknown
      timeout_sec?: unknown
      temperature?: unknown
      reasoning_effort?: unknown
      harness?: unknown
    }
    return {
      message:
        typeof record.message === "string"
          ? record.message
          : "Something went wrong.",
      hint: asOptionalString(record.hint),
      runId: asOptionalString(record.run_id),
      config:
        record.config && typeof record.config === "object"
          ? (record.config as EvalRunConfig)
          : undefined,
      model: asOptionalString(record.model) ?? null,
      timeout_sec: asOptionalNumber(record.timeout_sec) ?? null,
      temperature: asOptionalNumber(record.temperature) ?? null,
      reasoning_effort: asOptionalString(record.reasoning_effort) ?? null,
      harness: asOptionalString(record.harness),
    }
  }
  return { message: "Something went wrong." }
}

async function parseError(res: Response): Promise<ApiError> {
  const data: unknown = await res.json().catch(() => ({}))
  const parsed = detailFromBody(data)
  return new ApiError(parsed.message, parsed.hint, {
    runId: parsed.runId,
    config: parsed.config,
    model: parsed.model,
    timeout_sec: parsed.timeout_sec,
    temperature: parsed.temperature,
    reasoning_effort: parsed.reasoning_effort,
    harness: parsed.harness,
    status: res.status,
  })
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init)
  if (!res.ok) {
    throw await parseError(res)
  }
  return (await res.json()) as T
}

const jsonHeaders = { "Content-Type": "application/json" }

function packSkillName(skill: string): string {
  const parts = skill.replace(/\\/g, "/").split("/").filter(Boolean)
  if (parts.length === 0) {
    return skill
  }
  const last = parts[parts.length - 1]
  if (last.toLowerCase() === "skill.md" && parts.length >= 2) {
    return parts[parts.length - 2]
  }
  return last
}

export const api = {
  status: () => request<StatusPayload>("/api/status"),
  settingsKeys: () => request<SettingsKeysPayload>("/api/settings/keys"),
  setSettingsKey: (name: SettingsKeyId, value: string) =>
    request<SettingsKeysPayload>(`/api/settings/keys/${encodeURIComponent(name)}`, {
      method: "PUT",
      headers: jsonHeaders,
      body: JSON.stringify({ value }),
    }),
  clearSettingsKey: (name: SettingsKeyId) =>
    request<SettingsKeysPayload>(`/api/settings/keys/${encodeURIComponent(name)}`, {
      method: "DELETE",
    }),
  settingsJudge: () =>
    request<{
      judge: {
        provider: string
        chosen: boolean
        region: string | null
        model: string | null
        base_url: string | null
      }
    }>("/api/settings/judge"),
  setSettingsJudge: (body: {
    provider: string
    region?: string | null
    model?: string | null
    base_url?: string | null
  }) =>
    request<{
      judge: {
        provider: string
        chosen: boolean
        region: string | null
        model: string | null
        base_url: string | null
      }
    }>("/api/settings/judge", {
      method: "PUT",
      headers: jsonHeaders,
      body: JSON.stringify(body),
    }),
  pingJudge: () =>
    request<{ ok: boolean; message: string }>("/api/judge/ping", {
      method: "POST",
      headers: jsonHeaders,
      body: "{}",
    }),
  me: () => request<AuthMePayload>("/api/auth/me"),
  signOut: () =>
    request<Record<string, never>>("/api/auth/signout", {
      method: "POST",
      headers: jsonHeaders,
      body: "{}",
    }),
  skills: () =>
    request<{ skills: SkillPayload[]; catalog_error?: CatalogError | null }>(
      "/api/skills"
    ),
  importSources: () =>
    request<{
      sources: Array<{
        id: string
        label: string
        found: boolean
        count: number
        folder_label: string
      }>
    }>("/api/skills/import-sources"),
  importSkills: (sources?: string[]) =>
    request<{
      skills: SkillPayload[]
      imported: Array<{
        name: string
        source: string
        slug?: string
        warning?: string | null
      }>
      skipped: Array<{ name: string; source: string; reason?: string }>
      sources?: Array<{
        id: string
        label: string
        found: boolean
        count: number
        folder_label: string
      }>
      catalog_error?: CatalogError | null
    }>("/api/skills/import", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify(sources ? { sources } : {}),
    }),
  skill: (name: string) =>
    request<SkillDetailPayload>(`/api/skills/${encodeURIComponent(packSkillName(name))}`),
  packPreview: (name: string, path: string) =>
    request<PackPreview>(
      `/api/skills/${encodeURIComponent(packSkillName(name))}/pack-file?path=${encodeURIComponent(path)}`
    ),
  packRawUrl: (name: string, path: string) =>
    `/api/skills/${encodeURIComponent(packSkillName(name))}/pack-raw?path=${encodeURIComponent(path)}`,
  packFile: (payload: {
    skill: string
    generate?: boolean
    filename?: string
    path?: string
    content?: string
    prompt?: string
  }) =>
    request<{
      skill: SkillPayload
      file: { src: string; dest: string; path: string } | null
      needs_upload?: boolean
      message?: string
    }>(
      "/api/skills/pack-file",
      {
        method: "POST",
        headers: jsonHeaders,
        body: JSON.stringify(payload),
      }
    ),
  packUpload: async (skill: string, file: File, path?: string) => {
    const body = new FormData()
    body.append("skill", skill)
    body.append("file", file)
    if (path) {
      body.append("path", path)
    }
    const res = await fetch("/api/skills/pack-upload", { method: "POST", body })
    if (!res.ok) {
      throw await parseError(res)
    }
    return (await res.json()) as {
      skill: SkillPayload
      file: { src: string; dest: string; path: string }
    }
  },
  history: (skill?: string | null) => {
    const query = skill ? `?skill=${encodeURIComponent(skill)}` : ""
    return request<HistoryPayload>(`/api/history${query}`)
  },
  analytics: (skill?: string | null) => {
    const query = skill ? `?skill=${encodeURIComponent(skill)}` : ""
    return request<AnalyticsPayload>(`/api/analytics${query}`)
  },
  paste: (markdown: string) =>
    request<SkillPayload>("/api/skills/paste", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ markdown }),
    }),
  upload: async (file: File) => {
    const body = new FormData()
    body.append("file", file)
    const res = await fetch("/api/skills/upload", { method: "POST", body })
    if (!res.ok) {
      throw await parseError(res)
    }
    return (await res.json()) as SkillPayload
  },
  generate: (skill: string, yaml?: string, opts?: { forceSeed?: boolean }) =>
    request<GenerateResponse>("/api/evals/generate", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({
        skill,
        ...(yaml && yaml.trim() ? { yaml } : {}),
        force_seed: Boolean(opts?.forceSeed),
      }),
    }),
  pinChecks: (payload: {
    skill: string
    checks?: Check[]
    case_ids?: string[]
    pack_judge?: Check["judge"]
  }) =>
    request<{
      pack: unknown
      fingerprint: string
      checks: Check[]
      yaml: string
      skill?: SkillPayload
      pack_judge?: Check["judge"]
    }>("/api/evals/pin", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify(payload),
    }),
  pinBaseline: (payload: {
    skill: string
    run_id?: string | null
    follow_deploy?: boolean
  }) =>
    request<{
      skill: string
      baseline: {
        run_id: string
        source: "deploy" | "manual"
        pack_fingerprint?: string | null
        suite?: string | null
        pinned_at?: string | null
        resolved?: boolean
      }
    }>("/api/evals/baseline", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify(payload),
    }),
  dataset: (skill: string) =>
    request<DatasetView>(
      `/api/evals/dataset?skill=${encodeURIComponent(skill)}`
    ),
  fixtureBind: (payload: {
    skill: string
    checks: Check[]
    action?: "inherit" | "expand"
    inherit?: boolean
    glob?: string | null
  }) =>
    request<FixtureBindResponse>("/api/evals/fixture-bind", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify(payload),
    }),
  promoteDraft: (task: TaskResult, checks?: Check[], skill?: string | null) =>
    request<PromoteDraft>("/api/evals/promote-draft", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({
        task,
        checks: checks ?? [],
        skill: skill || undefined,
      }),
    }),
  applyFix: (payload: {
    skill: string
    paste: string
    restore_scripts_from?: string | null
  }) =>
    request<SkillPayload>("/api/skills/apply-fix", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify(payload),
    }),
  suggestSkillUpdates: (runId: string) =>
    request<SkillUpdatesPayload>("/api/evals/suggest-skill-updates", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ run_id: runId }),
    }),
  startRun: (payload: {
    suite?: string | null
    skill?: string | null
    checks?: Check[] | null
    demo?: boolean
    live?: boolean
    harness?: "auto" | "cursor-agent" | "codex" | "claude"
    config?: {
      model?: string | null
      timeout_sec?: number | null
      temperature?: number | null
      reasoning_effort?: string | null
    }
    fixture_bind?: {
      inherit?: boolean
      glob?: string | null
    }
    tryout?: boolean
  }) =>
    request<{ id: string; status: string }>("/api/runs", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify(payload),
    }),
  getRun: (id: string) => request<RunRecord>(`/api/runs/${id}`),
  skipRun: (id: string) =>
    request<RunControlResponse>(`/api/runs/${encodeURIComponent(id)}/skip`, {
      method: "POST",
      headers: jsonHeaders,
      body: "{}",
    }),
  killRun: (id: string) =>
    request<RunControlResponse>(`/api/runs/${encodeURIComponent(id)}/kill`, {
      method: "POST",
      headers: jsonHeaders,
      body: "{}",
    }),
  deploy: (
    target: DeployTarget | "git",
    skill: string,
    mode: "local" | "git" = "local"
  ) =>
    request<{
      status: string
      note: string
      live: boolean
      mode?: string
      skill: string
      dest?: string | null
      url?: string | null
      branch?: string | null
      pr_url?: string | null
      attempt?: DeployAttempt
    }>(
      "/api/deploy",
      {
        method: "POST",
        headers: jsonHeaders,
        body: JSON.stringify({ target, skill, mode }),
      }
    ),
}

/** WebKit "Load failed", Chromium "Failed to fetch", AbortError, etc. */
export function isTransientFetchError(err: unknown): boolean {
  if (err instanceof ApiError) {
    return false
  }
  if (err instanceof DOMException && err.name === "AbortError") {
    return true
  }
  if (!(err instanceof Error)) {
    return false
  }
  const msg = err.message || ""
  if (
    msg === "Load failed" ||
    msg === "Failed to fetch" ||
    msg === "NetworkError when attempting to fetch resource." ||
    msg.includes("network") ||
    msg.includes("NetworkError") ||
    err.name === "TypeError"
  ) {
    return true
  }
  return false
}

export type PollRunOptions = {
  onProgress?: (snapshot: RunRecord) => void
  onConnectionLost?: () => void
  onConnectionRestored?: () => void
  /** Abort/stop the poll loop (e.g. unmount). */
  signal?: AbortSignal
}

export async function pollRun(
  id: string,
  onProgressOrOpts?: ((snapshot: RunRecord) => void) | PollRunOptions
): Promise<RunRecord> {
  const opts: PollRunOptions =
    typeof onProgressOrOpts === "function"
      ? { onProgress: onProgressOrOpts }
      : onProgressOrOpts || {}
  let delayMs = 280
  let lost = false
  let consecutiveFailures = 0
  for (;;) {
    if (opts.signal?.aborted) {
      throw new DOMException("Aborted", "AbortError")
    }
    try {
      const data = await api.getRun(id)
      if (lost) {
        lost = false
        consecutiveFailures = 0
        delayMs = 280
        opts.onConnectionRestored?.()
      }
      opts.onProgress?.(data)
      if (data.status !== "running") {
        return data
      }
      await new Promise((resolve) => setTimeout(resolve, 280))
      delayMs = 280
      consecutiveFailures = 0
    } catch (err) {
      if (!isTransientFetchError(err)) {
        throw err
      }
      consecutiveFailures += 1
      if (!lost) {
        lost = true
        opts.onConnectionLost?.()
      }
      // Cap backoff ~5s; keep trying forever while the tab is interested.
      delayMs = Math.min(5000, 400 * 2 ** Math.min(consecutiveFailures - 1, 4))
      await new Promise((resolve) => setTimeout(resolve, delayMs))
    }
  }
}
