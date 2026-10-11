import { useEffect, useRef, useState } from "react"
import { FileTextIcon, PlusIcon } from "lucide-react"

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
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
  EmptyTitle,
} from "@/components/ui/empty"
import { Field, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { Skeleton } from "@/components/ui/skeleton"
import { Spinner } from "@/components/ui/spinner"
import { Textarea } from "@/components/ui/textarea"
import { api, ApiError } from "@/lib/api"
import { matchesSkill } from "@/lib/dashboard-helpers"
import { useDashboard } from "@/lib/dashboard-provider"
import { skillOutputPath, type Check, type DatasetCase, type DatasetFilePreview, type DatasetView } from "@/lib/types"

type RowDraft = { input: string; expected: string }

const INPUT_PLACEHOLDER = "Cafe Luna, 123 Market St…"
const EXPECTED_PLACEHOLDER = '{"merchant":"Cafe Luna"}…'
const byteCount = new Intl.NumberFormat()

function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    return err.message
  }
  if (err instanceof Error) {
    return err.message
  }
  return "Could not load Dataset."
}

function fileBasename(rel: string): string {
  const parts = rel.replace(/\\/g, "/").split("/").filter(Boolean)
  return parts[parts.length - 1] || rel
}

function displayFileName(file: DatasetFilePreview): string {
  const dest = (file.dest || "").trim()
  if (dest) {
    return dest
  }
  return fileBasename(file.src || file.path || file.output_path || "")
}

function fileSuffix(file: DatasetFilePreview): string {
  const name = displayFileName(file).toLowerCase()
  const dot = name.lastIndexOf(".")
  return dot >= 0 ? name.slice(dot) : ""
}

function fileKindPhrase(file: DatasetFilePreview): "image" | "PDF" | "file" | null {
  const kind = (file.kind || "").toLowerCase()
  const suffix = fileSuffix(file)
  if (
    kind === "image" ||
    [".png", ".jpg", ".jpeg", ".gif", ".webp"].includes(suffix)
  ) {
    return "image"
  }
  if (kind === "pdf" || suffix === ".pdf") {
    return "PDF"
  }
  if (kind === "binary" || kind === "bytes") {
    return "file"
  }
  return null
}

function fileHeading(role: string, file: DatasetFilePreview): string {
  const kind = fileKindPhrase(file)
  if (kind === "image") {
    return `${role} (image)`
  }
  if (kind === "PDF") {
    return `${role} (PDF)`
  }
  if (kind === "file") {
    return `${role} (file)`
  }
  return role
}

function isFilePreview(file: DatasetFilePreview): boolean {
  return fileKindPhrase(file) != null
}

function canEditInputText(item: DatasetCase): boolean {
  return item.fixtures.every((file) => !isFilePreview(file))
}

function rowFileName(item: DatasetCase): string {
  const input = item.fixtures.find((file) => isFilePreview(file))
  if (input) {
    return displayFileName(input)
  }
  if (item.golden && isFilePreview(item.golden)) {
    return displayFileName(item.golden)
  }
  return ""
}

function formatByteCount(bytes: number): string {
  return `${byteCount.format(bytes)} bytes`
}

function draftFromCase(item: DatasetCase): RowDraft {
  return {
    input: item.fixtures
      .map((file) => file.text || file.body || "")
      .filter(Boolean)
      .join("\n"),
    expected: item.golden?.text || item.golden?.body || "",
  }
}

function draftsDiffer(
  view: DatasetView | null,
  drafts: Record<string, RowDraft>
): boolean {
  if (!view) {
    return false
  }
  return view.cases.some((item) => {
    const original = draftFromCase(item)
    const draft = drafts[item.id] || original
    return draft.input !== original.input || draft.expected !== original.expected
  })
}

function nextExampleId(items: DatasetCase[]): string {
  const used = new Set(items.map((item) => item.id))
  let n = 1
  while (used.has(`example-${n}`)) {
    n += 1
  }
  return `example-${n}`
}

function FilePreview({
  skillId,
  file,
  label,
}: {
  skillId: string
  file: DatasetFilePreview
  label: "Input" | "Expected output"
}) {
  const rawPath = file.path || file.src || ""
  const text = file.text || file.body || ""
  const name = displayFileName(file)
  const kind = fileKindPhrase(file)
  const heading = fileHeading(label, file)
  const identity = name || heading
  const [mediaFailed, setMediaFailed] = useState(false)

  useEffect(() => {
    setMediaFailed(false)
  }, [rawPath])

  return (
    <div className="flex min-w-0 flex-col gap-2">
      <p className="text-sm font-medium text-pretty">{heading}</p>
      {name ? (
        <p className="min-w-0 truncate text-sm" translate="no" title={name}>
          {name}
        </p>
      ) : null}
      {file.missing ? (
        <p className="text-sm text-muted-foreground">Missing from this skill.</p>
      ) : kind === "image" && rawPath && !mediaFailed ? (
        <img
          alt={identity}
          src={api.packRawUrl(skillId, rawPath)}
          width={640}
          height={192}
          className="max-h-48 w-auto rounded-lg border"
          onError={() => setMediaFailed(true)}
        />
      ) : kind === "PDF" && rawPath && !mediaFailed ? (
        <iframe
          title={identity}
          src={api.packRawUrl(skillId, rawPath)}
          width={640}
          height={192}
          className="h-48 w-full rounded-lg border"
          onError={() => setMediaFailed(true)}
        />
      ) : mediaFailed && (kind === "image" || kind === "PDF") ? (
        <p className="text-sm text-muted-foreground">
          {kind === "PDF"
            ? "Could not load this PDF."
            : "Could not load this image."}
        </p>
      ) : kind === "file" ? (
        <p className="text-sm text-muted-foreground">
          {file.bytes != null ? formatByteCount(file.bytes) : "No preview."}
        </p>
      ) : text ? (
        <pre className="max-h-48 overflow-auto rounded-lg border bg-muted p-3 font-mono text-xs whitespace-pre-wrap">
          {text}
        </pre>
      ) : (
        <p className="text-sm text-muted-foreground">
          {file.bytes != null ? formatByteCount(file.bytes) : "No preview."}
        </p>
      )}
    </div>
  )
}

function ExampleEditor({
  skillId,
  item,
  index,
  draft,
  saving,
  onDraft,
  onSave,
}: {
  skillId: string
  item: DatasetCase
  index: number
  draft: RowDraft
  saving: boolean
  onDraft: (patch: Partial<RowDraft>) => void
  onSave: () => void
}) {
  const editInput = canEditInputText(item)
  const fileName = rowFileName(item)
  return (
    <AccordionItem value={item.id}>
      <AccordionTrigger className="px-1">
        <span className="flex min-w-0 flex-1 items-center gap-2">
          <span className="truncate text-sm">Example {index + 1}</span>
          {fileName ? (
            <span className="min-w-0 truncate text-sm font-normal" translate="no">
              {fileName}
            </span>
          ) : null}
          {item.status === "pinned" ? (
            <Badge variant="secondary">Saved</Badge>
          ) : (
            <Badge variant="outline">Draft</Badge>
          )}
          {item.should_trigger === false ? (
            <Badge variant="outline">No skill</Badge>
          ) : null}
        </span>
      </AccordionTrigger>
      <AccordionContent>
        <div className="flex flex-col gap-4 px-1 pb-3">
          {item.prompt ? (
            <p className="line-clamp-4 text-sm text-pretty">{item.prompt}</p>
          ) : null}
          <FieldGroup>
            {editInput ? (
              <Field data-disabled={saving || undefined}>
                <FieldLabel htmlFor={`dataset-input-${item.id}`}>Input</FieldLabel>
                <Textarea
                  id={`dataset-input-${item.id}`}
                  name={`dataset-input-${item.id}`}
                  autoComplete="off"
                  rows={6}
                  value={draft.input}
                  placeholder={INPUT_PLACEHOLDER}
                  disabled={saving}
                  onChange={(event) => onDraft({ input: event.target.value })}
                />
              </Field>
            ) : item.fixtures.length === 0 ? (
              <p className="text-sm text-muted-foreground">No input.</p>
            ) : (
              item.fixtures.map((file) => (
                <FilePreview
                  key={`${item.id}-${file.src || file.path}`}
                  skillId={skillId}
                  file={file}
                  label="Input"
                />
              ))
            )}
            {item.golden && isFilePreview(item.golden) ? (
              <FilePreview
                skillId={skillId}
                file={item.golden}
                label="Expected output"
              />
            ) : (
              <Field data-disabled={saving || undefined}>
                <FieldLabel htmlFor={`dataset-expected-${item.id}`}>
                  Expected output
                </FieldLabel>
                <Textarea
                  id={`dataset-expected-${item.id}`}
                  name={`dataset-expected-${item.id}`}
                  autoComplete="off"
                  spellCheck={false}
                  rows={6}
                  value={draft.expected}
                  placeholder={EXPECTED_PLACEHOLDER}
                  disabled={saving}
                  onChange={(event) => onDraft({ expected: event.target.value })}
                />
              </Field>
            )}
            <div className="flex justify-end">
              <Button
                id={`btn-save-dataset-${item.id}`}
                type="button"
                size="sm"
                className="touch-manipulation"
                disabled={saving}
                onClick={onSave}
              >
                {saving ? <Spinner data-icon="inline-start" /> : null}
                {saving ? "Saving…" : "Save to Dataset"}
              </Button>
            </div>
          </FieldGroup>
        </div>
      </AccordionContent>
    </AccordionItem>
  )
}

export function DatasetViewer({
  skillId,
  open,
  onOpenChange,
}: {
  skillId: string
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const { pinDatasetChecks, skill, skills } = useDashboard()
  const outputSkill =
    (skill && matchesSkill(skill, skillId) ? skill : null) ||
    skills.find((item) => matchesSkill(item, skillId)) ||
    null
  const [view, setView] = useState<DatasetView | null>(null)
  const [drafts, setDrafts] = useState<Record<string, RowDraft>>({})
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)
  const [adding, setAdding] = useState(false)
  const [newInput, setNewInput] = useState("")
  const [newExpected, setNewExpected] = useState("")
  const [newError, setNewError] = useState("")
  const [savingId, setSavingId] = useState<string | null>(null)
  const [discardOpen, setDiscardOpen] = useState(false)
  const discardKind = useRef<"sheet" | "add">("sheet")
  const newInputRef = useRef<HTMLTextAreaElement>(null)
  const newExpectedRef = useRef<HTMLTextAreaElement>(null)

  const startAdding = () => {
    setAdding(true)
    setNewError("")
  }

  const clearNewRow = () => {
    setAdding(false)
    setNewInput("")
    setNewExpected("")
    setNewError("")
  }

  const loadView = async () => {
    const data = await api.dataset(skillId)
    setView(data)
    setDrafts(
      Object.fromEntries(data.cases.map((item) => [item.id, draftFromCase(item)]))
    )
  }

  useEffect(() => {
    if (!open || !skillId) {
      return
    }
    let cancelled = false
    setLoading(true)
    setError("")
    setAdding(false)
    setNewInput("")
    setNewExpected("")
    setNewError("")
    setDiscardOpen(false)
    void api
      .dataset(skillId)
      .then((data) => {
        if (!cancelled) {
          setView(data)
          setDrafts(
            Object.fromEntries(
              data.cases.map((item) => [item.id, draftFromCase(item)])
            )
          )
        }
      })
      .catch((err) => {
        if (!cancelled) {
          const message = errorMessage(err)
          if (message.toLowerCase().includes("no dataset")) {
            setView({ skill: skillId, cases: [] })
            setDrafts({})
            setError("")
            return
          }
          setView(null)
          setError(message)
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [open, skillId])

  useEffect(() => {
    if (!adding) {
      return
    }
    if (!window.matchMedia("(pointer: fine)").matches) {
      return
    }
    newInputRef.current?.focus()
  }, [adding])

  const saveCheck = async (check: Check, rowId: string) => {
    setSavingId(rowId)
    try {
      const ok = await pinDatasetChecks([check], skillId)
      if (ok) {
        await loadView()
        if (rowId === "new") {
          clearNewRow()
        }
      }
    } finally {
      setSavingId(null)
    }
  }

  const saveNewRow = () => {
    const input = newInput.trim()
    const expected = newExpected.trim()
    if (!input || !expected) {
      setNewError("Add input and expected output.")
      const target = !input ? newInputRef.current : newExpectedRef.current
      target?.focus()
      return
    }
    const items = view?.cases ?? []
    const prompt =
      items.find((item) => item.prompt.trim())?.prompt.trim() || "Use this input."
    const outputPath =
      items.find((item) => item.golden?.output_path)?.golden?.output_path ||
      skillOutputPath(outputSkill)
    void saveCheck(
      {
        id: nextExampleId(items),
        prompt,
        should_trigger: true,
        input,
        contains: expected,
        output_path: outputPath,
      },
      "new"
    )
  }

  const saveExisting = (item: DatasetCase) => {
    const draft = drafts[item.id] || draftFromCase(item)
    const files = item.fixtures
      .filter((file) => file.src || file.path)
      .map((file) => ({
        src: file.src || file.path || "",
        dest: file.dest || fileBasename(file.src || file.path || ""),
      }))
    const check: Check = {
      id: item.id,
      prompt: item.prompt || "Use this input.",
      should_trigger: item.should_trigger !== false,
      output_path: item.golden?.output_path || skillOutputPath(outputSkill),
      contains: draft.expected,
      files,
      golden_path: item.golden?.path || null,
    }
    if (canEditInputText(item)) {
      check.input = draft.input
    }
    void saveCheck(check, item.id)
  }

  const empty = !view || view.cases.length === 0
  const unsavedNewRow = adding && Boolean(newInput.trim() || newExpected.trim())
  const unsavedEdits = draftsDiffer(view, drafts)
  const dirty = unsavedNewRow || unsavedEdits

  const requestDiscard = (kind: "sheet" | "add") => {
    discardKind.current = kind
    setDiscardOpen(true)
  }

  const handleOpenChange = (next: boolean) => {
    if (!next && dirty) {
      requestDiscard("sheet")
      return
    }
    onOpenChange(next)
  }

  const cancelAdd = () => {
    if (unsavedNewRow) {
      requestDiscard("add")
      return
    }
    clearNewRow()
  }

  const confirmDiscard = () => {
    const kind = discardKind.current
    setDiscardOpen(false)
    if (kind === "add") {
      clearNewRow()
      return
    }
    clearNewRow()
    onOpenChange(false)
  }

  return (
    <>
      <Sheet open={open} onOpenChange={handleOpenChange}>
        <SheetContent
          id="dataset-viewer"
          side="right"
          className="w-full overscroll-contain pb-[env(safe-area-inset-bottom)] motion-reduce:transition-none sm:max-w-xl"
        >
          <SheetHeader>
            <SheetTitle translate="no">Dataset</SheetTitle>
            <SheetDescription className="text-pretty">
              Examples in this Dataset. Add or edit input and expected output.
            </SheetDescription>
          </SheetHeader>
          <div className="flex items-center px-4">
            <Button
              id="btn-add-dataset-row"
              type="button"
              variant="outline"
              size="sm"
              className="touch-manipulation"
              disabled={loading || savingId !== null}
              onClick={startAdding}
            >
              <PlusIcon data-icon="inline-start" aria-hidden="true" />
              Add Row
            </Button>
          </div>
          <ScrollArea className="min-h-0 flex-1 overscroll-contain px-4 pb-4">
            {loading ? (
              <div
                id="dataset-viewer-loading"
                className="flex flex-col gap-3"
                aria-live="polite"
                aria-busy="true"
              >
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Spinner aria-hidden="true" />
                  Loading Dataset…
                </div>
                <Skeleton className="h-16 w-full rounded-xl" />
                <Skeleton className="h-16 w-full rounded-xl" />
              </div>
            ) : error ? (
              <Alert>
                <FileTextIcon aria-hidden="true" />
                <AlertTitle>Could not open Dataset</AlertTitle>
                <AlertDescription>
                  {error} Close, then View Dataset again.
                </AlertDescription>
              </Alert>
            ) : (
              <div className="flex flex-col gap-4">
                {adding ? (
                  <FieldGroup id="dataset-new-row">
                    <Field data-invalid={newError && !newInput.trim() ? true : undefined}>
                      <FieldLabel htmlFor="dataset-new-input">Input</FieldLabel>
                      <Textarea
                        id="dataset-new-input"
                        ref={newInputRef}
                        name="dataset-input"
                        autoComplete="off"
                        rows={6}
                        value={newInput}
                        placeholder={INPUT_PLACEHOLDER}
                        disabled={savingId === "new"}
                        aria-invalid={newError && !newInput.trim() ? true : undefined}
                        onChange={(event) => {
                          setNewInput(event.target.value)
                          if (newError) {
                            setNewError("")
                          }
                        }}
                      />
                    </Field>
                    <Field data-invalid={newError && !newExpected.trim() ? true : undefined}>
                      <FieldLabel htmlFor="dataset-new-expected">
                        Expected output
                      </FieldLabel>
                      <Textarea
                        id="dataset-new-expected"
                        ref={newExpectedRef}
                        name="dataset-expected-output"
                        autoComplete="off"
                        spellCheck={false}
                        rows={6}
                        value={newExpected}
                        placeholder={EXPECTED_PLACEHOLDER}
                        disabled={savingId === "new"}
                        aria-invalid={newError && !newExpected.trim() ? true : undefined}
                        onChange={(event) => {
                          setNewExpected(event.target.value)
                          if (newError) {
                            setNewError("")
                          }
                        }}
                      />
                      {newError ? (
                        <FieldError role="alert">{newError}</FieldError>
                      ) : null}
                    </Field>
                    <div className="flex justify-end gap-2">
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="touch-manipulation"
                        disabled={savingId === "new"}
                        onClick={cancelAdd}
                      >
                        Cancel
                      </Button>
                      <Button
                        id="btn-save-dataset-row"
                        type="button"
                        size="sm"
                        className="touch-manipulation"
                        disabled={savingId === "new"}
                        onClick={saveNewRow}
                      >
                        {savingId === "new" ? (
                          <Spinner data-icon="inline-start" />
                        ) : null}
                        {savingId === "new" ? "Saving…" : "Save to Dataset"}
                      </Button>
                    </div>
                  </FieldGroup>
                ) : null}
                {empty && !adding ? (
                  <Empty>
                    <EmptyHeader>
                      <EmptyTitle>No Dataset yet</EmptyTitle>
                      <EmptyDescription>
                        Add a row with input and expected output.
                      </EmptyDescription>
                    </EmptyHeader>
                    <EmptyContent>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="touch-manipulation"
                        onClick={startAdding}
                      >
                        <PlusIcon data-icon="inline-start" aria-hidden="true" />
                        Add Row
                      </Button>
                    </EmptyContent>
                  </Empty>
                ) : null}
                {!empty ? (
                  <Accordion
                    key={view.fingerprint || view.cases.map((item) => item.id).join()}
                    defaultValue={view.cases[0]?.id ? [view.cases[0].id] : []}
                    className="w-full"
                  >
                    {view.cases.map((item, index) => (
                      <ExampleEditor
                        key={item.id}
                        skillId={skillId}
                        item={item}
                        index={index}
                        draft={drafts[item.id] || draftFromCase(item)}
                        saving={savingId === item.id}
                        onDraft={(patch) =>
                          setDrafts((current) => ({
                            ...current,
                            [item.id]: {
                              ...(current[item.id] || draftFromCase(item)),
                              ...patch,
                            },
                          }))
                        }
                        onSave={() => saveExisting(item)}
                      />
                    ))}
                  </Accordion>
                ) : null}
              </div>
            )}
          </ScrollArea>
        </SheetContent>
      </Sheet>
      <Dialog open={discardOpen} onOpenChange={setDiscardOpen}>
        <DialogContent
          id="dataset-discard-dialog"
          showCloseButton={false}
          className="sm:max-w-sm"
        >
          <DialogHeader>
            <DialogTitle>Discard unsaved changes?</DialogTitle>
            <DialogDescription>
              Input and expected output that are not saved will be lost.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setDiscardOpen(false)}
            >
              Keep Editing
            </Button>
            <Button type="button" variant="destructive" onClick={confirmDiscard}>
              Discard
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
