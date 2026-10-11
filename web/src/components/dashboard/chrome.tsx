import type { ComponentType, ReactNode } from "react"
import { cn } from "cn"

import { Badge } from "@/components/ui/badge"
import { useDashboard } from "@/lib/dashboard-provider"
import { skillSlotKey } from "@/lib/skill-run-state"
import type { Stage } from "@/lib/types"

export function PageHeader({
  title,
  description,
  action,
}: {
  title: string
  description?: string
  action?: ReactNode
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div className="flex max-w-2xl flex-col gap-2">
        <h1 className="font-heading text-3xl font-medium tracking-tight">
          {title}
        </h1>
        {description ? (
          <p className="text-base text-pretty text-muted-foreground">
            {description}
          </p>
        ) : null}
      </div>
      {action ? <div className="flex shrink-0 items-center gap-2">{action}</div> : null}
    </div>
  )
}

export function IconRow({
  icon: Icon,
  title,
  description,
  action,
  className,
}: {
  icon: ComponentType<{ className?: string }>
  title: string
  description?: string
  action?: ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        "flex items-center gap-3 rounded-xl border px-3 py-3",
        className
      )}
    >
      <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-muted">
        <Icon className="size-4" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">{title}</p>
        {description ? (
          <p className="line-clamp-2 text-sm text-muted-foreground">{description}</p>
        ) : null}
      </div>
      {action}
    </div>
  )
}

export function gateTone(gate?: string | null, passed?: boolean | null) {
  if (gate === "blocked" || gate === "red") {
    return "red" as const
  }
  if (gate === "cleared" || gate === "green") {
    return "green" as const
  }
  if (passed === true) {
    return "green" as const
  }
  if (passed === false) {
    return "red" as const
  }
  return "pending" as const
}

export function stampBadgeProps(kind: "pass" | "fail"): {
  gate: "green" | "red"
  passed: boolean
} {
  if (kind === "pass") {
    return { gate: "green", passed: true }
  }
  return { gate: "red", passed: false }
}

export function GateBadge({
  gate,
  passed,
}: {
  gate?: string | null
  passed?: boolean | null
}) {
  const tone = gateTone(gate, passed)
  if (tone === "green") {
    return (
      <Badge variant="secondary" className="font-medium text-success">
        Ready
      </Badge>
    )
  }
  if (tone === "red") {
    return <Badge variant="destructive">Blocked</Badge>
  }
  return <Badge variant="outline">Pending</Badge>
}

export function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <p className="px-3 pt-4 pb-1 text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
      {children}
    </p>
  )
}

export function NavRow({
  active,
  icon: Icon,
  label,
  badge,
  onClick,
  id,
}: {
  active?: boolean
  icon: ComponentType<{ className?: string }>
  label: string
  badge?: ReactNode
  onClick: () => void
  id?: string
}) {
  return (
    <button
      type="button"
      id={id}
      onClick={onClick}
      className={cn(
        "flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors",
        active
          ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground"
          : "text-sidebar-foreground hover:bg-sidebar-accent/70"
      )}
      aria-current={active ? "page" : undefined}
    >
      <Icon className="size-4 shrink-0 text-muted-foreground" />
      <span className="min-w-0 flex-1 truncate text-left">{label}</span>
      {badge}
    </button>
  )
}

export function stageTitle(stage: Stage) {
  switch (stage) {
    case "home":
      return "Home"
    case "eval":
      return "Evaluate"
    case "deploy":
      return "Deploy"
    case "repository":
      return "Skill Repository"
    case "history":
      return "History"
    case "settings":
      return "Settings"
  }
}

export function useGateLabel() {
  const { liveGateResult, skillHistory, gateRunning, skill } = useDashboard()
  const runSkill = liveGateResult?.report?.skill || liveGateResult?.skill
  const identity = skillSlotKey(skill)
  const scoped =
    !liveGateResult || !identity || !runSkill || runSkill === identity
  const record = scoped ? liveGateResult : null
  if (gateRunning || record?.status === "running") {
    return "Running"
  }
  const decision = record?.gate_decision || skillHistory?.gate
  if (decision === "cleared") {
    return "Ready"
  }
  if (record?.status === "done" && record.report?.passed === true) {
    return decision === "blocked" ? "Blocked" : "Ready"
  }
  if (record && (record.status === "error" || record.status === "done")) {
    return "Blocked"
  }
  if (skillHistory?.gate === "blocked") {
    return "Blocked"
  }
  return "Pending"
}
