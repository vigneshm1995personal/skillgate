import { HistoryIcon } from "lucide-react"

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
import { PageHeader } from "@/components/dashboard/chrome"
import { useDashboard } from "@/lib/dashboard-provider"
import { historyMeta } from "@/lib/history-meta"
import { relativeTime } from "@/lib/time"

export function HistoryList() {
  const { history, openHistoryRun, searchQuery, pinBaseline } = useDashboard()
  const items = history?.timeline ?? []
  const query = searchQuery.trim().toLowerCase()
  const filtered = !query
    ? items
    : items.filter((item) => {
        const meta = historyMeta(item)
        const hay = [
          meta.skill,
          meta.version,
          meta.config,
          meta.fingerprint,
          item.label,
          item.skill,
          item.kind,
          item.passed === true ? "pass" : item.passed === false ? "fail" : "",
          item.id,
        ]
          .filter(Boolean)
          .join(" ")
          .toLowerCase()
        if (hay.includes(query)) return true
        // Light aliases so "fail" / "option a" / csv skill names find rows.
        if (query === "fail" || query === "failed" || query === "red") {
          return item.kind === "run" && item.passed === false
        }
        if (query === "pass" || query === "passed" || query === "green") {
          return item.kind === "run" && item.passed === true
        }
        return false
      })

  if (!items.length) {
    return (
      <Empty>
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <HistoryIcon />
          </EmptyMedia>
          <EmptyTitle>No runs yet</EmptyTitle>
          <EmptyDescription>
            Evaluate a skill to start a history. Each skill keeps its own gate.
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    )
  }

  if (!filtered.length) {
    return (
      <Empty>
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <HistoryIcon />
          </EmptyMedia>
          <EmptyTitle>No matching runs</EmptyTitle>
          <EmptyDescription>
            Nothing in History matches “{searchQuery.trim()}”. Try a skill name,
            fail/pass, or clear the top search box.
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    )
  }

  return (
    <ScrollArea className="max-h-[500px] overflow-hidden rounded-md border [&_[data-slot=scroll-area-viewport]]:max-h-[500px]">
      <Table>
        <TableHeader className="sticky top-0 z-10 bg-card shadow-xs">
          <TableRow>
            <TableHead>When</TableHead>
            <TableHead>Result</TableHead>
            <TableHead>Skill</TableHead>
            <TableHead>Config</TableHead>
            <TableHead />
          </TableRow>
        </TableHeader>
        <TableBody>
          {filtered.map((item, index) => {
            const canOpen = item.kind === "run" && Boolean(item.id)
            const meta = historyMeta(item)
            return (
              <TableRow
                key={`${item.kind}-${item.at}-${index}`}
                className={canOpen ? "cursor-pointer" : undefined}
                onClick={() => {
                  if (canOpen) {
                    void openHistoryRun(item)
                  }
                }}
              >
                <TableCell
                  className="text-muted-foreground tabular-nums whitespace-nowrap"
                  title={item.at}
                >
                  {relativeTime(item.at)}
                </TableCell>
                <TableCell>
                  {item.kind === "run" ? (
                    <div className="flex flex-wrap items-center gap-1">
                      <Badge variant={item.passed ? "secondary" : "destructive"}>
                        {item.passed ? "Pass" : "Fail"}
                      </Badge>
                      {item.tryout ? (
                        <Badge variant="outline">Single check</Badge>
                      ) : null}
                    </div>
                  ) : (
                    <Badge variant="outline">Deploy</Badge>
                  )}
                </TableCell>
                <TableCell className="max-w-xs">
                  <div className="flex flex-col gap-0.5">
                    <span className="font-medium">
                      {meta.skill}
                      {meta.version ? (
                        <span className="font-normal text-muted-foreground">
                          {" "}
                          · {meta.version}
                        </span>
                      ) : null}
                    </span>
                    {item.config_changed ? (
                      <Badge variant="outline" className="w-fit">
                        Config changed
                      </Badge>
                    ) : null}
                  </div>
                </TableCell>
                <TableCell
                  className="text-muted-foreground"
                  title={meta.fingerprint || undefined}
                >
                  <span className="tabular-nums">{meta.config}</span>
                </TableCell>
                <TableCell>
                  <div className="flex items-center justify-end gap-2">
                    {item.kind === "run" &&
                    (item.is_baseline ||
                      (history?.baseline?.run_id &&
                        item.id === history.baseline.run_id)) ? (
                      <Badge variant="outline">Baseline</Badge>
                    ) : null}
                    {canOpen && item.skill && item.id && !item.tryout ? (
                      <Button
                        id={`btn-pin-baseline-hist-${index}`}
                        variant="outline"
                        size="xs"
                        onClick={(event) => {
                          event.stopPropagation()
                          void pinBaseline({
                            skill: item.skill as string,
                            run_id: item.id,
                          })
                        }}
                      >
                        Save as baseline
                      </Button>
                    ) : null}
                    {canOpen ? (
                      <Button
                        variant="link"
                        size="sm"
                        onClick={(event) => {
                          event.stopPropagation()
                          void openHistoryRun(item)
                        }}
                      >
                        Open
                      </Button>
                    ) : null}
                  </div>
                </TableCell>
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
    </ScrollArea>
  )
}

export function HistoryPage() {
  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        title="History"
        description="Past runs on this machine. Shared team history is a hosted feature. Open a run to reload that Gate result."
      />
      <Card>
        <CardHeader>
          <CardTitle>Timeline</CardTitle>
          <CardDescription>
            Open a run to see that Gate — checks, scores, and advice.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <HistoryList />
        </CardContent>
      </Card>
    </div>
  )
}
