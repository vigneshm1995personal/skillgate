import { JudgeSetupCard } from "@/components/dashboard/judge-setup-form"

export function JudgeSection({ disabled }: { disabled?: boolean }) {
  return <JudgeSetupCard idPrefix="checks-judge" selectId="judge-select" disabled={disabled} />
}
