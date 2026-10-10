import { useEffect, useState, type FormEvent } from "react"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { Spinner } from "@/components/ui/spinner"
import { Textarea } from "@/components/ui/textarea"
import { toast } from "@/components/ui/toast"
import { api } from "@/lib/api"
import { useDashboard } from "@/lib/dashboard-provider"
import { draftCheckFromFailure } from "@/lib/promote-check"
import { skillOutputPath, type Check, type CheckFile, type PromoteDraft, type TaskResult } from "@/lib/types"

export function PromoteCheckDialog({
  task,
  open,
  onOpenChange,
}: {
  task: TaskResult | null
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const { skill, checks, addCheck, applySkill, setEvalTab } = useDashboard()
  const [loading, setLoading] = useState(false)
  const [prompt, setPrompt] = useState("")
  const [shouldTrigger, setShouldTrigger] = useState(true)
  const [outputPath, setOutputPath] = useState("")
  const [expected, setExpected] = useState("")
  const [files, setFiles] = useState<CheckFile[]>([])
  const [minPages, setMinPages] = useState<number | null>(null)
  const [draftId, setDraftId] = useState("")
  const [hints, setHints] = useState<string[]>([])
  const [promptError, setPromptError] = useState("")

  useEffect(() => {
    if (!open || !task) {
      return
    }
    if (task.passed !== false) {
      onOpenChange(false)
      return
    }
    let cancelled = false
    setLoading(true)
    setPromptError("")
    const apply = (draft: PromoteDraft) => {
      if (cancelled) {
        return
      }
      const check = draft.check
      setDraftId(check.id || "")
      setPrompt(check.prompt)
      setShouldTrigger(check.should_trigger !== false)
      setExpected(check.contains ?? "")
      setOutputPath(check.output_path ?? "")
      setFiles((check.files || []) as CheckFile[])
      setMinPages(check.min_pages ?? null)
      setHints(draft.hints)
    }
    void api
      .promoteDraft(task, checks, skill?.absolute || skill?.id)
      .then((draft) => {
        apply(draft)
        if (draft.skill) {
          applySkill(draft.skill)
        }
      })
      .catch(() => {
        try {
          apply(draftCheckFromFailure(task, checks, skillOutputPath(skill)))
        } catch {
          if (!cancelled) {
            toast.add({
              title: "Could not draft a check from this failed task.",
              type: "error",
            })
            onOpenChange(false)
          }
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
  }, [open, task])

  const submit = (event: FormEvent) => {
    event.preventDefault()
    const nextPrompt = prompt.trim()
    if (!nextPrompt) {
      setPromptError("Write what this check should ask the agent.")
      return
    }
    const nextExpected = expected.trim()
    const nextOutput = outputPath.trim() || (nextExpected ? skillOutputPath(skill) : "")
    const check: Partial<Check> = {
      id: draftId,
      prompt: nextPrompt,
      should_trigger: shouldTrigger,
      output_path: nextOutput,
      contains: nextExpected,
      min_pages: minPages,
      files,
      needs_upload: false,
    }
    addCheck(check)
    toast.add({ title: "Check added to suite", type: "success" })
    setEvalTab("checks")
    onOpenChange(false)
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        id="promote-check-dialog"
        side="right"
        className="w-full sm:max-w-lg"
      >
        <SheetHeader>
          <SheetTitle>Promote to check</SheetTitle>
          <SheetDescription>
            {skill
              ? `Drafted from the failed Gate task for ${skill.name}. Edit, then save — nothing is added until you save.`
              : "Edit this draft, then save. Nothing is added until you save."}
          </SheetDescription>
        </SheetHeader>
        {loading ? (
          <div className="flex items-center gap-2 px-4 py-6 text-sm text-muted-foreground">
            <Spinner />
            Drafting from the failed run…
          </div>
        ) : (
          <form
            id="promote-check-form"
            className="flex min-h-0 flex-1 flex-col"
            onSubmit={submit}
          >
            <ScrollArea className="min-h-0 flex-1 px-4">
              <div className="flex flex-col gap-4 pb-4">
                {hints.length ? (
                  <Alert id="promote-check-hints">
                    <AlertTitle>From the failed run</AlertTitle>
                    <AlertDescription>
                      <div className="flex flex-col gap-1">
                        {hints.map((hint) => (
                          <p key={hint}>{hint}</p>
                        ))}
                      </div>
                    </AlertDescription>
                  </Alert>
                ) : null}
                <FieldGroup>
                  <Field data-invalid={promptError ? true : undefined}>
                    <FieldLabel htmlFor="promote-check-prompt">Prompt</FieldLabel>
                    <Textarea
                      id="promote-check-prompt"
                      rows={4}
                      value={prompt}
                      aria-invalid={promptError ? true : undefined}
                      onChange={(event) => {
                        setPrompt(event.target.value)
                        if (promptError) {
                          setPromptError("")
                        }
                      }}
                    />
                    {promptError ? <FieldError>{promptError}</FieldError> : null}
                  </Field>
                  <Field orientation="horizontal">
                    <Checkbox
                      id="promote-check-trigger"
                      checked={shouldTrigger}
                      onCheckedChange={(checked) =>
                        setShouldTrigger(checked === true)
                      }
                    />
                    <FieldLabel htmlFor="promote-check-trigger">
                      This should trigger the skill
                    </FieldLabel>
                  </Field>
                  <Field>
                    <FieldLabel htmlFor="promote-check-expected">
                      Expected
                    </FieldLabel>
                    <Input
                      id="promote-check-expected"
                      value={expected}
                      placeholder="Hello Skill Gate"
                      onChange={(event) => setExpected(event.target.value)}
                    />
                    <FieldDescription>
                      Optional substring the output should contain.
                    </FieldDescription>
                  </Field>
                  <Field>
                    <FieldLabel htmlFor="promote-check-output">
                      Output file (optional)
                    </FieldLabel>
                    <Input
                      id="promote-check-output"
                      value={outputPath}
                      placeholder={skillOutputPath(skill)}
                      onChange={(event) => setOutputPath(event.target.value)}
                    />
                    <FieldDescription>
                      Used when Expected is set.
                    </FieldDescription>
                  </Field>
                  {files.length ? (
                    <Field>
                      <FieldLabel>Pack files</FieldLabel>
                      <FieldDescription>
                        Copied into this skill folder.
                      </FieldDescription>
                      <div className="flex flex-wrap gap-2" id="promote-check-files">
                        {files.map((file, fileIndex) => (
                          <span
                            key={`${file.src}-${fileIndex}`}
                            className="font-mono text-xs text-muted-foreground"
                          >
                            {file.src}
                          </span>
                        ))}
                      </div>
                    </Field>
                  ) : null}
                </FieldGroup>
              </div>
            </ScrollArea>
            <SheetFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => onOpenChange(false)}
              >
                Cancel
              </Button>
              <Button id="btn-promote-check-save" type="submit">
                Save check
              </Button>
            </SheetFooter>
          </form>
        )}
      </SheetContent>
    </Sheet>
  )
}
