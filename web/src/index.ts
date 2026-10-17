export { App } from "@/App"
export { SkillGateRoot } from "@/root"
export { PageHeader, GateBadge } from "@/components/dashboard/chrome"
export { api, ApiError } from "@/lib/api"
export { useDashboard } from "@/lib/dashboard-provider"
export {
  SkillGateSlotsProvider,
  useSkillGateSlots,
  settingsSurface,
} from "@/slots"
export type { PublicRouteProps, SignInProps, SkillGateSlots } from "@/slots"
