import { cn } from "cn"
import {
  Columns2Icon,
  FlaskConicalIcon,
  FolderIcon,
  GitBranchIcon,
  HistoryIcon,
  LayoutDashboardIcon,
  RocketIcon,
  Settings2Icon,
} from "lucide-react"

import { SgMark } from "@/components/brand/sg-mark"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import {
  GateBadge,
  NavRow,
  useGateLabel,
} from "@/components/dashboard/chrome"
import { sidebarVersionLabel } from "@/lib/dashboard-helpers"
import { useDashboard } from "@/lib/dashboard-provider"
import { isLocalMode, slotOn } from "@/lib/mode"
import { type Stage } from "@/lib/types"

export function AppSidebar({
  className,
  onNavigate,
}: {
  className?: string
  onNavigate?: () => void
}) {
  const {
    stage,
    setStage,
    gateRunning,
    history,
    skillHistory,
    liveGateResult,
    status,
    skill,
    skills,
    openRepository,
  } = useDashboard()
  const go = (next: Stage) => {
    if (next === "repository") {
      openRepository(null)
      onNavigate?.()
      return
    }
    setStage(next)
    onNavigate?.()
  }
  const gateLabel = useGateLabel()
  const timelineCount = history?.timeline.length ?? 0
  const ciUrl = (status?.ci.url || "").trim()

  return (
    <aside
      className={cn(
        "flex h-full w-60 shrink-0 flex-col border-r bg-sidebar text-sidebar-foreground",
        className
      )}
    >
      <div className="flex items-center gap-2.5 px-4 py-5">
        <SgMark className="size-8 shrink-0" />
        <div className="min-w-0">
          <p className="truncate text-sm font-medium tracking-tight">Skill Gate</p>
          <p className="truncate text-xs text-muted-foreground">Evaluate, Gate, Deploy</p>
        </div>
      </div>
      <Separator />
      <ScrollArea className="min-h-0 flex-1">
        <div className="flex flex-col gap-0.5 px-2 pt-3">
          <NavRow
            id="tab-home"
            active={stage === "home"}
            icon={LayoutDashboardIcon}
            label="Home"
            onClick={() => go("home")}
          />
          <NavRow
            id="tab-repository"
            active={stage === "repository"}
            icon={FolderIcon}
            label="Skills"
            badge={
              skills.length ? (
                <Badge variant="secondary">{skills.length}</Badge>
              ) : null
            }
            onClick={() => go("repository")}
          />
          <NavRow
            id="tab-eval"
            active={stage === "eval"}
            icon={FlaskConicalIcon}
            label="Evaluate"
            onClick={() => go("eval")}
          />
          <NavRow
            id="tab-deploy"
            active={stage === "deploy"}
            icon={RocketIcon}
            label="Deploy"
            onClick={() => go("deploy")}
          />
          {isLocalMode(status) ? (
            <NavRow
              id="tab-compare"
              active={stage === "compare"}
              icon={Columns2Icon}
              label="Compare"
              onClick={() => go("compare")}
            />
          ) : null}
          {slotOn(status, "sharedHistory") || isLocalMode(status) ? (
            <NavRow
              id="tab-history"
              active={stage === "history"}
              icon={HistoryIcon}
              label="History"
              badge={
                timelineCount ? (
                  <Badge variant="secondary">{timelineCount}</Badge>
                ) : null
              }
              onClick={() => go("history")}
            />
          ) : null}
          <NavRow
            id="tab-settings"
            active={stage === "settings"}
            icon={Settings2Icon}
            label="Settings"
            onClick={() => go("settings")}
          />
          {ciUrl ? (
            <a
              href={ciUrl}
              target="_blank"
              rel="noreferrer"
              className="ml-9 mt-0.5 flex items-center gap-1.5 px-3 py-1 text-xs text-muted-foreground hover:text-sidebar-foreground"
            >
              <GitBranchIcon className="size-3.5 shrink-0" />
              <span className="truncate">GitHub Action</span>
            </a>
          ) : null}
        </div>
      </ScrollArea>
      <div className="mt-auto flex flex-col gap-3 p-3">
        {skill ? (
          <div className="rounded-xl border bg-background p-3">
            <p className="text-sm font-medium">{skill.name}</p>
            <p className="mt-1 text-xs text-muted-foreground">
              {gateRunning || liveGateResult?.status === "running"
                ? `Evaluating — ${liveGateResult?.completed_count ?? 0}/${liveGateResult?.task_count ?? liveGateResult?.report?.task_count ?? "?"} done`
                : "Deploy follows this skill’s last gate."}
            </p>
            <div className="mt-2">
              <GateBadge
                gate={
                  gateRunning || liveGateResult?.status === "running"
                    ? null
                    : (liveGateResult?.gate_decision ??
                      skillHistory?.gate ??
                      liveGateResult?.gate)
                }
              />
            </div>
          </div>
        ) : null}
        <div className="px-1 pb-1">
          <p className="text-sm font-medium">{sidebarVersionLabel(status)}</p>
          <p className="text-xs text-muted-foreground">Codex may use CLI login</p>
        </div>
      </div>
      <span className="sr-only">{gateLabel}</span>
    </aside>
  )
}
