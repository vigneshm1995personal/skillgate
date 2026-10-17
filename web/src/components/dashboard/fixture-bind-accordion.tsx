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
import { authenticFixtureDefaults, leakedPdfDemoNames } from "@/lib/check-guards"
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
  const ignored = leakedPdfDemoNames(skill, packFiles)
  if (!skill) {
    return null
  }
  const summary = !dataset.length
    ? ignored.length
      ? "No sample files for this skill"
      : "No sample files yet"
    : inherit
      ? `${dataset.length} sample file${dataset.length === 1 ? "" : "s"}`
      : "Sample files are off"

  return (
    <Accordion defaultValue={[]} id="fixture-bind-accordion">
      <AccordionItem value="fixture-bind" className="rounded-lg border px-2">
        <AccordionTrigger className="py-1.5 hover:no-underline">
          <span className="flex min-w-0 flex-1 items-center gap-2 pr-2">
            <span className="text-sm font-medium text-foreground">Sample files</span>
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
          <p className="mb-3 text-sm text-muted-foreground">
            These are the files in this skill that a test case can read.
            {checks.length
              ? ` ${checks.length} test case${checks.length === 1 ? "" : "s"} can use them.`
              : ""}
          </p>
          {ignored.length ? (
            <p id="ignored-pdf-demo" className="mb-3 text-sm text-muted-foreground">
              Ignored the PDF example files found in this folder ({ignored.join(", ")}).
              They are not this skill’s samples.
            </p>
          ) : null}
          {dataset.length ? (
            <FieldSet>
              <FieldLegend className="sr-only">Sample files</FieldLegend>
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
                      Use pack fixtures for completion checks
                    </FieldLabel>
                    <FieldDescription>
                      Test cases that check a result use these files, unless that
                      case already picked its own. Trigger-only cases stay file-free.
                    </FieldDescription>
                  </FieldContent>
                </Field>
                <Field data-disabled={disabled || undefined}>
                  <FieldLabel htmlFor="fixture-glob">Only files matching</FieldLabel>
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
                    Uses the same instructions for each sample file. Trigger-only
                    cases stay as they are.
                  </FieldDescription>
                </Field>
              </FieldGroup>
            </FieldSet>
          ) : (
            <Empty className="border-0 px-1 py-3">
              <EmptyHeader>
                <EmptyTitle className="text-pretty">No sample files yet</EmptyTitle>
                <EmptyDescription className="text-pretty">
                  Add a file to this skill’s folder if a test case needs an input.
                  A test case that is only a prompt can still run.
                </EmptyDescription>
              </EmptyHeader>
            </Empty>
          )}
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  )
}
