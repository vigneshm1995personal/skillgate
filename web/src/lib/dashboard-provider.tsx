import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react"

import { toast } from "@/components/ui/toast"
import { api } from "@/lib/api"
import {
  asApiError,
  collectChecksForRun,
  deployLabel,
  isSameSkill,
  shouldSeedChecks,
  uniqueCheckId,
} from "@/lib/dashboard-helpers"
import { authenticFixtureDefaults, resolvedHarnessName, skillOutputPath, startBlockedMessage } from "@/lib/types"
import {
  DEFAULT_EVAL_CONFIG_DRAFT,
  type EvalConfigDraft,
} from "@/lib/eval-config"
import { useEvalSession } from "@/lib/use-eval-session"
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

type DashboardContextValue = {
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

const DashboardContext = createContext<DashboardContextValue | undefined>(
  undefined
)

export function DashboardProvider({ children }: { children: ReactNode }) {
  const [stage, setStage] = useState<Stage>("home")
  const [evalTab, setEvalTab] = useState<EvalTab>("skill")
  const [repoSkill, setRepoSkill] = useState<string | null>(null)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState("")
  const [paste, setPaste] = useState("")
  const [pendingPaste, setPendingPaste] = useState("")
  const [skill, setSkill] = useState<SkillPayload | null>(null)
  const [skills, setSkills] = useState<SkillPayload[]>([])
  const [checks, setChecks] = useState<Check[]>([])
  const [yaml, setYaml] = useState("")
  const [seeding, setSeeding] = useState(false)
  const [seedingAssist, setSeedingAssist] = useState(false)
  const [checksSeeded, setChecksSeeded] = useState(false)
  const [checksSource, setChecksSource] = useState<
    | "model"
    | "heuristic"
    | "template"
    | "suite"
    | "yaml"
    | "pack"
    | "assist"
    | "empty"
    | null
  >(null)
  const [checksNote, setChecksNote] = useState("")
  const [checksWarning, setChecksWarning] = useState("")
  const [intakeError, setIntakeError] = useState("")
  const [catalogError, setCatalogError] = useState<CatalogError | null>(null)
  const seedSeq = useRef(0)
  const checksRef = useRef(checks)
  const skillRef = useRef(skill)
  checksRef.current = checks
  skillRef.current = skill
  const [history, setHistory] = useState<HistoryPayload | null>(null)
  const [skillHistory, setSkillHistory] = useState<HistoryPayload | null>(null)
  const [analytics, setAnalytics] = useState<AnalyticsPayload | null>(null)
  const [status, setStatus] = useState<StatusPayload | null>(null)
  const [copiedFix, setCopiedFix] = useState(false)
  const [deployLast, setDeployLast] = useState<string | null>(null)
  const [harnessPref, setHarnessPref] = useState<HarnessPref>("auto")
  const [evalConfig, setEvalConfig] = useState<EvalConfigDraft>(DEFAULT_EVAL_CONFIG_DRAFT)
  const [fixtureInherit, setFixtureInherit] = useState(true)
  const [fixtureGlob, setFixtureGlob] = useState("evals/fixtures/*")
  const resolvedHarness = resolvedHarnessName(harnessPref, status)

  const refreshSkills = useCallback(async () => {
    try {
      const data = await api.skills()
      const next = data.skills ?? []
      setSkills(next)
      if (next.length === 0 && data.catalog_error) {
        setCatalogError(data.catalog_error)
      } else if (next.length > 0) {
        setCatalogError(data.catalog_error ?? null)
      } else {
        setCatalogError(null)
      }
      return next
    } catch (err) {
      const error = asApiError(err)
      setSkills([])
      setCatalogError({
        message: error.message || "Could not load skills.",
        hint: error.hint,
      })
      return []
    }
  }, [])

  const refreshWorkspaceHistory = useCallback(async () => {
    try {
      const hist = await api.history()
      setHistory(hist)
      return hist
    } catch {
      return null
    }
  }, [])

  const refreshAnalytics = useCallback(async () => {
    try {
      const data = await api.analytics()
      setAnalytics(data)
      return data
    } catch {
      return null
    }
  }, [])

  const refreshStatus = useCallback(async () => {
    try {
      const next = await api.status()
      setStatus(next)
      return next
    } catch {
      return null
    }
  }, [])

  const refreshSkillHistory = useCallback(async (skillName?: string | null) => {
    const name = skillName?.trim()
    if (!name) {
      setSkillHistory(null)
      setDeployLast(null)
      return null
    }
    try {
      const hist = await api.history(name)
      setSkillHistory(hist)
      setDeployLast(deployLabel(hist.last_deploy?.target))
      return hist
    } catch {
      return null
    }
  }, [])

  const session = useEvalSession({
    skill,
    skills,
    checks,
    evalConfig,
    harnessPref,
    resolvedHarness,
    fixtureInherit,
    fixtureGlob,
    setStage,
    setEvalTab,
    setSkill,
    setCopiedFix,
    setIntakeError,
    setHistoryOpen,
    setPaste,
    setPendingPaste,
    refreshWorkspaceHistory,
    refreshSkillHistory,
    refreshSkills,
    refreshAnalytics,
    status,
  })
  const {
    connectionLost,
    lastResult,
    liveGateResult,
    tryoutResult,
    lastAdvice,
    viewingPinnedHistory,
    running,
    gateRunning,
    tryoutRunning,
    deployAllowed,
    suggestBusy,
    suggestError,
    suggestByRunId,
    applySkillHistory,
    applyResult,
    runNow,
    runThisCheck,
    openHistoryRun,
    pinBaseline,
    copyFix,
    requestSkillUpdates,
    copySkillUpdates,
  } = session

  const collectChecks = useCallback(
    () => collectChecksForRun(checks, skill),
    [checks, skill]
  )

  const selectSkill = useCallback(
    async (
      skillId: string,
      opts: { tab?: EvalTab; fallbackSkill?: SkillPayload; forceSeed?: boolean } = {}
    ) => {
      const targetTab = opts.tab ?? "checks"
      const nextSkill =
        opts.fallbackSkill ||
        skills.find(
          (item) =>
            item.absolute === skillId ||
            item.id === skillId ||
            item.name === skillId
        )
      const sameSkill = isSameSkill(skillRef.current, skillId, opts.fallbackSkill)
      if (!sameSkill) {
        setSkillHistory(null)
      }
      if (
        !shouldSeedChecks({
          forceSeed: opts.forceSeed,
          sameSkill,
          checkCount: checksRef.current.length,
        })
      ) {
        setIntakeError("")
        if (nextSkill) {
          setSkill(nextSkill)
        }
        setStage("eval")
        setEvalTab(targetTab)
        return
      }
      const mySeq = ++seedSeq.current
      setIntakeError("")
      setSeeding(true)
      setSeedingAssist(Boolean(opts.forceSeed))
      setStage("eval")
      setEvalTab(targetTab)
      if (nextSkill) {
        setSkill(nextSkill)
      }
      if (targetTab === "checks") {
        setChecks([])
        setYaml("")
        setChecksSeeded(false)
        setChecksSource(null)
        setChecksNote("")
        setChecksWarning("")
        setFixtureInherit(true)
        setFixtureGlob("evals/fixtures/*")
        setEvalTab("checks")
      }
      try {
        const data = await api.generate(skillId, undefined, {
          forceSeed: opts.forceSeed,
        })
        if (mySeq !== seedSeq.current) {
          return
        }
        setSkill({
          ...data.skill,
          fixture_defaults: data.fixture_defaults ?? data.skill.fixture_defaults,
        })
        setChecks(data.checks)
        setYaml(data.yaml || "")
        setChecksSeeded(data.checks.length > 0)
        setChecksSource(data.source ?? null)
        setChecksNote(data.note || "")
        setChecksWarning(data.warning || "")
        if (data.checks.length === 0) {
          if (opts.forceSeed) {
            setEvalTab("skill")
            setIntakeError(
              "Could not suggest checks for this skill. Add a check or expand the description."
            )
            return
          }
          return
        }
        const hist = await refreshSkillHistory(data.skill.name)
        if (mySeq !== seedSeq.current) {
          return
        }
        applySkillHistory(hist, data.skill.name)
        setStage("eval")
      } catch (err) {
        if (mySeq !== seedSeq.current) {
          return
        }
        const error = asApiError(err)
        setChecks([])
        setYaml("")
        setChecksSeeded(false)
        setChecksSource(null)
        setChecksNote("")
        setChecksWarning("")
        setEvalTab("skill")
        if (nextSkill) {
          setSkill(nextSkill)
          const hist = await refreshSkillHistory(nextSkill.name)
          applySkillHistory(hist, nextSkill.name)
        }
        setIntakeError(
          error.hint ? `${error.message}\n${error.hint}` : error.message
        )
      } finally {
        if (mySeq === seedSeq.current) {
          setSeeding(false)
          setSeedingAssist(false)
        }
      }
    },
    [applySkillHistory, refreshSkillHistory, skills]
  )

  const openRepository = useCallback((name?: string | null) => {
    setRepoSkill(name ?? null)
    setStage("repository")
  }, [])

  const pasteSkill = useCallback(async () => {
    setIntakeError("")
    setSeeding(true)
    setSeedingAssist(false)
    try {
      const data = await api.paste(paste)
      await refreshSkills()
      await selectSkill(data.absolute || data.id, {
        tab: "checks",
        fallbackSkill: data,
      })
    } catch (err) {
      const error = asApiError(err)
      setSeeding(false)
      setSeedingAssist(false)
      setEvalTab("skill")
      setIntakeError(
        error.hint ? `${error.message}\n${error.hint}` : error.message
      )
    }
  }, [paste, refreshSkills, selectSkill])

  const uploadZip = useCallback(
    async (file: File) => {
      setIntakeError("")
      setSeeding(true)
      setSeedingAssist(false)
      try {
        const data = await api.upload(file)
        await refreshSkills()
        await selectSkill(data.absolute || data.id, {
          tab: "checks",
          fallbackSkill: data,
        })
      } catch (err) {
        const error = asApiError(err)
        setSeeding(false)
        setSeedingAssist(false)
        setEvalTab("skill")
        setIntakeError(
          error.hint ? `${error.message}\n${error.hint}` : error.message
        )
      }
    },
    [refreshSkills, selectSkill]
  )

  const addCheck = useCallback((draft?: Partial<Check>) => {
    const contains = (draft?.contains ?? "").trim()
    const outputPath =
      (draft?.output_path ?? "").trim() || (contains ? skillOutputPath(skill) : "")
    setChecks((current) => [
      ...current,
      {
        id: uniqueCheckId(draft?.id || `check-${current.length + 1}`, current),
        prompt: draft?.prompt ?? "",
        should_trigger: draft?.should_trigger !== false,
        output_path: outputPath,
        contains,
        min_pages: draft?.min_pages ?? null,
        files: draft?.files || [],
        needs_upload: Boolean(draft?.needs_upload),
        golden_path: draft?.golden_path ?? null,
        bank_status: draft?.bank_status ?? "draft",
      },
    ])
  }, [skill])

  const applySkill = useCallback((next: SkillPayload) => {
    setSkill(next)
  }, [])

  const updateCheck = useCallback((index: number, patch: Partial<Check>) => {
    setChecks((current) =>
      current.map((check, i) => (i === index ? { ...check, ...patch } : check))
    )
  }, [])

  const removeCheck = useCallback((index: number) => {
    setChecks((current) => current.filter((_, i) => i !== index))
  }, [])

  const importYaml = useCallback(
    async (text: string) => {
      const skillId = skill?.absolute || skill?.id
      if (!skillId) {
        setIntakeError("Pick a skill first.")
        setEvalTab("skill")
        return
      }
      const yamlText = text.trim()
      if (!yamlText) {
        toast.add({ title: "Paste YAML to import.", type: "error" })
        return
      }
      try {
        const data = await api.generate(skillId, yamlText)
        setChecks(data.checks)
        setYaml(data.yaml || yamlText)
        setChecksSeeded(false)
        setChecksSource("yaml")
        setChecksNote(data.note || "")
        setChecksWarning("")
        toast.add({ title: "YAML loaded into checks", type: "success" })
      } catch (err) {
        const error = asApiError(err)
        toast.add({ title: error.message, type: "error" })
      }
    },
    [skill]
  )

  const persistPinnedChecks = useCallback(
    async (toPin: Check[], pinSkillId?: string) => {
      const skillId = pinSkillId || skill?.absolute || skill?.id
      if (!skillId) {
        toast.add({ title: "Pick a skill first.", type: "error" })
        return false
      }
      try {
        const data = await api.pinChecks({ skill: skillId, checks: toPin })
        if (isSameSkill(skill, skillId, data.skill)) {
          setChecks(data.checks)
          setYaml(data.yaml || "")
          setChecksSource("pack")
          setChecksNote(
            "Deploy follows this Dataset. Generate drafts checks — doesn't unlock Deploy."
          )
          setChecksSeeded(true)
          if (data.skill) {
            setSkill(data.skill)
          }
        }
        toast.add({ title: "Saved to Dataset", type: "success" })
        return true
      } catch (err) {
        const error = asApiError(err)
        toast.add({ title: error.message, type: "error" })
        return false
      }
    },
    [skill]
  )

  const pinShownChecks = useCallback(async () => {
    await persistPinnedChecks(checks)
  }, [checks, persistPinnedChecks])

  const pinCheckAt = useCallback(
    async (index: number) => {
      const check = checks[index]
      if (!check) {
        toast.add({ title: "Pick a skill first.", type: "error" })
        return
      }
      await persistPinnedChecks([check])
    },
    [checks, persistPinnedChecks]
  )

  const pinDatasetChecks = useCallback(
    async (toPin: Check[], pinSkillId?: string) =>
      persistPinnedChecks(toPin, pinSkillId),
    [persistPinnedChecks]
  )

  const bindPackFixtures = useCallback(
    async (inherit: boolean) => {
      const skillId = skill?.absolute || skill?.id
      if (!skillId) {
        return
      }
      setFixtureInherit(inherit)
      try {
        const data = await api.fixtureBind({
          skill: skillId,
          checks: collectChecks(),
          action: "inherit",
          inherit,
          glob: fixtureGlob,
        })
        setChecks(data.checks)
        setSkill({
          ...data.skill,
          fixture_defaults: data.fixture_defaults ?? data.skill.fixture_defaults,
        })
        toast.add({
          title: inherit
            ? "Completion checks now use pack fixtures"
            : "Pack fixture inherit is off",
          type: "success",
        })
        return data.checks
      } catch (err) {
        const error = asApiError(err)
        toast.add({ title: error.message, type: "error" })
      }
    },
    [collectChecks, fixtureGlob, skill]
  )

  const expandPackFixtures = useCallback(async () => {
    const skillId = skill?.absolute || skill?.id
    if (!skillId) {
      return
    }
    try {
      const data = await api.fixtureBind({
        skill: skillId,
        checks: collectChecks(),
        action: "expand",
        inherit: fixtureInherit,
        glob: fixtureGlob,
      })
      setChecks(data.checks)
      setSkill({
        ...data.skill,
        fixture_defaults: data.fixture_defaults ?? data.skill.fixture_defaults,
      })
      toast.add({ title: "Made cases from the pack folder", type: "success" })
    } catch (err) {
      const error = asApiError(err)
      toast.add({ title: error.message, type: "error" })
    }
  }, [collectChecks, fixtureGlob, fixtureInherit, skill])

  const startEvaluations = useCallback(async () => {
    if (!skill) {
      setIntakeError("Pick a skill first.")
      setEvalTab("skill")
      return
    }
    let checkList = collectChecks()
    if (checkList.length === 0) {
      setIntakeError("Add at least one check before starting evaluations.")
      setEvalTab("checks")
      return
    }
    if (
      checkList.some((check) => check.needs_upload) &&
      fixtureInherit &&
      authenticFixtureDefaults(skill).length > 0
    ) {
      const bound = await bindPackFixtures(true)
      if (bound?.length) {
        checkList = collectChecksForRun(bound, skill)
      }
    }
    const namedBlock = startBlockedMessage(checkList, fixtureInherit, skill)
    if (namedBlock) {
      setEvalTab("checks")
      toast.add({ title: namedBlock, type: "error" })
      return
    }
    await runNow({
      skill: skill.absolute || skill.id,
      checks: checkList,
      live: Boolean(status?.has_key),
    })
  }, [bindPackFixtures, collectChecks, fixtureInherit, runNow, skill, status?.has_key])

  const runAfterPossiblePaste = useCallback(async () => {
    setIntakeError("")
    const markdown = paste.trim() || pendingPaste.trim()
    let skillId = skill?.absolute || skill?.id
    const looksLikeFix =
      markdown.startsWith("---") && markdown.includes("description:")
    try {
      if (looksLikeFix) {
        if (!skillId) {
          setIntakeError("Pick a skill first.")
          setEvalTab("skill")
          return
        }
        const restore =
          lastAdvice?.restore_scripts_from ||
          (skill?.name === "pdf-sabotaged" ? "pdf" : null)
        const applied = await api.applyFix({
          skill: skillId,
          paste: markdown,
          restore_scripts_from: restore,
        })
        setSkill(applied)
        skillId = applied.absolute
      }
      const checkList = collectChecks()
      if (checkList.length === 0) {
        setIntakeError("Add at least one check before starting evaluations.")
        setEvalTab("checks")
        return
      }
      await runNow({
        skill: skillId,
        checks: checkList,
        live: Boolean(status?.has_key),
      })
    } catch (err) {
      const error = asApiError(err)
      await applyResult({
        status: "error",
        error: { message: error.message, hint: error.hint },
        harness: resolvedHarness,
      })
    }
  }, [
    applyResult,
    collectChecks,
    lastAdvice,
    paste,
    pendingPaste,
    resolvedHarness,
    runNow,
    skill,
    status?.has_key,
  ])

  const installTo = useCallback(
    async (target: DeployTarget) => {
      if (!deployAllowed || !skill) {
        return
      }
      try {
        const data = await api.deploy(target, skill.name, "local")
        setDeployLast(deployLabel(target))
        const label = deployLabel(target) ?? target
        toast.add({ title: data.note || data.dest || `Installed to ${label}`, type: "success" })
        await Promise.all([
          refreshSkillHistory(skill.name),
          refreshWorkspaceHistory(),
          refreshSkills(),
        ])
      } catch (err) {
        const error = asApiError(err)
        toast.add({ title: error.message, type: "error" })
      }
    },
    [deployAllowed, refreshSkillHistory, refreshSkills, refreshWorkspaceHistory, skill]
  )

  const publishToGit = useCallback(async () => {
    if (!deployAllowed || !skill) {
      return
    }
    try {
      const data = await api.deploy("git", skill.name, "git")
      setDeployLast("git")
      toast.add({
        title: data.note || data.url || data.dest || "Published to git",
        type: "success",
      })
      await Promise.all([
        refreshSkillHistory(skill.name),
        refreshWorkspaceHistory(),
        refreshSkills(),
      ])
    } catch (err) {
      const error = asApiError(err)
      toast.add({ title: error.message, type: "error" })
    }
  }, [deployAllowed, refreshSkillHistory, refreshSkills, refreshWorkspaceHistory, skill])

  useEffect(() => {
    if (stage !== "eval" || evalTab !== "checks") {
      return
    }
    if (!skill || checks.length > 0 || seeding || intakeError) {
      return
    }
    const skillId = skill.absolute || skill.id
    if (!skillId) {
      return
    }
    void selectSkill(skillId, { tab: "checks", fallbackSkill: skill })
  }, [checks.length, evalTab, intakeError, seeding, selectSkill, skill, stage])

  const localHomeBooted = useRef(false)
  useEffect(() => {
    void (async () => {
      try {
        setStatus(await api.status())
      } catch {
        /* ignore */
      }
      await Promise.all([refreshSkills(), refreshWorkspaceHistory(), refreshAnalytics()])
    })()
  }, [refreshAnalytics, refreshSkills, refreshWorkspaceHistory])

  useEffect(() => {
    if (!status || localHomeBooted.current) {
      return
    }
    localHomeBooted.current = true
    if (status.mode === "local" && !status.slots?.analyticsHome) {
      setStage("repository")
    }
  }, [status])

  const value = useMemo<DashboardContextValue>(
    () => ({
      stage,
      setStage,
      evalTab,
      setEvalTab,
      repoSkill,
      setRepoSkill,
      historyOpen,
      setHistoryOpen,
      searchQuery,
      setSearchQuery,
      paste,
      setPaste,
      skill,
      skills,
      checks,
      yaml,
      running,
      connectionLost,
      seeding,
      seedingAssist,
      checksSeeded,
      checksSource,
      checksNote,
      checksWarning,
      intakeError,
      catalogError,
      lastResult,
      liveGateResult,
      tryoutResult,
      lastAdvice,
      history,
      skillHistory,
      analytics,
      status,
      copiedFix,
      deployLast,
      deployAllowed,
      suggestBusy,
      suggestError,
      suggestByRunId,
      requestSkillUpdates,
      copySkillUpdates,
      refreshSkills,
      refreshAnalytics,
      refreshStatus,
      selectSkill,
      openHistoryRun,
      openRepository,
      pasteSkill,
      uploadZip,
      addCheck,
      updateCheck,
      removeCheck,
      applySkill,
      importYaml,
      pinShownChecks,
      pinCheckAt,
      pinDatasetChecks,
      pinBaseline,
      startEvaluations,
      runThisCheck,
      fixtureInherit,
      fixtureGlob,
      setFixtureInherit,
      setFixtureGlob,
      bindPackFixtures,
      expandPackFixtures,
      runAfterPossiblePaste,
      copyFix,
      installTo,
      publishToGit,
      harnessPref,
      setHarnessPref,
      resolvedHarness,
      evalConfig,
      setEvalConfig,
      viewingPinnedHistory,
      gateRunning,
      tryoutRunning,
    }),
    [
      addCheck,
      analytics,
      applySkill,
      bindPackFixtures,
      checks,
      checksSeeded,
      checksSource,
      checksNote,
      checksWarning,
      copiedFix,
      connectionLost,
      copyFix,
      copySkillUpdates,
      deployAllowed,
      deployLast,
      evalTab,
      harnessPref,
      evalConfig,
      expandPackFixtures,
      fixtureGlob,
      fixtureInherit,
      history,
      historyOpen,
      importYaml,
      installTo,
      publishToGit,
      intakeError,
      catalogError,
      lastAdvice,
      lastResult,
      liveGateResult,
      tryoutResult,
      openHistoryRun,
      openRepository,
      paste,
      pasteSkill,
      pinBaseline,
      pinCheckAt,
      pinDatasetChecks,
      pinShownChecks,
      refreshAnalytics,
      refreshSkills,
      refreshStatus,
      requestSkillUpdates,
      repoSkill,
      resolvedHarness,
      runAfterPossiblePaste,
      running,
      searchQuery,
      seeding,
      seedingAssist,
      selectSkill,
      skill,
      skillHistory,
      skills,
      stage,
      startEvaluations,
      runThisCheck,
      status,
      suggestBusy,
      suggestByRunId,
      suggestError,
      updateCheck,
      uploadZip,
      yaml,
      removeCheck,
      viewingPinnedHistory,
      gateRunning,
      tryoutRunning,
    ]
  )

  return (
    <DashboardContext.Provider value={value}>
      {children}
    </DashboardContext.Provider>
  )
}

export function useDashboard() {
  const context = useContext(DashboardContext)
  if (!context) {
    throw new Error("useDashboard must be used within DashboardProvider")
  }
  return context
}
