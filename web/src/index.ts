export { App } from "@/App"
export { SkillGateRoot } from "@/root"
export { PageHeader, GateBadge } from "@/components/dashboard/chrome"
export { Badge } from "@/components/ui/badge"
export {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
export { Button } from "@/components/ui/button"
export {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field"
export { Input } from "@/components/ui/input"
export { Spinner } from "@/components/ui/spinner"
export { toast } from "@/components/ui/toast"
export {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
export { api, ApiError } from "@/lib/api"
export { useDashboard } from "@/lib/dashboard-provider"
export type { SettingsKeyId, SettingsKeyPresence } from "@/lib/types"
export {
  SkillGateSlotsProvider,
  useSkillGateSlots,
  settingsSurface,
} from "@/slots"
export type { PublicRouteProps, SignInProps, SkillGateSlots } from "@/slots"
