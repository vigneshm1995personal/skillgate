/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext, type ComponentType, type ReactNode } from "react"

export type SignInProps = {
  error?: string | null
  configured?: boolean
}

export type PublicRouteProps = {
  pathname: string
  configured: boolean
  children: ReactNode
}

/** Paid surfaces the hosted app fills in. Absent slots stay hidden. */
export type SkillGateSlots = {
  Settings?: ComponentType
  Billing?: ComponentType
  SignIn?: ComponentType<SignInProps>
  PublicRoute?: ComponentType<PublicRouteProps>
}

const SlotContext = createContext<SkillGateSlots>({})

export function SkillGateSlotsProvider({
  slots,
  children,
}: {
  slots?: SkillGateSlots
  children: ReactNode
}) {
  return <SlotContext.Provider value={slots ?? {}}>{children}</SlotContext.Provider>
}

export function useSkillGateSlots(): SkillGateSlots {
  return useContext(SlotContext)
}
