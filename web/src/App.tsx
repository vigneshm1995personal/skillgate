import { useEffect, useState, type ReactNode } from "react"

import { LoginPage } from "@/components/auth/login-page"
import { LandingPage } from "@/components/marketing/landing-page"
import { AppSidebar } from "@/components/dashboard/app-sidebar"
import { AppTopbar } from "@/components/dashboard/app-topbar"
import { DeployPage } from "@/components/dashboard/deploy-page"
import { EvalPage } from "@/components/dashboard/eval-page"
import { HistoryPage } from "@/components/dashboard/history-page"
import { HistorySheet } from "@/components/dashboard/history-sheet"
import { HomePage } from "@/components/dashboard/home-page"
import { RepositoryPage } from "@/components/dashboard/repository-page"
import { SettingsPage } from "@/components/dashboard/settings-page"
import { Alert, AlertTitle } from "@/components/ui/alert"
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet"
import { api } from "@/lib/api"
import { DashboardProvider, useDashboard } from "@/lib/dashboard-provider"
import type { AuthMePayload, StatusPayload } from "@/lib/types"

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
        <main className="min-w-0 flex-1 overflow-x-clip overflow-y-auto px-4 py-6 sm:px-6 sm:py-8 lg:px-10 lg:py-10">
          {stage === "home" ? <HomePage /> : null}
          {stage === "eval" ? <EvalPage /> : null}
          {stage === "deploy" ? <DeployPage /> : null}
          {stage === "repository" ? <RepositoryPage /> : null}
          {stage === "history" ? <HistoryPage /> : null}
          {stage === "settings" ? <SettingsPage /> : null}
        </main>
      </div>
      <HistorySheet />
    </div>
  )
}

function AuthGate({ children }: { children: ReactNode }) {
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

  if (!ready) {
    return (
      <div className="flex min-h-svh items-center justify-center text-sm text-muted-foreground">
        Loading…
      </div>
    )
  }

  if (status?.auth_required && !me?.user) {
    const configured = status.siwv_configured !== false
    const authError = error || (me?.denied ? "not_allowlisted" : null)
    if (authError) {
      return <LoginPage error={authError} configured={configured} />
    }
    return <LandingPage configured={configured} />
  }

  return <>{children}</>
}

export function App() {
  return (
    <AuthGate>
      <DashboardProvider>
        <DashboardMain />
      </DashboardProvider>
    </AuthGate>
  )
}

export default App
