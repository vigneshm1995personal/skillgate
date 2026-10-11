import { useCallback, useEffect, useState } from "react"
import { Columns2Icon } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
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
import { useDashboard } from "@/lib/dashboard-provider"
import { api } from "@/lib/api"
import type { HarnessPref } from "@/lib/types"

const HARNESS_OPTS: { value: HarnessPref; label: string }[] = [
  { value: "auto", label: "Auto" },
  { value: "cursor-agent", label: "Cursor" },
  { value: "codex", label: "Codex" },
  { value: "claude", label: "Claude" },
]

type ArmDraft = { label: string; harness: HarnessPref }

export function ComparePage() {
  const { skill, skills, setStage, openHistoryRun, status } = useDashboard()
  const [mode, setMode] = useState<"models" | "versions">("models")
  const [arms, setArms] = useState<ArmDraft[]>([
    { label: "Arm A", harness: "codex" },
    { label: "Arm B", harness: "cursor-agent" },
  ])
  const [maxSpend, setMaxSpend] = useState("5")
  const [runA, setRunA] = useState("")
  const [runB, setRunB] = useState("")
  const [result, setResult] = useState<ComparePayload | null>(null)
  const [running, setRunning] = useState(false)
  const [activeCompareId, setActiveCompareId] = useState<string | null>(null)
  const [pastCompares, setPastCompares] = useState<ComparePayload[]>([])
  const [error, setError] = useState("")

  const activeSkill = skill?.name || skills[0]?.name || ""

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
        arms: arms.map((arm) => ({
          label: arm.label,
          harness_pref: arm.harness,
        })),
        max_spend_usd: Number(maxSpend) || 5,
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
    if (!runA.trim() || !runB.trim()) {
      setError("Pick two history runs.")
      return
    }
    setError("")
    setRunning(true)
    setResult(null)
    try {
      const started = await api.startCompareVersions({
        skill: activeSkill,
        run_ids: [runA.trim(), runB.trim()],
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
              <div key={index} className="grid gap-3 sm:grid-cols-2">
                <div>
                  <Label>Arm {index + 1} label</Label>
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
                        harness: value as HarnessPref,
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
            ))}
            <div className="max-w-xs">
              <Label>Spend cap (USD)</Label>
              <Input value={maxSpend} onChange={(e) => setMaxSpend(e.target.value)} />
            </div>
            <div className="flex flex-wrap gap-2">
              <Button id="btn-compare-models" disabled={running} onClick={() => void runModels()}>
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
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <Label>History run A</Label>
                <Input value={runA} onChange={(e) => setRunA(e.target.value)} placeholder="run id" />
              </div>
              <div>
                <Label>History run B</Label>
                <Input value={runB} onChange={(e) => setRunB(e.target.value)} placeholder="run id" />
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                id="btn-compare-versions"
                disabled={running}
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
            <div className="flex flex-wrap gap-2">
              {result.arms.map((arm) => (
                <Badge key={arm.arm_id} variant="secondary">
                  {arm.label}: {armChecksLine(arm)}
                </Badge>
              ))}
            </div>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Check</TableHead>
                  {result.arms.map((arm) => (
                    <TableHead key={arm.arm_id}>{arm.label}</TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {(result.cases ?? []).map((row) => (
                  <TableRow key={row.case_id}>
                    <TableCell className="font-mono text-xs">{row.case_id}</TableCell>
                    {result.arms?.map((arm) => {
                      const cell = row.results?.[arm.arm_id]
                      const label = passLabel(cell?.passed)
                      const tone =
                        label === "Pass"
                          ? "text-success"
                          : label === "Fail"
                            ? "text-destructive"
                            : ""
                      return (
                        <TableCell key={arm.arm_id} className={tone}>
                          {label}
                        </TableCell>
                      )
                    })}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
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
          </CardContent>
        </Card>
      ) : null}
    </div>
  )
}
