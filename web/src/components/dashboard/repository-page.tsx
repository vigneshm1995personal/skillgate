import { FolderIcon, TriangleAlertIcon } from "lucide-react"

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
import { GateBadge, PageHeader } from "@/components/dashboard/chrome"
import { useDashboard } from "@/lib/dashboard-provider"
import { SkillDetailPage } from "@/components/dashboard/skill-detail-page"
import { api, ApiError } from "@/lib/api"
import { isLocalMode } from "@/lib/mode"
import { relativeTime } from "@/lib/time"
import type { SkillPayload } from "@/lib/types"
import { useState } from "react"
import { toast } from "@/components/ui/toast"

export function RepositoryPage() {
  const {
    repoSkill,
    skills,
    searchQuery,
    selectSkill,
    openRepository,
    setStage,
    setEvalTab,
    catalogError,
    refreshSkills,
    status,
  } = useDashboard()
  const [importing, setImporting] = useState(false)

  const importAgentSkills = async () => {
    setImporting(true)
    try {
      const data = await api.importSkills()
      await refreshSkills()
      const count = data.imported?.length ?? 0
      toast.add({
        title:
          count > 0
            ? `Imported ${count} skill${count === 1 ? "" : "s"} from Cursor, Codex, and Claude folders.`
            : "No new skills to import. Folders already in this project were skipped.",
        type: "success",
      })
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Could not import skills."
      toast.add({ title: message, type: "error" })
    } finally {
      setImporting(false)
    }
  }

  if (repoSkill) {
    return <SkillDetailPage name={repoSkill} />
  }

  const query = searchQuery.trim().toLowerCase()
  const visible = skills.filter((item) => {
    if (!query) {
      return true
    }
    return (
      item.name.toLowerCase().includes(query) ||
      (item.description || "").toLowerCase().includes(query)
    )
  })

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        title="Skills"
        description={
          isLocalMode(status)
            ? "Skills in this project plus ~/.cursor/skills, ~/.codex/skills, and ~/.claude/skills. Open one to read SKILL.md. Run never starts until you press it."
            : "Every skill on disk, with last gate, evals, versions, and deploys. Last eval is the latest full run; single checks don't count."
        }
        action={
          <div className="flex flex-wrap gap-2">
            {isLocalMode(status) ? (
              <Button
                id="btn-import-skills"
                variant="outline"
                disabled={importing}
                onClick={() => void importAgentSkills()}
              >
                {importing ? "Importing…" : "Import from agent folders"}
              </Button>
            ) : null}
            <Button
              variant="outline"
              onClick={() => {
                setEvalTab("skill")
                setStage("eval")
              }}
            >
              Evaluate
            </Button>
          </div>
        }
      />
      <Card>
        <CardHeader className="sticky top-0 z-10 bg-card/95 backdrop-blur supports-[backdrop-filter]:bg-card/80">
          <CardTitle>Skills</CardTitle>
          <CardDescription>
            {skills.length
              ? `${visible.length} of ${skills.length} skills${query ? " matching search" : ""}. Use ⌘K to filter.`
              : catalogError
                ? catalogError.message
                : "pdf is the seed skill for testing. It is not a magic demo button."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {catalogError && skills.length > 0 ? (
            <Alert className="mb-4">
              <TriangleAlertIcon />
              <AlertTitle>{catalogError.message}</AlertTitle>
              {catalogError.hint ? (
                <AlertDescription>{catalogError.hint}</AlertDescription>
              ) : null}
            </Alert>
          ) : null}
          {visible.length === 0 ? (
            catalogError && skills.length === 0 ? (
              <Empty>
                <EmptyHeader>
                  <EmptyMedia variant="icon">
                    <TriangleAlertIcon />
                  </EmptyMedia>
                  <EmptyTitle>Could not load skills</EmptyTitle>
                  <EmptyDescription>{catalogError.message}</EmptyDescription>
                  {catalogError.hint ? (
                    <EmptyDescription>{catalogError.hint}</EmptyDescription>
                  ) : null}
                </EmptyHeader>
                <EmptyContent>
                  <Button variant="outline" onClick={() => void refreshSkills()}>
                    Retry
                  </Button>
                </EmptyContent>
              </Empty>
            ) : (
            <Empty>
              <EmptyHeader>
                <EmptyMedia variant="icon">
                  <FolderIcon />
                </EmptyMedia>
                <EmptyTitle>No skills in the repository</EmptyTitle>
                <EmptyDescription>
                  Bundled skills live under skills/. You can also paste SKILL.md on Evaluate.
                </EmptyDescription>
              </EmptyHeader>
              <EmptyContent>
                <Button onClick={() => setStage("eval")}>Evaluate</Button>
              </EmptyContent>
            </Empty>
            )
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Skill</TableHead>
                  <TableHead>Gate</TableHead>
                  <TableHead>Evals</TableHead>
                  <TableHead>Versions</TableHead>
                  <TableHead title="Latest full run. Single checks are excluded.">
                    Last eval
                  </TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {visible.map((item) => (
                  <SkillRow
                    key={item.id}
                    skill={item}
                    onOpen={() => openRepository(item.name)}
                    onEvaluate={() => void selectSkill(item.absolute || item.id)}
                  />
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

function SkillRow({
  skill,
  onOpen,
  onEvaluate,
}: {
  skill: SkillPayload
  onOpen: () => void
  onEvaluate: () => void
}) {
  return (
    <TableRow
      className="cursor-pointer"
      onClick={onOpen}
      title={skill.description || undefined}
    >
      <TableCell>
        <div className="flex items-center gap-2">
          <span className="font-medium">{skill.name}</span>
          {skill.seed ? <Badge variant="outline">Seed</Badge> : null}
        </div>
      </TableCell>
      <TableCell>
        <GateBadge gate={skill.gate} />
      </TableCell>
      <TableCell>{skill.eval_count ?? 0}</TableCell>
      <TableCell>{skill.version_count ?? 0}</TableCell>
      <TableCell
        className="text-muted-foreground tabular-nums"
        title={skill.last_eval_at ?? undefined}
      >
        {relativeTime(skill.last_eval_at)}
      </TableCell>
      <TableCell>
        <div className="flex justify-end">
          <Button
            size="sm"
            onClick={(event) => {
              event.stopPropagation()
              onEvaluate()
            }}
          >
            Evaluate →
          </Button>
        </div>
      </TableCell>
    </TableRow>
  )
}
