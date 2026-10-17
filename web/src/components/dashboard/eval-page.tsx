import { useState } from "react"
import {
  AlertCircleIcon,
  FileArchiveIcon,
  FileTextIcon,
  PlusIcon,
  SparklesIcon,
  XIcon,
} from "lucide-react"

import { AddCheckDialog } from "@/components/dashboard/add-check-dialog"
import { AssistantMarkdown } from "@/components/dashboard/assistant-markdown"
import { CheckList } from "@/components/dashboard/check-list"
import { EvalResultMark } from "@/components/dashboard/eval-result-mark"
import { DatasetViewer } from "@/components/dashboard/dataset-viewer"
import { GateBadge, PageHeader } from "@/components/dashboard/chrome"
import { FixtureBindAccordion } from "@/components/dashboard/fixture-bind-accordion"
import { GatePage } from "@/components/dashboard/gate-page"
import { RunConfigAccordion } from "@/components/dashboard/run-config-accordion"
import {
  Alert,
  AlertAction,
  AlertDescription,
  AlertTitle,
} from "@/components/ui/alert"
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardFooter,
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
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Skeleton } from "@/components/ui/skeleton"
import { Spinner } from "@/components/ui/spinner"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"
import { canPinCheck, pinnedCaseCount } from "@/lib/case-pack"
import {
  BuiltinChecks,
  PackScoringExtras,
} from "@/components/dashboard/scoring-questions"
import { useDashboard } from "@/lib/dashboard-provider"
import { runBelongsToSkill } from "@/lib/eval-row-state"
import type { RunRecord } from "@/lib/types"
import { isLocalMode, slotOn } from "@/lib/mode"
import {
  ASSIST_CHECKS_NOTICE,
  BUNDLED_TEMPLATE_NOTICE,
  BUNDLED_SUITE_NOTICE,
  FIXTURE_NOTICE,
  MODEL_GENERATED_NOTICE,
  NEEDS_UPLOAD_NOTICE,
  PACK_BANK_NOTICE,
  PACK_FIXTURE_NOTICE,
  PACK_INHERIT_HINT,
  PASTE_PLACEHOLDER,
  START_NEEDS_UPLOAD,
  STARTER_FROM_DESCRIPTION_NOTICE,
  authenticFixtureDefaults,
  checkNeedsInput,
  needsFixtureNotice,
  startBlockedByNeedsUpload,
  startBlockedIssues,
  startBlockedMessage,
} from "@/lib/check-guards"

const MISSING_KEY_DISMISS = "skillgate-missing-key-dismissed"

function seedNoticeCopy(
  source:
    | "model"
    | "heuristic"
    | "template"
    | "suite"
    | "yaml"
    | "pack"
    | "assist"
    | "empty"
    | null,
  note: string
) {
  if (source === "pack") {
    return {
      title: "Dataset",
      description: note || PACK_BANK_NOTICE,
    }
  }
  if (source === "assist") {
    return {
      title: "Draft checks",
      description: note || ASSIST_CHECKS_NOTICE,
    }
  }
  if (source === "model") {
    return {
      title: "Model-generated",
      description: note || MODEL_GENERATED_NOTICE,
    }
  }
  if (source === "template") {
    return {
      title: "Starter checks",
      description: note || BUNDLED_TEMPLATE_NOTICE,
    }
  }
  if (source === "suite") {
    return {
      title: "Bundled suite",
      description: note || BUNDLED_SUITE_NOTICE,
    }
  }
  return {
    title: "Starter checks from your description",
    description: note || STARTER_FROM_DESCRIPTION_NOTICE,
  }
}

function seedingSpinnerCopy(opts: {
  seedingAssist: boolean
  hasDataset: boolean
  skillName?: string | null
}): { title: string; description: string } {
  if (opts.seedingAssist) {
    if (opts.hasDataset) {
      return {
        title: "Asking the model",
        description: "Generating draft checks. They don’t unlock Deploy.",
      }
    }
    return {
      title: "Asking the model",
      description: "Generating 3–5 model-authored checks from this skill.",
    }
  }
  if (opts.skillName === "pdf" || opts.skillName === "pdf-sabotaged") {
    return {
      title: "Building starter checks",
      description: "Generating 3–5 starter checks from your description.",
    }
  }
  if (opts.hasDataset) {
    return {
      title: "Loading Dataset",
      description: "Loading pinned checks from this skill’s Dataset.",
    }
  }
  return {
    title: "Loading checks",
    description: "Loading checks for this skill.",
  }
}

export function EvalPage() {
  const {
    evalTab,
    setEvalTab,
    running,
    lastResult,
    skillHistory,
    tryoutResult,
    skill,
    skills,
    checks,
    yaml,
    paste,
    setPaste,
    intakeError,
    catalogError,
    refreshSkills,
    seeding,
    seedingAssist,
    checksSeeded,
    checksSource,
    checksNote,
    checksWarning,
    searchQuery,
    selectSkill,
    pasteSkill,
    uploadZip,
    updateCheck,
    removeCheck,
    packJudge,
    setPackJudge,
    applySkill,
    startEvaluations,
    runThisCheck,
    importYaml,
    status,
    harnessPref,
    setHarnessPref,
    resolvedHarness,
    evalConfig,
    setEvalConfig,
    fixtureInherit,
    fixtureGlob,
    bindPackFixtures,
    expandPackFixtures,
    setFixtureGlob,
    openRepository,
    pinShownChecks,
    pinCheckAt,
    setStage,
  } = useDashboard()
  const [addCheckOpen, setAddCheckOpen] = useState(false)
  const [datasetOpen, setDatasetOpen] = useState(false)
  const [yamlDraft, setYamlDraft] = useState("")
  const [keyBannerDismissed, setKeyBannerDismissed] = useState(() => {
    try {
      return sessionStorage.getItem(MISSING_KEY_DISMISS) === "1"
    } catch {
      return false
    }
  })
  const startBlocked = startBlockedByNeedsUpload(checks, fixtureInherit, skill)
  const startBlockReason = startBlockedMessage(checks, fixtureInherit, skill)
  const startIssues = startBlockedIssues(checks, fixtureInherit, skill)
  const anyNeedsInput = checks.some((check) =>
    checkNeedsInput(check, fixtureInherit, skill)
  )
  const startTitle = !status?.has_key
    ? "Add a key in Settings, then press Run."
    : !skill
      ? "Pick a skill first."
      : checks.length === 0
        ? "Add at least one check before starting evaluations."
        : startBlocked
          ? startBlockReason || START_NEEDS_UPLOAD
          : undefined
  const runLabel = running
    ? `${lastResult?.completed_count ?? 0}/${lastResult?.task_count ?? checks.length} done`
    : "Run"
  const runHelp = !skill
    ? "Next: pick a skill."
    : checks.length === 0
      ? "Next: add a test case, then press Run."
      : !status?.has_key
        ? "Next: sign in or add a key in Settings, then press Run."
        : startBlocked
          ? startBlockReason || "Next: add the missing file, then press Run."
          : running
            ? "Running the test cases. Results show up below."
            : "Press Run. Nothing runs until you do."
  const seedCopy = seedNoticeCopy(checksSource, checksNote)
  const seedingCopy = seedingSpinnerCopy({
    seedingAssist,
    hasDataset: Boolean(skill?.has_dataset),
    skillName: skill?.name,
  })
  const packPinnedCount = pinnedCaseCount(checks)
  const canPinAll =
    checks.length > 0 && checks.every((check) => canPinCheck(check))

  const query = searchQuery.trim().toLowerCase()
  const visibleSkills = skills.filter((item) => {
    if (!query) {
      return true
    }
    return (
      item.name.toLowerCase().includes(query) ||
      (item.description || "").toLowerCase().includes(query)
    )
  })

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="Evaluate"
        description="Test a skill on this computer. Pick it, read the test cases, then press Run."
        action={
          status && !status.has_key && keyBannerDismissed ? (
            <Button
              id="missing-key"
              variant="ghost"
              size="xs"
              onClick={() => {
                try {
                  sessionStorage.removeItem(MISSING_KEY_DISMISS)
                } catch {
                  // ignore
                }
                setKeyBannerDismissed(false)
              }}
            >
              {status.missing_key_message || "No agent is available to run checks."}
            </Button>
          ) : undefined
        }
      />

      {status && !status.has_key && !keyBannerDismissed ? (
        <Alert id="missing-key">
          <AlertTitle className="truncate pr-8">
            {status.missing_key_message || "No agent is available to run checks."}
          </AlertTitle>
          <AlertDescription id="missing-key-hint">
            {status.missing_key_hint ||
              (isLocalMode(status)
                ? "Run skillgate login or add a key in Settings, then press Run."
                : "Run skillgate login or add a key in Settings to run live.")}{" "}
            <Button
              id="btn-open-settings"
              variant="link"
              size="xs"
              onClick={() => setStage("settings")}
            >
              Open Settings
            </Button>
          </AlertDescription>
          <AlertAction>
            <Button
              variant="ghost"
              size="icon-xs"
              aria-label="Dismiss"
              onClick={() => {
                try {
                  sessionStorage.setItem(MISSING_KEY_DISMISS, "1")
                } catch {
                  // ignore
                }
                setKeyBannerDismissed(true)
              }}
            >
              <XIcon />
            </Button>
          </AlertAction>
        </Alert>
      ) : status && !status.has_key && keyBannerDismissed ? (
        <p id="missing-key-hint" className="sr-only">
          {status.missing_key_hint ||
            (isLocalMode(status)
              ? "Run skillgate login or add a key in Settings, then press Run."
              : "Run skillgate login or add a key in Settings to run live.")}
        </p>
      ) : null}

      <Tabs
        value={evalTab === "gate" ? "gate" : evalTab === "skill" ? "skill" : "checks"}
        onValueChange={(value) => {
          if (value === "skill" || value === "checks" || value === "gate") {
            setEvalTab(value)
          }
        }}
      >
        <TabsList variant="line">
          <TabsTrigger value="skill">Skill</TabsTrigger>
          <TabsTrigger value="checks">Checks</TabsTrigger>
          <TabsTrigger value="gate">Gate</TabsTrigger>
        </TabsList>
        <TabsContent value="skill" className="flex flex-col gap-4 pt-4">
        <section className="flex flex-col gap-4" aria-labelledby="eval-step-skill">
          <Card>
            <CardHeader>
              <CardTitle id="eval-step-skill">1. Pick a skill</CardTitle>
              <CardDescription>
                Choose the skill to test. You will see the files that belong to it.
              </CardDescription>
              <CardAction>
                <Button
                  variant="link"
                  size="sm"
                  className="h-auto px-0"
                  onClick={() => {
                    openRepository(null)
                  }}
                >
                  Browse all skills
                </Button>
              </CardAction>
            </CardHeader>
            <CardContent className="flex flex-col gap-2">
              {catalogError && skills.length > 0 ? (
                <Alert>
                  <AlertCircleIcon />
                  <AlertTitle>{catalogError.message}</AlertTitle>
                  {catalogError.hint ? (
                    <AlertDescription>{catalogError.hint}</AlertDescription>
                  ) : null}
                </Alert>
              ) : null}
              {visibleSkills.length === 0 ? (
                catalogError && skills.length === 0 ? (
                  <Empty>
                    <EmptyHeader>
                      <EmptyMedia variant="icon">
                        <AlertCircleIcon />
                      </EmptyMedia>
                      <EmptyTitle>Could not load skills</EmptyTitle>
                      <EmptyDescription>{catalogError.message}</EmptyDescription>
                      {catalogError.hint ? (
                        <EmptyDescription>{catalogError.hint}</EmptyDescription>
                      ) : null}
                    </EmptyHeader>
                    <EmptyContent>
                      <Button
                        variant="outline"
                        onClick={() => void refreshSkills()}
                      >
                        Retry
                      </Button>
                    </EmptyContent>
                  </Empty>
                ) : (
                <Empty>
                  <EmptyHeader>
                    <EmptyMedia variant="icon">
                      <FileTextIcon />
                    </EmptyMedia>
                    <EmptyTitle>No skills yet</EmptyTitle>
                    <EmptyDescription>
                      Paste a SKILL.md below, or add a folder under skills/.
                    </EmptyDescription>
                  </EmptyHeader>
                </Empty>
                )
              ) : (
                (query
                  ? visibleSkills
                  : visibleSkills.slice(0, 8)
                ).map((item) => (
                  <div
                    key={item.id}
                    className="flex items-center gap-2 rounded-lg border px-3 py-2"
                  >
                    <span className="min-w-0 flex-1 truncate text-sm font-medium">
                      {item.name}
                    </span>
                    {item.warning ? (
                      <Badge variant="outline">Needs attention</Badge>
                    ) : null}
                    {item.seed ? (
                      <Badge variant="outline">Seed</Badge>
                    ) : null}
                    <GateBadge gate={item.gate} />
                    <Button
                      size="sm"
                      variant={
                        skill?.name === item.name ? "secondary" : "default"
                      }
                      disabled={running || seeding}
                      onClick={() =>
                        void selectSkill(item.absolute || item.id, {
                          fallbackSkill: item,
                        })
                      }
                    >
                      {seeding && skill?.name === item.name ? (
                        <Spinner data-icon="inline-start" />
                      ) : null}
                      {skill?.name === item.name ? "Using" : "Use"}
                    </Button>
                  </div>
                ))
              )}
              {!query && visibleSkills.length > 8 ? (
                <p className="text-xs text-muted-foreground">
                  Showing 8 of {visibleSkills.length}. Search above or{" "}
                  <button
                    type="button"
                    className="underline underline-offset-2"
                    onClick={() => openRepository(null)}
                  >
                    browse all skills
                  </button>
                  .
                </p>
              ) : null}
            </CardContent>
          </Card>

          {skill ? (
            <Card size="sm">
              <CardHeader>
                <CardTitle className="min-w-0 text-pretty">
                  <span id="skill-chip" className="block truncate">
                    Using “{skill.name}”
                  </span>
                </CardTitle>
                <CardDescription className="text-pretty">
                  {skill.warning || skill.description || "Input and expected output for this skill."}
                </CardDescription>
                <CardAction>
                  <Button
                    id="btn-view-dataset-skill"
                    size="sm"
                    className="touch-manipulation"
                    aria-haspopup="dialog"
                    aria-expanded={datasetOpen}
                    translate="no"
                    onClick={() => setDatasetOpen(true)}
                  >
                    View Dataset
                  </Button>
                </CardAction>
              </CardHeader>
            </Card>
          ) : null}

          {skill?.body?.trim() ? (
            <Accordion className="rounded-xl border px-3">
              <AccordionItem value="skill-md">
                <AccordionTrigger id="eval-skill-md">SKILL.md</AccordionTrigger>
                <AccordionContent className="text-sm leading-relaxed">
                  <AssistantMarkdown text={skill.body} />
                </AccordionContent>
              </AccordionItem>
            </Accordion>
          ) : null}

          <Card>
            <CardHeader>
              <CardTitle>Bring a skill</CardTitle>
              <CardDescription>Paste SKILL.md or drop a zip.</CardDescription>
            </CardHeader>
            <CardContent>
              <FieldGroup>
                <Field>
                  <FieldLabel htmlFor="paste">Paste SKILL.md</FieldLabel>
                  <Textarea
                    id="paste"
                    rows={8}
                    spellCheck={false}
                    placeholder={PASTE_PLACEHOLDER}
                    value={paste}
                    onChange={(event) => setPaste(event.target.value)}
                    className="field-sizing-fixed max-h-56 min-h-40"
                  />
                </Field>
                {intakeError ? (
                  <Alert id="intake-error">
                    <AlertTitle>Could not use that skill</AlertTitle>
                    <AlertDescription>
                      <pre className="font-sans text-sm whitespace-pre-wrap">
                        {intakeError}
                      </pre>
                    </AlertDescription>
                  </Alert>
                ) : null}
              </FieldGroup>
            </CardContent>
            <CardFooter className="flex flex-wrap gap-2">
              <Button
                id="btn-paste"
                size="lg"
                disabled={running || seeding}
                onClick={() => void pasteSkill()}
              >
                {seeding ? <Spinner data-icon="inline-start" /> : null}
                Use this skill
              </Button>
              <Button
                variant="outline"
                disabled={running || seeding}
                render={<label htmlFor="zip" />}
              >
                <FileArchiveIcon data-icon="inline-start" />
                Drop a .zip of the skill folder
              </Button>
              <input
                id="zip"
                type="file"
                accept=".zip,.md"
                className="sr-only"
                onChange={(event) => {
                  const file = event.target.files?.[0]
                  if (file) {
                    void uploadZip(file)
                  }
                  event.target.value = ""
                }}
              />
            </CardFooter>
          </Card>
        </section>
        </TabsContent>
        <TabsContent value="checks" className="flex flex-col gap-4 pt-4">
        <section aria-labelledby="eval-step-cases">
          <Card>
            <CardHeader>
              <CardTitle id="eval-step-cases">2. Test cases</CardTitle>
              <CardDescription>
                Each row is one thing you ask the agent to do. Edit them, then press Run.
              </CardDescription>
              <CardAction>
                {skill || checks.length > 0 ? (
                  <div className="flex flex-wrap gap-2">
                    <Button
                      id="btn-add"
                      variant="outline"
                      size="sm"
                      disabled={seeding}
                      onClick={() => setAddCheckOpen(true)}
                    >
                      <PlusIcon data-icon="inline-start" />
                      Add a check
                    </Button>
                  </div>
                ) : null}
              </CardAction>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              <RunConfigAccordion
                harnessPref={harnessPref}
                setHarnessPref={setHarnessPref}
                resolvedHarness={resolvedHarness}
                evalConfig={evalConfig}
                setEvalConfig={setEvalConfig}
                disabled={running || seeding}
                supportedModels={status?.supported_models}
                supportedModelsMeta={status?.supported_models_meta}
                availableHarnesses={status?.available_harnesses}
                defaultTimeoutSec={status?.default_eval_config?.timeout_sec}
              />
              <FixtureBindAccordion
                skill={skill}
                packFiles={skill?.pack_files ?? []}
                checks={checks}
                inherit={fixtureInherit}
                glob={fixtureGlob}
                disabled={running || seeding}
                onInheritChange={(next) => void bindPackFixtures(next)}
                onGlobChange={setFixtureGlob}
                onExpand={() => void expandPackFixtures()}
              />
              {!skill ? (
                <Empty>
                  <EmptyHeader>
                    <EmptyTitle>No skill yet</EmptyTitle>
                    <EmptyDescription>
                      Pick a skill above to load its test cases.
                    </EmptyDescription>
                  </EmptyHeader>
                  <EmptyContent>
                    <Button onClick={() => document.getElementById("eval-step-skill")?.scrollIntoView()}>
                      Pick a skill
                    </Button>
                  </EmptyContent>
                </Empty>
              ) : null}
              {skill ? (
                <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
                  {checksSource === "pack" && checks.length > 0 && !seeding ? (
                    <p
                      id="pack-banner"
                      className="min-w-0 text-sm text-pretty text-muted-foreground"
                    >
                      {PACK_BANK_NOTICE}
                    </p>
                  ) : null}
                  <Button
                    id="btn-view-dataset"
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
                </div>
              ) : null}
              {checksSeeded &&
              checks.length > 0 &&
              !seeding &&
              checksSource !== "pack" ? (
                <Alert
                  id="checks-seed-notice"
                  data-source={checksSource || undefined}
                >
                  {checksSource === "model" || checksSource === "assist" ? (
                    <SparklesIcon />
                  ) : (
                    <FileTextIcon />
                  )}
                  <AlertTitle>{seedCopy.title}</AlertTitle>
                  <AlertDescription>{seedCopy.description}</AlertDescription>
                </Alert>
              ) : null}
              {checksWarning ? (
                <Alert id="checks-seed-warning">
                  <AlertTitle>
                    Used starter checks from your description
                  </AlertTitle>
                  <AlertDescription>{checksWarning}</AlertDescription>
                </Alert>
              ) : null}
              {needsFixtureNotice(skill, checks) &&
              checks.length > 0 &&
              !seeding ? (
                <Alert id="fixture-notice">
                  <FileArchiveIcon />
                  <AlertTitle>
                    {anyNeedsInput
                      ? "Needs input"
                      : authenticFixtureDefaults(skill).length
                        ? "Skill files ready"
                        : "Add input or expected output"}
                  </AlertTitle>
                  <AlertDescription>
                    {anyNeedsInput
                      ? NEEDS_UPLOAD_NOTICE
                      : authenticFixtureDefaults(skill).length
                        ? PACK_FIXTURE_NOTICE
                        : FIXTURE_NOTICE}
                  </AlertDescription>
                </Alert>
              ) : null}
              {startIssues.length > 0 && checks.length > 0 && !seeding ? (
                <Alert
                  id="start-needs-file"
                  variant="destructive"
                  tabIndex={-1}
                  aria-labelledby="start-needs-file-title"
                >
                  <AlertCircleIcon />
                  <AlertTitle id="start-needs-file-title">
                    Add a file before Start
                  </AlertTitle>
                  <AlertDescription>
                    <div className="flex flex-col gap-2">
                      <ul
                        id="start-needs-file-list"
                        className="flex list-disc flex-col gap-1 pl-4"
                      >
                        {startIssues.map((issue) => (
                          <li key={`${issue.index}-${issue.id || "row"}`}>
                            <a href={`#check-needs-upload-${issue.index - 1}`}>
                              {issue.label}: needs a file in the skill folder
                            </a>
                          </li>
                        ))}
                      </ul>
                      <p>{PACK_INHERIT_HINT}</p>
                    </div>
                  </AlertDescription>
                </Alert>
              ) : null}
              {seeding ? (
                <div id="checks-seeding" className="flex flex-col gap-3">
                  <Empty>
                    <EmptyHeader>
                      <EmptyMedia variant="icon">
                        <Spinner />
                      </EmptyMedia>
                      <EmptyTitle>{seedingCopy.title}</EmptyTitle>
                      <EmptyDescription>{seedingCopy.description}</EmptyDescription>
                    </EmptyHeader>
                  </Empty>
                  <Skeleton className="h-32 w-full rounded-xl" />
                  <Skeleton className="h-32 w-full rounded-xl" />
                  <Skeleton className="h-32 w-full rounded-xl" />
                </div>
              ) : checks.length === 0 ? (
                <Empty>
                  <EmptyHeader>
                    <EmptyMedia variant="icon">
                      <FileTextIcon />
                    </EmptyMedia>
                    <EmptyTitle>
                      {skill && intakeError
                        ? "Could not suggest checks"
                        : skill
                          ? "No checks yet"
                          : "No skill yet"}
                    </EmptyTitle>
                    <EmptyDescription>
                      {skill && intakeError
                        ? "Fix the skill description, or add a check yourself."
                        : skill
                          ? "Add a check, or generate drafts."
                          : "Select a skill to load its checks, or add a check manually."}
                    </EmptyDescription>
                  </EmptyHeader>
                  <EmptyContent>
                    {skill && intakeError ? (
                      <Alert id="checks-intake-error">
                        <AlertTitle>Could not suggest checks</AlertTitle>
                        <AlertDescription>
                          <pre className="font-sans text-sm whitespace-pre-wrap">
                            {intakeError}
                          </pre>
                        </AlertDescription>
                      </Alert>
                    ) : null}
                    <div className="flex flex-wrap justify-center gap-2">
                      {skill && slotOn(status, "generateChecks") ? (
                        <Button
                          id="btn-generate-checks"
                          disabled={seeding}
                          onClick={() =>
                            void selectSkill(skill.absolute || skill.id, {
                              tab: "checks",
                              fallbackSkill: skill,
                              forceSeed: true,
                            })
                          }
                        >
                          <SparklesIcon data-icon="inline-start" />
                          Generate checks
                        </Button>
                      ) : skill ? null : (
                        <Button onClick={() => setEvalTab("skill")}>
                          Select a skill
                        </Button>
                      )}
                      {skill && intakeError ? (
                        <Button
                          variant="outline"
                          onClick={() => setEvalTab("skill")}
                        >
                          Fix the skill
                        </Button>
                      ) : null}
                      <Button
                        variant="outline"
                        onClick={() => setAddCheckOpen(true)}
                      >
                        <PlusIcon data-icon="inline-start" />
                        Add a check manually
                      </Button>
                    </div>
                  </EmptyContent>
                </Empty>
              ) : (
                <ScrollArea className="max-h-[min(32rem,55vh)] overflow-hidden [&_[data-slot=scroll-area-viewport]]:max-h-[min(32rem,55vh)]">
                  <CheckList
                    key={`${skill?.id ?? skill?.name ?? "none"}:${yaml}`}
                    checks={checks}
                    running={running}
                    skill={skill}
                    packFiles={skill?.pack_files}
                    inherit={fixtureInherit}
                    lastResult={lastResult}
                    tryoutResult={tryoutResult}
                    updateCheck={updateCheck}
                    removeCheck={removeCheck}
                    packJudge={packJudge}
                    onPackJudge={setPackJudge}
                    onSkill={applySkill}
                    onPin={(index) => void pinCheckAt(index)}
                    onRunCheck={(check) => void runThisCheck(check)}
                    showPackQuestions={false}
                  />
                </ScrollArea>
              )}
              {skill && checks.length > 0 && !seeding ? (
                <div className="flex flex-wrap gap-2">
                  <Button
                    id="btn-pin-all"
                    variant="outline"
                    disabled={running || !canPinAll}
                    onClick={() => void pinShownChecks()}
                  >
                    Save all shown
                  </Button>
                  {slotOn(status, "generateChecks") ? (
                  <Button
                    id="btn-generate-checks-assist"
                    variant="outline"
                    disabled={seeding || running}
                    onClick={() =>
                      void selectSkill(skill.absolute || skill.id, {
                        tab: "checks",
                        fallbackSkill: skill,
                        forceSeed: true,
                      })
                    }
                  >
                    <SparklesIcon data-icon="inline-start" />
                    {packPinnedCount > 0 ? "Generate drafts" : "Generate checks"}
                  </Button>
                  ) : null}
                </div>
              ) : null}
              {skill && !isLocalMode(status) ? (
              <Accordion className="rounded-lg border px-2">
                <AccordionItem value="yaml">
                  <AccordionTrigger className="py-1.5">
                    Import a list
                  </AccordionTrigger>
                  <AccordionContent>
                    <FieldGroup>
                      <Field>
                        <FieldLabel htmlFor="yaml-in">
                          Paste a list
                        </FieldLabel>
                        <Textarea
                          id="yaml-in"
                          rows={6}
                          spellCheck={false}
                          value={yamlDraft}
                          placeholder={
                            "suite: my-skill-starter\nskill: skills/my-skill\ntasks:\n  - id: check-1\n    prompt: …"
                          }
                          onChange={(event) => setYamlDraft(event.target.value)}
                          className="field-sizing-fixed max-h-56 min-h-32 font-mono text-xs"
                        />
                      </Field>
                      <Button
                        id="btn-yaml-import"
                        variant="outline"
                        disabled={running || seeding || !skill}
                        onClick={() => void importYaml(yamlDraft)}
                      >
                        Load list
                      </Button>
                      {yaml ? (
                        <pre
                          id="yaml-out"
                          className="max-h-64 overflow-auto rounded-xl border bg-muted/40 p-3 font-mono text-xs whitespace-pre-wrap"
                        >
                          {yaml}
                        </pre>
                      ) : null}
                    </FieldGroup>
                  </AccordionContent>
                </AccordionItem>
              </Accordion>
              ) : null}
            </CardContent>
          </Card>
        </section>

        <Accordion className="rounded-xl border px-3">
          <AccordionItem value="checks">
            <AccordionTrigger id="eval-step-checks">What gets checked</AccordionTrigger>
            <AccordionContent className="flex flex-col gap-4">
              <p className="text-sm text-muted-foreground">
                Every test case is scored with these checks. Add your own questions if you want more.
              </p>
              <BuiltinChecks />
              <PackScoringExtras
                packJudge={packJudge}
                disabled={running || seeding || !skill}
                onPackJudge={setPackJudge}
              />
            </AccordionContent>
          </AccordionItem>
          <AccordionItem value="results">
            <AccordionTrigger id="eval-step-results">Results</AccordionTrigger>
            <AccordionContent>
              <EvalResults
                skillName={skill?.name}
                running={running}
                lastResult={lastResult}
                historyRun={skillHistory?.last_run ?? null}
              />
            </AccordionContent>
          </AccordionItem>
        </Accordion>

        <div className="flex flex-col gap-2">
          <p id="run-help" className="text-sm text-muted-foreground">
            {runHelp}
          </p>
          <Button
            id="btn-run"
            size="lg"
            className="w-full"
            disabled={
              running ||
              seeding ||
              !skill ||
              checks.length === 0 ||
              startBlocked ||
              !status?.has_key
            }
            title={startTitle}
            aria-describedby="run-help"
            onClick={() => void startEvaluations()}
          >
            {running ? <Spinner data-icon="inline-start" /> : null}
            {runLabel}
          </Button>
        </div>
        </TabsContent>
        <TabsContent value="gate" className="pt-4">
          <GatePage embedded />
        </TabsContent>
      </Tabs>
      <AddCheckDialog open={addCheckOpen} onOpenChange={setAddCheckOpen} />
      {skill ? (
        <DatasetViewer
          skillId={skill.absolute || skill.id}
          open={datasetOpen}
          onOpenChange={setDatasetOpen}
        />
      ) : null}
    </div>
  )
}

function EvalResults({
  skillName,
  running,
  lastResult,
  historyRun,
}: {
  skillName?: string | null
  running: boolean
  lastResult: RunRecord | null
  historyRun: RunRecord | null
}) {
  const live =
    lastResult && runBelongsToSkill(lastResult, skillName) ? lastResult : null
  const stored =
    historyRun && runBelongsToSkill(historyRun, skillName) ? historyRun : null
  const run =
    live && (running || live.status === "running" || live.status === "done" || live.status === "error")
      ? live
      : stored
  const tasks = run?.report?.tasks ?? []
  const passed = run?.passed === true || run?.report?.passed === true
  const failed = run?.passed === false || run?.report?.passed === false
  const busy = Boolean(run && (running || run.status === "running") && live)
  return (
    <Card id="eval-results">
      <CardHeader>
        <CardTitle id="eval-step-results">5. Results</CardTitle>
        <CardDescription>
          Passed checks use a green mark. Failed checks use a red mark.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {!run || (!busy && !passed && !failed && tasks.length === 0) ? (
          <Empty>
            <EmptyHeader>
              <EmptyTitle>No results yet</EmptyTitle>
              <EmptyDescription>
                Press Run. This stays empty until a test finishes.
              </EmptyDescription>
            </EmptyHeader>
          </Empty>
        ) : (
          <div className="flex flex-col gap-4">
            {busy ? (
              <p className="text-sm font-medium">Running the test cases.</p>
            ) : (
              <div className="flex items-center gap-3">
                <EvalResultMark
                  kind={passed ? "pass" : "fail"}
                  mode="complete"
                />
                <p className={passed ? "text-sm font-medium text-success" : "text-sm font-medium text-destructive"}>
                  {passed ? "Passed" : "Failed"}
                </p>
              </div>
            )}
            {tasks.length > 0 ? (
              <ul className="flex flex-col gap-2">
                {tasks.map((task) => (
                  <li key={task.id || task.prompt} className="flex items-baseline gap-2 text-sm">
                    <span className={task.passed ? "text-success" : "text-destructive"}>
                      {task.passed ? "Passed" : "Failed"}
                    </span>
                    <span className="min-w-0 text-pretty">{task.prompt || task.id}</span>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
