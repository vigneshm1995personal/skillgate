import { useEffect, useState, type FormEvent } from "react"
import { FileTextIcon } from "lucide-react"

import { CheckInputControls } from "@/components/dashboard/check-input"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
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
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty"
import {
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { toast } from "@/components/ui/toast"
import { useDashboard } from "@/lib/dashboard-provider"
import { skillOutputPath, type CheckFile } from "@/lib/types"

export function AddCheckDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const { skill, addCheck, applySkill, setEvalTab, fixtureInherit } =
    useDashboard()
  const [prompt, setPrompt] = useState("")
  const [shouldTrigger, setShouldTrigger] = useState(true)
  const [outputPath, setOutputPath] = useState("")
  const [expected, setExpected] = useState("")
  const [files, setFiles] = useState<CheckFile[]>([])
  const [needsUpload, setNeedsUpload] = useState(false)
  const [promptError, setPromptError] = useState("")

  useEffect(() => {
    if (!open) {
      return
    }
    setPrompt("")
    setShouldTrigger(true)
    setOutputPath("")
    setExpected("")
    setFiles([])
    setNeedsUpload(false)
    setPromptError("")
  }, [open])

  const submit = (event: FormEvent) => {
    event.preventDefault()
    const nextPrompt = prompt.trim()
    if (!nextPrompt) {
      setPromptError("Write what this check should ask the agent.")
      return
    }
    const nextExpected = shouldTrigger ? expected.trim() : ""
    const nextOutput = shouldTrigger
      ? outputPath.trim() || (nextExpected ? skillOutputPath(skill) : "")
      : ""
    addCheck({
      prompt: nextPrompt,
      should_trigger: shouldTrigger,
      output_path: nextOutput,
      contains: nextExpected,
      files,
      needs_upload: needsUpload && files.length === 0,
    })
    toast.add({ title: "Check added", type: "success" })
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent id="add-check-dialog" className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Add a check</DialogTitle>
          <DialogDescription>
            {skill
              ? `This check will run against ${skill.name}.`
              : "Pick a skill first, then describe the check."}
          </DialogDescription>
        </DialogHeader>
        {skill ? (
          <form className="flex w-full flex-col gap-4" onSubmit={submit}>
            <FieldGroup>
              <Field data-invalid={promptError ? true : undefined}>
                <FieldLabel htmlFor="new-check-prompt">Prompt</FieldLabel>
                <Textarea
                  id="new-check-prompt"
                  rows={4}
                  value={prompt}
                  aria-invalid={promptError ? true : undefined}
                  placeholder={`Extract the title from invoices/hello.pdf and write it to ${skillOutputPath(skill)}`}
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
                  id="new-check-trigger"
                  checked={shouldTrigger}
                  onCheckedChange={(checked) =>
                    setShouldTrigger(checked === true)
                  }
                />
                <FieldLabel htmlFor="new-check-trigger">
                  This should trigger the skill
                </FieldLabel>
              </Field>
              {shouldTrigger ? (
                <>
                  <Field>
                    <FieldLabel htmlFor="new-check-expected">Expected</FieldLabel>
                    <Input
                      id="new-check-expected"
                      value={expected}
                      placeholder="Hello Skill Gate"
                      onChange={(event) => setExpected(event.target.value)}
                    />
                  </Field>
                  <Field>
                    <FieldLabel htmlFor="new-check-output">
                      Output file (optional)
                    </FieldLabel>
                    <Input
                      id="new-check-output"
                      value={outputPath}
                      placeholder={skillOutputPath(skill)}
                      onChange={(event) => setOutputPath(event.target.value)}
                    />
                    <FieldDescription>Used when Expected is set.</FieldDescription>
                  </Field>
                </>
              ) : null}
              <CheckInputControls
                check={{
                  prompt,
                  should_trigger: shouldTrigger,
                  output_path: outputPath,
                  contains: expected,
                  files,
                  needs_upload: needsUpload,
                }}
                skill={skill}
                packFiles={skill?.pack_files ?? []}
                inherit={fixtureInherit}
                onUpdate={(patch) => {
                  if (patch.prompt != null) {
                    setPrompt(patch.prompt)
                  }
                  if (patch.files) {
                    setFiles(patch.files)
                  }
                  if (patch.needs_upload != null) {
                    setNeedsUpload(patch.needs_upload)
                  }
                }}
                onSkill={applySkill}
              />
            </FieldGroup>
            <DialogFooter>
              <DialogClose render={<Button type="button" variant="outline" />}>
                Cancel
              </DialogClose>
              <Button id="btn-add-check-save" type="submit">
                Add check
              </Button>
            </DialogFooter>
          </form>
        ) : (
          <>
            <Empty className="border">
              <EmptyHeader>
                <EmptyMedia variant="icon">
                  <FileTextIcon />
                </EmptyMedia>
                <EmptyTitle>Select a skill first</EmptyTitle>
                <EmptyDescription>
                  Checks belong to a skill. Pick one on the Skill tab, then add
                  a check here.
                </EmptyDescription>
              </EmptyHeader>
              <EmptyContent>
                <Button
                  onClick={() => {
                    onOpenChange(false)
                    setEvalTab("skill")
                  }}
                >
                  Select a skill
                </Button>
              </EmptyContent>
            </Empty>
            <DialogFooter>
              <DialogClose render={<Button type="button" variant="outline" />}>
                Close
              </DialogClose>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
