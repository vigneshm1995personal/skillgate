import { BotIcon, GitBranchIcon, LaptopIcon, SparklesIcon, TerminalIcon } from "lucide-react"

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
import { useDashboard } from "@/lib/dashboard-provider"
import { runMetricsLine } from "@/lib/metrics-label"
import { slotOn } from "@/lib/mode"
import { useHelperDevices } from "@/lib/use-helper-devices"
import { agentLabel } from "@/lib/agent-label"
import {
  isLiveHarness,
  type DeployTarget,
  type HelperJob,
  type HelperTargetStatus,
} from "@/lib/types"

const TARGETS: Array<{
  target: DeployTarget
  label: string
  icon: typeof SparklesIcon
  hint: string
}> = [
  {
    target: "cursor",
    label: agentLabel("cursor"),
    icon: SparklesIcon,
    hint: "Editor agent's skills folder.",
  },
  {
    target: "codex",
    label: agentLabel("codex"),
    icon: TerminalIcon,
    hint: "Terminal agent's skills folder.",
  },
  {
    target: "claude",
    label: agentLabel("claude"),
    icon: BotIcon,
    hint: "Code agent's skills folder.",
  },
]

function targetStatusForDevice(
  deviceId: string,
  target: DeployTarget,
  jobs: HelperJob[]
): { status: HelperTargetStatus; error?: string | null } {
  const matches = jobs.filter(
    (job) => job.device_id === deviceId && job.targets.includes(target)
  )
  const job = matches[0]
  if (!job) {
    return { status: "waiting" }
  }
  const result = job.results?.find((item) => item.target === target)
  const status = (result?.status || job.status || "waiting").toLowerCase()
  if (status === "installed") {
    return { status: "installed" }
  }
  if (status === "failed") {
    return { status: "failed", error: result?.error || job.error }
  }
  if (status === "installing") {
    return { status: "installing" }
  }
  return { status: "waiting" }
}

function publicDestPath(path?: string | null): string | null {
  if (!path) {
    return null
  }
  const value = path.trim()
  if (!value) {
    return null
  }
  const lower = value.toLowerCase()
  if (
    lower.startsWith("/root") ||
    lower.startsWith("/tmp") ||
    lower.startsWith("/var/") ||
    lower.startsWith("/app/") ||
    /\/\.(cursor|codex|claude)(\/|$)/.test(lower)
  ) {
    return null
  }
  return value
}

function targetStatusLabel(state: {
  status: HelperTargetStatus
  error?: string | null
}): string {
  switch (state.status) {
    case "installed":
      return "Installed"
    case "failed":
      return state.error ? `Couldn't install: ${state.error}` : "Couldn't install"
    case "installing":
      return "Installing"
    default:
      return "Waiting"
  }
}

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
    stage,
  } = useDashboard()

  const {
    devices,
    helperJobs,
    pairingCode,
    createPairingCode,
    removeDevice,
    installToDevice,
  } = useHelperDevices({ stage, deployAllowed, skill })

  const last = skillHistory?.last_run || liveGateResult
  const lastDeploy = skillHistory?.last_deploy
  const skillName = skill?.name || last?.skill || "this skill"
  const versionLine = last?.semver
    ? `${skillName} v${last.semver}`
    : skill
      ? `${skill.name} — evaluate to record a version.`
      : "Select a skill on Evaluate first."

  const activeDevices = devices.filter((device) => !device.revoked_at)
  const localAvailable = status?.deploy?.local_available !== false
  const showMac = !localAvailable || slotOn(status, "sandboxes")
  const showGit = !localAvailable || slotOn(status, "gitPublish")
  const live = localAvailable
    ? status?.deploy?.live || ["cursor", "claude", "codex"]
    : []
  const targets = TARGETS.filter((item) =>
    localAvailable ? live.includes(item.target) : true
  )
  const git = status?.deploy?.git
  const gitConfigured = Boolean(git?.configured)

  let note = "Pick a skill on Evaluate, then clear Gate green."
  let title = deployAllowed ? "Unlocked" : "Blocked"
  if (!skill) {
    note = "Pick a skill on Evaluate. A green gate unlocks install."
  } else if (deployAllowed && lastDeploy?.mode === "git" && (lastDeploy.url || lastDeploy.dest_path)) {
    const dest = publicDestPath(lastDeploy.dest_path)
    note = lastDeploy.url
      ? `Published ${skillName} to your skills repo → ${lastDeploy.url}`
      : dest
        ? `Published ${skillName} to your skills repo → ${dest}`
        : `Published ${skillName} to your skills repo.`
    title = "Published"
  } else if (deployAllowed && lastDeploy?.dest_path) {
    const ver = lastDeploy.semver ? ` v${lastDeploy.semver}` : ""
    const target = lastDeploy.target ? ` to ${agentLabel(lastDeploy.target)}` : ""
    const dest = lastDeploy.dest_label || publicDestPath(lastDeploy.dest_path)
    note = dest
      ? `Installed ${skillName}${ver}${target} → ${dest}`
      : `Installed ${skillName}${ver}${target}.`
    title = "Installed"
  } else if (deployAllowed && deployLast) {
    note = `Last install: ${deployLast}. Gate is green for ${skillName}.`
  } else if (deployAllowed) {
    note = localAvailable
      ? `Gate is green for ${skillName}. Install into an agent skills folder is unlocked.`
      : `Gate is green for ${skillName}. Install on your Mac below, or publish to your skills repo.`
  } else if (last?.passed && !isLiveHarness(last.report?.harness || last.harness)) {
    note = `Demo evals do not unlock Deploy. Run a live check for ${skillName}.`
  } else if (deployLast) {
    note = `Last install: ${deployLast}. Gate is red for ${skillName}.`
  } else if (skill) {
    note = `Clear Gate green for ${skillName} to unlock install.`
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
            ? "Install this gated skill into an agent skills folder when the gate is green."
            : "This hosted workspace can't install straight onto your Mac — connect your Mac, or publish to your skills repo."
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
          <AlertTitle>Install on your Mac</AlertTitle>
          <AlertDescription>
            This hosted workspace can't write into your editor's skills folders.
            Connect your Mac below to install hands-free, or use the CLI on your
            own machine.
          </AlertDescription>
        </Alert>
      ) : null}

      {showMac ? (
        <div className="flex max-w-xl flex-col gap-4">
          <h2 className="text-sm font-medium text-muted-foreground">Your Mac</h2>
          {activeDevices.length === 0 ? (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-3">
                  <span className="flex size-10 items-center justify-center rounded-lg bg-muted">
                    <LaptopIcon className="size-4" />
                  </span>
                  Connect your Mac
                </CardTitle>
                <CardDescription>
                  Connect your Mac to install skills hands-free from here.
                </CardDescription>
              </CardHeader>
              <CardContent className="flex flex-col gap-3">
                {pairingCode ? (
                  <>
                    <p id="pairing-code" className="font-mono text-lg tracking-wider">
                      {pairingCode.code}
                    </p>
                    <p id="connect-command" className="text-sm text-muted-foreground">
                      On your Mac, run <code className="text-xs">pip install skillgate-ai</code>, then{" "}
                      <code className="text-xs">
                        skillgate connect --url &lt;this site&gt; --code {pairingCode.code}
                      </code>
                      , then <code className="text-xs">skillgate helper</code>.
                    </p>
                  </>
                ) : (
                  <Button
                    id="btn-connect-mac"
                    size="lg"
                    className="w-full"
                    onClick={() => void createPairingCode()}
                  >
                    Connect your Mac
                  </Button>
                )}
              </CardContent>
            </Card>
          ) : (
            activeDevices.map((device) => (
              <Card key={device.id}>
                <CardHeader>
                  <CardTitle className="flex items-center justify-between gap-3">
                    <span className="flex items-center gap-2">
                      <LaptopIcon className="size-4" />
                      {device.name}
                      <span
                        className={`size-2 rounded-full ${
                          device.online ? "bg-emerald-500" : "bg-muted-foreground"
                        }`}
                      />
                    </span>
                    <Button
                      id={`btn-remove-device-${device.id}`}
                      variant="ghost"
                      size="sm"
                      onClick={() => void removeDevice(device.id)}
                    >
                      Remove
                    </Button>
                  </CardTitle>
                  <CardDescription>{device.online ? "Online" : "Offline"}</CardDescription>
                </CardHeader>
                <CardContent className="flex flex-col gap-2">
                  {TARGETS.map(({ target, label }) => {
                    const state = targetStatusForDevice(device.id, target, helperJobs)
                    return (
                      <div key={target} className="flex items-center justify-between gap-3">
                        <span
                          id={`device-${device.id}-status-${target}`}
                          className="text-sm text-muted-foreground"
                        >
                          {label}: {targetStatusLabel(state)}
                        </span>
                        <Button
                          id={`btn-device-${device.id}-${target}`}
                          size="sm"
                          disabled={!device.online || !deployAllowed || gateRunning}
                          onClick={() => void installToDevice(device.id, target)}
                        >
                          Install on {device.name}
                        </Button>
                      </div>
                    )
                  })}
                </CardContent>
              </Card>
            ))
          )}
        </div>
      ) : null}

      {localAvailable ? (
        <div className="flex max-w-xl flex-col gap-4">
          <h2 className="text-sm font-medium text-muted-foreground">Install locally</h2>
          {targets.map(({ target, label, icon: Icon, hint }) => (
            <Card key={target}>
              <CardHeader>
                <CardTitle className="flex items-center gap-3">
                  <span className="flex size-10 items-center justify-center rounded-lg bg-muted">
                    <Icon className="size-4" />
                  </span>
                  {label}
                </CardTitle>
                <CardDescription>{`Copy this skill into ${hint}`}</CardDescription>
              </CardHeader>
              <CardContent>
                <Button
                  id={`btn-deploy-${target}`}
                  size="lg"
                  className="w-full"
                  disabled={!deployAllowed || gateRunning}
                  onClick={() => void installTo(target)}
                >
                  {`Install to ${label}`}
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : (
        <p className="max-w-xl text-sm text-muted-foreground" id="deploy-local-cli">
          Or install with the free CLI on your machine.
        </p>
      )}

      {showGit ? (
        <div className="max-w-xl">
          <Accordion
            key={status ? (localAvailable ? "local" : "hosted") : "pending"}
            className="rounded-lg border px-3"
            defaultValue={status && !localAvailable && gitConfigured ? ["git"] : []}
          >
            <AccordionItem value="git">
              <AccordionTrigger className="py-3" id="deploy-git-trigger">
                <span className="flex items-center gap-2">
                  <GitBranchIcon className="size-4" />
                  Publish to your skills repo
                </span>
              </AccordionTrigger>
              <AccordionContent>
                <Card className="border-0 shadow-none">
                  <CardHeader className="px-0 pt-0">
                    <CardTitle className="text-base">Skills repository</CardTitle>
                    <CardDescription id="deploy-git-hint">
                      {gitConfigured
                        ? `Publish this skill to ${git?.repo_url || "your skills repo"} so your team can review it.`
                        : "Publishing to a skills repo isn't set up yet."}
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
                      {gitConfigured ? "Publish to your skills repo" : "Not set up yet"}
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
