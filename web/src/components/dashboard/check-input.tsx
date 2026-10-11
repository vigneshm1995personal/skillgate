import { useRef, useState } from "react"
import { PlusIcon } from "lucide-react"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
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
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Textarea } from "@/components/ui/textarea"
import { toast } from "@/components/ui/toast"
import { api } from "@/lib/api"
import {
  NEEDS_UPLOAD_NOTICE,
  checkNeedsInput,
  displayCheckFiles,
  filesAreInherited,
} from "@/lib/check-guards"
import type { Check, CheckFile, PackFile, SkillPayload } from "@/lib/types"

export function CheckInputControls({
  check,
  index,
  skill,
  packFiles,
  inherit = true,
  disabled,
  onUpdate,
  onSkill,
}: {
  check: Check
  index?: number
  skill: SkillPayload | null
  packFiles: PackFile[]
  inherit?: boolean
  disabled?: boolean
  onUpdate: (patch: Partial<Check>) => void
  onSkill?: (skill: SkillPayload) => void
}) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [factsOpen, setFactsOpen] = useState(false)
  const [facts, setFacts] = useState("")
  const attached = check.files ?? []
  const files = displayCheckFiles(check, inherit, skill)
  const inherited = filesAreInherited(check, inherit, skill)
  const needsInput = checkNeedsInput(check, inherit, skill)
  const suffix = index != null ? `-${index}` : ""

  const applyFile = (file: CheckFile, nextSkill?: SkillPayload) => {
    onUpdate({
      files: [...attached, { src: file.src, dest: file.dest }],
      needs_upload: false,
    })
    if (nextSkill) {
      onSkill?.(nextSkill)
    }
  }

  const attachPackPath = (path: string) => {
    const dest = path.split("/").pop() || path
    applyFile({ src: path, dest })
  }

  const generateSample = async () => {
    const skillId = skill?.absolute || skill?.id
    if (!skillId) {
      toast.add({ title: "Pick a skill first.", type: "error" })
      return
    }
    try {
      const data = await api.packFile({
        skill: skillId,
        generate: true,
        prompt: check.prompt,
      })
      if (data.needs_upload || !data.file) {
        onUpdate({ needs_upload: true })
        toast.add({
          title:
            data.message ||
            "This check needs a real photo or scan — upload one instead of a generated sample.",
          type: "error",
        })
        return
      }
      applyFile(data.file, data.skill)
      toast.add({ title: "Sample saved in the skill folder", type: "success" })
    } catch (err) {
      toast.add({
        title:
          err instanceof Error ? err.message : "Could not generate a sample.",
        type: "error",
      })
    }
  }

  const uploadFile = async (file: File) => {
    const skillId = skill?.absolute || skill?.id
    if (!skillId) {
      toast.add({ title: "Pick a skill first.", type: "error" })
      return
    }
    try {
      const data = await api.packUpload(skillId, file)
      applyFile(data.file, data.skill)
      toast.add({ title: "File saved in the skill folder", type: "success" })
    } catch (err) {
      toast.add({
        title:
          err instanceof Error ? err.message : "Could not upload that file.",
        type: "error",
      })
    }
  }

  const applyFacts = () => {
    const extra = facts.trim()
    if (!extra) {
      return
    }
    const prompt = check.prompt.trim()
    onUpdate({
      prompt: prompt ? `${prompt}\n\n${extra}` : extra,
      needs_upload: false,
    })
    setFacts("")
    setFactsOpen(false)
  }

  const removeFile = (fileIndex: number) => {
    onUpdate({
      files: attached.filter((_, i) => i !== fileIndex),
    })
  }

  return (
    <div className="flex flex-col gap-2">
      {needsInput ? (
        <Alert id={`check-needs-upload${suffix}`}>
          <AlertTitle>Needs input</AlertTitle>
          <AlertDescription>{NEEDS_UPLOAD_NOTICE}</AlertDescription>
        </Alert>
      ) : null}
      <div className="flex flex-wrap items-center gap-2">
        <DropdownMenu>
          <DropdownMenuTrigger
            id={`check-add-input${suffix}`}
            disabled={disabled || !skill}
            render={<Button variant="outline" size="sm" />}
          >
            <PlusIcon data-icon="inline-start" />
            Add input
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            <DropdownMenuGroup>
              <DropdownMenuItem onClick={() => setFactsOpen(true)}>
                Paste into prompt
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => fileRef.current?.click()}>
                Upload file
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => void generateSample()}>
                Generate sample
              </DropdownMenuItem>
              {packFiles.filter((item) => item.path !== "SKILL.md").length ? (
                <DropdownMenuSub>
                  <DropdownMenuSubTrigger>
                    Attach from pack
                  </DropdownMenuSubTrigger>
                  <DropdownMenuSubContent>
                    <DropdownMenuGroup>
                      {packFiles
                        .filter((item) => item.path !== "SKILL.md")
                        .map((item) => (
                          <DropdownMenuItem
                            key={item.path}
                            onClick={() => attachPackPath(item.path)}
                          >
                            {item.path}
                          </DropdownMenuItem>
                        ))}
                    </DropdownMenuGroup>
                  </DropdownMenuSubContent>
                </DropdownMenuSub>
              ) : null}
            </DropdownMenuGroup>
          </DropdownMenuContent>
        </DropdownMenu>
        <input
          ref={fileRef}
          id={`check-upload${suffix}`}
          type="file"
          className="sr-only"
          disabled={disabled || !skill}
          onChange={(event) => {
            const file = event.target.files?.[0]
            if (file) {
              void uploadFile(file)
            }
            event.target.value = ""
          }}
        />
      </div>
      {files.length ? (
        <div className="flex flex-wrap gap-2" id={`check-files${suffix}`}>
          {files.map((file, fileIndex) => (
            <Badge
              key={`${file.src}-${fileIndex}`}
              variant={inherited ? "secondary" : "outline"}
              title={
                inherited
                  ? `${file.dest || file.src} from pack fixtures`
                  : undefined
              }
            >
              {file.dest || file.src}
              {disabled || inherited ? null : (
                <button
                  type="button"
                  className="ml-1 text-muted-foreground"
                  onClick={() => removeFile(fileIndex)}
                >
                  ×
                </button>
              )}
            </Badge>
          ))}
        </div>
      ) : null}
      <Dialog open={factsOpen} onOpenChange={setFactsOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Paste into prompt</DialogTitle>
            <DialogDescription>
              Facts a user would type — standup bullets, invoice #, merchant,
              amounts.
            </DialogDescription>
          </DialogHeader>
          <FieldGroup>
            <Field>
              <FieldLabel htmlFor={`check-facts${suffix}`}>Facts</FieldLabel>
              <Textarea
                id={`check-facts${suffix}`}
                rows={5}
                value={facts}
                onChange={(event) => setFacts(event.target.value)}
                placeholder="Yesterday: shipped billing. Today: pairing on checks. Blocker: review."
              />
            </Field>
          </FieldGroup>
          <DialogFooter>
            <DialogClose render={<Button type="button" variant="outline" />}>
              Cancel
            </DialogClose>
            <Button type="button" onClick={applyFacts}>
              Add to prompt
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
