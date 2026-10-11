export function SignInWithVercelButton({
  className,
}: {
  className?: string
}) {
  return (
    <a
      href="/api/auth/authorize"
      className={
        className ??
        "inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90"
      }
    >
      Sign in
    </a>
  )
}
