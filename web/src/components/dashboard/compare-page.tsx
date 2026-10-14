import { useCallback, useEffect, useMemo, useState } from "react"
import { Columns2Icon } from "lucide-react"

import { EvalConfigFields } from "@/components/dashboard/eval-config-fields"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { PageHeader } from "@/components/dashboard/chrome"
import {
  armChecksLine,
  disagreementCount,
  passLabel,
  type ComparePayload,
} from "@/lib/compare"
import {
  DEFAULT_EVAL_CONFIG_DRAFT,
  draftToApiConfig,
  type EvalConfigDraft,
} from "@/lib/eval-config"
import { useDashboard } from "@/lib/dashboard-provider"
import { api } from "@/lib/api"
import { resolvedHarnessName } from "@/lib/types"

type CompareHarnessPref = "auto" | "cursor-agent" | "codex" | "claude" | "llm"

type ArmDraft = {
  label: string
  harness: CompareHarnessPref
  config: EvalConfigDraft
}

const HARNESS_OPTS: { value: CompareHarnessPref; label: string }[] = [
  { value: "auto", label: "Auto" },
  { value: "llm", label: "LLM (AI Gateway key)" },
  { value: "cursor-agent", label: "Cursor" },
  { value: "codex", label: "Codex" },
  { value: "claude", label: "Claude" },
]

export function ComparePage() {
  const { skill, skills, setStage, openHistoryRun, status } = useDashboard()
  const [mode, setMode] = useState<"models" | "versions">("models")
  const [arms, setArms] = useState<ArmDraft[]>([
    { label: "Arm A", harness: "auto", config: { ...DEFAULT_EVAL_CONFIG_DRAFT } },
    { label: "Arm B", harness: "auto", config: { ...DEFAULT_EVAL_CONFIG_DRAFT } },
  ])
  const [maxSpend, setMaxSpend] = useState("5")
  const [versionMode, setVersionMode] = useState<"runs" | "git">("runs")
  const [runA, setRunA] = useState("")
  const [runB, setRunB] = useState("")
  const [gitRefA, setGitRefA] = useState("HEAD~1")
  const [gitRefB, setGitRefB] = useState("HEAD")
  const [historyRuns, setHistoryRuns] = useState<
    Array<{ id: string; label: string }>
  >([])
  const [caseIds, setCaseIds] = useState<string[] | null>(null)
  const [datasetChecks, setDatasetChecks] = useState<Array<{ id: string; prompt: string }>>([])
  const [result, setResult] = useState<ComparePayload | null>(null)
  const [running, setRunning] = useState(false)
  const [activeCompareId, setActiveCompareId] = useState<string | null>(null)
  const [pastCompares, setPastCompares] = useState<ComparePayload[]>([])
  const [error, setError] = useState("")

  const activeSkill = skill?.name || skills[0]?.name || ""
  const resolvedHarness = resolvedHarnessName("auto", status)

  const allCaseIds = useMemo(
    () => datasetChecks.map((row) => row.id),
    [datasetChecks]
  )

  const selectedCaseIds = useMemo(
    () => caseIds ?? allCaseIds,
    [caseIds, allCaseIds]
  )

  const pollCompare = useCallback(async (compareId: string) => {
    for (let i = 0; i < 120; i++) {
      const row = await api.getCompare(compareId, activeSkill)
      if (row.status === "done" || row.status === "cancelled") {
        setResult(row)
        setRunning(false)
        setActiveCompareId(null)
        return
      }
      if (row.status === "error") {
        setError(row.error?.message || "Compare failed.")
        setRunning(false)
        return
      }
      await new Promise((r) => setTimeout(r, 1500))
    }
    setError("Compare timed out.")
    setRunning(false)
  }, [activeSkill])

  const runModels = async () => {
    if (!activeSkill) {
      setError("Pick a skill first.")
      return
    }
    if (!status?.has_key) {
      setError("Add a model key in Settings first.")
      return
    }
    setError("")
    setRunning(true)
    setResult(null)
    try {
      const started = await api.startCompareModels({
        skill: activeSkill,
        arms: arms.map((arm) => {
          const cfg = draftToApiConfig(
            arm.config,
            arm.harness === "codex" || resolvedHarness === "codex"
          )
          return {
            label: arm.label,
            harness_pref: arm.harness,
            model: cfg.model,
            timeout_sec: cfg.timeout_sec,
            temperature: cfg.temperature,
            reasoning_effort: cfg.reasoning_effort,
          }
        }),
        max_spend_usd: Number(maxSpend) || 5,
        case_ids: caseIds ?? undefined,
      })
      setActiveCompareId(started.compare_id)
      await pollCompare(started.compare_id)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Compare failed.")
      setRunning(false)
    }
  }

  const runVersions = async () => {
    if (!activeSkill) {
      setError("Pick a skill first.")
      return
    }
    if (versionMode === "runs" && (!runA.trim() || !runB.trim())) {
      setError("Pick two history runs.")
      return
    }
    if (versionMode === "git" && (!gitRefA.trim() || !gitRefB.trim())) {
      setError("Pick two git refs.")
      return
    }
    if (versionMode === "git" && !status?.has_key) {
      setError("Add a model key in Settings first.")
      return
    }
    setError("")
    setRunning(true)
    setResult(null)
    try {
      const started = await api.startCompareVersions({
        skill: activeSkill,
        ...(versionMode === "runs"
          ? { run_ids: [runA.trim(), runB.trim()] }
          : { git_refs: [gitRefA.trim(), gitRefB.trim()] }),
      })
      setActiveCompareId(started.compare_id)
      await pollCompare(started.compare_id)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Compare failed.")
      setRunning(false)
    }
  }

  useEffect(() => {
    if (!activeSkill) {
      return
    }
    void api.listCompares(activeSkill).then((payload) => {
      setPastCompares(payload.compares ?? [])
      const latest = payload.compares?.[0]
      if (latest?.status === "done" || latest?.status === "cancelled") {
        setResult(latest)
      }
    })
  }, [activeSkill])

  useEffect(() => {
    if (!activeSkill) {
      setHistoryRuns([])
      return
    }
    void api.history(activeSkill).then((payload) => {
      const rows = (payload.runs ?? []).map((row) => {
        const id = String(row.id ?? "")
        const scored = row.passed === true ? "pass" : row.passed === false ? "fail" : "—"
        return {
          id,
          label: `${id} · ${scored}${row.tryout ? " · tryout" : ""}`,
        }
      })
      setHistoryRuns(rows)
      if (rows.length >= 2) {
        setRunA((prev) => prev || rows[1].id)
        setRunB((prev) => prev || rows[0].id)
      }
    })
  }, [activeSkill])

  useEffect(() => {
    if (!activeSkill) {
      setDatasetChecks([])
      setCaseIds(null)
      return
    }
    void api.dataset(activeSkill).then((payload) => {
      const rows = (payload.cases ?? []).map((row) => ({
        id: String(row.id),
        prompt: String(row.prompt || ""),
      }))
      setDatasetChecks(rows)
      setCaseIds(null)
    })
  }, [activeSkill])

  const cancelCompare = async () => {
    if (!activeCompareId) {
      return
    }
    try {
      await api.cancelCompare(activeCompareId)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not cancel.")
    }
  }

  const toggleCase = (id: string, checked: boolean) => {
    setCaseIds((prev) => {
      const base = prev ?? allCaseIds
      let next: string[]
      if (checked) {
        next = base.includes(id) ? base : [...base, id]
      } else {
        next = base.filter((item) => item !== id)
      }
      if (next.length === allCaseIds.length) {
        return null
      }
      return next
    })
  }

  const disagreements = disagreementCount(result?.cases)

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        title="Compare"
        description="Same Dataset, multiple setups or versions. Pass and Fail only use color."
        action={
          <Button variant="outline" onClick={() => setStage("repository")}>
            Pick skill
          </Button>
        }
      />
      {!activeSkill ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Columns2Icon className="size-5" />
              No skill selected
            </CardTitle>
            <CardDescription>Open Skills and choose a pack first.</CardDescription>
          </CardHeader>
        </Card>
      ) : (
        <Tabs value={mode} onValueChange={(v) => setMode(v as "models" | "versions")}>
          <TabsList>
            <TabsTrigger value="models">Models</TabsTrigger>
            <TabsTrigger value="versions">Versions</TabsTrigger>
          </TabsList>
          <TabsContent value="models" className="space-y-4 pt-4">
            {arms.map((arm, index) => (
              <Card key={index}>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">Arm {index + 1}</CardTitle>
                </CardHeader>
                <CardContent className="grid gap-4">
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div>
                      <Label>Label</Label>
                      <Input
                        value={arm.label}
                        onChange={(e) => {
                          const next = [...arms]
                          next[index] = { ...next[index], label: e.target.value }
                          setArms(next)
                        }}
                      />
                    </div>
                    <div>
                      <Label>Agent</Label>
                      <Select
                        value={arm.harness}
                        onValueChange={(value) => {
                          const next = [...arms]
                          next[index] = {
                            ...next[index],
                            harness: value as CompareHarnessPref,
                          }
                          setArms(next)
                        }}
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {HARNESS_OPTS.map((opt) => (
                            <SelectItem key={opt.value} value={opt.value}>
                              {opt.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                  <EvalConfigFields
                    value={arm.config}
                    onChange={(config) => {
                      const next = [...arms]
                      next[index] = { ...next[index], config }
                      setArms(next)
                    }}
                    harnessPref={arm.harness}
                    resolvedHarness={
                      arm.harness === "auto" ? resolvedHarness : arm.harness
                    }
                    disabled={running}
                    supportedModels={status?.supported_models}
                    supportedModelsMeta={status?.supported_models_meta}
                    defaultTimeoutSec={status?.default_eval_config?.timeout_sec}
                  />
                </CardContent>
              </Card>
            ))}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Checks</CardTitle>
                <CardDescription>
                  Leave all selected to run the full Dataset ({datasetChecks.length} checks).
                  Uncheck to match `skillgate compare models --cases`.
                </CardDescription>
              </CardHeader>
              <CardContent className="max-h-56 space-y-2 overflow-y-auto">
                {datasetChecks.map((row) => {
                  const checked =
                    caseIds === null || caseIds.includes(row.id)
                  return (
                    <label
                      key={row.id}
                      className="flex cursor-pointer items-start gap-2 text-sm"
                    >
                      <Checkbox
                        checked={checked}
                        onCheckedChange={(value) =>
                          toggleCase(row.id, value === true)
                        }
                      />
                      <span>
                        <span className="font-mono text-xs text-muted-foreground">
                          {row.id}
                        </span>
                        <span className="block text-muted-foreground">
                          {row.prompt.slice(0, 120)}
                        </span>
                      </span>
                    </label>
                  )
                })}
              </CardContent>
              <CardContent className="border-t pt-3 text-sm text-muted-foreground">
                Will run {selectedCaseIds.length} check
                {selectedCaseIds.length === 1 ? "" : "s"}.
              </CardContent>
            </Card>
            <div className="max-w-xs">
              <Label>Spend cap (USD)</Label>
              <Input value={maxSpend} onChange={(e) => setMaxSpend(e.target.value)} />
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                id="btn-compare-models"
                disabled={running || !status?.has_key}
                onClick={() => void runModels()}
              >
                {running ? "Comparing…" : "Run compare"}
              </Button>
              {running && activeCompareId ? (
                <Button
                  id="btn-compare-cancel"
                  variant="outline"
                  onClick={() => void cancelCompare()}
                >
                  Cancel
                </Button>
              ) : null}
            </div>
          </TabsContent>
          <TabsContent value="versions" className="space-y-4 pt-4">
            <Tabs
              value={versionMode}
              onValueChange={(v) => setVersionMode(v as "runs" | "git")}
            >
              <TabsList>
                <TabsTrigger value="runs">History runs</TabsTrigger>
                <TabsTrigger value="git">Git refs</TabsTrigger>
              </TabsList>
              <TabsContent value="runs" className="grid gap-3 pt-3 sm:grid-cols-2">
                <div>
                  <Label>History run A</Label>
                  {historyRuns.length > 0 ? (
                    <Select
                      value={runA}
                      onValueChange={(value) => value && setRunA(value)}
                    >
                      <SelectTrigger id="compare-run-a">
                        <SelectValue placeholder="Pick a run" />
                      </SelectTrigger>
                      <SelectContent>
                        {historyRuns.map((row) => (
                          <SelectItem key={row.id} value={row.id}>
                            {row.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  ) : (
                    <Input
                      id="compare-run-a"
                      value={runA}
                      onChange={(e) => setRunA(e.target.value)}
                      placeholder="run id"
                    />
                  )}
                </div>
                <div>
                  <Label>History run B</Label>
                  {historyRuns.length > 0 ? (
                    <Select
                      value={runB}
                      onValueChange={(value) => value && setRunB(value)}
                    >
                      <SelectTrigger id="compare-run-b">
                        <SelectValue placeholder="Pick a run" />
                      </SelectTrigger>
                      <SelectContent>
                        {historyRuns.map((row) => (
                          <SelectItem key={row.id} value={row.id}>
                            {row.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  ) : (
                    <Input
                      id="compare-run-b"
                      value={runB}
                      onChange={(e) => setRunB(e.target.value)}
                      placeholder="run id"
                    />
                  )}
                </div>
              </TabsContent>
              <TabsContent value="git" className="grid gap-3 pt-3 sm:grid-cols-2">
                <div>
                  <Label>Git ref A</Label>
                  <Input
                    id="compare-git-a"
                    value={gitRefA}
                    onChange={(e) => setGitRefA(e.target.value)}
                    placeholder="HEAD~1"
                  />
                </div>
                <div>
                  <Label>Git ref B</Label>
                  <Input
                    id="compare-git-b"
                    value={gitRefB}
                    onChange={(e) => setGitRefB(e.target.value)}
                    placeholder="HEAD"
                  />
                </div>
                <p className="col-span-full text-sm text-muted-foreground">
                  Same as <span className="font-mono text-xs">skillgate compare versions --git</span>.
                  Re-runs the Dataset at each ref (needs a model key).
                </p>
              </TabsContent>
            </Tabs>
            <div className="flex flex-wrap gap-2">
              <Button
                id="btn-compare-versions"
                disabled={
                  running ||
                  (versionMode === "runs" ? false : !status?.has_key)
                }
                onClick={() => void runVersions()}
              >
                {running ? "Comparing…" : "Compare versions"}
              </Button>
              {running && activeCompareId ? (
                <Button
                  id="btn-compare-versions-cancel"
                  variant="outline"
                  onClick={() => void cancelCompare()}
                >
                  Cancel
                </Button>
              ) : null}
            </div>
          </TabsContent>
        </Tabs>
      )}
      {pastCompares.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Recent compares</CardTitle>
            <CardDescription>Same as `skillgate compare list`.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            {pastCompares.map((row) => (
              <Button
                key={row.compare_id}
                size="sm"
                variant="outline"
                onClick={() => setResult(row)}
              >
                {row.compare_id} · {row.mode}
              </Button>
            ))}
          </CardContent>
        </Card>
      ) : null}
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      {result?.arms?.length ? (
        <Card>
          <CardHeader>
            <CardTitle>
              {result.skill} · {result.mode}
            </CardTitle>
            <CardDescription>
              {disagreements ? `${disagreements} cases disagreed.` : "All arms agreed."}
              {result.spend?.stopped_reason === "spend_cap"
                ? " Stopped at spend cap."
                : null}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead />
                  {result.arms.map((arm) => (
                    <TableHead key={arm.arm_id}>{arm.label}</TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                <TableRow>
                  <TableCell className="font-medium">Checks</TableCell>
                  {result.arms.map((arm) => (
                    <TableCell key={arm.arm_id}>{armChecksLine(arm)}</TableCell>
                  ))}
                </TableRow>
                {(result.cases ?? []).map((caseRow) => (
                  <TableRow key={caseRow.case_id}>
                    <TableCell className="font-mono text-xs">{caseRow.case_id}</TableCell>
                    {(result.arms ?? []).map((arm) => {
                      const cell = caseRow.results?.[arm.arm_id]
                      const passed = cell?.passed
                      return (
                        <TableCell key={arm.arm_id}>
                          {passed === true ? (
                            <Badge variant="outline" className="border-emerald-600 text-emerald-700">
                              {passLabel(passed)}
                            </Badge>
                          ) : passed === false ? (
                            <Badge variant="outline" className="border-destructive text-destructive">
                              {passLabel(passed)}
                            </Badge>
                          ) : (
                            passLabel(passed ?? null)
                          )}
                          {caseRow.disagreement ? (
                            <span className="ml-1 text-xs text-muted-foreground">≠</span>
                          ) : null}
                        </TableCell>
                      )
                    })}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            {result.arms.some((arm) => arm.run_id) ? (
              <div className="flex flex-wrap gap-2">
                {result.arms.map((arm) =>
                  arm.run_id ? (
                    <Button
                      key={arm.arm_id}
                      size="sm"
                      variant="outline"
                      onClick={() =>
                        void openHistoryRun({
                          kind: "run",
                          id: arm.run_id!,
                          skill: result.skill,
                        })
                      }
                    >
                      Open {arm.label} run
                    </Button>
                  ) : null
                )}
              </div>
            ) : null}
          </CardContent>
        </Card>
      ) : null}
    </div>
  )
}
