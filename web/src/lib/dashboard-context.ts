import type { EvalConfigDraft } from "@/lib/eval-config"
import type {
  Advice,
  AnalyticsPayload,
  CatalogError,
  Check,
  DeployTarget,
  EvalTab,
  HarnessPref,
  HistoryPayload,
  RunRecord,
  SkillPayload,
  SkillUpdatesPayload,
  Stage,
  StatusPayload,
  TimelineItem,
} from "@/lib/types"

export type DashboardContextValue = {
  stage: Stage
  setStage: (stage: Stage) => void
  evalTab: EvalTab
  setEvalTab: (tab: EvalTab) => void
  repoSkill: string | null
  setRepoSkill: (name: string | null) => void
  historyOpen: boolean
  setHistoryOpen: (open: boolean) => void
  searchQuery: string
  setSearchQuery: (value: string) => void
  paste: string
  setPaste: (value: string) => void
  skill: SkillPayload | null
  skills: SkillPayload[]
  checks: Check[]
  yaml: string
  running: boolean
  connectionLost: boolean
  seeding: boolean
  seedingAssist: boolean
  checksSeeded: boolean
  checksSource:
    | "model"
    | "heuristic"
    | "template"
    | "suite"
    | "yaml"
    | "pack"
    | "assist"
    | "empty"
    | null
  checksNote: string
  checksWarning: string
  intakeError: string
  catalogError: CatalogError | null
  lastResult: RunRecord | null
  liveGateResult: RunRecord | null
  tryoutResult: RunRecord | null
  lastAdvice: Advice | null
  history: HistoryPayload | null
  skillHistory: HistoryPayload | null
  analytics: AnalyticsPayload | null
  status: StatusPayload | null
  copiedFix: boolean
  deployLast: string | null
  deployAllowed: boolean
  suggestBusy: boolean
  suggestError: { message: string; hint?: string } | null
  suggestByRunId: Record<string, SkillUpdatesPayload>
  requestSkillUpdates: (opts?: { force?: boolean }) => Promise<void>
  copySkillUpdates: () => Promise<void>
  refreshSkills: () => Promise<SkillPayload[]>
  refreshAnalytics: () => Promise<AnalyticsPayload | null>
  refreshStatus: () => Promise<StatusPayload | null>
  selectSkill: (
    skillId: string,
    opts?: { tab?: EvalTab; fallbackSkill?: SkillPayload; forceSeed?: boolean }
  ) => Promise<void>
  pinShownChecks: () => Promise<void>
  pinCheckAt: (index: number) => Promise<void>
  pinDatasetChecks: (checks: Check[], pinSkillId?: string) => Promise<boolean>
  pinBaseline: (opts: {
    skill: string
    run_id?: string | null
    follow_deploy?: boolean
  }) => Promise<boolean>
  openHistoryRun: (item: TimelineItem) => Promise<void>
  openRepository: (name?: string | null) => void
  pasteSkill: () => Promise<void>
  uploadZip: (file: File) => Promise<void>
  addCheck: (draft?: Partial<Check>) => void
  updateCheck: (index: number, patch: Partial<Check>) => void
  removeCheck: (index: number) => void
  packJudge: Check["judge"]
  setPackJudge: (next: Check["judge"]) => void
  applySkill: (next: SkillPayload) => void
  importYaml: (text: string) => Promise<void>
  startEvaluations: () => Promise<void>
  runThisCheck: (check: Check) => Promise<void>
  fixtureInherit: boolean
  fixtureGlob: string
  setFixtureInherit: (next: boolean) => void
  setFixtureGlob: (next: string) => void
  bindPackFixtures: (inherit: boolean) => Promise<Check[] | void>
  expandPackFixtures: () => Promise<void>
  runAfterPossiblePaste: () => Promise<void>
  copyFix: () => Promise<void>
  installTo: (target: DeployTarget) => Promise<void>
  publishToGit: () => Promise<void>
  harnessPref: HarnessPref
  setHarnessPref: (value: HarnessPref) => void
  resolvedHarness: string
  evalConfig: EvalConfigDraft
  setEvalConfig: (value: EvalConfigDraft) => void
  viewingPinnedHistory: boolean
  gateRunning: boolean
  tryoutRunning: boolean
}
