import { useMemo, useRef, useState } from "react"
import { FileTextIcon, FolderIcon, PlusIcon } from "lucide-react"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
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
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty"
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Textarea } from "@/components/ui/textarea"
import { toast } from "@/components/ui/toast"
import { DatasetViewer } from "@/components/dashboard/dataset-viewer"
import { api } from "@/lib/api"
import type { PackFile, PackPreview, SkillPayload } from "@/lib/types"

export function SkillPackBrowser({
  skill,
  files,
  onSkill,
  datasetOpen: datasetOpenControlled,
  onDatasetOpenChange,
}: {
  skill: SkillPayload
  files: PackFile[]
  onSkill?: (skill: SkillPayload) => void
  datasetOpen?: boolean
  onDatasetOpenChange?: (open: boolean) => void
}) {
  const [selected, setSelected] = useState<string | null>(null)
  const [preview, setPreview] = useState<PackPreview | null>(null)
  const [previewError, setPreviewError] = useState("")
  const [addOpen, setAddOpen] = useState(false)
  const [uncontrolledDatasetOpen, setUncontrolledDatasetOpen] = useState(false)
  const datasetOpen = datasetOpenControlled ?? uncontrolledDatasetOpen
  const setDatasetOpen = onDatasetOpenChange ?? setUncontrolledDatasetOpen
  const [paste, setPaste] = useState("")
  const [filename, setFilename] = useState("notes.txt")
  const fileRef = useRef<HTMLInputElement>(null)

  const rows = useMemo(
    () =>
      [...files].sort((a, b) => {
        if (a.path === "SKILL.md") {
          return -1
        }
        if (b.path === "SKILL.md") {
          return 1
        }
        return a.path.localeCompare(b.path)
      }),
    [files]
  )

  const openPreview = async (path: string) => {
    setSelected(path)
    setPreviewError("")
    try {
      const data = await api.packPreview(skill.id, path)
      setPreview(data)
    } catch (err) {
      setPreview(null)
      setPreviewError(err instanceof Error ? err.message : "Could not open that file.")
    }
  }

  const savePasted = async () => {
    const content = paste.trim()
    if (!content) {
      toast.add({ title: "Paste text or drop a file.", type: "error" })
      return
    }
    try {
      const data = await api.packFile({
        skill: skill.absolute || skill.id,
        path: filename.trim() || "notes.txt",
        content,
      })
      const saved = data.file
      if (!saved) {
        toast.add({
          title: data.message || "Could not save that file.",
          type: "error",
        })
        return
      }
      onSkill?.(data.skill)
      setPaste("")
      setAddOpen(false)
      toast.add({ title: "Saved into the skill folder", type: "success" })
      void openPreview(saved.path || saved.src)
    } catch (err) {
      toast.add({
        title: err instanceof Error ? err.message : "Could not save that file.",
        type: "error",
      })
    }
  }

  const uploadDropped = async (file: File) => {
    try {
      const data = await api.packUpload(skill.absolute || skill.id, file)
      onSkill?.(data.skill)
      setAddOpen(false)
      toast.add({ title: "Saved into the skill folder", type: "success" })
      void openPreview(data.file.path || data.file.src)
    } catch (err) {
      toast.add({
        title: err instanceof Error ? err.message : "Could not upload that file.",
        type: "error",
      })
    }
  }

  const rawUrl = selected ? api.packRawUrl(skill.id, selected) : ""

  return (
    <Card id="skill-pack-files" className="overflow-x-visible overflow-y-visible">
      <CardHeader>
        <CardTitle>Pack files</CardTitle>
        <CardDescription>
          The skill folder — SKILL.md plus scripts, references, assets, and
          evals/fixtures. Checks reference these paths.
        </CardDescription>
        <CardAction>
          <div className="flex flex-wrap gap-2">
            <Button
              id="btn-view-dataset-pack"
              variant="outline"
              size="sm"
              className="touch-manipulation"
              aria-haspopup="dialog"
              aria-expanded={datasetOpen}
              translate="no"
              onClick={() => setDatasetOpen(true)}
            >
              View Dataset
            </Button>
            <Button
              id="btn-add-artifact"
              variant="outline"
              size="sm"
              onClick={() => setAddOpen(true)}
            >
              <PlusIcon data-icon="inline-start" />
              Add artifact
            </Button>
          </div>
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {rows.length === 0 ? (
          <Empty>
            <EmptyHeader>
              <EmptyMedia variant="icon">
                <FolderIcon />
              </EmptyMedia>
              <EmptyTitle>No pack files yet</EmptyTitle>
              <EmptyDescription>
                Add a fixture, sample, or notes file to this skill folder.
              </EmptyDescription>
            </EmptyHeader>
          </Empty>
        ) : (
          <div className="grid gap-4 xl:grid-cols-2">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Path</TableHead>
                  <TableHead>Size</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((item) => (
                  <TableRow
                    key={item.path}
                    data-selected={selected === item.path || undefined}
                    className="cursor-pointer"
                    onClick={() => void openPreview(item.path)}
                  >
                    <TableCell className="font-mono text-xs">{item.path}</TableCell>
                    <TableCell className="text-muted-foreground">
                      {formatBytes(item.bytes)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <div id="skill-pack-preview" className="flex min-h-48 flex-col gap-2 rounded-xl border p-3">
              {previewError ? (
                <Alert variant="destructive">
                  <AlertTitle>Could not preview</AlertTitle>
                  <AlertDescription>{previewError}</AlertDescription>
                </Alert>
              ) : preview ? (
                <PackPreviewPane preview={preview} rawUrl={rawUrl} />
              ) : (
                <p className="text-sm text-muted-foreground">
                  Select a file to preview it.
                </p>
              )}
            </div>
          </div>
        )}
      </CardContent>
      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <DialogContent id="add-artifact-dialog" className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Add artifact</DialogTitle>
            <DialogDescription>
              Saved into this skill folder (evals/fixtures/ or assets/). Same pack
              Evaluate checks use.
            </DialogDescription>
          </DialogHeader>
          <FieldGroup
            onDragOver={(event) => {
              event.preventDefault()
            }}
            onDrop={(event) => {
              event.preventDefault()
              const file = event.dataTransfer.files?.[0]
              if (file) {
                void uploadDropped(file)
              }
            }}
          >
            <Field>
              <FieldLabel htmlFor="artifact-filename">Path</FieldLabel>
              <Input
                id="artifact-filename"
                value={filename}
                onChange={(event) => setFilename(event.target.value)}
                placeholder="evals/fixtures/notes.txt"
              />
              <FieldDescription>
                A bare name lands in evals/fixtures/.
              </FieldDescription>
            </Field>
            <Field>
              <FieldLabel htmlFor="artifact-paste">Paste text</FieldLabel>
              <Textarea
                id="artifact-paste"
                rows={6}
                value={paste}
                onChange={(event) => setPaste(event.target.value)}
                placeholder="Yesterday: shipped billing. Today: pairing. Blocker: none."
              />
            </Field>
            <Button
              type="button"
              variant="outline"
              render={<label htmlFor="artifact-upload" />}
            >
              <FileTextIcon data-icon="inline-start" />
              Drop a file
            </Button>
            <input
              id="artifact-upload"
              ref={fileRef}
              type="file"
              className="sr-only"
              onChange={(event) => {
                const file = event.target.files?.[0]
                if (file) {
                  void uploadDropped(file)
                }
                event.target.value = ""
              }}
            />
          </FieldGroup>
          <DialogFooter>
            <DialogClose render={<Button type="button" variant="outline" />}>
              Cancel
            </DialogClose>
            <Button id="btn-add-artifact-save" type="button" onClick={() => void savePasted()}>
              Save into pack
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      {onDatasetOpenChange ? null : (
        <DatasetViewer
          skillId={skill.absolute || skill.id}
          open={datasetOpen}
          onOpenChange={setDatasetOpen}
        />
      )}
    </Card>
  )
}

function PackPreviewPane({
  preview,
  rawUrl,
}: {
  preview: PackPreview
  rawUrl: string
}) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <p className="font-mono text-xs">{preview.path}</p>
        <Badge variant="outline">{preview.kind}</Badge>
      </div>
      {preview.kind === "text" && preview.text != null ? (
        <ScrollArea className="h-64">
          <pre className="whitespace-pre-wrap font-mono text-xs">{preview.text}</pre>
        </ScrollArea>
      ) : null}
      {preview.kind === "image" ? (
        <img alt={preview.path} src={rawUrl} className="max-h-80 rounded-lg border" />
      ) : null}
      {preview.kind === "pdf" ? (
        <iframe title={preview.path} src={rawUrl} className="h-80 w-full rounded-lg border" />
      ) : null}
      {preview.kind === "binary" ? (
        <p className="text-sm text-muted-foreground">
          Binary file · {formatBytes(preview.bytes)}
        </p>
      ) : null}
      <Button variant="outline" size="sm" render={<a href={rawUrl} target="_blank" rel="noreferrer" />}>
        Open file
      </Button>
    </div>
  )
}

function formatBytes(value?: number) {
  if (!value && value !== 0) {
    return "—"
  }
  if (value < 1024) {
    return `${value} B`
  }
  return `${(value / 1024).toFixed(1)} KB`
}
