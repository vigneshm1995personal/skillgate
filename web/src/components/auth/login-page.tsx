import { SignInWithVercelButton } from "@/components/auth/sign-in-with-vercel"

export function LoginPage({
  error,
  configured,
}: {
  error?: string | null
  configured?: boolean
}) {
  const hint =
    error === "not_allowlisted"
      ? "Your identity is not on the Skill Gate allowlist."
      : error === "not_configured"
        ? "Sign in is not configured on this deployment."
        : error
          ? "Sign-in failed. Try again."
          : null

  return (
    <div className="flex min-h-svh items-center justify-center bg-background px-6">
      <div className="flex w-full max-w-md flex-col gap-6 rounded-2xl border bg-card p-8 shadow-sm">
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-3">
            <img
              src="/skill-gate-mark.png"
              alt=""
              className="size-10 rounded-lg"
            />
            <h1 className="font-heading text-2xl font-medium tracking-tight">
              Skill Gate
            </h1>
          </div>
          <p className="text-sm text-muted-foreground">
            Sign in to continue.
          </p>
        </div>
        {hint ? (
          <p className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {hint}
          </p>
        ) : null}
        {configured === false ? (
          <p className="text-sm text-muted-foreground">
            Sign in isn’t available on this deployment. Contact the admin.
          </p>
        ) : (
          <SignInWithVercelButton />
        )}
      </div>
    </div>
  )
}
