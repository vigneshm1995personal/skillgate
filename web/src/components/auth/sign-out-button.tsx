import { useState } from "react"

import { Button } from "@/components/ui/button"
import { api } from "@/lib/api"

export function SignOutButton({
  onSignedOut,
}: {
  onSignedOut?: () => void
}) {
  const [pending, setPending] = useState(false)

  return (
    <Button
      variant="outline"
      size="sm"
      disabled={pending}
      onClick={() => {
        void (async () => {
          setPending(true)
          try {
            await api.signOut()
            onSignedOut?.()
            window.location.assign("/")
          } finally {
            setPending(false)
          }
        })()
      }}
    >
      {pending ? "Signing out…" : "Sign out"}
    </Button>
  )
}
