import { FolderIcon, TriangleAlertIcon } from "lucide-react"
import { useState } from "react"

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
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
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
  const [folderPath, setFolderPath] = useState("")
  const [gitUrl, setGitUrl] = useState("")

  const openImport = async () => {
    setImportOpen(true)
    setSourcesError("")
    setSelected([])
    try {
      const data = await api.importSources()
      setSources(data.sources ?? [])
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : "Could not look up agent folders."
      setSourcesError(message)
      setSources([])
    }
  }

  const importAgentSkills = async (wanted: string[]) => {
    if (!wanted.length) {
      toast.add({ title: "Choose Cursor, Codex, or Claude first.", type: "error" })
      return
    }
    setSelected(wanted)
    setImporting(true)
    try {
      const data = await api.importSkills({ sources: wanted })
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

  const importFolderOrGit = async (opts: { folder?: string; git_url?: string }) => {
    setImporting(true)
    try {
      const data = await api.importSkills(opts)
      await refreshSkills()
      const count = data.imported?.length ?? 0
      toast.add({
        title:
          count > 0
            ? `Imported ${count} skill${count === 1 ? "" : "s"}.`
            : "Nothing was imported.",
        type: count > 0 ? "success" : "error",
      })
      if (count > 0) {
        setImportOpen(false)
        setFolderPath("")
        setGitUrl("")
      }
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
            ? "Skills in this project. Connect Cursor, Codex, or Claude to import. Open one to read SKILL.md. Run never starts until you press it."
            : "Every skill on disk, with last gate, runs, versions, and deploys. Last run is the last complete run."
        }
        action={
          <div className="flex flex-wrap gap-2">
            {isLocalMode(status) ? (
              <Button
                id="btn-import-skills"
                variant="outline"
                onClick={() => void openImport()}
              >
                Connect
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
                <EmptyTitle>No skills yet</EmptyTitle>
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
                  <TableHead>Runs</TableHead>
                  <TableHead>Versions</TableHead>
                  <TableHead title="Last complete run">
                    Last run
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
            <DialogTitle>Connect</DialogTitle>
            <DialogDescription>
              Choose Cursor, Codex, or Claude first. We’ll copy that agent’s skills into this project.
            </DialogDescription>
          </DialogHeader>
          {sourcesError ? (
            <Alert>
              <AlertTitle>Could not find agent folders</AlertTitle>
              <AlertDescription>{sourcesError}</AlertDescription>
            </Alert>
          ) : sources.length === 0 ? (
            <p className="text-sm text-muted-foreground">Looking up agent folders…</p>
          ) : (
            <div className="flex flex-col gap-3">
              {sources.map((source) => (
                <div
                  key={source.id}
                  className="flex items-start gap-3 rounded-lg border px-3 py-2"
                >
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm font-medium">{source.label}</span>
                    <span className="block text-xs text-muted-foreground">
                      {source.found
                        ? `${source.folder_label} · ${source.count} skill${source.count === 1 ? "" : "s"}`
                        : `${source.folder_label} not found`}
                    </span>
                  </span>
                  <Button
                    id={`btn-import-${source.id}`}
                    size="sm"
                    disabled={importing || !source.found || source.count === 0}
                    onClick={() => void importAgentSkills([source.id])}
                  >
                    {importing && selected.includes(source.id)
                      ? "Importing…"
                      : "Import"}
                  </Button>
                </div>
              ))}
            </div>
          )}
          <div className="flex flex-col gap-3 border-t pt-4">
            <p className="text-sm font-medium">From disk or git</p>
            <div className="flex flex-col gap-2">
              <Label htmlFor="import-folder-path">Skill folder</Label>
              <div className="flex gap-2">
                <Input
                  id="import-folder-path"
                  placeholder="/path/to/my-skill"
                  value={folderPath}
                  disabled={importing}
                  onChange={(event) => setFolderPath(event.target.value)}
                />
                <Button
                  id="btn-import-folder"
                  variant="secondary"
                  disabled={importing || !folderPath.trim()}
                  onClick={() =>
                    void importFolderOrGit({ folder: folderPath.trim() })
                  }
                >
                  Import
                </Button>
              </div>
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="import-git-url">Git URL</Label>
              <div className="flex gap-2">
                <Input
                  id="import-git-url"
                  placeholder="https://github.com/org/skills.git"
                  value={gitUrl}
                  disabled={importing}
                  onChange={(event) => setGitUrl(event.target.value)}
                />
                <Button
                  id="btn-import-git"
                  variant="secondary"
                  disabled={importing || !gitUrl.trim()}
                  onClick={() => void importFolderOrGit({ git_url: gitUrl.trim() })}
                >
                  Clone
                </Button>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setImportOpen(false)}>
              Cancel
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
