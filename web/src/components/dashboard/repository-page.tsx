import { FolderIcon, TriangleAlertIcon } from "lucide-react"
import { useState } from "react"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
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
import { toast } from "@/components/ui/toast"

type ImportSource = {
  id: string
  label: string
  found: boolean
  count: number
  folder_label: string
}

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
  const [importOpen, setImportOpen] = useState(false)
  const [importing, setImporting] = useState(false)
  const [sources, setSources] = useState<ImportSource[]>([])
  const [selected, setSelected] = useState<string[]>([])
  const [sourcesError, setSourcesError] = useState("")

  const openImport = async () => {
    setImportOpen(true)
    setSourcesError("")
    try {
      const data = await api.importSources()
      const next = data.sources ?? []
      setSources(next)
      setSelected(next.filter((item) => item.found && item.count > 0).map((item) => item.id))
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : "Could not look up agent folders."
      setSourcesError(message)
      setSources([])
    }
  }

  const importAgentSkills = async () => {
    const wanted = selected.length ? selected : sources.filter((item) => item.found).map((item) => item.id)
    setImporting(true)
    try {
      const data = await api.importSkills(wanted)
      await refreshSkills()
      const count = data.imported?.length ?? 0
      toast.add({
        title:
          count > 0
            ? `Imported ${count} skill${count === 1 ? "" : "s"}.`
            : "No new skills to import. Skills already here were skipped.",
        type: "success",
      })
      setImportOpen(false)
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
            ? "Skills in this project plus Cursor, Codex, and Claude. Open one to read SKILL.md. Run never starts until you press it."
            : "Every skill on disk, with last gate, evals, versions, and deploys. Last eval is the latest full run; single checks don't count."
        }
        action={
          <div className="flex flex-wrap gap-2">
            {isLocalMode(status) ? (
              <Button
                id="btn-import-skills"
                variant="outline"
                onClick={() => void openImport()}
              >
                Import from agent folders
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
                : "Connect Cursor, Codex, or Claude, or paste a SKILL.md on Evaluate."}
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
                  Connect Cursor, Codex, or Claude, or paste a SKILL.md on Evaluate.
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
                    onOpen={() => openRepository(item.slug || item.id || item.name)}
                    onEvaluate={() => void selectSkill(item.absolute || item.slug || item.id)}
                  />
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
      <Dialog open={importOpen} onOpenChange={setImportOpen}>
        <DialogContent id="import-agent-folders" className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Connect agent folders</DialogTitle>
            <DialogDescription>
              Choose Cursor, Codex, and Claude. We’ll copy whole skill folders into this project.
            </DialogDescription>
          </DialogHeader>
          {sourcesError ? (
            <Alert variant="destructive">
              <AlertTitle>Could not find agent folders</AlertTitle>
              <AlertDescription>{sourcesError}</AlertDescription>
            </Alert>
          ) : sources.length === 0 ? (
            <p className="text-sm text-muted-foreground">Looking up agent folders…</p>
          ) : (
            <div className="flex flex-col gap-3">
              {sources.map((source) => {
                const checked = selected.includes(source.id)
                return (
                  <label
                    key={source.id}
                    className="flex items-start gap-3 rounded-lg border px-3 py-2"
                  >
                    <Checkbox
                      checked={checked}
                      disabled={!source.found}
                      onCheckedChange={(value) => {
                        const on = value === true
                        setSelected((current) =>
                          on
                            ? Array.from(new Set([...current, source.id]))
                            : current.filter((id) => id !== source.id)
                        )
                      }}
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm font-medium">{source.label}</span>
                      <span className="block text-xs text-muted-foreground">
                        {source.found
                          ? `${source.folder_label} · ${source.count} skill${source.count === 1 ? "" : "s"}`
                          : `${source.folder_label} not found`}
                      </span>
                    </span>
                  </label>
                )
              })}
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setImportOpen(false)}>
              Cancel
            </Button>
            <Button
              id="btn-import-confirm"
              disabled={importing || selected.length === 0}
              onClick={() => void importAgentSkills()}
            >
              {importing ? "Importing…" : "Import"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
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
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2">
            <span className="font-medium">{skill.name}</span>
            {skill.seed ? <Badge variant="outline">Seed</Badge> : null}
          </div>
          {skill.warning ? (
            <span className="text-xs text-muted-foreground">{skill.warning}</span>
          ) : null}
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
