import { BotIcon, GitBranchIcon, SparklesIcon, TerminalIcon } from "lucide-react"

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { PageHeader } from "@/components/dashboard/chrome"
import { installedNote } from "@/lib/dashboard-helpers"
import { useDashboard } from "@/lib/dashboard-provider"
import { runMetricsLine } from "@/lib/metrics-label"
import { slotOn } from "@/lib/mode"
import { isLiveHarness, type DeployTarget } from "@/lib/types"

const TARGETS: Array<{
  target: DeployTarget
  label: string
  icon: typeof SparklesIcon
  rootKey: string
  hint: string
}> = [
  {
    target: "cursor",
    label: "Cursor",
    icon: SparklesIcon,
    rootKey: "cursor",
    hint: "Cursor's skills folder",
  },
  {
    target: "codex",
    label: "Codex",
    icon: TerminalIcon,
    rootKey: "codex",
    hint: "Codex's skills folder",
  },
  {
    target: "claude",
    label: "Claude",
    icon: BotIcon,
    rootKey: "claude",
    hint: "Claude's skills folder",
  },
]

export function DeployPage() {
  const {
    deployAllowed,
    deployLast,
    installTo,
    publishToGit,
    liveGateResult,
    gateRunning,
    skill,
    skillHistory,
    status,
    setStage,
    setEvalTab,
  } = useDashboard()

  const last = skillHistory?.last_run || liveGateResult
  const lastDeploy = skillHistory?.last_deploy
  const digest = (last?.skill_md_hash || "").slice(0, 12)
  const skillName = skill?.name || last?.skill || "this skill"
  const versionLine = last?.semver
    ? `${skillName} v${last.semver}${digest ? ` · ${digest}` : ""}`
    : skill
      ? `${skill.name} — evaluate to record a version.`
      : "Select a skill on Evaluate first."

  const localAvailable = status?.deploy?.local_available !== false
  const live = localAvailable
    ? status?.deploy?.live || ["cursor", "claude", "codex"]
    : []
  const targets = TARGETS.filter((item) =>
    localAvailable ? live.includes(item.target) : true
  )
  const git = status?.deploy?.git
  const gitConfigured = Boolean(git?.configured)

  let note = "Pick a skill on Evaluate, then pass the checks to unlock Install."
  let title = deployAllowed ? "Ready" : "Blocked"
  if (!skill) {
    note = "Pick a skill on Evaluate. Pass the checks to unlock Install."
  } else if (deployAllowed && lastDeploy?.mode === "git" && (lastDeploy.url || lastDeploy.dest_label || lastDeploy.dest_path)) {
    note = lastDeploy.url
      ? `Published ${skillName} to git.`
      : `Published ${skillName} to git.`
    title = "Published"
  } else if (
    deployAllowed &&
    (lastDeploy?.dest_label || lastDeploy?.dest_path || lastDeploy?.status === "installed")
  ) {
    note = installedNote(skillName, lastDeploy)
    title = "Installed"
  } else if (deployAllowed && deployLast) {
    note = `Last install: ${deployLast}. Checks passed for ${skillName} — Install is unlocked.`
  } else if (deployAllowed) {
    note = localAvailable
      ? `Checks passed for ${skillName}. Install to Cursor, Codex, or Claude is unlocked.`
      : `Checks passed for ${skillName}. Local install needs the app on your machine — or Publish to git below.`
  } else if (
    last?.passed &&
    !isLiveHarness(last.report?.harness || last.harness) &&
    status?.mode !== "local"
  ) {
    note = `Demo runs do not unlock Deploy. Run live Start Evaluations for ${skillName}.`
  } else if (deployLast) {
    note = `Last install: ${deployLast}. Pass the checks to unlock Install.`
  } else if (skill) {
    note = "Pass the checks to unlock Install."
  }

  const stampMetrics =
    last?.status === "done" && last.report
      ? runMetricsLine({
          usage: last.report.usage,
          metrics: last.report.metrics,
          tasks: last.report.tasks,
        })
      : null

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        title="Deploy"
        description={
          localAvailable
            ? "Install this gated skill into Cursor, Codex, or Claude when the checks pass."
            : "Hosted Skill Gate cannot write your skills folders — publish to git, or run the app locally."
        }
        action={
          <Button
            variant="outline"
            onClick={() => {
              setEvalTab("gate")
              setStage("eval")
            }}
          >
            Back to Gate
          </Button>
        }
      />

      <Alert id="deploy-note" variant={deployAllowed ? "default" : "destructive"}>
        <AlertTitle>{title}</AlertTitle>
        <AlertDescription>{note}</AlertDescription>
      </Alert>
      {stampMetrics ? (
        <p className="text-sm text-muted-foreground" id="run-usage">
          {stampMetrics}
        </p>
      ) : null}

      {!localAvailable ? (
        <Alert id="deploy-local-hosted">
          <AlertTitle>Local install on your machine</AlertTitle>
          <AlertDescription>
            This hosted app cannot copy skills into Cursor, Codex, or Claude
            folders on your machine. Run Skill Gate locally, pass the checks,
            then use Install there.
          </AlertDescription>
        </Alert>
      ) : null}

      <div className="flex max-w-xl flex-col gap-4">
        <h2 className="text-sm font-medium text-muted-foreground">
          Install locally
        </h2>
        {targets.map(({ target, label, icon: Icon, hint }) => (
          <Card key={target}>
            <CardHeader>
              <CardTitle className="flex items-center gap-3">
                <span className="flex size-10 items-center justify-center rounded-lg bg-muted">
                  <Icon className="size-4" />
                </span>
                {label}
              </CardTitle>
              <CardDescription>
                {localAvailable
                  ? `Copy the gated skill into ${hint}`
                  : `Run the app on your machine to install into ${hint}`}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button
                id={`btn-deploy-${target}`}
                size="lg"
                className="w-full"
                disabled={!deployAllowed || gateRunning || !localAvailable}
                onClick={() => void installTo(target)}
              >
                {localAvailable ? `Install to ${label}` : `Run CLI for ${label}`}
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>

      {slotOn(status, "gitPublish") ? (
      <div className="max-w-xl">
        <Accordion
          key={status ? (localAvailable ? "local" : "hosted") : "pending"}
          className="rounded-lg border px-3"
          defaultValue={status && !localAvailable ? ["git"] : []}
        >
          <AccordionItem value="git">
            <AccordionTrigger className="py-3" id="deploy-git-trigger">
              <span className="flex items-center gap-2">
                <GitBranchIcon className="size-4" />
                Publish to git
                <span className="text-muted-foreground font-normal">
                  (hosted / teams)
                </span>
              </span>
            </AccordionTrigger>
            <AccordionContent>
              <Card className="border-0 shadow-none">
                <CardHeader className="px-0 pt-0">
                  <CardTitle className="text-base">Skills remote</CardTitle>
                  <CardDescription id="deploy-git-hint">
                    {gitConfigured
                      ? `Push the gated pack to ${git?.repo_url || "the configured remote"} under ${git?.path_prefix || "skills"}/<name> (branch from ${git?.base_ref || "main"}). Opens a PR when a GitHub token is available.`
                      : "Set SKILLGATE_SKILLS_REPO_URL (and a GitHub token) to publish gated packs to a skills repo."}
                  </CardDescription>
                </CardHeader>
                <CardContent className="px-0 pb-0">
                  <Button
                    id="btn-deploy-git"
                    size="lg"
                    className="w-full"
                    disabled={!deployAllowed || gateRunning || !gitConfigured}
                    onClick={() => void publishToGit()}
                  >
                    {gitConfigured ? "Publish to git" : "Git remote not configured"}
                  </Button>
                </CardContent>
              </Card>
            </AccordionContent>
          </AccordionItem>
        </Accordion>
      </div>
      ) : null}

      <p className="text-sm text-muted-foreground" id="deploy-version">
        {versionLine}
      </p>
    </div>
  )
}
