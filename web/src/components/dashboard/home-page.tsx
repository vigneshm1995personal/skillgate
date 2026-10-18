import type { ReactNode } from "react"
import {
  FlaskConicalIcon,
  LayoutDashboardIcon,
  RefreshCwIcon,
} from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Empty,
  EmptyContent,
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
import { PageHeader } from "@/components/dashboard/chrome"
import { useDashboard } from "@/lib/dashboard-provider"
import { absoluteTime, relativeTime } from "@/lib/time"
import type { AnalyticsDeploy, AnalyticsRun } from "@/lib/types"

export function HomePage() {
  const { analytics, refreshAnalytics, setStage, setEvalTab, openHistoryRun } =
    useDashboard()

  const goEvaluate = () => {
    setEvalTab("skill")
    setStage("eval")
  }

  const openRun = (run: AnalyticsRun) => {
    if (!run.id) {
      return
    }
    void openHistoryRun({
      kind: "run",
      id: run.id,
      skill: run.skill ?? undefined,
    })
  }

  const totals = analytics?.totals
  const usage = analytics?.usage
  const hasWorkspace =
    analytics != null &&
    ((totals?.runs ?? 0) > 0 || (totals?.deployments ?? 0) > 0)
  const passRate =
    totals && totals.runs > 0
      ? `${Math.round((totals.green / totals.runs) * 100)}%`
      : null
  const recentDeploys = analytics?.recent_deploys ?? []

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        title="Home"
        description="Where the workspace stands: eval runs, gate outcomes, deployments, and eval spend."
        action={
          <>
            <Button
              variant="outline"
              size="lg"
              onClick={() => void refreshAnalytics()}
            >
              <RefreshCwIcon data-icon="inline-start" />
              Refresh
            </Button>
            <Button size="lg" onClick={goEvaluate}>
              <FlaskConicalIcon data-icon="inline-start" />
              Evaluate
            </Button>
          </>
        }
      />

      {hasWorkspace && totals && usage ? (
        <div className="flex flex-col gap-4">
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <KpiCard
              label="Eval runs"
              value={String(totals.runs)}
              hint={`${totals.runs_7d} in 7d · ${totals.runs_30d} in 30d`}
            />
            <KpiCard
              label="Pass rate"
              value={passRate ?? "—"}
              hint={
                <>
                  <span className="text-success tabular-nums">
                    {totals.green} pass
                  </span>
                  {" · "}
                  <span className="text-destructive tabular-nums">
                    {totals.red} fail
                  </span>
                </>
              }
            />
            <KpiCard
              label="Deployments"
              value={String(totals.deployments)}
              hint={
                totals.skills_cleared != null
                  ? `Skills green for Deploy: ${totals.skills_cleared}`
                  : undefined
              }
            />
            <KpiCard
              label="Eval spend"
              value={formatCost(usage.cost_usd) ?? "—"}
              hint={
                <>
                  {formatTokens(usage.tokens_total) ?? "—"} tokens
                  {usage.runs_with_usage > 0
                    ? ` · ${usage.runs_with_usage}/${totals.runs} reported`
                    : " · no usage stamped yet"}
                </>
              }
            />
          </div>

          {recentDeploys.length > 0 ? (
            <Card>
              <CardHeader>
                <CardTitle>Recent deploys</CardTitle>
                <CardDescription>
                  Latest installs into an agent skills folder.
                </CardDescription>
              </CardHeader>
              <CardContent className="px-0">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="pl-6">Skill</TableHead>
                      <TableHead>Target</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead className="pr-6 text-right">When</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {recentDeploys.slice(0, 5).map((deploy) => (
                      <DeployRow key={String(deploy.id)} deploy={deploy} />
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          ) : null}

          {analytics.recent.length > 0 ? (
            <Card>
              <CardHeader>
                <CardTitle>Recent runs</CardTitle>
                <CardDescription>
                  The last {analytics.recent.length} evaluations, newest first.
                  Open one to reload its Gate.
                </CardDescription>
                <CardAction>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setStage("history")}
                  >
                    All history
                  </Button>
                </CardAction>
              </CardHeader>
              <CardContent className="px-0">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="pl-6">Skill</TableHead>
                      <TableHead>Harness</TableHead>
                      <TableHead>Result</TableHead>
                      <TableHead className="pr-6 text-right">When</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {analytics.recent.map((run, index) => {
                      const canOpen = Boolean(run.id)
                      return (
                        <TableRow
                          key={run.id ?? `${run.skill}-${index}`}
                          className={canOpen ? "cursor-pointer" : undefined}
                          tabIndex={canOpen ? 0 : undefined}
                          onClick={() => openRun(run)}
                          onKeyDown={(event) => {
                            if (!canOpen || event.key !== "Enter") {
                              return
                            }
                            openRun(run)
                          }}
                        >
                          <TableCell className="pl-6 font-medium">
                            {run.skill || "—"}
                          </TableCell>
                          <TableCell className="text-muted-foreground">
                            {run.harness || "—"}
                          </TableCell>
                          <TableCell>
                            <ResultBadge run={run} />
                          </TableCell>
                          <TableCell
                            className="pr-6 text-right text-muted-foreground tabular-nums"
                            title={absoluteTime(run.created_at)}
                          >
                            {relativeTime(run.created_at)}
                          </TableCell>
                        </TableRow>
                      )
                    })}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          ) : null}
        </div>
      ) : (
        <div className="rounded-2xl border bg-muted/30 p-4 lg:p-5">
          <Empty>
            <EmptyHeader>
              <EmptyMedia variant="icon">
                <LayoutDashboardIcon />
              </EmptyMedia>
              <EmptyTitle>No runs yet</EmptyTitle>
              <EmptyDescription>
                Analytics build from your evaluations. Run a skill with checks
                and the summary fills in here.
              </EmptyDescription>
            </EmptyHeader>
            <EmptyContent>
              <Button onClick={goEvaluate}>Evaluate a skill</Button>
            </EmptyContent>
          </Empty>
        </div>
      )}
    </div>
  )
}

function KpiCard({
  label,
  value,
  hint,
}: {
  label: string
  value: string
  hint?: ReactNode
}) {
  return (
    <Card>
      <CardHeader className="gap-1">
        <CardDescription>{label}</CardDescription>
        <CardTitle className="text-3xl tabular-nums tracking-tight">
          {value}
        </CardTitle>
      </CardHeader>
      {hint ? (
        <CardContent className="pt-0 text-xs text-muted-foreground">
          {hint}
        </CardContent>
      ) : null}
    </Card>
  )
}

function DeployRow({ deploy }: { deploy: AnalyticsDeploy }) {
  return (
    <TableRow>
      <TableCell className="pl-6 font-medium">
        {deploy.skill_name || "—"}
      </TableCell>
      <TableCell className="capitalize text-muted-foreground">
        {deploy.target || "—"}
      </TableCell>
      <TableCell>
        <Badge variant="outline">{deploy.status || "—"}</Badge>
      </TableCell>
      <TableCell
        className="pr-6 text-right text-muted-foreground tabular-nums"
        title={absoluteTime(deploy.created_at)}
      >
        {relativeTime(deploy.created_at)}
      </TableCell>
    </TableRow>
  )
}

function ResultBadge({ run }: { run: AnalyticsRun }) {
  if (run.status === "error") {
    return <Badge variant="destructive">Error</Badge>
  }
  if (run.passed) {
    return (
      <Badge variant="secondary" className="font-medium text-success">
        Pass
      </Badge>
    )
  }
  return <Badge variant="destructive">Fail</Badge>
}

function trimZero(value: number) {
  return value.toFixed(1).replace(/\.0$/, "")
}

function formatTokens(value?: number | null) {
  if (value == null) {
    return null
  }
  if (value < 1000) {
    return String(value)
  }
  if (value < 1_000_000) {
    return `${trimZero(value / 1000)}k`
  }
  return `${trimZero(value / 1_000_000)}M`
}

function formatCost(value?: number | null) {
  if (value == null) {
    return null
  }
  if (value > 0 && value < 0.01) {
    return "<$0.01"
  }
  return `$${value.toFixed(2)}`
}
