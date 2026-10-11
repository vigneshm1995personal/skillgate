import { useEffect, useRef } from "react"
import {
  HistoryIcon,
  MenuIcon,
  MoonIcon,
  SearchIcon,
  SunIcon,
} from "lucide-react"

import { Breadcrumb, BreadcrumbItem, BreadcrumbList, BreadcrumbPage } from "@/components/ui/breadcrumb"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Kbd } from "@/components/ui/kbd"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { useTheme } from "@/components/theme-provider"
import { SignOutButton } from "@/components/auth/sign-out-button"
import { stageTitle } from "@/components/dashboard/chrome"
import { useDashboard } from "@/lib/dashboard-provider"
import { slotOn } from "@/lib/mode"
import type { Stage } from "@/lib/types"

const SEARCH_STAGES: Stage[] = ["eval", "deploy", "repository", "settings"]

export function AppTopbar({ onMenuClick }: { onMenuClick?: () => void }) {
  const {
    stage,
    setStage,
    setHistoryOpen,
    searchQuery,
    setSearchQuery,
    openRepository,
    setEvalTab,
    status,
  } = useDashboard()
  const { theme, setTheme } = useTheme()
  const searchRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault()
        searchRef.current?.focus()
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])

  const resolvedDark =
    theme === "dark" ||
    (theme === "system" &&
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-color-scheme: dark)").matches)

  return (
    <header className="flex h-14 shrink-0 items-center gap-4 border-b border-border/80 bg-card/60 px-6 backdrop-blur-sm">
      {onMenuClick ? (
        <Button
          variant="ghost"
          size="icon"
          className="md:hidden"
          aria-label="Open menu"
          onClick={onMenuClick}
        >
          <MenuIcon />
        </Button>
      ) : null}
      <Breadcrumb className="hidden md:block">
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbPage className="font-medium">{stageTitle(stage)}</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>
      <div className="relative mx-auto w-full max-w-md">
        <SearchIcon className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          ref={searchRef}
          value={searchQuery}
          onChange={(event) => setSearchQuery(event.target.value)}
          onKeyDown={(event) => {
            if (event.key !== "Enter") {
              return
            }
            const raw = searchQuery.trim().toLowerCase()
            const aliases: Record<string, Stage> = {
              evaluate: "eval",
              eval: "eval",
              skills: "repository",
              repository: "repository",
              repo: "repository",
              deploy: "deploy",
              settings: "settings",
            }
            if (slotOn(status, "sharedHistory")) {
              aliases.history = "history"
            }
            if (slotOn(status, "analyticsHome")) {
              aliases.home = "home"
            }
            const match =
              aliases[raw] ||
              SEARCH_STAGES.find((item) => item.startsWith(raw))
            if (match) {
              if (match === "repository") {
                openRepository(null)
              } else {
                if (match === "eval") {
                  setEvalTab("skill")
                }
                setStage(match)
              }
              if (match === "history") {
                setHistoryOpen(true)
              }
            }
          }}
          placeholder="Search…"
          className="bg-muted/40 pr-14 pl-8"
          aria-label="Search"
        />
        <Kbd className="absolute top-1/2 right-2 -translate-y-1/2">⌘K</Kbd>
      </div>
      <div className="ml-auto flex items-center gap-1">
        {status?.auth_required ? <SignOutButton /> : null}
        {slotOn(status, "sharedHistory") ? (
        <Tooltip>
          <TooltipTrigger
            render={
              <Button
                id="btn-history"
                variant="ghost"
                size="icon"
                aria-label="History"
                onClick={() => {
                  setStage("history")
                  setHistoryOpen(true)
                }}
              />
            }
          >
            <HistoryIcon />
          </TooltipTrigger>
          <TooltipContent>History</TooltipContent>
        </Tooltip>
        ) : null}
        <Tooltip>
          <TooltipTrigger
            render={
              <Button
                variant="ghost"
                size="icon"
                aria-label="Toggle theme"
                onClick={() => setTheme(resolvedDark ? "light" : "dark")}
              />
            }
          >
            {resolvedDark ? <SunIcon /> : <MoonIcon />}
          </TooltipTrigger>
          <TooltipContent>Theme</TooltipContent>
        </Tooltip>
      </div>
    </header>
  )
}
