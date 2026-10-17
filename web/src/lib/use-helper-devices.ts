import { useCallback, useEffect, useState } from "react"

import { toast } from "@/components/ui/toast"
import { api } from "@/lib/api"
import { asApiError } from "@/lib/dashboard-helpers"
import type {
  DeployTarget,
  HelperDevice,
  HelperJob,
  SkillPayload,
  Stage,
} from "@/lib/types"

export type PairingCode = { code: string; expires_at: string }

export function useHelperDevices({
  stage,
  deployAllowed,
  skill,
}: {
  stage: Stage
  deployAllowed: boolean
  skill: SkillPayload | null
}) {
  const [devices, setDevices] = useState<HelperDevice[]>([])
  const [helperJobs, setHelperJobs] = useState<HelperJob[]>([])
  const [pairingCode, setPairingCode] = useState<PairingCode | null>(null)

  const refreshDevices = useCallback(async () => {
    try {
      const data = await api.helper.devices()
      const next = (data.devices ?? []).filter((device) => !device.revoked_at)
      setDevices(next)
      if (next.length > 0) {
        setPairingCode(null)
      }
    } catch {
      setDevices([])
    }
  }, [])

  const refreshHelperJobs = useCallback(async () => {
    try {
      const data = await api.helper.jobs()
      setHelperJobs(data.jobs ?? [])
    } catch {
      setHelperJobs([])
    }
  }, [])

  const createPairingCode = useCallback(async () => {
    try {
      const data = await api.helper.createPairingCode()
      setPairingCode(data)
    } catch (err) {
      const error = asApiError(err)
      setPairingCode(null)
      toast.add({ title: error.message, type: "error" })
    }
  }, [])

  const removeDevice = useCallback(
    async (deviceId: string) => {
      try {
        await api.helper.removeDevice(deviceId)
        setPairingCode(null)
      } catch (err) {
        const error = asApiError(err)
        toast.add({ title: error.message, type: "error" })
      }
      await refreshDevices()
    },
    [refreshDevices]
  )

  const installToDevice = useCallback(
    async (deviceId: string, target: DeployTarget) => {
      if (!deployAllowed || !skill) {
        return
      }
      try {
        await api.helper.enqueueJob({
          skill: skill.name,
          device_id: deviceId,
          targets: [target],
        })
        toast.add({ title: `Sent ${skill.name} to your Mac`, type: "success" })
        await refreshHelperJobs()
      } catch (err) {
        const error = asApiError(err)
        toast.add({ title: error.message, type: "error" })
      }
    },
    [deployAllowed, refreshHelperJobs, skill]
  )

  useEffect(() => {
    if (!pairingCode?.expires_at) {
      return
    }
    const remaining = Date.parse(pairingCode.expires_at) - Date.now()
    if (Number.isNaN(remaining) || remaining <= 0) {
      setPairingCode(null)
      return
    }
    const timer = window.setTimeout(() => setPairingCode(null), remaining)
    return () => window.clearTimeout(timer)
  }, [pairingCode])

  useEffect(() => {
    if (stage !== "deploy") {
      return
    }
    void refreshDevices()
    void refreshHelperJobs()
    const timer = window.setInterval(() => {
      void refreshDevices()
      void refreshHelperJobs()
    }, 10_000)
    return () => window.clearInterval(timer)
  }, [stage, refreshDevices, refreshHelperJobs])

  return {
    devices,
    helperJobs,
    pairingCode,
    createPairingCode,
    refreshDevices,
    refreshHelperJobs,
    removeDevice,
    installToDevice,
  }
}
