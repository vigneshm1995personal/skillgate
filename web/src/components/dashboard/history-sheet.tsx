import { ScrollArea } from "@/components/ui/scroll-area"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { HistoryList } from "@/components/dashboard/history-page"
import { useDashboard } from "@/lib/dashboard-provider"
import { slotOn } from "@/lib/mode"

export function HistorySheet() {
  const { historyOpen, setHistoryOpen, setStage, status } = useDashboard()

  return (
    <Sheet
      open={historyOpen}
      onOpenChange={(open) => {
        setHistoryOpen(open)
        if (open && slotOn(status, "sharedHistory")) {
          setStage("history")
        }
      }}
    >
      <SheetContent id="history-drawer" side="right" className="w-full sm:max-w-lg">
        <SheetHeader>
          <SheetTitle>History</SheetTitle>
          <SheetDescription>
            Workspace timeline. Open a run to see what happened on that eval.
          </SheetDescription>
        </SheetHeader>
        <ScrollArea className="min-h-0 flex-1 px-4 pb-4">
          <HistoryList />
        </ScrollArea>
      </SheetContent>
    </Sheet>
  )
}
