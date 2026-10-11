import { FolderOpenIcon } from "lucide-react"

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
} from "@/components/ui/empty"
import {
  Field,
  FieldContent,
  FieldDescription,
  FieldGroup,
  FieldLabel,
  FieldLegend,
  FieldSet,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { authenticFixtureDefaults } from "@/lib/check-guards"
import type { Check, PackFile, SkillPayload } from "@/lib/types"

function fileParts(path: string) {
  const name = path.split("/").pop() || path
  const dot = name.lastIndexOf(".")
  if (dot <= 0) {
    return { name, stem: name, ext: "" }
  }
  return { name, stem: name.slice(0, dot), ext: name.slice(dot) }
}

export function FixtureBindAccordion({
  skill,
  packFiles,
  checks,
  inherit,
  glob,
  disabled,
  onInheritChange,
  onGlobChange,
  onExpand,
}: {
  skill: SkillPayload | null
  packFiles: PackFile[]
  checks: Check[]
  inherit: boolean
  glob: string
  disabled?: boolean
  onInheritChange: (next: boolean) => void
  onGlobChange: (next: string) => void
  onExpand: () => void
}) {
  const dataset = authenticFixtureDefaults(skill, packFiles)
  const needsUpload = checks.some((check) => check.needs_upload)
  if (!skill || (!dataset.length && !needsUpload)) {
    return null
  }
  const names = dataset.map((item) => item.path.split("/").pop() || item.path)
  const summary = !dataset.length
    ? "Add a sample file to this skill to bind completion checks"
    : inherit
      ? names.join(", ")
      : `Not using skill files: ${names.join(", ")}`

  return (
    <Accordion defaultValue={[]} id="fixture-bind-accordion">
      <AccordionItem value="fixture-bind" className="rounded-lg border px-2">
        <AccordionTrigger className="py-1.5 hover:no-underline">
          <span className="flex min-w-0 flex-1 items-center gap-2 pr-2">
            <span className="sr-only">Skill files </span>
            <span
              id="fixture-bind-summary"
              title={summary}
              className="min-w-0 flex-1 truncate text-left text-sm font-normal text-pretty text-muted-foreground"
            >
              {summary}
            </span>
          </span>
        </AccordionTrigger>
        <AccordionContent>
          {dataset.length ? (
            <FieldSet>
              <FieldLegend className="sr-only">Skill files</FieldLegend>
              <FieldGroup className="gap-4">
                <ul
                  id="pack-fixture-chips"
                  className="flex flex-wrap gap-1.5"
                >
                  {dataset.map((item) => {
                    const { name, stem, ext } = fileParts(item.path)
                    return (
                      <li key={item.path} className="max-w-full min-w-0">
                        <Badge
                          variant="secondary"
                          aria-label={item.path}
                          title={item.path}
                          className="h-7 max-w-full gap-0 rounded-sm px-2 font-medium tracking-tight whitespace-nowrap"
                        >
                          <span className="truncate">{stem}</span>
                          {ext ? (
                            <span className="shrink-0 font-normal text-muted-foreground">
                              {ext}
                            </span>
                          ) : (
                            <span className="sr-only">{name}</span>
                          )}
                        </Badge>
                      </li>
                    )
                  })}
                </ul>
                <Field
                  orientation="horizontal"
                  className="min-h-11 items-center"
                  data-disabled={disabled || undefined}
                >
                  <Checkbox
                    id="btn-use-pack-fixtures"
                    checked={inherit}
                    disabled={disabled || dataset.length === 0}
                    onCheckedChange={(checked) =>
                      onInheritChange(checked === true)
                    }
                  />
                  <FieldContent>
                    <FieldLabel htmlFor="btn-use-pack-fixtures">
                      Use this skill’s files for completion checks
                    </FieldLabel>
                    <FieldDescription>
                      Completion rows inherit these files unless a row already
                      picked its own. Trigger and should-not-trigger rows stay
                      file-free.
                    </FieldDescription>
                  </FieldContent>
                </Field>
                <Field data-disabled={disabled || undefined}>
                  <FieldLabel htmlFor="fixture-glob">Which files</FieldLabel>
                  <Input
                    id="fixture-glob"
                    value={glob}
                    disabled={disabled}
                    onChange={(event) => onGlobChange(event.target.value)}
                    placeholder="samples/*"
                    className="text-sm"
                  />
                </Field>
                <Field>
                  <Button
                    id="btn-expand-fixtures"
                    type="button"
                    variant="outline"
                    size="sm"
                    className="min-h-11"
                    disabled={disabled || dataset.length === 0}
                    onClick={onExpand}
                  >
                    <FolderOpenIcon data-icon="inline-start" />
                    Make cases from folder
                  </Button>
                  <FieldDescription>
                    One prompt template times each file. Existing completion
                    rows are replaced; trigger and negative rows stay.
                  </FieldDescription>
                </Field>
              </FieldGroup>
            </FieldSet>
          ) : (
            <Empty className="border-0 px-1 py-3">
              <EmptyHeader>
                <EmptyTitle className="text-pretty">
                  Add a sample file to this skill to bind completion checks
                </EmptyTitle>
                <EmptyDescription className="text-pretty">
                  Upload a real file into this skill folder. Completion checks
                  inherit it here, not as a per-row attach.
                </EmptyDescription>
              </EmptyHeader>
            </Empty>
          )}
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  )
}
