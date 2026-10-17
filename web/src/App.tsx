import { useEffect, useState, type ReactNode } from "react"

import { LoginPage } from "@/components/auth/login-page"
import { LandingPage } from "@/components/marketing/landing-page"
import { AppSidebar } from "@/components/dashboard/app-sidebar"
import { AppTopbar } from "@/components/dashboard/app-topbar"
import { DeployPage } from "@/components/dashboard/deploy-page"
import { EvalPage } from "@/components/dashboard/eval-page"
import { ComparePage } from "@/components/dashboard/compare-page"
import { HistoryPage } from "@/components/dashboard/history-page"
import { HistorySheet } from "@/components/dashboard/history-sheet"
import { HomePage } from "@/components/dashboard/home-page"
import { RepositoryPage } from "@/components/dashboard/repository-page"
import { SettingsPage } from "@/components/dashboard/settings-page"
import { Alert, AlertTitle } from "@/components/ui/alert"
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet"
import { api } from "@/lib/api"
import { DashboardProvider, useDashboard } from "@/lib/dashboard-provider"
import { useSkillGateSlots } from "@/slots/context"
import type { AuthMePayload, StatusPayload } from "@/lib/types"

function usePathname(): string {
  const [pathname, setPathname] = useState(
    () => (typeof window !== "undefined" ? window.location.pathname : "/") as string
  )

  useEffect(() => {
    const onPop = () => setPathname(window.location.pathname)
    window.addEventListener("popstate", onPop)
    return () => window.removeEventListener("popstate", onPop)
  }, [])

  return pathname
}

function authErrorFromUrl(): string | null {
  if (typeof window === "undefined") {
    return null
  }
  const value = new URLSearchParams(window.location.search).get("auth_error")
  return value || null
}

function DashboardMain() {
  const { stage, status } = useDashboard()
  const [navOpen, setNavOpen] = useState(false)

  return (
    <div className="flex h-svh overflow-hidden bg-background">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-background focus:px-3 focus:py-2 focus:text-sm focus:ring-2 focus:ring-ring"
      >
        Skip to main content
      </a>
      <div className="hidden md:block">
        <AppSidebar className="h-svh" />
      </div>
      <Sheet open={navOpen} onOpenChange={setNavOpen}>
        <SheetContent side="left" className="w-60 p-0">
          <SheetTitle className="sr-only">Skill Gate</SheetTitle>
          <AppSidebar onNavigate={() => setNavOpen(false)} />
        </SheetContent>
      </Sheet>
      <div className="flex min-w-0 flex-1 flex-col">
        <AppTopbar onMenuClick={() => setNavOpen(true)} />
        {status?.auth_open_reason === "qa" && status?.mode !== "local" ? (
          <div className="px-4 pt-4 sm:px-6 lg:px-10">
            <Alert id="qa-auth-open-banner">
              <AlertTitle>
                QA environment — sign-in is off. Not production.
              </AlertTitle>
            </Alert>
          </div>
        ) : null}
        <main
          id="main"
          tabIndex={-1}
          className="min-w-0 flex-1 overflow-x-clip overflow-y-auto px-4 py-6 sm:px-6 sm:py-8 lg:px-10 lg:py-10"
        >
          {stage === "home" ? <HomePage /> : null}
          {stage === "eval" ? <EvalPage /> : null}
          {stage === "deploy" ? <DeployPage /> : null}
          {stage === "repository" ? <RepositoryPage /> : null}
          {stage === "history" ? <HistoryPage /> : null}
          {stage === "compare" ? <ComparePage /> : null}
          {stage === "settings" ? <SettingsPage /> : null}
        </main>
      </div>
      <HistorySheet />
    </div>
  )
}

function AuthGate({ children }: { children: ReactNode }) {
  const slots = useSkillGateSlots()
  const pathname = usePathname()
  const [ready, setReady] = useState(false)
  const [status, setStatus] = useState<StatusPayload | null>(null)
  const [me, setMe] = useState<AuthMePayload | null>(null)
  const [error] = useState(() => authErrorFromUrl())

  useEffect(() => {
    void (async () => {
      try {
        const nextStatus = await api.status()
        setStatus(nextStatus)
        if (nextStatus.auth_required) {
          setMe(await api.me())
        } else {
          setMe({ auth_required: false, user: null })
        }
      } catch {
        setStatus(null)
        setMe({ auth_required: false, user: null })
      } finally {
        setReady(true)
      }
    })()
  }, [])

  const configured = status?.siwv_configured !== false
  let screen: ReactNode
  if (!ready) {
    screen = (
      <div className="flex min-h-svh items-center justify-center text-sm text-muted-foreground">
        Loading…
      </div>
    )
  } else if (status?.auth_required && !me?.user) {
    const authError = error || (me?.denied ? "not_allowlisted" : null)
    const SignIn = slots.SignIn
    if (SignIn) {
      screen = <SignIn error={authError} configured={configured} />
    } else if (authError) {
      screen = <LoginPage error={authError} configured={configured} />
    } else {
      screen = <LandingPage configured={configured} />
    }
  } else {
    screen = (
      <DashboardProvider initialStatus={status}>{children}</DashboardProvider>
    )
  }

  const PublicRoute = slots.PublicRoute
  if (PublicRoute) {
    return (
      <PublicRoute pathname={pathname} configured={configured}>
        {screen}
      </PublicRoute>
    )
  }
  return screen
}

export function App() {
  return (
    <AuthGate>
      <DashboardMain />
    </AuthGate>
  )
}

export default App
