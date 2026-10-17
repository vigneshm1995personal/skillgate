import { ThemeProvider } from "@/components/theme-provider"
import { Toaster } from "@/components/ui/toast"
import { TooltipProvider } from "@/components/ui/tooltip"
import { App } from "@/App"
import { SkillGateSlotsProvider, type SkillGateSlots } from "@/slots/context"

export function SkillGateRoot({ slots }: { slots?: SkillGateSlots }) {
  return (
    <SkillGateSlotsProvider slots={slots}>
      <ThemeProvider defaultTheme="light">
        <TooltipProvider>
          <Toaster>
            <App />
          </Toaster>
        </TooltipProvider>
      </ThemeProvider>
    </SkillGateSlotsProvider>
  )
}
