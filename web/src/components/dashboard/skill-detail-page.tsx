import { useEffect, useState, type ReactNode } from "react"
import { ArrowLeftIcon, FolderIcon } from "lucide-react"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { ScrollArea } from "@/components/ui/scroll-area"
import { AssistantMarkdown } from "@/components/dashboard/assistant-markdown"
import { EvalMosaic, MosaicLegend } from "@/components/dashboard/eval-mosaic"
import { DatasetImportDialog } from "@/components/dashboard/dataset-import-dialog"
import { DatasetViewer } from "@/components/dashboard/dataset-viewer"
import { SkillPackBrowser } from "@/components/dashboard/skill-pack-browser"
import { GateBadge, PageHeader } from "@/components/dashboard/chrome"
import { Skeleton } from "@/components/ui/skeleton"
import { api, ApiError } from "@/lib/api"
import { useDashboard } from "@/lib/dashboard-provider"
import { customerConfigLabel, harnessDisplayName } from "@/lib/eval-config"
import { skillDetailStatus } from "@/lib/skill-detail-state"
import { isTryoutRun } from "@/lib/skill-run-state"
import { absoluteTime, relativeTime } from "@/lib/time"
import type { AnalyticsPayload, AnalyticsRun, SkillDetailPayload } from "@/lib/types"

export function SkillDetailPage({ name }: { name: string }) {
  const {
    openRepository,
    selectSkill,
    setStage,
    openHistoryRun,
  } = useDashboard()
  const [detail, setDetail] = useState<SkillDetailPayload | null>(null)
  const [analytics, setAnalytics] = useState<AnalyticsPayload | null>(null)
  const [error, setError] = useState("")
  const [skillSettled, setSkillSettled] = useState(false)
  const [datasetOpen, setDatasetOpen] = useState(false)
  const [importOpen, setImportOpen] = useState(false)

  useEffect(() => {
    let cancelled = false
    setSkillSettled(false)
    setDetail(null)
    setError("")
    void (async () => {
      try {
        const data = await api.skill(name)
        if (!cancelled) {
          setDetail(data)
          setError("")
        }
      } catch (err) {
        if (!cancelled) {
          const message =
            err instanceof ApiError ? err.message : "Could not load this skill."
          setError(message)
        }
      } finally {
        if (!cancelled) {
          setSkillSettled(true)
        }
      }
    })()
    void (async () => {
      try {
        const skillAnalytics = await api.analytics(name)
        if (!cancelled) {
          setAnalytics(skillAnalytics)
        }
      } catch {
        if (!cancelled) {
          setAnalytics(null)
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [name])

  const item = detail?.skill
  const view = skillDetailStatus({ skillSettled, error })
  const loading = view === "loading"
  const versions = detail?.versions ?? []
  const runs = detail?.runs ?? []
  const deploys = detail?.deploys ?? []
  const fromAnalytics =
    analytics?.outcomes && analytics.outcomes.length > 0
      ? analytics.outcomes
      : analytics?.recent ?? []
  const mosaicRuns =
    fromAnalytics.length > 0
      ? fromAnalytics
      : (detail?.runs ?? []).flatMap((run) =>
          run.id
            ? [
                {
                  id: run.id,
                  skill: run.skill,
                  harness: run.harness,
                  passed: run.passed ?? null,
                  status: run.status,
                  gate: run.gate,
                  created_at: run.created_at,
                },
              ]
            : []
        )

  const openRun = (run: AnalyticsRun) => {
    if (!run.id) {
      return
    }
    void openHistoryRun({
      kind: "run",
      id: run.id,
      skill: run.skill ?? name,
    })
  }

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        title={item?.name ?? name}
        description={item?.description || "Skill detail"}
        action={
          <div className="flex flex-wrap gap-2">
            <Button
              id="btn-repo-back"
              type="button"
              variant="outline"
              onClick={() => {
                openRepository(null)
                setStage("repository")
              }}
            >
              <ArrowLeftIcon data-icon="inline-start" />
              Repository
            </Button>
            <Button
              id="btn-view-dataset-detail"
              variant="outline"
              className="touch-manipulation"
              aria-haspopup="dialog"
              aria-expanded={datasetOpen}
              translate="no"
              onClick={() => setDatasetOpen(true)}
            >
              View Dataset
            </Button>
            <Button
              id="btn-import-dataset-detail"
              variant="outline"
              className="touch-manipulation"
              aria-haspopup="dialog"
              aria-expanded={importOpen}
              onClick={() => setImportOpen(true)}
            >
              Import dataset
            </Button>
            <Button
              onClick={() => void selectSkill(item?.absolute || name)}
            >
              Evaluate this skill
            </Button>
            <Button
              variant="secondary"
              disabled={detail?.gate !== "cleared"}
              onClick={() => {
                void selectSkill(item?.absolute || name, { tab: "gate" }).then(
                  () => setStage("deploy")
                )
              }}
            >
              Deploy
            </Button>
          </div>
        }
      />

      {error ? (
        <Alert>
          <AlertTitle>Could not load skill</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      {mosaicRuns.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Eval activity</CardTitle>
            <CardDescription>
              Pass rate per day for this skill over the last year. Click a day
              to open its latest run.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            <EvalMosaic runs={mosaicRuns} onOpen={openRun} />
            <MosaicLegend />
          </CardContent>
        </Card>
      ) : null}

      <div className="grid gap-4 md:grid-cols-4">
        <StatCard
          label="Last gate"
          value={
            loading ? (
              <Skeleton className="h-6 w-16" />
            ) : (
              <GateBadge gate={detail?.gate} />
            )
          }
        />
        <StatCard
          label="Evals"
          value={loading ? <Skeleton className="h-6 w-10" /> : String(item?.eval_count ?? runs.length)}
        />
        <StatCard
          label="Versions"
          value={
            loading ? (
              <Skeleton className="h-6 w-10" />
            ) : (
              String(item?.version_count ?? versions.length)
            )
          }
        />
        <StatCard
          label="Deploys"
          value={
            loading ? (
              <Skeleton className="h-6 w-10" />
            ) : (
              String(item?.deploy_count ?? deploys.length)
            )
          }
        />
      </div>

      {item?.warning ? (
        <Alert>
          <AlertTitle>This skill needs attention</AlertTitle>
          <AlertDescription>{item.warning}</AlertDescription>
        </Alert>
      ) : null}

      {item ? (
        <Card id="skill-md-readable">
          <CardHeader>
            <CardTitle>SKILL.md</CardTitle>
            <CardDescription>
              {item.description || "How this skill works."}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {item.body?.trim() ? (
              <div className="text-sm leading-relaxed">
                <AssistantMarkdown text={item.body} />
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                This skill has no SKILL.md body yet.
              </p>
            )}
          </CardContent>
        </Card>
      ) : null}

      {item ? (
        <SkillPackBrowser
          skill={item}
          files={item.pack_files ?? detail?.pack_files ?? []}
          datasetOpen={datasetOpen}
          onDatasetOpenChange={setDatasetOpen}
          onSkill={(next) =>
            setDetail((current) =>
              current
                ? {
                    ...current,
                    skill: { ...current.skill, ...next },
                    pack_files: next.pack_files ?? current.pack_files,
                  }
                : current
            )
          }
        />
      ) : null}

      <Card>
        <CardHeader>
            <CardTitle>Runs</CardTitle>
            <CardDescription>
            A complete run sets Deploy. Running one example by itself is labeled and doesn't count.
            </CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex flex-col gap-2">
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-3/4" />
            </div>
          ) : runs.length === 0 ? (
            <Empty>
              <EmptyHeader>
                <EmptyMedia variant="icon">
                  <FolderIcon />
                </EmptyMedia>
                <EmptyTitle>No runs yet</EmptyTitle>
                <EmptyDescription>
                  Run this skill to record a gate decision.
                </EmptyDescription>
              </EmptyHeader>
            </Empty>
          ) : (
            <ScrollArea className="max-h-[380px] overflow-hidden rounded-md border [&_[data-slot=scroll-area-viewport]]:max-h-[380px]">
              <Table>
                <TableHeader className="sticky top-0 z-10 bg-card shadow-xs">
                  <TableRow>
                    <TableHead>When</TableHead>
                    <TableHead>Gate</TableHead>
                    <TableHead>Agent</TableHead>
                    <TableHead>Config</TableHead>
                    <TableHead>Version</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {runs.map((run) => (
                    <TableRow
                      key={run.id}
                      className={run.id ? "cursor-pointer" : undefined}
                      tabIndex={run.id ? 0 : undefined}
                      onClick={() => openRun(run)}
                      onKeyDown={
                        run.id
                          ? (event) => {
                              if (event.key !== "Enter" && event.key !== " ") {
                                return
                              }
                              event.preventDefault()
                              openRun(run)
                            }
                          : undefined
                      }
                    >
                      <TableCell
                        className="text-muted-foreground tabular-nums whitespace-nowrap"
                        title={absoluteTime(run.created_at)}
                      >
                        {relativeTime(run.created_at)}
                      </TableCell>
                      <TableCell>
                        {isTryoutRun(run) ? (
                          <div className="flex flex-wrap items-center gap-1">
                            <Badge variant={run.passed ? "secondary" : "destructive"}>
                              {run.passed ? "Pass" : "Fail"}
                            </Badge>
                            <Badge variant="outline">Single check</Badge>
                          </div>
                        ) : (
                          <GateBadge
                            gate={run.gate_decision}
                            passed={run.passed}
                          />
                        )}
                      </TableCell>
                      <TableCell>
                        {harnessDisplayName(run.harness || "", run.harness || "")}
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-col gap-1">
                          <span className="truncate">
                            {customerConfigLabel(run.config, run.harness) ||
                              run.config_label ||
                              run.harness ||
                              "—"}
                          </span>
                          {run.config_changed ? (
                            <Badge variant="warning">
                              Settings changed from the last run
                            </Badge>
                          ) : null}
                        </div>
                      </TableCell>
                      <TableCell className="whitespace-nowrap">
                        {run.semver ? `v${run.semver}` : "—"}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </ScrollArea>
          )}
        </CardContent>
      </Card>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Versions</CardTitle>
            <CardDescription>Recorded versions of this skill.</CardDescription>
          </CardHeader>
          <CardContent>
            {loading ? (
              <Skeleton className="h-16 w-full" />
            ) : versions.length === 0 ? (
              <p className="text-sm text-muted-foreground">No versions recorded yet.</p>
            ) : (
              <ScrollArea className="max-h-[260px] overflow-hidden rounded-md border [&_[data-slot=scroll-area-viewport]]:max-h-[260px]">
                <Table>
                  <TableHeader className="sticky top-0 z-10 bg-card shadow-xs">
                    <TableRow>
                      <TableHead>Version</TableHead>
                      <TableHead>When</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {versions.map((version) => (
                      <TableRow key={`${version.skill_md_hash}-${version.id}`}>
                        <TableCell>v{version.semver}</TableCell>
                        <TableCell
                          className="text-muted-foreground tabular-nums whitespace-nowrap"
                          title={absoluteTime(version.created_at)}
                        >
                          {relativeTime(version.created_at)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </ScrollArea>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Deployments</CardTitle>
            <CardDescription>Installs of this gated skill into Cursor, Claude, or Codex.</CardDescription>
          </CardHeader>
          <CardContent>
            {loading ? (
              <Skeleton className="h-16 w-full" />
            ) : deploys.length === 0 ? (
              <p className="text-sm text-muted-foreground">No deploy attempts yet.</p>
            ) : (
              <ScrollArea className="max-h-[260px] overflow-hidden rounded-md border [&_[data-slot=scroll-area-viewport]]:max-h-[260px]">
                <Table>
                  <TableHeader className="sticky top-0 z-10 bg-card shadow-xs">
                    <TableRow>
                      <TableHead>When</TableHead>
                      <TableHead>Target</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Version</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {deploys.map((attempt) => (
                      <TableRow key={attempt.id}>
                        <TableCell
                          className="text-muted-foreground tabular-nums whitespace-nowrap"
                          title={absoluteTime(attempt.created_at)}
                        >
                          {relativeTime(attempt.created_at)}
                        </TableCell>
                        <TableCell className="capitalize">{attempt.target}</TableCell>
                        <TableCell>
                          <Badge variant="outline">{attempt.status}</Badge>
                        </TableCell>
                        <TableCell className="whitespace-nowrap">
                          {attempt.semver ? `v${attempt.semver}` : "—"}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </ScrollArea>
            )}
          </CardContent>
        </Card>
      </div>
      <DatasetViewer
        skillId={item?.absolute || item?.id || name}
        open={datasetOpen}
        onOpenChange={setDatasetOpen}
      />
      <DatasetImportDialog
        skillId={item?.absolute || item?.id || name}
        open={importOpen}
        onOpenChange={setImportOpen}
        onImported={() => setDatasetOpen(true)}
      />
    </div>
  )
}

function StatCard({ label, value }: { label: string; value: ReactNode }) {
  return (
    <Card>
      <CardHeader>
        <CardDescription>{label}</CardDescription>
        <CardTitle>{value}</CardTitle>
      </CardHeader>
    </Card>
  )
}
