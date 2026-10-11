import { useCallback, useEffect, useRef, useState } from "react"

import { toast } from "@/components/ui/toast"
import { api, isTransientFetchError, pollRun } from "@/lib/api"
import { asApiError, collectChecksForRun, matchesSkill, SIGNED_OUT_CHECK } from "@/lib/dashboard-helpers"
import { draftToApiConfig, type EvalConfigDraft } from "@/lib/eval-config"
import { mergeEvalSnapshot, seededRunningReport } from "@/lib/eval-row-state"
import {
  deployAllowedForLiveGate,
  emptySkillRunSlot,
  isTryoutRun,
  liveGateRun,
  patchSkillSlot,
  pinBelongsToSkill,
  shownGateRun,
  skillSlotKey,
  type RunPurpose,
  type SkillRunSlot,
} from "@/lib/skill-run-state"
import type {
  Advice,
  AnalyticsPayload,
  Check,
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

type EvalSessionOpts = {
  skill: SkillPayload | null
  skills: SkillPayload[]
  checks: Check[]
  evalConfig: EvalConfigDraft
  harnessPref: HarnessPref
  resolvedHarness: string
  fixtureInherit: boolean
  fixtureGlob: string
  setStage: (stage: Stage) => void
  setEvalTab: (tab: EvalTab) => void
  setSkill: (skill: SkillPayload) => void
  setCopiedFix: (value: boolean) => void
  setIntakeError: (value: string) => void
  setHistoryOpen: (open: boolean) => void
  setPaste: (value: string) => void
  setPendingPaste: (value: string) => void
  refreshWorkspaceHistory: () => Promise<HistoryPayload | null>
  refreshSkillHistory: (name?: string | null) => Promise<HistoryPayload | null>
  refreshSkills: () => Promise<SkillPayload[]>
  refreshAnalytics: () => Promise<AnalyticsPayload | null>
  status?: StatusPayload | null
}

export function useEvalSession(opts: EvalSessionOpts) {
  const {
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
  } = opts

  const [slots, setSlots] = useState<Record<string, SkillRunSlot>>({})
  const slotsRef = useRef(slots)
  slotsRef.current = slots
  const [connectionLost, setConnectionLost] = useState(false)
  const pollsRef = useRef(new Map<string, AbortController>())
  const pollMetaRef = useRef(
    new Map<string, { skillName: string; purpose: RunPurpose }>()
  )
  const skillRef = useRef(skill)
  skillRef.current = skill
  const [suggestBusy, setSuggestBusy] = useState(false)
  const [suggestError, setSuggestError] = useState<{
    message: string
    hint?: string
  } | null>(null)
  const [suggestByRunId, setSuggestByRunId] = useState<
    Record<string, SkillUpdatesPayload>
  >({})

  const patchSlot = useCallback(
    (key: string, patch: (slot: SkillRunSlot) => SkillRunSlot) => {
      setSlots((prev) => patchSkillSlot(prev, key, patch))
    },
    []
  )

  const skillKey = skillSlotKey(skill)
  const slot = slots[skillKey] ?? emptySkillRunSlot()
  const liveGateResult = liveGateRun(slot, skillKey)
  const tryoutResult = slot.tryout
  const viewingPinnedHistory = pinBelongsToSkill(slot.pin, skillKey)
  const lastResult = shownGateRun(slot, skillKey)
  const lastAdvice: Advice | null = lastResult?.report?.advice ?? null
  const gateRunning = slot.runningPurpose === "gate"
  const tryoutRunning = slot.runningPurpose === "tryout"
  const running = gateRunning || tryoutRunning
  const deployAllowed = deployAllowedForLiveGate({
    skill,
    liveGate: liveGateResult,
    gateRunning,
    mode: status?.mode,
  })

  const resumePoll = useCallback(
    async (
      runId: string,
      skillName: string,
      purpose: RunPurpose
    ): Promise<RunRecord> => {
      if (pollsRef.current.has(runId)) {
        return api.getRun(runId)
      }
      for (const [id, meta] of pollMetaRef.current) {
        if (id !== runId && meta.skillName === skillName && meta.purpose === purpose) {
          pollsRef.current.get(id)?.abort()
          pollsRef.current.delete(id)
          pollMetaRef.current.delete(id)
        }
      }
      const ac = new AbortController()
      pollsRef.current.set(runId, ac)
      pollMetaRef.current.set(runId, { skillName, purpose })
      patchSlot(skillName, (current) => ({ ...current, runningPurpose: purpose }))
      setConnectionLost(false)
      if (purpose === "gate") {
        setEvalTab("gate")
        setStage("eval")
      }
      try {
        const done = await pollRun(runId, {
          signal: ac.signal,
          onProgress: (snap) => {
            patchSlot(skillName, (current) => {
              if (purpose === "tryout") {
                return {
                  ...current,
                  tryout: mergeEvalSnapshot(current.tryout, snap),
                }
              }
              return {
                ...current,
                gate: mergeEvalSnapshot(current.gate, snap),
              }
            })
          },
          onConnectionLost: () => setConnectionLost(true),
          onConnectionRestored: () => setConnectionLost(false),
        })
        return done
      } finally {
        if (pollsRef.current.get(runId) === ac) {
          pollsRef.current.delete(runId)
          pollMetaRef.current.delete(runId)
          patchSlot(skillName, (current) => ({
            ...current,
            runningPurpose:
              current.runningPurpose === purpose ? null : current.runningPurpose,
          }))
          setConnectionLost(false)
        }
      }
    },
    [patchSlot, setEvalTab, setStage]
  )

  const applySkillHistory = useCallback((hist: HistoryPayload | null, skillName?: string | null) => {
    const name = (skillName || hist?.skill || "").trim()
    if (!name) {
      return
    }
    const last =
      hist?.last_run && !isTryoutRun(hist.last_run) ? hist.last_run : null
    patchSlot(name, (current) => ({ ...current, gate: last }))
    if (last?.status === "running" && last.id) {
      const id = last.id
      void resumePoll(id, name, "gate")
        .then((done) => {
          if (isTryoutRun(done)) {
            return
          }
          patchSlot(name, (current) => ({ ...current, gate: done }))
          if (done.status !== "running") {
            setEvalTab("gate")
            void refreshWorkspaceHistory()
            void refreshSkillHistory(done.report?.skill || done.skill || name)
          }
        })
        .catch((err) => {
          if (!isTransientFetchError(err)) {
            console.warn("resume running run failed", err)
          }
        })
    }
  }, [patchSlot, refreshSkillHistory, refreshWorkspaceHistory, resumePoll, setEvalTab])

  const applyResult = useCallback(
    async (data: RunRecord, purpose: RunPurpose = "gate") => {
      const name =
        data.report?.skill || data.skill || skillSlotKey(skillRef.current) || ""
      const tryout = purpose === "tryout" || isTryoutRun(data)
      if (name) {
        patchSlot(name, (current) =>
          tryout ? { ...current, tryout: data } : { ...current, gate: data }
        )
        if (!tryout) {
          setCopiedFix(false)
          setEvalTab("gate")
          setStage("eval")
        }
      }
      await Promise.all([
        refreshWorkspaceHistory(),
        refreshSkillHistory(name || skillKey),
        tryout ? Promise.resolve([]) : refreshSkills(),
        tryout ? Promise.resolve(null) : refreshAnalytics(),
      ])
    },
    [
      patchSlot,
      refreshAnalytics,
      refreshSkillHistory,
      refreshSkills,
      refreshWorkspaceHistory,
      setCopiedFix,
      setEvalTab,
      setStage,
      skillKey,
    ]
  )

  const runNow = useCallback(
    async ({
      skill: skillId,
      checks: nextChecks,
      live: liveFlag,
      tryout = false,
    }: {
      skill?: string | null
      checks?: Check[] | null
      live?: boolean
      tryout?: boolean
    } = {}) => {
      const name = skillSlotKey(skill)
      const purpose: RunPurpose = tryout ? "tryout" : "gate"
      const current = slotsRef.current[name] ?? emptySkillRunSlot()
      if (name && current.runningPurpose === purpose) {
        return
      }
      setIntakeError("")
      setStage("eval")
      const checkList = nextChecks || collectChecksForRun(checks, skill)
      const includeReasoning = resolvedHarness === "codex"
      const apiConfig = draftToApiConfig(evalConfig, includeReasoning)
      const requestedConfig = {
        harness: resolvedHarness,
        harness_pref: harnessPref,
        model: apiConfig.model,
        timeout_sec: apiConfig.timeout_sec,
        temperature: apiConfig.temperature,
        reasoning_effort: apiConfig.reasoning_effort,
      }
      const seed: RunRecord = {
        status: "running",
        passed: null,
        gate: null,
        completed_count: 0,
        task_count: checkList.length,
        current_task_id: null,
        tryout,
        report: checkList.length
          ? { ...seededRunningReport(checkList, name), tryout }
          : tryout
            ? { ...seededRunningReport([], name), tryout: true }
            : null,
        harness: resolvedHarness,
        config: requestedConfig,
        model: apiConfig.model,
        timeout_sec: apiConfig.timeout_sec,
        temperature: apiConfig.temperature,
        reasoning_effort: apiConfig.reasoning_effort,
        skill: name,
      }
      if (name) {
        patchSlot(name, (slot) =>
          tryout
            ? { ...slot, runningPurpose: "tryout", tryout: seed }
            : { ...slot, pin: null, runningPurpose: "gate", gate: seed }
        )
      }
      if (!tryout) {
        setEvalTab("gate")
        setCopiedFix(false)
      }
      let startedId: string | null = null
      try {
        const live = liveFlag === true
        const payload = {
          live,
          demo: !live,
          harness: harnessPref,
          skill: skillId || skill?.absolute || skill?.id,
          suite: null as string | null,
          checks: checkList,
          config: apiConfig,
          fixture_bind: {
            inherit: fixtureInherit,
            glob: fixtureGlob,
          },
          tryout,
        }
        const started = await api.startRun(payload)
        startedId = started.id
        const done = await resumePoll(started.id, name, purpose)
        await applyResult(done, purpose)
      } catch (err) {
        if (isTransientFetchError(err)) {
          return
        }
        const error = asApiError(err)
        const message =
          error.status === 401 ? SIGNED_OUT_CHECK : error.message
        if (error.status === 401) {
          setIntakeError(message)
        }
        if (message.includes("needs a file in the skill folder")) {
          setEvalTab("checks")
          toast.add({ title: message, type: "error" })
        }
        await applyResult(
          {
            id: error.runId,
            status: "error",
            error: { message, hint: error.hint },
            harness: error.harness || resolvedHarness,
            skill: name,
            tryout,
            config: error.config || requestedConfig,
            model: error.model ?? apiConfig.model,
            timeout_sec: error.timeout_sec ?? apiConfig.timeout_sec,
            temperature: error.temperature ?? apiConfig.temperature,
            reasoning_effort: error.reasoning_effort ?? apiConfig.reasoning_effort,
          },
          purpose
        )
      } finally {
        if (name && !startedId) {
          patchSlot(name, (slot) => ({
            ...slot,
            runningPurpose:
              slot.runningPurpose === purpose ? null : slot.runningPurpose,
          }))
        }
        setConnectionLost(false)
      }
    },
    [
      applyResult,
      checks,
      evalConfig,
      fixtureGlob,
      fixtureInherit,
      harnessPref,
      patchSlot,
      resolvedHarness,
      resumePoll,
      setCopiedFix,
      setEvalTab,
      setIntakeError,
      setStage,
      skill,
    ]
  )

  const runThisCheck = useCallback(
    async (check: Check) => {
      await runNow({
        skill: skill?.absolute || skill?.id,
        checks: [check],
        live: Boolean(status?.has_key),
        tryout: true,
      })
    },
    [runNow, skill, status?.has_key]
  )

  const openHistoryRun = useCallback(
    async (item: TimelineItem) => {
      if (item.kind !== "run" || !item.id) {
        return
      }
      setHistoryOpen(false)
      setIntakeError("")
      try {
        const data = await api.getRun(item.id)
        const skillName = data.skill || data.report?.skill || item.skill || null
        if (skillName) {
          const match = skills.find((s) => matchesSkill(s, skillName))
          if (match) {
            setSkill(match)
          }
          await refreshSkillHistory(skillName)
          if (isTryoutRun(data)) {
            patchSlot(skillName, (current) => ({ ...current, tryout: data }))
          } else {
            patchSlot(skillName, (current) => ({ ...current, pin: data }))
          }
        }
        setCopiedFix(false)
        setEvalTab("gate")
        setStage("eval")
        await refreshWorkspaceHistory()
      } catch (err) {
        const apiErr = asApiError(err)
        setIntakeError(apiErr.message || "Could not open that run.")
        toast.add({ title: apiErr.message || "Could not open that run.", type: "error" })
      }
    },
    [
      patchSlot,
      refreshSkillHistory,
      refreshWorkspaceHistory,
      setCopiedFix,
      setEvalTab,
      setHistoryOpen,
      setIntakeError,
      setSkill,
      setStage,
      skills,
    ]
  )

  const pinBaseline = useCallback(
    async (request: {
      skill: string
      run_id?: string | null
      follow_deploy?: boolean
    }) => {
      try {
        const data = await api.pinBaseline(request)
        toast.add({
          title: request.follow_deploy
            ? "Using last Deploy as baseline"
            : "Saved as baseline",
          type: "success",
        })
        const skillName = data.skill || request.skill
        await Promise.all([
          refreshSkillHistory(skillName),
          refreshWorkspaceHistory(),
        ])
        const viewed = lastResult
        const viewedId = viewed?.id
        if (viewedId && !isTryoutRun(viewed)) {
          try {
            const fresh = await api.getRun(viewedId)
            const name = fresh.skill || fresh.report?.skill || skillName
            if (name) {
              patchSlot(name, (current) =>
                current.pin?.id === viewedId
                  ? { ...current, pin: fresh }
                  : { ...current, gate: fresh }
              )
            }
          } catch {
            // Keep the current Gate snapshot if the run cannot be reloaded.
          }
        }
        return true
      } catch (err) {
        const error = asApiError(err)
        toast.add({ title: error.message, type: "error" })
        return false
      }
    },
    [lastResult, patchSlot, refreshSkillHistory, refreshWorkspaceHistory]
  )

  const copyFix = useCallback(async () => {
    const text = lastAdvice?.paste
    if (!text) {
      return
    }
    setPaste(text)
    setPendingPaste(text)
    setCopiedFix(true)
    try {
      await navigator.clipboard.writeText(text)
    } catch {
      /* clipboard may be blocked; the paste box still has it */
    }
    toast.add({
      title: "Copied into the skill — now click Run",
      type: "success",
    })
  }, [lastAdvice, setCopiedFix, setPaste, setPendingPaste])

  const requestSkillUpdates = useCallback(
    async (opts?: { force?: boolean }) => {
      const runId = lastResult?.id
      if (!runId) {
        return
      }
      if (!opts?.force && suggestByRunId[runId]) {
        setSuggestError(null)
        return
      }
      setSuggestBusy(true)
      setSuggestError(null)
      try {
        const data = await api.suggestSkillUpdates(runId)
        setSuggestByRunId((prev) => ({ ...prev, [runId]: data }))
      } catch (err) {
        const error = asApiError(err)
        setSuggestError({ message: error.message, hint: error.hint })
      } finally {
        setSuggestBusy(false)
      }
    },
    [lastResult?.id, suggestByRunId]
  )

  const copySkillUpdates = useCallback(async () => {
    const runId = lastResult?.id
    const payload = runId ? suggestByRunId[runId] : null
    const lines = (payload?.items ?? []).map(
      (item, index) => `${index + 1}. ${item.title}`
    )
    if (lines.length === 0) {
      return
    }
    try {
      await navigator.clipboard.writeText(lines.join("\n"))
    } catch {
      /* clipboard may be blocked */
    }
    toast.add({
      title: "Copied checklist",
      type: "success",
    })
  }, [lastResult?.id, suggestByRunId])

  useEffect(() => {
    const kick = () => {
      if (document.visibilityState === "hidden") {
        return
      }
      const pending: Array<[string, { skillName: string; purpose: RunPurpose }]> =
        [...pollMetaRef.current.entries()]
      if (pending.length === 0) {
        const name = skillSlotKey(skillRef.current)
        const current = name ? slotsRef.current[name] : null
        if (current?.runningPurpose === "gate" && current.gate?.id) {
          pending.push([
            current.gate.id,
            { skillName: name || "", purpose: "gate" },
          ])
        } else if (current?.runningPurpose === "tryout" && current.tryout?.id) {
          pending.push([
            current.tryout.id,
            { skillName: name || "", purpose: "tryout" },
          ])
        }
      }
      for (const [id, meta] of pending) {
        if (!id || !meta.skillName) {
          continue
        }
        void resumePoll(id, meta.skillName, meta.purpose)
          .then((done) => {
            if (done.status !== "running") {
              void applyResult(done, meta.purpose)
            }
          })
          .catch((err) => {
            if (!isTransientFetchError(err)) {
              console.warn("resume poll failed", err)
            }
          })
      }
    }
    const onVis = () => {
      if (document.visibilityState === "visible") kick()
    }
    window.addEventListener("online", kick)
    document.addEventListener("visibilitychange", onVis)
    return () => {
      window.removeEventListener("online", kick)
      document.removeEventListener("visibilitychange", onVis)
    }
  }, [applyResult, resumePoll])

  return {
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
  }
}
